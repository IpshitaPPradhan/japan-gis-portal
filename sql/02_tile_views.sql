-- ── Tile-optimized views for pg_tileserv ─────────────────────────────────────
-- These views are what pg_tileserv serves as vector tiles.
-- Geometry simplification happens inside PostGIS, not Python.

-- Tsunami zones
CREATE OR REPLACE VIEW tile_tsunami AS
SELECT id, prefecture, severity,
       ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
FROM   hazard_zones
WHERE  hazard_type = 'tsunami'
AND    geometry IS NOT NULL;

-- Flood Level 1
CREATE OR REPLACE VIEW tile_flood_l1 AS
SELECT id, prefecture, severity,
       ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
FROM   hazard_zones
WHERE  hazard_type = 'flood_l1'
AND    geometry IS NOT NULL;

-- Flood Level 2
CREATE OR REPLACE VIEW tile_flood_l2 AS
SELECT id, prefecture, severity,
       ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
FROM   hazard_zones
WHERE  hazard_type = 'flood_l2'
AND    geometry IS NOT NULL;

-- Landslide zones
CREATE OR REPLACE VIEW tile_landslide AS
SELECT id, prefecture, severity,
       ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
FROM   hazard_zones
WHERE  hazard_type = 'landslide'
AND    geometry IS NOT NULL;

-- Disaster danger zones
CREATE OR REPLACE VIEW tile_disaster_danger AS
SELECT id, prefecture, severity,
       ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
FROM   hazard_zones
WHERE  hazard_type = 'disaster_danger'
AND    geometry IS NOT NULL;

-- Evacuation shelters
CREATE OR REPLACE VIEW tile_shelters AS
SELECT id, name, capacity, in_hazard, hazard_types, risk_score,
       geometry
FROM   facilities
WHERE  type = 'shelter'
AND    geometry IS NOT NULL;

-- Hospitals
CREATE OR REPLACE VIEW tile_hospitals AS
SELECT id, name, in_hazard,
       geometry
FROM   facilities
WHERE  type = 'hospital'
AND    geometry IS NOT NULL;

-- Fire stations
CREATE OR REPLACE VIEW tile_fire_stations AS
SELECT id, name, geometry
FROM   facilities
WHERE  type = 'fire_station'
AND    geometry IS NOT NULL;

-- Police stations
CREATE OR REPLACE VIEW tile_police AS
SELECT id, name, geometry
FROM   facilities
WHERE  type = 'police_station'
AND    geometry IS NOT NULL;

-- Emergency roads
CREATE OR REPLACE VIEW tile_emergency_roads AS
SELECT id, name, highway, length_m, geometry
FROM   roads
WHERE  source_file = 'N10-24_04'
AND    geometry IS NOT NULL;

-- Major OSM roads only (motorway + trunk + primary)
CREATE OR REPLACE VIEW tile_major_roads AS
SELECT id, name, highway, speed_kph, geometry
FROM   roads
WHERE  source_file = 'osmnx_miyagi'
AND    highway IN ('motorway', 'trunk', 'primary')
AND    geometry IS NOT NULL;

-- Bridges
CREATE OR REPLACE VIEW tile_bridges AS
SELECT id, name, highway, speed_kph, length_m, bridge_risk, geometry
FROM   roads
WHERE  is_bridge = TRUE
AND    source_file = 'osmnx_miyagi'
AND    geometry IS NOT NULL;

-- Population grid 2020
CREATE OR REPLACE VIEW tile_population_2020 AS
SELECT id, population, geometry
FROM   population_grid
WHERE  year = 2020
AND    population > 0
AND    geometry IS NOT NULL;

-- Population grid 2050
CREATE OR REPLACE VIEW tile_population_2050 AS
SELECT id, population, geometry
FROM   population_grid
WHERE  year = 2050
AND    population > 0
AND    geometry IS NOT NULL;