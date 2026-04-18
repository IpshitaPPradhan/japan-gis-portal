"""
ingestion/load_mlit.py
----------------------
Loads all Miyagi MLIT datasets into PostGIS.
Run from project root:
    python ingestion/load_mlit.py
"""

import os
import sys
import glob
import warnings
warnings.filterwarnings('ignore')

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ── Database connection ───────────────────────────────────────────────────────
DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)
engine = create_engine(DB_URL)

PREFECTURE = 'miyagi'
PREF_CODE  = '04'
DATA_ROOT  = os.path.join('data', 'miyagi')

TARGET_CRS = 'EPSG:4326'


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_shp(path, encoding='utf-8'):
    """Load shapefile, reproject to WGS84."""
    try:
        gdf = gpd.read_file(path, encoding=encoding)
    except Exception:
        gdf = gpd.read_file(path, encoding='shift-jis')
    if gdf.crs is None:
        gdf = gdf.set_crs('EPSG:6668')
    if gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(TARGET_CRS)
    gdf = gdf[gdf.geometry.notna()]
    gdf = gdf[~gdf.geometry.is_empty]
    return gdf


def to_multipolygon(geom):
    """Ensure geometry is MultiPolygon for hazard_zones table."""
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    return geom


def build_hazard_gdf(gdf, hazard_type, severity_col=None, source_file=''):
    """Build a clean GeoDataFrame ready for hazard_zones table."""
    severity = gdf[severity_col] if severity_col and severity_col in gdf.columns else None
    geoms = gdf.geometry.apply(to_multipolygon)

    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'hazard_type': hazard_type,
        'severity':    severity,
        'source_file': source_file,
    })
    out = gpd.GeoDataFrame(df, geometry=geoms, crs=TARGET_CRS)
    out = out[out.geometry.notna()]
    out = out[~out.geometry.is_empty]
    return out


def insert(gdf, table, method='replace'):
    """Write GeoDataFrame to PostGIS."""
    gdf.to_postgis(
        table, engine,
        if_exists=method,
        index=False,
        dtype={'geom': None}
    )


def log(msg):
    print(f"\n{'='*55}")
    print(f"  {msg}")
    print('='*55)


# ── 1. Tsunami inundation (A40) ───────────────────────────────────────────────

def load_tsunami():
    log("A40 — Tsunami inundation zones")
    path = os.path.join(DATA_ROOT, 'A40-22_04_GML', 'A40-22_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    out  = build_hazard_gdf(gdf, 'tsunami', 'A40_003', 'A40-22_04')
    out.to_postgis('hazard_zones', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} tsunami polygons")


# ── 2. Flood Level 1 (A31a _10 files) ────────────────────────────────────────

def load_flood(level, folder_suffix):
    log(f"A31a — Flood inundation Level {level}")
    folder = os.path.join(DATA_ROOT, f'A31a-24_04_{folder_suffix}_SHP')

    # Find all shapefiles recursively
    shp_files = glob.glob(os.path.join(folder, '**/*.shp'), recursive=True)
    if not shp_files:
        print(f"  WARNING: no shapefiles found in {folder}")
        return

    print(f"  Found {len(shp_files)} shapefiles — loading in chunks")
    total = 0

    # Load and insert one shapefile at a time — avoids MemoryError
    for i, shp in enumerate(shp_files, 1):
        try:
            gdf = load_shp(shp)
            if gdf is None or len(gdf) == 0:
                continue

            out = build_hazard_gdf(
                gdf,
                f'flood_l{level}',
                'A31a_302',
                f'A31a-24_04_{folder_suffix}'
            )
            if len(out) == 0:
                continue

            out.to_postgis(
                'hazard_zones', engine,
                if_exists='append', index=False
            )
            total += len(out)

            # Progress every 10 files
            if i % 10 == 0:
                print(f"  ... {i}/{len(shp_files)} files, {total:,} rows so far")

        except Exception as e:
            print(f"  skipping {os.path.basename(shp)}: {e}")

    print(f"  inserted {total:,} flood L{level} polygons")


# ── 3. Landslide hazard (A33) ─────────────────────────────────────────────────

def load_landslide():
    log("A33 — Landslide hazard zones")
    path = os.path.join(DATA_ROOT, 'A33-24_04_SHP', 'A33-24_04Polygon.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    type_map = {1: 'debris_flow', 2: 'steep_slope', 3: 'landslide'}
    severity = gdf['A33_001'].map(type_map).fillna('landslide')
    geoms    = gdf.geometry.apply(to_multipolygon)
    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'hazard_type': 'landslide',
        'severity':    severity,
        'source_file': 'A33-24_04',
    })
    out = gpd.GeoDataFrame(df, geometry=geoms, crs=TARGET_CRS)
    out = out[out.geometry.notna() & ~out.geometry.is_empty]
    out.to_postgis('hazard_zones', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} landslide polygons")


# ── 4. Disaster prone areas (A47) ────────────────────────────────────────────

def load_disaster_prone():
    log("A47 — Disaster prone areas")
    path = os.path.join(DATA_ROOT, 'A47-21_04_GML', 'A47-21_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    out  = build_hazard_gdf(gdf, 'disaster_prone', 'A47_004', 'A47-21_04')
    out.to_postgis('hazard_zones', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} disaster prone polygons")


# ── 5. Disaster danger zones (A48) ───────────────────────────────────────────

def load_disaster_danger():
    log("A48 — Disaster danger zones")
    path = os.path.join(DATA_ROOT, 'A48-21_04_GML', 'A48-21_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    out  = build_hazard_gdf(gdf, 'disaster_danger', 'A48_008', 'A48-21_04')
    out.to_postgis('hazard_zones', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} danger zone polygons")


# ── 6. Evacuation facilities (P20) ───────────────────────────────────────────

def load_evacuation():
    log("P20 — Evacuation facilities")
    path = os.path.join(DATA_ROOT, 'P20-12_04_GML', 'P20-12_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")

    def hazard_types(row):
        flags = []
        mapping = {
            'P20_007': 'flood', 'P20_008': 'landslide',
            'P20_009': 'storm_surge', 'P20_010': 'earthquake',
            'P20_011': 'tsunami', 'P20_012': 'fire'
        }
        for col, label in mapping.items():
            if col in row and row[col] == 1:
                flags.append(label)
        return ','.join(flags) if flags else None

    hazard_list = gdf.apply(hazard_types, axis=1)
    in_hazard   = hazard_list.notna()

    df = pd.DataFrame({
        'prefecture':   PREFECTURE,
        'type':         'shelter',
        'name':         gdf.get('P20_002', None),
        'name_ja':      gdf.get('P20_002', None),
        'capacity':     pd.to_numeric(gdf.get('P20_005', None), errors='coerce'),
        'in_hazard':    in_hazard,
        'hazard_types': hazard_list,
        'risk_score':   pd.to_numeric(gdf.get('レベル', None), errors='coerce'),
        'source_file':  'P20-12_04',
    })
    out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
    out.to_postgis('facilities', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} evacuation facilities")


def load_medical():
    log("P04 — Medical institutions")
    path = os.path.join(DATA_ROOT, 'P04-20_04_GML', 'P04-20_04.shp')
    gdf  = load_shp(path, encoding='shift-jis')
    print(f"  rows: {len(gdf):,}")
    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'type':        'hospital',
        'name':        gdf.get('P04_002', None),
        'name_ja':     gdf.get('P04_002', None),
        'capacity':    None,
        'in_hazard':   False,
        'source_file': 'P04-20_04',
    })
    out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
    out.to_postgis('facilities', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} medical facilities")


def load_fire_stations():
    log("P17 — Fire stations")
    path = os.path.join(DATA_ROOT, 'P17-12_04_GML',
                        'P17-12_04_FireStation.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'type':        'fire_station',
        'name':        gdf.get('P17_001', None),
        'name_ja':     gdf.get('P17_001', None),
        'capacity':    None,
        'in_hazard':   False,
        'source_file': 'P17-12_04',
    })
    out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
    out.to_postgis('facilities', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} fire stations")


def load_police_stations():
    log("P18 — Police stations")
    path = os.path.join(DATA_ROOT, 'P18-12_04_GML',
                        'P18-12_04_PoliceStation.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'type':        'police_station',
        'name':        gdf.get('P18_001', None),
        'name_ja':     gdf.get('P18_001', None),
        'capacity':    None,
        'in_hazard':   False,
        'source_file': 'P18-12_04',
    })
    out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
    out.to_postgis('facilities', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} police stations")


def load_emergency_roads():
    log("N10 — Emergency transport road network")
    path = os.path.join(DATA_ROOT, 'N10-24_04_GML', 'N10-24_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")
    df = pd.DataFrame({
        'prefecture':  PREFECTURE,
        'osm_id':      None,
        'name':        gdf.get('N10_004', None),
        'highway':     'emergency',
        'is_bridge':   False,
        'speed_kph':   None,
        'length_m':    gdf.geometry.length * 111320,
        'betweenness': None,
        'bridge_risk': None,
        'source_file': 'N10-24_04',
    })
    out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
    out.to_postgis('roads', engine, if_exists='append', index=False)
    print(f"  inserted {len(out):,} emergency road segments")


def load_population():
    log("500m mesh — Population projections 2020 + 2050")
    path = os.path.join(DATA_ROOT, '500m_mesh_2024_04_SHP',
                        '500m_mesh_2024_04.shp')
    gdf  = load_shp(path)
    print(f"  rows: {len(gdf):,}")

    for year, col in [('2020', 'PTN_2020'), ('2050', 'PTN_2050')]:
        df = pd.DataFrame({
            'prefecture':  PREFECTURE,
            'population':  pd.to_numeric(gdf[col], errors='coerce'),
            'year':        int(year),
            'grid_size_m': 500,
            'source_file': '500m_mesh_2024_04',
        })
        out = gpd.GeoDataFrame(df, geometry=gdf.geometry, crs=TARGET_CRS)
        out = out[out.geometry.notna()]
        out.to_postgis('population_grid', engine, if_exists='append', index=False)
        print(f"  inserted {len(out):,} grid cells ({year})")


# ── Main ──────────────────────────────────────────────────────────────────────

def clear_miyagi():
    """Clear existing Miyagi data before re-ingestion."""
    print("\nClearing existing Miyagi data...")
    with engine.connect() as conn:
        for table in ['hazard_zones', 'facilities', 'roads', 'population_grid']:
            conn.execute(
                text(f"DELETE FROM {table} WHERE prefecture = :p"),
                {'p': PREFECTURE}
            )
        conn.commit()
    print("  cleared")


if __name__ == '__main__':
    print("\n" + "="*55)
    print("  MLIT MIYAGI DATA INGESTION")
    print("="*55)
    print(f"  Database : localhost:{os.getenv('POSTGRES_PORT')}")
    print(f"  Database name: {os.getenv('POSTGRES_DB')}")

    # Test connection first
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  Database connection successful")
    except Exception as e:
        print(f"  Cannot connect to database: {e}")
        print("  Make sure Docker is running: docker compose up -d")
        sys.exit(1)

    clear_miyagi()

    # Hazard layers
    load_tsunami()
    load_flood(level=1, folder_suffix='10')
    load_flood(level=2, folder_suffix='20')
    load_landslide()
    load_disaster_prone()
    load_disaster_danger()

    # Facilities
    load_evacuation()
    load_medical()
    load_fire_stations()
    load_police_stations()

    # Infrastructure
    load_emergency_roads()

    # Population
    load_population()

    print("\n" + "="*55)
    print("  INGESTION COMPLETE")
    print("="*55)

    # Summary
    with engine.connect() as conn:
        for table in ['hazard_zones', 'facilities', 'roads', 'population_grid']:
            count = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE prefecture = 'miyagi'")
            ).scalar()
            print(f"  {table:<20} : {count:>8,} rows")