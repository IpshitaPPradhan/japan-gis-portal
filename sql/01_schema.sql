CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Hazard zones
CREATE TABLE IF NOT EXISTS hazard_zones (
    id           SERIAL PRIMARY KEY,
    prefecture   VARCHAR(50)  NOT NULL,
    hazard_type  VARCHAR(50)  NOT NULL,
    severity     VARCHAR(200),
    source_file  VARCHAR(200),
    geometry     GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_hazard_geom       ON hazard_zones USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_hazard_prefecture ON hazard_zones (prefecture);

-- Facilities
CREATE TABLE IF NOT EXISTS facilities (
    id           SERIAL PRIMARY KEY,
    prefecture   VARCHAR(50)  NOT NULL,
    type         VARCHAR(50)  NOT NULL,
    name         VARCHAR(200),
    name_ja      VARCHAR(200),
    capacity     INTEGER,
    in_hazard    BOOLEAN      DEFAULT FALSE,
    hazard_types VARCHAR(200),
    risk_score   FLOAT,
    source_file  VARCHAR(200),
    geometry     GEOMETRY(Point, 4326)
);
CREATE INDEX IF NOT EXISTS idx_facilities_geom       ON facilities USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_facilities_prefecture ON facilities (prefecture);
CREATE INDEX IF NOT EXISTS idx_facilities_type       ON facilities (type);

-- Roads
CREATE TABLE IF NOT EXISTS roads (
    id           SERIAL PRIMARY KEY,
    prefecture   VARCHAR(50)  NOT NULL,
    osm_id       BIGINT,
    name         VARCHAR(200),
    highway      VARCHAR(50),
    is_bridge    BOOLEAN      DEFAULT FALSE,
    speed_kph    FLOAT,
    length_m     FLOAT,
    betweenness  FLOAT,
    bridge_risk  FLOAT,
    source_file  VARCHAR(200),
    geometry     GEOMETRY(LineString, 4326)
);
CREATE INDEX IF NOT EXISTS idx_roads_geom       ON roads USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_roads_prefecture ON roads (prefecture);

-- Population grid
CREATE TABLE IF NOT EXISTS population_grid (
    id           SERIAL PRIMARY KEY,
    prefecture   VARCHAR(50)  NOT NULL,
    population   FLOAT,
    year         INTEGER,
    grid_size_m  INTEGER,
    source_file  VARCHAR(200),
    geometry     GEOMETRY(Polygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_population_geom       ON population_grid USING GIST (geometry);
CREATE INDEX IF NOT EXISTS idx_population_prefecture ON population_grid (prefecture);

-- Prefectures
CREATE TABLE IF NOT EXISTS prefectures (
    id           SERIAL PRIMARY KEY,
    code         VARCHAR(5)   NOT NULL UNIQUE,
    name_en      VARCHAR(100) NOT NULL,
    name_ja      VARCHAR(100) NOT NULL,
    region       VARCHAR(50),
    center_lat   FLOAT,
    center_lon   FLOAT,
    zoom_level   INTEGER      DEFAULT 11,
    geometry     GEOMETRY(MultiPolygon, 4326)
);
CREATE INDEX IF NOT EXISTS idx_prefectures_geom ON prefectures USING GIST (geometry);

INSERT INTO prefectures
    (code, name_en, name_ja, region, center_lat, center_lon, zoom_level)
VALUES
    ('04', 'Miyagi',   '宮城県', 'Tohoku',  38.2688, 140.8721, 11),
    ('13', 'Tokyo',    '東京都', 'Kanto',   35.6762, 139.6503, 11),
    ('27', 'Osaka',    '大阪府', 'Kansai',  34.6937, 135.5023, 11),
    ('01', 'Hokkaido', '北海道', 'Hokkaido',43.0646, 141.3468,  9),
    ('14', 'Kanagawa', '神奈川県','Kanto',  35.4478, 139.6425, 11),
    ('23', 'Aichi',    '愛知県', 'Chubu',   35.1802, 136.9066, 11),
    ('40', 'Fukuoka',  '福岡県', 'Kyushu',  33.5904, 130.4017, 11),
    ('11', 'Saitama',  '埼玉県', 'Kanto',   35.8575, 139.6489, 11),
    ('12', 'Chiba',    '千葉県', 'Kanto',   35.6050, 140.1233, 11),
    ('28', 'Hyogo',    '兵庫県', 'Kansai',  34.6913, 135.1830, 11)
ON CONFLICT (code) DO NOTHING;