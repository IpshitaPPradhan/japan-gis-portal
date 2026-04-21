"""
analysis/spatial_analysis.py
-----------------------------
Comprehensive spatial analysis of Miyagi disaster risk.

Run: python analysis/spatial_analysis.py
"""

import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DB_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@localhost:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)
engine = create_engine(DB_URL)

PREFECTURE = 'miyagi'


def log(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── 1. Facility exposure by hazard zone ───────────────────────────────────────

def analyse_facility_exposure():
    log("FACILITY EXPOSURE BY HAZARD ZONE")

    sql = text("""
        SELECT
            h.hazard_type,
            f.type                          AS facility_type,
            COUNT(DISTINCT f.id)            AS count,
            COALESCE(SUM(f.capacity), 0)    AS total_capacity
        FROM   facilities f
        JOIN   hazard_zones h
               ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture = :p
        AND    h.prefecture = :p
        GROUP  BY h.hazard_type, f.type
        ORDER  BY h.hazard_type, f.type
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    print("\nFacilities inside each hazard zone:")
    print(df.to_string(index=False))

    # Total facilities for reference
    sql2 = text("""
        SELECT type, COUNT(*) as total,
               COALESCE(SUM(capacity), 0) as total_capacity
        FROM   facilities
        WHERE  prefecture = :p
        GROUP  BY type
        ORDER  BY type
    """)
    with engine.connect() as conn:
        totals = pd.read_sql(sql2, conn, params={'p': PREFECTURE})

    print("\nTotal facilities (all zones):")
    print(totals.to_string(index=False))

    # Compute % at risk
    print("\n% of facilities inside hazard zones:")
    for _, row in df.iterrows():
        total_row = totals[totals['type'] == row['facility_type']]
        if not total_row.empty:
            total = total_row['total'].values[0]
            pct = row['count'] / total * 100
            print(f"  {row['hazard_type']:<20} {row['facility_type']:<15} "
                  f"{row['count']:>5} / {total:>5} ({pct:.1f}%)")

    return df, totals


# ── 2. Population exposure by hazard zone ────────────────────────────────────

def analyse_population_exposure():
    log("POPULATION EXPOSURE BY HAZARD ZONE")

    sql = text("""
        SELECT
            h.hazard_type,
            p.year,
            COUNT(DISTINCT p.id)            AS grid_cells,
            ROUND(SUM(p.population))        AS population_exposed
        FROM   population_grid p
        JOIN   hazard_zones h
               ON ST_Intersects(p.geometry, h.geometry)
        WHERE  p.prefecture = :p
        AND    h.prefecture = :p
        GROUP  BY h.hazard_type, p.year
        ORDER  BY h.hazard_type, p.year
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    # Total population
    sql2 = text("""
        SELECT year,
               ROUND(SUM(population)) as total_population,
               COUNT(*) as total_cells
        FROM   population_grid
        WHERE  prefecture = :p
        GROUP  BY year
        ORDER  BY year
    """)
    with engine.connect() as conn:
        totals = pd.read_sql(sql2, conn, params={'p': PREFECTURE})

    print("\nPopulation exposed by hazard zone:")
    for _, row in df.iterrows():
        total_row = totals[totals['year'] == row['year']]
        if not total_row.empty:
            total_pop = total_row['total_population'].values[0]
            pct = row['population_exposed'] / total_pop * 100
            print(f"  {row['hazard_type']:<22} {row['year']}  "
                  f"{row['population_exposed']:>10,.0f} / {total_pop:>10,.0f} "
                  f"({pct:.1f}%)")

    return df, totals


# ── 3. Overlapping hazard zones ───────────────────────────────────────────────

def analyse_overlapping_hazards():
    log("OVERLAPPING HAZARD ZONES (Multi-hazard exposure)")

    sql = text("""
        SELECT
            f.type                  AS facility_type,
            f.name,
            COUNT(DISTINCT h.hazard_type) AS hazard_count,
            STRING_AGG(DISTINCT h.hazard_type, ', '
                       ORDER BY h.hazard_type) AS hazard_types
        FROM   facilities f
        JOIN   hazard_zones h
               ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture = :p
        AND    h.prefecture = :p
        GROUP  BY f.type, f.name, f.id
        HAVING COUNT(DISTINCT h.hazard_type) >= 2
        ORDER  BY hazard_count DESC, f.type
        LIMIT  20
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    print("\nFacilities exposed to 2+ hazard types (top 20):")
    print(df.to_string(index=False))

    # Summary count
    sql2 = text("""
        SELECT
            f.type,
            COUNT(DISTINCT h.hazard_type) AS hazard_count,
            COUNT(DISTINCT f.id)          AS facility_count
        FROM   facilities f
        JOIN   hazard_zones h
               ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture = :p
        AND    h.prefecture = :p
        GROUP  BY f.type, f.id
        HAVING COUNT(DISTINCT h.hazard_type) >= 2
    """)

    with engine.connect() as conn:
        raw = pd.read_sql(sql2, conn, params={'p': PREFECTURE})

    summary = raw.groupby('type')['facility_count'].count().reset_index()
    summary.columns = ['facility_type', 'multi_hazard_count']
    print("\nSummary — facilities in 2+ hazard zones:")
    print(summary.to_string(index=False))

    return df


# ── 4. Nearest emergency service distance ────────────────────────────────────

def analyse_service_distances():
    log("NEAREST EMERGENCY SERVICE DISTANCES")

    # Distance from each shelter to nearest hospital
    sql_shelter_hospital = text("""
        SELECT
            AVG(min_dist_m)     AS avg_dist_m,
            MIN(min_dist_m)     AS min_dist_m,
            MAX(min_dist_m)     AS max_dist_m,
            PERCENTILE_CONT(0.5)
                WITHIN GROUP (ORDER BY min_dist_m) AS median_dist_m,
            PERCENTILE_CONT(0.9)
                WITHIN GROUP (ORDER BY min_dist_m) AS pct90_dist_m
        FROM (
            SELECT
                s.id,
                MIN(ST_Distance(
                    ST_Transform(s.geometry, 3857),
                    ST_Transform(h.geometry, 3857)
                )) AS min_dist_m
            FROM facilities s
            JOIN facilities h ON h.type = 'hospital'
                AND h.prefecture = :p
            WHERE s.type       = 'shelter'
            AND   s.prefecture = :p
            GROUP BY s.id
        ) sub
    """)

    # Distance from each shelter to nearest fire station
    sql_shelter_fire = text("""
        SELECT
            AVG(min_dist_m)     AS avg_dist_m,
            MIN(min_dist_m)     AS min_dist_m,
            MAX(min_dist_m)     AS max_dist_m,
            PERCENTILE_CONT(0.5)
                WITHIN GROUP (ORDER BY min_dist_m) AS median_dist_m,
            PERCENTILE_CONT(0.9)
                WITHIN GROUP (ORDER BY min_dist_m) AS pct90_dist_m
        FROM (
            SELECT
                s.id,
                MIN(ST_Distance(
                    ST_Transform(s.geometry, 3857),
                    ST_Transform(f.geometry, 3857)
                )) AS min_dist_m
            FROM facilities s
            JOIN facilities f ON f.type = 'fire_station'
                AND f.prefecture = :p
            WHERE s.type       = 'shelter'
            AND   s.prefecture = :p
            GROUP BY s.id
        ) sub
    """)

    # Distance from each shelter to nearest police station
    sql_shelter_police = text("""
        SELECT
            AVG(min_dist_m)     AS avg_dist_m,
            MIN(min_dist_m)     AS min_dist_m,
            MAX(min_dist_m)     AS max_dist_m,
            PERCENTILE_CONT(0.5)
                WITHIN GROUP (ORDER BY min_dist_m) AS median_dist_m,
            PERCENTILE_CONT(0.9)
                WITHIN GROUP (ORDER BY min_dist_m) AS pct90_dist_m
        FROM (
            SELECT
                s.id,
                MIN(ST_Distance(
                    ST_Transform(s.geometry, 3857),
                    ST_Transform(p.geometry, 3857)
                )) AS min_dist_m
            FROM facilities s
            JOIN facilities p ON p.type = 'police_station'
                AND p.prefecture = :p
            WHERE s.type       = 'shelter'
            AND   s.prefecture = :p
            GROUP BY s.id
        ) sub
    """)

    with engine.connect() as conn:
        sh = pd.read_sql(sql_shelter_hospital, conn, params={'p': PREFECTURE})
        sf = pd.read_sql(sql_shelter_fire,     conn, params={'p': PREFECTURE})
        sp = pd.read_sql(sql_shelter_police,   conn, params={'p': PREFECTURE})

    print("\nShelter → Nearest Hospital distance (meters):")
    print(f"  Mean   : {sh['avg_dist_m'].values[0]:>10,.0f} m")
    print(f"  Median : {sh['median_dist_m'].values[0]:>10,.0f} m")
    print(f"  Max    : {sh['max_dist_m'].values[0]:>10,.0f} m")
    print(f"  P90    : {sh['pct90_dist_m'].values[0]:>10,.0f} m")

    print("\nShelter → Nearest Fire Station distance (meters):")
    print(f"  Mean   : {sf['avg_dist_m'].values[0]:>10,.0f} m")
    print(f"  Median : {sf['median_dist_m'].values[0]:>10,.0f} m")
    print(f"  Max    : {sf['max_dist_m'].values[0]:>10,.0f} m")
    print(f"  P90    : {sf['pct90_dist_m'].values[0]:>10,.0f} m")

    print("\nShelter → Nearest Police Station distance (meters):")
    print(f"  Mean   : {sp['avg_dist_m'].values[0]:>10,.0f} m")
    print(f"  Median : {sp['median_dist_m'].values[0]:>10,.0f} m")
    print(f"  Max    : {sp['max_dist_m'].values[0]:>10,.0f} m")
    print(f"  P90    : {sp['pct90_dist_m'].values[0]:>10,.0f} m")

    return sh, sf, sp


# ── 5. Shelter capacity adequacy ─────────────────────────────────────────────

def analyse_shelter_capacity():
    log("SHELTER CAPACITY VS POPULATION")

    sql = text("""
        WITH shelter_capacity AS (
            SELECT
                COALESCE(SUM(capacity), 0)::numeric AS total_capacity,
                COUNT(*)                            AS shelter_count
            FROM facilities
            WHERE type       = 'shelter'
            AND   prefecture = :p
        ),
        population AS (
            SELECT
                year,
                ROUND(SUM(population)::numeric) AS total_population
            FROM population_grid
            WHERE prefecture = :p
            GROUP BY year
        )
        SELECT
            p.year,
            p.total_population,
            sc.total_capacity,
            sc.shelter_count,
            ROUND(p.total_population::numeric /
                  NULLIF(sc.shelter_count, 0)) AS people_per_shelter,
            ROUND(sc.total_capacity /
                  NULLIF(p.total_population, 0) * 100, 1) AS capacity_coverage_pct
        FROM population p
        CROSS JOIN shelter_capacity sc
        ORDER BY p.year
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    print("\nShelter capacity vs population:")
    print(df.to_string(index=False))

    # At-risk capacity
    sql2 = text("""
        SELECT
            h.hazard_type,
            COUNT(DISTINCT f.id)         AS shelters_at_risk,
            COALESCE(SUM(f.capacity), 0) AS capacity_at_risk
        FROM   facilities f
        JOIN   hazard_zones h
               ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.type        = 'shelter'
        AND    f.prefecture  = :p
        AND    h.prefecture  = :p
        GROUP  BY h.hazard_type
        ORDER  BY shelters_at_risk DESC
    """)

    with engine.connect() as conn:
        df2 = pd.read_sql(sql2, conn, params={'p': PREFECTURE})

    print("\nShelter capacity AT RISK by hazard zone:")
    print(df2.to_string(index=False))

    return df, df2


# ── 6. Most vulnerable areas ─────────────────────────────────────────────────

def analyse_vulnerability_hotspots():
    log("VULNERABILITY HOTSPOTS (High population + High hazard exposure)")

    sql = text("""
        SELECT
            p.id,
            ROUND(p.population)             AS population_2020,
            COUNT(DISTINCT h.hazard_type)   AS hazard_types_count,
            STRING_AGG(DISTINCT h.hazard_type, ', '
                       ORDER BY h.hazard_type) AS hazard_types,
            MIN(ST_Distance(
                ST_Transform(p.geometry, 3857),
                ST_Transform(s.geometry, 3857)
            ))                              AS dist_to_nearest_shelter_m
        FROM   population_grid p
        JOIN   hazard_zones h
               ON ST_Intersects(p.geometry, h.geometry)
               AND h.prefecture = :p
        JOIN   facilities s
               ON s.type       = 'shelter'
               AND s.prefecture = :p
        WHERE  p.prefecture = :p
        AND    p.year       = 2020
        AND    p.population > 500
        GROUP  BY p.id, p.population, p.geometry
        HAVING COUNT(DISTINCT h.hazard_type) >= 2
        ORDER  BY p.population DESC
        LIMIT  15
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    print("\nTop 15 vulnerability hotspots (pop > 500, 2+ hazard types):")
    print(df.to_string(index=False))

    return df


# ── 7. Road network resilience ────────────────────────────────────────────────

def analyse_road_resilience():
    log("ROAD NETWORK RESILIENCE")

    sql = text("""
        SELECT
            h.hazard_type,
            COUNT(DISTINCT r.id)                        AS roads_in_hazard_zone,
            ROUND(SUM(r.length_m)::numeric/1000, 1)    AS total_km,
            COUNT(DISTINCT r.id)
                FILTER (WHERE r.is_bridge)              AS bridges_at_risk
        FROM   roads r
        JOIN   hazard_zones h
               ON ST_Intersects(r.geometry, h.geometry)
        WHERE  r.prefecture  = :p
        AND    h.prefecture  = :p
        AND    r.source_file = 'osmnx_miyagi'
        GROUP  BY h.hazard_type
        ORDER  BY total_km DESC
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={'p': PREFECTURE})

    print("\nRoads inside hazard zones:")
    print(df.to_string(index=False))

    # Emergency roads at risk
    sql2 = text("""
        SELECT
            h.hazard_type,
            COUNT(DISTINCT r.id)                        AS emergency_roads_at_risk,
            ROUND(SUM(r.length_m)::numeric/1000, 1)    AS km_at_risk
        FROM   roads r
        JOIN   hazard_zones h
               ON ST_Intersects(r.geometry, h.geometry)
        WHERE  r.prefecture  = :p
        AND    h.prefecture  = :p
        AND    r.source_file = 'N10-24_04'
        GROUP  BY h.hazard_type
        ORDER  BY km_at_risk DESC
    """)

    with engine.connect() as conn:
        df2 = pd.read_sql(sql2, conn, params={'p': PREFECTURE})

    print("\nEmergency transport routes inside hazard zones:")
    print(df2.to_string(index=False))

    return df, df2


# ── 8. Population decline risk ────────────────────────────────────────────────

def analyse_population_decline():
    log("POPULATION DECLINE 2020 → 2050 BY HAZARD ZONE")

    sql = text("""
        SELECT
            h.hazard_type,
            ROUND(SUM(p2020.population))    AS population_2020,
            ROUND(SUM(p2050.population))    AS population_2050,
            ROUND(SUM(p2050.population) -
                  SUM(p2020.population))    AS change,
            ROUND((SUM(p2050.population) -
                   SUM(p2020.population)) /
                   NULLIF(SUM(p2020.population), 0) * 100, 1) AS change_pct
        FROM   population_grid p2020
        JOIN   population_grid p2050
               ON p2020.id = p2050.id - (
                   SELECT COUNT(*) FROM population_grid
                   WHERE year = 2020 AND prefecture = :p
               )
               AND p2050.year = 2050
        JOIN   hazard_zones h
               ON ST_Intersects(p2020.geometry, h.geometry)
               AND h.prefecture = :p
        WHERE  p2020.year       = 2020
        AND    p2020.prefecture = :p
        GROUP  BY h.hazard_type
        ORDER  BY change_pct
    """)

    # Simpler version using subquery
    sql_simple = text("""
        SELECT
            h.hazard_type,
            p.year,
            ROUND(SUM(p.population)) AS population
        FROM   population_grid p
        JOIN   hazard_zones h
               ON ST_Intersects(p.geometry, h.geometry)
        WHERE  p.prefecture = :p
        AND    h.prefecture = :p
        GROUP  BY h.hazard_type, p.year
        ORDER  BY h.hazard_type, p.year
    """)

    with engine.connect() as conn:
        df = pd.read_sql(sql_simple, conn, params={'p': PREFECTURE})

    # Pivot to show 2020 vs 2050
    pivot = df.pivot(index='hazard_type',
                     columns='year',
                     values='population').reset_index()
    pivot.columns = ['hazard_type', 'pop_2020', 'pop_2050']
    pivot['change'] = pivot['pop_2050'] - pivot['pop_2020']
    pivot['change_pct'] = (pivot['change'] /
                           pivot['pop_2020'] * 100).round(1)
    pivot = pivot.sort_values('change_pct')

    print("\nPopulation change 2020→2050 inside hazard zones:")
    print(pivot.to_string(index=False))

    return pivot


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    
    print("  MIYAGI PREFECTURE — COMPREHENSIVE DISASTER RISK ANALYSIS")


    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("\n Database connected")
    except Exception as e:
        print(f" {e}")
        exit(1)

    # Run all analyses
    df_exposure, df_totals  = analyse_facility_exposure()
    df_pop, df_pop_totals   = analyse_population_exposure()
    df_multi                = analyse_overlapping_hazards()
    sh, sf, sp              = analyse_service_distances()
    df_cap, df_cap_risk     = analyse_shelter_capacity()
    df_hotspots             = analyse_vulnerability_hotspots()
    df_roads, df_emroads    = analyse_road_resilience()
    df_decline              = analyse_population_decline()

    print("""
  Results cover:
  1. Facility exposure by hazard zone
  2. Population exposure by hazard zone
  3. Multi-hazard overlapping zones
  4. Emergency service distances from shelters
  5. Shelter capacity vs population
  6. Vulnerability hotspots
  7. Road network resilience
  8. Population decline 2020→2050 in hazard zones
    """)