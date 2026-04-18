"""
modules/db.py
-------------
Database connection and all spatial queries.
All map data comes through here — no direct DB calls in app.py.
"""

import os
import warnings
warnings.filterwarnings('ignore')

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()


# ── Connection ────────────────────────────────────────────────────────────────

def get_engine():
    """Create SQLAlchemy engine. Uses POSTGRES_HOST env var so it works
    both locally (localhost:5434) and inside Docker (postgis:5432)."""
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5434')
    db   = os.getenv('POSTGRES_DB')
    user = os.getenv('POSTGRES_USER')
    pw   = os.getenv('POSTGRES_PASSWORD')
    return create_engine(f"postgresql://{user}:{pw}@{host}:{port}/{db}")


engine = get_engine()


# ── Prefecture queries ────────────────────────────────────────────────────────

def get_prefectures() -> pd.DataFrame:
    """Return all prefecture config rows."""
    with engine.connect() as conn:
        return pd.read_sql(
            text("SELECT * FROM prefectures ORDER BY name_en"),
            conn
        )


def get_prefecture(name_en: str) -> pd.Series:
    """Return a single prefecture row by English name."""
    with engine.connect() as conn:
        df = pd.read_sql(
            text("SELECT * FROM prefectures WHERE name_en = :name"),
            conn, params={'name': name_en}
        )
    if df.empty:
        raise ValueError(f"Prefecture '{name_en}' not found")
    return df.iloc[0]


# ── Hazard queries ────────────────────────────────────────────────────────────

def get_hazard_layer(prefecture: str, hazard_type: str,
                     simplify_tolerance: float = 0.005) -> gpd.GeoDataFrame:
    sql = text("""
        SELECT id, hazard_type, severity,
               ST_SimplifyPreserveTopology(geometry, :tol) AS geometry
        FROM   hazard_zones
        WHERE  prefecture  = :pref
        AND    hazard_type = :htype
        AND    geometry IS NOT NULL
        AND    ST_IsValid(geometry)
        LIMIT  50000
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn, geom_col='geometry',
            params={'pref': prefecture, 'htype': hazard_type, 'tol': simplify_tolerance}
        )
    return gdf


def get_hazard_types(prefecture: str) -> list:
    """Return list of hazard types available for a prefecture."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("""SELECT DISTINCT hazard_type
                    FROM hazard_zones
                    WHERE prefecture = :p
                    ORDER BY hazard_type"""),
            {'p': prefecture}
        ).fetchall()
    return [r[0] for r in rows]


# ── Facility queries ──────────────────────────────────────────────────────────

def get_facilities(prefecture: str,
                   facility_types: list = None) -> gpd.GeoDataFrame:
    """
    Load facility points for a prefecture.
    facility_types: list of types to include e.g. ['shelter', 'hospital']
                    None = all types.
    """
    if facility_types:
        placeholders = ', '.join(f':t{i}' for i in range(len(facility_types)))
        sql = text(f"""
            SELECT id, type, name, name_ja, capacity,
                   in_hazard, hazard_types, risk_score, source_file,
                   geometry
            FROM   facilities
            WHERE  prefecture = :pref
            AND    type IN ({placeholders})
            AND    geometry IS NOT NULL
        """)
        params = {'pref': prefecture}
        params.update({f't{i}': t for i, t in enumerate(facility_types)})
    else:
        sql = text("""
            SELECT id, type, name, name_ja, capacity,
                   in_hazard, hazard_types, risk_score, source_file,
                   geometry
            FROM   facilities
            WHERE  prefecture = :pref
            AND    geometry IS NOT NULL
        """)
        params = {'pref': prefecture}

    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params=params
        )
    return gdf


def get_facilities_in_hazard(prefecture: str,
                              hazard_type: str) -> gpd.GeoDataFrame:
    """
    Return facilities that spatially intersect a hazard zone.
    This is the key analysis query — answers 'which shelters are
    inside a tsunami zone?'
    """
    sql = text("""
        SELECT f.id, f.type, f.name, f.capacity,
               f.in_hazard, f.hazard_types, f.risk_score,
               f.geometry
        FROM   facilities f
        JOIN   hazard_zones h
               ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture  = :pref
        AND    h.hazard_type = :htype
        AND    f.geometry IS NOT NULL
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params={'pref': prefecture, 'htype': hazard_type}
        )
    return gdf


# ── Road queries ──────────────────────────────────────────────────────────────

def get_emergency_roads(prefecture: str) -> gpd.GeoDataFrame:
    """Load official emergency transport routes (N10)."""
    sql = text("""
        SELECT id, name, highway, length_m, geometry
        FROM   roads
        WHERE  prefecture   = :pref
        AND    source_file  = 'N10-24_04'
        AND    geometry IS NOT NULL
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params={'pref': prefecture}
        )
    return gdf


def get_bridges(prefecture: str) -> gpd.GeoDataFrame:
    """Load bridge segments from OSM road network."""
    sql = text("""
        SELECT id, name, highway, speed_kph, length_m,
               bridge_risk, geometry
        FROM   roads
        WHERE  prefecture   = :pref
        AND    is_bridge     = TRUE
        AND    source_file  = 'osmnx_miyagi'
        AND    geometry IS NOT NULL
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params={'pref': prefecture}
        )
    return gdf


def get_osm_roads(prefecture: str,
                  simplify: bool = True) -> gpd.GeoDataFrame:
    """
    Load full OSM road network.
    For display only — major roads filtered to keep rendering fast.
    """
    sql = text("""
        SELECT id, name, highway, speed_kph, length_m, is_bridge,
               geometry
        FROM   roads
        WHERE  prefecture  = :pref
        AND    source_file = 'osmnx_miyagi'
        AND    highway IN (
            'motorway', 'trunk', 'primary', 'secondary', 'tertiary'
        )
        AND    geometry IS NOT NULL
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params={'pref': prefecture}
        )
    return gdf


# ── Population queries ────────────────────────────────────────────────────────

def get_population_grid(prefecture: str,
                         year: int = 2020) -> gpd.GeoDataFrame:
    """Load population mesh for a given year."""
    sql = text("""
        SELECT id, population, year, grid_size_m, geometry
        FROM   population_grid
        WHERE  prefecture = :pref
        AND    year       = :year
        AND    population > 0
        AND    geometry IS NOT NULL
    """)
    with engine.connect() as conn:
        gdf = gpd.read_postgis(
            sql, conn,
            geom_col='geometry',
            params={'pref': prefecture, 'year': year}
        )
    return gdf


# ── Stats queries ─────────────────────────────────────────────────────────────

def get_stats(prefecture: str) -> dict:
    """
    Return summary statistics for the sidebar.
    Single query per stat to keep it fast.
    """
    stats = {}
    with engine.connect() as conn:

        # Total shelters
        stats['total_shelters'] = conn.execute(text("""
            SELECT COUNT(*) FROM facilities
            WHERE prefecture = :p AND type = 'shelter'
        """), {'p': prefecture}).scalar()

        # Shelter capacity
        stats['total_capacity'] = conn.execute(text("""
            SELECT COALESCE(SUM(capacity), 0) FROM facilities
            WHERE prefecture = :p AND type = 'shelter'
        """), {'p': prefecture}).scalar()

        # Shelters inside tsunami zone
        stats['shelters_in_tsunami'] = conn.execute(text("""
            SELECT COUNT(DISTINCT f.id)
            FROM   facilities f
            JOIN   hazard_zones h ON ST_Intersects(f.geometry, h.geometry)
            WHERE  f.prefecture  = :p
            AND    f.type        = 'shelter'
            AND    h.hazard_type = 'tsunami'
        """), {'p': prefecture}).scalar()

        # Hospitals
        stats['total_hospitals'] = conn.execute(text("""
            SELECT COUNT(*) FROM facilities
            WHERE prefecture = :p AND type = 'hospital'
        """), {'p': prefecture}).scalar()

        # Hospitals inside tsunami zone
        stats['hospitals_in_tsunami'] = conn.execute(text("""
            SELECT COUNT(DISTINCT f.id)
            FROM   facilities f
            JOIN   hazard_zones h ON ST_Intersects(f.geometry, h.geometry)
            WHERE  f.prefecture  = :p
            AND    f.type        = 'hospital'
            AND    h.hazard_type = 'tsunami'
        """), {'p': prefecture}).scalar()

        # Emergency road km
        stats['emergency_road_km'] = conn.execute(text("""
            SELECT COALESCE(ROUND(SUM(length_m) / 1000), 0)
            FROM   roads
            WHERE  prefecture  = :p
            AND    source_file = 'N10-24_04'
        """), {'p': prefecture}).scalar()

        # Population 2020
        stats['population_2020'] = conn.execute(text("""
            SELECT COALESCE(ROUND(SUM(population)), 0)
            FROM   population_grid
            WHERE  prefecture = :p AND year = 2020
        """), {'p': prefecture}).scalar()

        # Population 2050
        stats['population_2050'] = conn.execute(text("""
            SELECT COALESCE(ROUND(SUM(population)), 0)
            FROM   population_grid
            WHERE  prefecture = :p AND year = 2050
        """), {'p': prefecture}).scalar()

        # Hazard zone counts
        for htype in ['tsunami', 'flood_l1', 'flood_l2',
                      'landslide', 'disaster_danger']:
            stats[f'{htype}_zones'] = conn.execute(text("""
                SELECT COUNT(*) FROM hazard_zones
                WHERE prefecture = :p AND hazard_type = :h
            """), {'p': prefecture, 'h': htype}).scalar()

    return stats


# ── Health check ──────────────────────────────────────────────────────────────

def check_connection() -> bool:
    """Returns True if DB is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False