"""
ingestion/fast_write_scores.py
------------------------------
Recomputes betweenness + bridge risk and writes to PostGIS
using bulk COPY — finishes in ~2 minutes instead of 2 hours.

Run from project root:
    python ingestion/fast_write_scores.py
"""

import os
import sys
import csv
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import geopandas as gpd
import networkx as nx
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import io

load_dotenv()

DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)
engine = create_engine(DB_URL)

PREFECTURE = 'miyagi'


def log(msg):
    print(f"\n{'='*55}\n  {msg}\n{'='*55}")


def build_graph():
    log("Loading road network from PostGIS")
    gdf = gpd.read_postgis(
        text("""
            SELECT osm_id, name, highway, speed_kph,
                   length_m, is_bridge, geometry
            FROM   roads
            WHERE  prefecture  = 'miyagi'
            AND    source_file = 'osmnx_miyagi'
            AND    geometry IS NOT NULL
        """),
        engine, geom_col='geometry'
    )
    print(f"  Segments loaded : {len(gdf):,}")

    G = nx.DiGraph()
    for _, row in gdf.iterrows():
        if row.geometry is None or row.geometry.is_empty:
            continue
        coords = list(row.geometry.coords)
        if len(coords) < 2:
            continue
        u = coords[0]
        v = coords[-1]
        length   = float(row['length_m'])  if row['length_m']  else 10.0
        speed    = float(row['speed_kph']) if row['speed_kph'] else 30.0
        travel_t = (length / 1000) / speed * 3600
        osm_id   = row['osm_id']

        G.add_node(u, x=u[0], y=u[1])
        G.add_node(v, x=v[0], y=v[1])
        for a, b in [(u,v),(v,u)]:
            G.add_edge(a, b,
                osmid=osm_id,
                name=str(row['name'] or ''),
                highway=str(row['highway'] or ''),
                length=length,
                speed_kph=speed,
                travel_time=travel_t,
                is_bridge=bool(row['is_bridge']))

    print(f"  Nodes : {len(G.nodes):,}")
    print(f"  Edges : {len(G.edges):,}")
    return G


def compute_scores(G, k=500):
    log(f"Computing betweenness centrality (k={k})")
    print("  Takes 10–20 minutes...")

    bc = nx.edge_betweenness_centrality(
        G, weight='travel_time', normalized=True, k=k
    )

    # Bridge risk
    bridge_edges = [
        (u, v, d) for u, v, d in G.edges(data=True)
        if d.get('is_bridge') is True
    ]
    print(f"  Bridge segments : {len(bridge_edges):,}")

    risk_scores = {}
    if bridge_edges:
        all_bc  = [bc.get((u,v), 0)              for u,v,_ in bridge_edges]
        all_len = [d.get('length', 0)             for _,_,d in bridge_edges]
        all_spd = [float(d.get('speed_kph', 30))  for _,_,d in bridge_edges]
        max_bc  = max(all_bc)  or 1
        max_len = max(all_len) or 1
        max_spd = max(all_spd) or 1
        for u, v, d in bridge_edges:
            score = (
                0.5 * (bc.get((u,v), 0)          / max_bc)  +
                0.3 * (d.get('length', 0)         / max_len) +
                0.2 * (float(d.get('speed_kph',30)) / max_spd)
            )
            risk_scores[(u, v)] = round(score, 4)

    nonzero = [v for v in bc.values() if v > 0]
    print(f"  Non-zero edges  : {len(nonzero):,}")
    return bc, risk_scores


def bulk_write(G, bc, risk_scores):
    log("Bulk writing scores to PostGIS")

    # Build (osm_id → scores) mapping
    scores_by_osmid = {}
    for (u, v), bc_val in bc.items():
        osm_id = G.edges[u, v].get('osmid')
        if osm_id is None:
            continue
        if isinstance(osm_id, list):
            osm_id = osm_id[0]
        try:
            osm_id = int(osm_id)
        except (ValueError, TypeError):
            continue

        br = risk_scores.get((u, v))

        # Keep highest betweenness if osm_id seen multiple times
        existing = scores_by_osmid.get(osm_id)
        if existing is None or bc_val > existing[0]:
            scores_by_osmid[osm_id] = (bc_val, br)

    print(f"  Unique osm_ids  : {len(scores_by_osmid):,}")

    # Write to CSV in memory
    buf = io.StringIO()
    writer = csv.writer(buf)
    for osm_id, (bc_val, br) in scores_by_osmid.items():
        br_str = str(round(br, 4)) if br is not None else ''
        writer.writerow([osm_id, round(bc_val, 6), br_str])

    buf.seek(0)

    # Use raw psycopg2 connection for COPY
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()

        # Create temp table
        cur.execute("""
            CREATE TEMP TABLE _bc_scores (
                osm_id      BIGINT,
                betweenness FLOAT,
                bridge_risk FLOAT
            )
        """)

        # Bulk COPY into temp table
        cur.copy_expert(
            "COPY _bc_scores FROM STDIN WITH CSV NULL ''",
            buf
        )

        print(f"  COPY complete — updating roads table...")

        # Single bulk UPDATE
        cur.execute("""
            UPDATE roads r
            SET    betweenness = s.betweenness,
                   bridge_risk = s.bridge_risk
            FROM   _bc_scores s
            WHERE  r.osm_id      = s.osm_id
            AND    r.prefecture  = 'miyagi'
            AND    r.source_file = 'osmnx_miyagi'
        """)

        affected = cur.rowcount
        raw_conn.commit()
        print(f"  ✅ Updated {affected:,} road segments in one SQL statement")

    finally:
        raw_conn.close()


def create_views():
    log("Creating analysis views")

    with engine.connect() as conn:
        pct90 = conn.execute(text("""
            SELECT PERCENTILE_CONT(0.9)
                   WITHIN GROUP (ORDER BY betweenness)
            FROM   roads
            WHERE  prefecture  = 'miyagi'
            AND    source_file = 'osmnx_miyagi'
            AND    betweenness > 0.0001
        """)).scalar() or 0.001

        print(f"  Threshold (90th pct non-zero) : {pct90:.6f}")

        conn.execute(text("""
            UPDATE roads SET name = NULL
            WHERE name = 'nan' AND prefecture = 'miyagi'
        """))

        conn.execute(text(f"""
            CREATE OR REPLACE VIEW tile_bottleneck_roads AS
            SELECT id,
                   COALESCE(NULLIF(name,'nan'),'Unnamed road') AS name,
                   highway, betweenness, bridge_risk,
                   is_bridge, speed_kph, length_m, geometry
            FROM   roads
            WHERE  prefecture  = 'miyagi'
            AND    source_file = 'osmnx_miyagi'
            AND    betweenness >= {pct90}
            ORDER  BY betweenness DESC
        """))

        conn.execute(text("""
            CREATE OR REPLACE VIEW tile_critical_bridges AS
            SELECT id,
                   COALESCE(NULLIF(name,'nan'),'Unnamed bridge') AS name,
                   highway, betweenness, bridge_risk,
                   speed_kph, length_m, geometry
            FROM   roads
            WHERE  prefecture  = 'miyagi'
            AND    is_bridge   = TRUE
            AND    source_file = 'osmnx_miyagi'
            AND    bridge_risk IS NOT NULL
            ORDER  BY bridge_risk DESC
        """))

        conn.commit()

        # Verify
        bn = conn.execute(text(
            "SELECT COUNT(*) FROM tile_bottleneck_roads"
        )).scalar()
        cb = conn.execute(text(
            "SELECT COUNT(*) FROM tile_critical_bridges"
        )).scalar()

    print(f"  ✅ tile_bottleneck_roads : {bn:,} roads")
    print(f"  ✅ tile_critical_bridges : {cb:,} bridges")


def shelter_accessibility(G):
    log("Shelter accessibility (Dijkstra)")

    shelters_gdf = gpd.read_postgis(
        text("""
            SELECT id, name, capacity, geometry
            FROM facilities
            WHERE prefecture = 'miyagi'
            AND type = 'shelter'
            AND geometry IS NOT NULL
        """),
        engine, geom_col='geometry'
    )
    print(f"  Shelters : {len(shelters_gdf):,}")

    nodes = list(G.nodes())
    def nearest_node(lon, lat):
        return min(nodes, key=lambda n: abs(n[0]-lon) + abs(n[1]-lat))

    sources = list(set(
        nearest_node(r.geometry.x, r.geometry.y)
        for _, r in shelters_gdf.iterrows()
    ))
    print(f"  Source nodes : {len(sources):,}")
    print(f"  Running multi-source Dijkstra...")

    lengths = nx.multi_source_dijkstra_path_length(
        G, sources=sources, weight='travel_time'
    )
    times = [v/60 for v in lengths.values()]
    print(f"  Reachable nodes : {len(times):,}")
    print(f"  Min : {min(times):.1f} min")
    print(f"  Max : {max(times):.1f} min")
    print(f"  Median : {np.median(times):.1f} min")


if __name__ == '__main__':
    log("FAST GRAPH ANALYSIS — BULK WRITE")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  ✅ Database connected")
    except Exception as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    G              = build_graph()
    bc, risk       = compute_scores(G, k=500)
    bulk_write(G, bc, risk)
    create_views()
    shelter_accessibility(G)

    log("COMPLETE")
    with engine.connect() as conn:
        n = conn.execute(text("""
            SELECT COUNT(*) FROM roads
            WHERE betweenness IS NOT NULL AND prefecture='miyagi'
        """)).scalar()
        print(f"  Roads with scores : {n:,}")