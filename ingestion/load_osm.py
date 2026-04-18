"""
ingestion/load_osm.py
---------------------
Downloads Miyagi Prefecture road network city by city from OSM.
Avoids memory errors from downloading the entire prefecture at once.

Run from project root:
    python ingestion/load_osm.py
"""

import os
import sys
import warnings
warnings.filterwarnings('ignore')

import osmnx as ox
import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

ox.settings.log_console = False
ox.settings.use_cache = True

DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)
engine = create_engine(DB_URL)

PREFECTURE  = 'miyagi'
TARGET_CRS  = 'EPSG:4326'

# All Miyagi cities and towns — downloaded one at a time
MIYAGI_AREAS = [
    'Sendai, Miyagi, Japan',
    'Ishinomaki, Miyagi, Japan',
    'Osaki, Miyagi, Japan',
    'Kesennuma, Miyagi, Japan',
    'Shiogama, Miyagi, Japan',
    'Natori, Miyagi, Japan',
    'Tome, Miyagi, Japan',
    'Kurihara, Miyagi, Japan',
    'Higashimatsushima, Miyagi, Japan',
    'Taiwa, Miyagi, Japan',
    'Ohira, Miyagi, Japan',
    'Shichigahama, Miyagi, Japan',
    'Matsushima, Miyagi, Japan',
    'Wakuya, Miyagi, Japan',
    'Misato, Miyagi, Japan',
    'Kami, Miyagi, Japan',
    'Minamisanriku, Miyagi, Japan',
    'Onagawa, Miyagi, Japan',
    'Yamamoto, Miyagi, Japan',
    'Marumori, Miyagi, Japan',
    'Watari, Miyagi, Japan',
    'Kakuda, Miyagi, Japan',
    'Murata, Miyagi, Japan',
    'Shibata, Miyagi, Japan',
    'Shiroishi, Miyagi, Japan',
    'Zao, Miyagi, Japan',
    'Kawasaki, Miyagi, Japan',
    'Ogawara, Miyagi, Japan',
    'Rifu, Miyagi, Japan',
    'Tagajo, Miyagi, Japan',
]


def get_name(val):
    if val is None:
        return None
    if isinstance(val, list):
        return str(val[0]) if val else None
    return str(val)


def is_bridge(val):
    if val is None or (isinstance(val, float)):
        return False
    if isinstance(val, list):
        return any(str(v).lower() == 'yes' for v in val)
    return str(val).lower() == 'yes'


def get_speed(val):
    if val is None:
        return None
    if isinstance(val, list):
        try:
            return float(val[0])
        except:
            return None
    try:
        return float(val)
    except:
        return None


def process_area(place_name):
    """Download one city, return as GeoDataFrame. Returns None on failure."""
    try:
        G = ox.graph_from_place(place_name, network_type='drive')
        G = ox.add_edge_speeds(G)
        G = ox.add_edge_travel_times(G)
        _, edges = ox.graph_to_gdfs(G)
        edges = edges.reset_index()

        gdf = gpd.GeoDataFrame({
            'prefecture':  PREFECTURE,
            'osm_id':      edges.get('osmid', pd.Series([None]*len(edges))).apply(
                   lambda x: x[0] if isinstance(x, list) else x
               ),
            'name':        edges.get('name', pd.Series([None]*len(edges))).apply(get_name),
            'highway':     edges.get('highway', pd.Series([None]*len(edges))).apply(get_name),
            'is_bridge':   edges.get('bridge', pd.Series([None]*len(edges))).apply(is_bridge),
            'speed_kph':   edges.get('speed_kph', pd.Series([None]*len(edges))).apply(get_speed),
            'length_m':    edges.get('length', None),
            'betweenness': None,
            'bridge_risk': None,
            'source_file': 'osmnx_miyagi',
        }, geometry=edges.geometry, crs=TARGET_CRS)

        # Ensure LineString only — drop MultiLineString
        gdf = gdf[gdf.geometry.geom_type == 'LineString']
        return gdf

    except Exception as e:
        print(f"    Failed: {e}")
        return None


def insert_chunk(gdf):
    """Insert a GeoDataFrame into PostGIS in chunks of 2000."""
    chunk_size = 2000
    for start in range(0, len(gdf), chunk_size):
        chunk = gdf.iloc[start:start + chunk_size].copy()
        chunk.to_postgis(
            'roads', engine,
            if_exists='append',
            index=False
        )


if __name__ == '__main__':
    
    print("  OSM MIYAGI ROAD NETWORK — CITY BY CITY")

    # Test connection
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("   Database connection successful")
    except Exception as e:
        print(f"  Cannot connect: {e}")
        sys.exit(1)

    # Clear existing OSM roads
    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM roads WHERE source_file = 'osmnx_miyagi'"),
        )
        conn.commit()
    print("  Cleared existing OSM roads\n")

    total_inserted = 0
    failed = []

    for i, place in enumerate(MIYAGI_AREAS, 1):
        city = place.split(',')[0]
        print(f"  [{i:02d}/{len(MIYAGI_AREAS)}] {city:<25}", end=' ', flush=True)

        gdf = process_area(place)
        if gdf is not None and len(gdf) > 0:
            insert_chunk(gdf)
            total_inserted += len(gdf)
            print(f"→ {len(gdf):,} segments  (total: {total_inserted:,})")
        else:
            print("→ skipped")
            failed.append(place)

    print(f"  Total OSM segments inserted : {total_inserted:,}")
    if failed:
        print(f"  Failed areas ({len(failed)}):")
        for f in failed:
            print(f"     {f}")

    # Final count
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM roads WHERE prefecture = 'miyagi'")
        ).scalar()
        print(f"  Total rows in roads table     : {total:,}")