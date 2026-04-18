"""
config.py
---------
All layer definitions, colors, labels, and app configuration.
Single source of truth — change here, reflects everywhere.
"""

# ── App settings ──────────────────────────────────────────────────────────────

APP_TITLE    = "Japan Disaster Risk GIS Portal"
APP_SUBTITLE = "防災リスク GIS ポータル"
APP_ICON     = "🗾"

# Default prefecture on load
DEFAULT_PREFECTURE = "Miyagi"

# Tile options for base map
BASEMAPS = {
    "Dark":      "CartoDB dark_matter",
    "Light":     "CartoDB positron",
    "Street":    "OpenStreetMap",
    "Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
}
DEFAULT_BASEMAP = "Dark"


# ── Prefecture display config ─────────────────────────────────────────────────

PREFECTURE_META = {
    "Miyagi": {
        "name_ja":    "宮城県",
        "region":     "Tohoku",
        "db_key":     "miyagi",
        "note":       "2011 Tōhoku earthquake epicenter region",
        "has_data":   True,
    },
    "Tokyo": {
        "name_ja":    "東京都",
        "region":     "Kanto",
        "db_key":     "tokyo",
        "note":       "Capital — data coming soon",
        "has_data":   False,
    },
    "Osaka": {
        "name_ja":    "大阪府",
        "region":     "Kansai",
        "db_key":     "osaka",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Hokkaido": {
        "name_ja":    "北海道",
        "region":     "Hokkaido",
        "db_key":     "hokkaido",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Kanagawa": {
        "name_ja":    "神奈川県",
        "region":     "Kanto",
        "db_key":     "kanagawa",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Aichi": {
        "name_ja":    "愛知県",
        "region":     "Chubu",
        "db_key":     "aichi",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Fukuoka": {
        "name_ja":    "福岡県",
        "region":     "Kyushu",
        "db_key":     "fukuoka",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Saitama": {
        "name_ja":    "埼玉県",
        "region":     "Kanto",
        "db_key":     "saitama",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Chiba": {
        "name_ja":    "千葉県",
        "region":     "Kanto",
        "db_key":     "chiba",
        "note":       "Data coming soon",
        "has_data":   False,
    },
    "Hyogo": {
        "name_ja":    "兵庫県",
        "region":     "Kansai",
        "db_key":     "hyogo",
        "note":       "1995 Kobe earthquake region — data coming soon",
        "has_data":   False,
    },
}


# ── Hazard layer config ───────────────────────────────────────────────────────

HAZARD_LAYERS = {
    "tsunami": {
        "label":       "Tsunami Inundation",
        "label_ja":    "津波浸水想定",
        "color":       "#1a6fba",
        "fill_color":  "#1a6fba",
        "fill_opacity": 0.45,
        "weight":      0.5,
        "description": "Projected tsunami inundation zones with depth classification",
        "source":      "MLIT A40",
        "default_on":  True,
    },
    "flood_l1": {
        "label":       "Flood Zone — Level 1",
        "label_ja":    "浸水想定区域（L1）",
        "color":       "#2196a8",
        "fill_color":  "#2196a8",
        "fill_opacity": 0.35,
        "weight":      0.5,
        "description": "Frequent flood inundation zones (river overflow, 10–30 yr return)",
        "source":      "MLIT A31a",
        "default_on":  False,
    },
    "flood_l2": {
        "label":       "Flood Zone — Level 2",
        "label_ja":    "浸水想定区域（L2）",
        "color":       "#0d5c8a",
        "fill_color":  "#0d5c8a",
        "fill_opacity": 0.4,
        "weight":      0.5,
        "description": "Extreme flood inundation zones (max probable flood)",
        "source":      "MLIT A31a",
        "default_on":  False,
    },
    "landslide": {
        "label":       "Landslide Hazard",
        "label_ja":    "土砂災害警戒区域",
        "color":       "#c0392b",
        "fill_color":  "#c0392b",
        "fill_opacity": 0.4,
        "weight":      0.5,
        "description": "Debris flow, steep slope, and landslide warning zones",
        "source":      "MLIT A33",
        "default_on":  True,
    },
    "disaster_danger": {
        "label":       "Disaster Danger Zones",
        "label_ja":    "災害危険区域",
        "color":       "#8e44ad",
        "fill_color":  "#8e44ad",
        "fill_opacity": 0.5,
        "weight":      0.5,
        "description": "Post-disaster legally designated danger zones",
        "source":      "MLIT A48",
        "default_on":  False,
    },
    "disaster_prone": {
        "label":       "Disaster Prone Areas",
        "label_ja":    "災害発生危険地区",
        "color":       "#e67e22",
        "fill_color":  "#e67e22",
        "fill_opacity": 0.45,
        "weight":      0.5,
        "description": "Areas with known disaster occurrence history",
        "source":      "MLIT A47",
        "default_on":  False,
    },
}


# ── Facility layer config ─────────────────────────────────────────────────────

FACILITY_LAYERS = {
    "shelter": {
        "label":       "Evacuation Shelters",
        "label_ja":    "避難施設",
        "color":       "green",
        "icon":        "home",
        "icon_prefix": "fa",
        "description": "Designated evacuation shelters with capacity data",
        "source":      "MLIT P20",
        "default_on":  True,
    },
    "hospital": {
        "label":       "Medical Institutions",
        "label_ja":    "医療機関",
        "color":       "red",
        "icon":        "plus-square",
        "icon_prefix": "fa",
        "description": "Hospitals, clinics, and medical facilities",
        "source":      "MLIT P04",
        "default_on":  True,
    },
    "fire_station": {
        "label":       "Fire Stations",
        "label_ja":    "消防署",
        "color":       "orange",
        "icon":        "fire",
        "icon_prefix": "fa",
        "description": "Fire stations and sub-stations",
        "source":      "MLIT P17",
        "default_on":  False,
    },
    "police_station": {
        "label":       "Police Stations",
        "label_ja":    "警察署",
        "color":       "darkblue",
        "icon":        "shield",
        "icon_prefix": "fa",
        "description": "Police stations and koban (police boxes)",
        "source":      "MLIT P18",
        "default_on":  False,
    },
}


# ── Road layer config ─────────────────────────────────────────────────────────

ROAD_LAYERS = {
    "emergency_roads": {
        "label":       "Emergency Transport Routes",
        "label_ja":    "緊急輸送道路",
        "color":       "#c084fc",
        "weight":      2.5,
        "opacity":     0.8,
        "dash_array":  "8 4",
        "description": "Official emergency transport road network (N10)",
        "source":      "MLIT N10",
        "default_on":  True,
    },
    "osm_roads": {
        "label":       "Road Network",
        "label_ja":    "道路網",
        "color":       "#445566",
        "weight":      1,
        "opacity":     0.5,
        "dash_array":  None,
        "description": "Major roads (motorway to tertiary) from OpenStreetMap",
        "source":      "OSM",
        "default_on":  False,
    },
    "bridges": {
        "label":       "Bridge Segments",
        "label_ja":    "橋梁",
        "color":       "#ff6b35",
        "weight":      3,
        "opacity":     0.85,
        "dash_array":  None,
        "description": "Bridge segments identified from OSM",
        "source":      "OSM",
        "default_on":  False,
    },

    # ── New analysis layers ──
    "bottleneck_roads": {
        "label":       "High-Risk Road Corridors",
        "label_ja":    "重要道路回廊",
        "color":       "#ff3333",
        "weight":      3,
        "opacity":     0.85,
        "dash_array":  None,
        "description": "Roads whose closure would cut off the most evacuation routes — identified by network analysis across 354,000 road segments",
        "source":      "Graph analysis (networkx)",
        "default_on":  False,
    },
    "critical_bridges": {
        "label":       "Vulnerable Bridges",
        "label_ja":    "脆弱橋梁",
        "color":       "#ff6b35",
        "weight":      4,
        "opacity":     0.9,
        "dash_array":  None,
        "description": "Bridges ranked by vulnerability — scored by network criticality, length, and traffic speed",
        "source":      "Graph analysis (networkx)",
        "default_on":  False,
    },
}

# ── Population layer config ───────────────────────────────────────────────────

POPULATION_YEARS = [2020, 2050]

POPULATION_COLORSCALE = [
    (0,    "#0d1117"),
    (0.2,  "#0d3b6e"),
    (0.4,  "#1a6fba"),
    (0.6,  "#4db8ff"),
    (0.8,  "#99d6ff"),
    (1.0,  "#ffffff"),
]


# ── Stats display config ──────────────────────────────────────────────────────

STATS_CONFIG = [
    {
        "key":     "total_shelters",
        "label":   "Shelters",
        "icon":    "🏠",
        "format":  "{:,}",
        "color":   "#22bb66",
    },
    {
        "key":     "shelters_in_tsunami",
        "label":   "Shelters in Tsunami Zone",
        "icon":    "⚠️",
        "format":  "{:,}",
        "color":   "#ff4444",
    },
    {
        "key":     "total_hospitals",
        "label":   "Hospitals",
        "icon":    "🏥",
        "format":  "{:,}",
        "color":   "#22bbaa",
    },
    {
        "key":     "hospitals_in_tsunami",
        "label":   "Hospitals in Tsunami Zone",
        "icon":    "⚠️",
        "format":  "{:,}",
        "color":   "#ff4444",
    },
    {
        "key":     "emergency_road_km",
        "label":   "Emergency Road km",
        "icon":    "🛣️",
        "format":  "{:,.0f} km",
        "color":   "#c084fc",
    },
    {
        "key":     "population_2020",
        "label":   "Population (2020)",
        "icon":    "👥",
        "format":  "{:,.0f}",
        "color":   "#4db8ff",
    },
    {
        "key":     "population_2050",
        "label":   "Population (2050 est.)",
        "icon":    "📉",
        "format":  "{:,.0f}",
        "color":   "#ffaa33",
    },
]


# ── Popup templates ───────────────────────────────────────────────────────────

def shelter_popup(row) -> str:
    hazard = row.get('hazard_types') or 'None'
    capacity = f"{int(row['capacity']):,}" if row.get('capacity') else 'N/A'
    risk = row.get('risk_score') or 'N/A'
    in_hazard = "⚠️ YES" if row.get('in_hazard') else "✅ No"
    return f"""
        <div style='font-family:sans-serif;min-width:180px'>
        <b style='font-size:13px'>{row.get('name','Unknown')}</b><br>
        <hr style='margin:4px 0'>
        <b>Type:</b> Evacuation Shelter<br>
        <b>Capacity:</b> {capacity}<br>
        <b>In hazard zone:</b> {in_hazard}<br>
        <b>Hazard types:</b> {hazard}<br>
        <b>Risk level:</b> {risk}
        </div>
    """


def hospital_popup(row) -> str:
    in_hazard = "⚠️ YES" if row.get('in_hazard') else "✅ No"
    return f"""
        <div style='font-family:sans-serif;min-width:180px'>
        <b style='font-size:13px'>{row.get('name','Unknown')}</b><br>
        <hr style='margin:4px 0'>
        <b>Type:</b> Medical Institution<br>
        <b>In hazard zone:</b> {in_hazard}
        </div>
    """


def fire_station_popup(row) -> str:
    return f"""
        <div style='font-family:sans-serif;min-width:180px'>
        <b style='font-size:13px'>{row.get('name','Unknown')}</b><br>
        <hr style='margin:4px 0'>
        <b>Type:</b> Fire Station
        </div>
    """


def police_popup(row) -> str:
    return f"""
        <div style='font-family:sans-serif;min-width:180px'>
        <b style='font-size:13px'>{row.get('name','Unknown')}</b><br>
        <hr style='margin:4px 0'>
        <b>Type:</b> Police Station
        </div>
    """


POPUP_BUILDERS = {
    'shelter':        shelter_popup,
    'hospital':       hospital_popup,
    'fire_station':   fire_station_popup,
    'police_station': police_popup,
}