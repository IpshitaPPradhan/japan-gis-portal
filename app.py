"""
app.py
Run: streamlit run app.py
"""

import warnings
warnings.filterwarnings('ignore')

import streamlit as st
from streamlit_folium import st_folium

import modules.db as db

from modules.map_builder import build_map
from config import (
    APP_TITLE, APP_SUBTITLE, APP_ICON,
    PREFECTURE_META, DEFAULT_PREFECTURE,
    HAZARD_LAYERS, FACILITY_LAYERS, ROAD_LAYERS,
    BASEMAPS, STATS_CONFIG, POPULATION_YEARS,
    DEFAULT_BASEMAP
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    /* Dark sidebar */
    [data-testid="stSidebar"] {
        background-color: #0d0a1a;
    }
    [data-testid="stSidebar"] * {
        color: #e0d8f5 !important;
    }

    /* Header */
    .portal-header {
        background: linear-gradient(135deg, #0d0a1a 0%, #1a1040 100%);
        padding: 16px 24px;
        border-radius: 10px;
        border: 1px solid #2a2444;
        margin-bottom: 12px;
    }
    .portal-title {
        font-size: 22px;
        font-weight: 700;
        color: #e0d8f5;
        margin: 0;
    }
    .portal-subtitle {
        font-size: 13px;
        color: #a084cc;
        margin: 4px 0 0 0;
    }

    /* Stat cards */
    .stat-card {
        background: #0d0a1a;
        border: 1px solid #2a2444;
        border-radius: 10px;
        padding: 12px 16px;
        text-align: center;
        margin-bottom: 8px;
    }
    .stat-value {
        font-size: 22px;
        font-weight: 700;
        margin: 0;
    }
    .stat-label {
        font-size: 11px;
        color: #7066a0;
        margin: 2px 0 0 0;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;            
    }

    /* Section headers in sidebar */
    .section-header {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #7066a0;
        padding: 8px 0 4px 0;
        border-bottom: 1px solid #2a2444;
        margin-bottom: 6px;
    }

    /* Warning badge */
    .warning-badge {
        background: rgba(255,68,68,0.15);
        border: 1px solid rgba(255,68,68,0.4);
        color: #ff8888;
        padding: 6px 10px;
        border-radius: 8px;
        font-size: 12px;
        margin: 4px 0;
    }

    /* Info badge */
    .info-badge {
        background: rgba(192,132,252,0.1);
        border: 1px solid rgba(192,132,252,0.3);
        color: #c084fc;
        padding: 6px 10px;
        border-radius: 8px;
        font-size: 12px;
        margin: 4px 0;
    }

    /* Hide streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Make map fill space */
    .stFolium {border-radius: 10px; overflow: hidden;}
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────

if 'prefecture' not in st.session_state:
    st.session_state.prefecture = DEFAULT_PREFECTURE

if 'active_hazards' not in st.session_state:
    st.session_state.active_hazards = [
        k for k, v in HAZARD_LAYERS.items() if v['default_on']
    ]

if 'active_facilities' not in st.session_state:
    st.session_state.active_facilities = [
        k for k, v in FACILITY_LAYERS.items() if v['default_on']
    ]

if 'active_roads' not in st.session_state:
    st.session_state.active_roads = [
        k for k, v in ROAD_LAYERS.items() if v['default_on']
    ]

if 'show_population' not in st.session_state:
    st.session_state.show_population = False

if 'population_year' not in st.session_state:
    st.session_state.population_year = 2020

if 'basemap' not in st.session_state:
    st.session_state.basemap = DEFAULT_BASEMAP


# ── DB connection check ───────────────────────────────────────────────────────

if not db.check_connection():
    st.error(
        "Cannot connect to PostGIS database. "
        "Make sure Docker is running: `docker compose up -d`"
    )
    st.stop()


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:

    # Logo / title
    st.markdown(f"""
    <div style='padding:12px 0 16px 0'>
        <div style='font-size:24px'>🗾</div>
        <div style='font-size:16px;font-weight:700;color:#e0d8f5'>
            {APP_TITLE}
        </div>
        <div style='font-size:12px;color:#a084cc'>{APP_SUBTITLE}</div>
    </div>
    """, unsafe_allow_html=True)

    # ── Prefecture selector ──
    st.markdown("<div class='section-header'>Prefecture</div>",
                unsafe_allow_html=True)

    all_prefectures = list(PREFECTURE_META.keys())

    selected = st.selectbox(
        "Select prefecture",
        options=all_prefectures,
        index=all_prefectures.index(st.session_state.prefecture),
        format_func=lambda x: f"{x}  {PREFECTURE_META[x]['name_ja']}",
        label_visibility='collapsed'
    )

    meta = PREFECTURE_META[selected]

    if not meta['has_data']:
        st.markdown(
            f"<div class='info-badge'>📋 {meta['note']}</div>",
            unsafe_allow_html=True
        )
        st.info("Only Miyagi has data loaded. Select Miyagi to explore the portal.")
        selected = 'Miyagi'

    if selected != st.session_state.prefecture:
        st.session_state.prefecture = selected
        st.rerun()

    pref_meta = PREFECTURE_META[st.session_state.prefecture]
    st.markdown(
        f"<div class='info-badge'>📍 {pref_meta['region']}  ·  "
        f"{pref_meta.get('note','')}</div>",
        unsafe_allow_html=True
    )

    st.divider()

    # ── Base map ──
    st.markdown("<div class='section-header'>Base Map</div>",
                unsafe_allow_html=True)

    basemap = st.radio(
        "Basemap",
        options=list(BASEMAPS.keys()),
        index=list(BASEMAPS.keys()).index(st.session_state.basemap),
        horizontal=True,
        label_visibility='collapsed'
    )
    st.session_state.basemap = basemap

    st.divider()

    # ── Hazard layers ──
    st.markdown("<div class='section-header'>Hazard Layers</div>",
                unsafe_allow_html=True)

    active_hazards = []
    for htype, cfg in HAZARD_LAYERS.items():
        checked = st.checkbox(
            f"{cfg['label']}",
            value=(htype in st.session_state.active_hazards),
            key=f"hz_{htype}",
            help=f"{cfg['description']}  |  Source: {cfg['source']}"
        )
        if checked:
            active_hazards.append(htype)
    st.session_state.active_hazards = active_hazards

    st.divider()

    # ── Facility layers ──
    st.markdown("<div class='section-header'>Facilities</div>",
                unsafe_allow_html=True)

    active_facilities = []
    for ftype, cfg in FACILITY_LAYERS.items():
        checked = st.checkbox(
            f"{cfg['label']}",
            value=(ftype in st.session_state.active_facilities),
            key=f"fc_{ftype}",
            help=f"{cfg['description']}  |  Source: {cfg['source']}"
        )
        if checked:
            active_facilities.append(ftype)
    st.session_state.active_facilities = active_facilities

    st.divider()

    # ── Road layers ──
    st.markdown("<div class='section-header'>Roads & Infrastructure</div>",
                unsafe_allow_html=True)

    active_roads = []
    for rtype, cfg in ROAD_LAYERS.items():
        checked = st.checkbox(
            f"{cfg['label']}",
            value=(rtype in st.session_state.active_roads),
            key=f"rd_{rtype}",
            help=f"{cfg['description']}  |  Source: {cfg['source']}"
        )
        if checked:
            active_roads.append(rtype)
    st.session_state.active_roads = active_roads

    st.divider()

    # ── Population layer ──
    st.markdown("<div class='section-header'>Population</div>",
                unsafe_allow_html=True)

    show_pop = st.checkbox(
        "Population Grid (500m mesh)",
        value=st.session_state.show_population,
        key="show_pop",
        help="500m grid cells with population projections from MLIT"
    )
    st.session_state.show_population = show_pop

    if show_pop:
        pop_year = st.radio(
            "Year",
            options=POPULATION_YEARS,
            index=POPULATION_YEARS.index(st.session_state.population_year),
            horizontal=True,
            key="pop_year"
        )
        st.session_state.population_year = pop_year

    st.divider()

    # ── Data info ──
    st.markdown("<div class='section-header'>Data Sources</div>",
                unsafe_allow_html=True)
    st.markdown("""
    <div style='font-size:11px;color:#7066a0;line-height:1.8'>
    MLIT 国土数値情報 CC-BY 4.0<br>
    OpenStreetMap contributors<br>
    500m Population Mesh 2024
    </div>
    """, unsafe_allow_html=True)


# ── Main area ─────────────────────────────────────────────────────────────────

prefecture_name = st.session_state.prefecture
prefecture_db   = PREFECTURE_META[prefecture_name]['db_key']

# Header
st.markdown(f"""
<div class='portal-header'>
    <p class='portal-title'>
        {APP_ICON} {prefecture_name}
        {PREFECTURE_META[prefecture_name]['name_ja']}
        — Disaster Risk Map
    </p>
    <p class='portal-subtitle'>
        Multi-hazard overlay · Emergency infrastructure ·
        Population vulnerability
    </p>
</div>
""", unsafe_allow_html=True)


# ── Stats row ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def load_stats(prefecture: str) -> dict:
    return db.get_stats(prefecture)


with st.spinner("Loading statistics..."):
    stats = load_stats(prefecture_db)

cols = st.columns(7)
for i, cfg in enumerate(STATS_CONFIG):
    val = stats.get(cfg['key'], 0)
    try:
        formatted = cfg['format'].format(val)
    except Exception:
        formatted = str(val)

    with cols[i]:
        st.markdown(f"""
        <div class='stat-card'>
            <div style='font-size:18px'>{cfg['icon']}</div>
            <p class='stat-value' style='color:{cfg['color']}'>{formatted}</p>
            <p class='stat-label'>{cfg['label']}</p>
        </div>
        """, unsafe_allow_html=True)

# Warning if shelters in tsunami zone
shelters_at_risk = stats.get('shelters_in_tsunami', 0)
hospitals_at_risk = stats.get('hospitals_in_tsunami', 0)
if shelters_at_risk > 0 or hospitals_at_risk > 0:
    st.markdown(
        f"<div class='warning-badge'>"
        f"⚠️  <b>{shelters_at_risk:,}</b> evacuation shelters and "
        f"<b>{hospitals_at_risk:,}</b> hospitals are located inside "
        f"tsunami inundation zones in {prefecture_name}."
        f"</div>",
        unsafe_allow_html=True
    )


# ── Map ───────────────────────────────────────────────────────────────────────

with st.spinner("Building map..."):
    folium_map = build_map(
        prefecture_name   = prefecture_name,
        active_hazards    = st.session_state.active_hazards,
        active_facilities = st.session_state.active_facilities,
        active_roads      = st.session_state.active_roads,
        show_population   = st.session_state.show_population,
        population_year   = st.session_state.population_year,
        basemap           = st.session_state.basemap
    )

# Dynamic key — forces re-render when any layer selection changes
map_key = (
    f"{prefecture_name}_"
    f"{'_'.join(sorted(st.session_state.active_hazards))}_"
    f"{'_'.join(sorted(st.session_state.active_facilities))}_"
    f"{'_'.join(sorted(st.session_state.active_roads))}_"
    f"{st.session_state.show_population}_"
    f"{st.session_state.population_year}_"
    f"{st.session_state.basemap}"
)

st_folium(
    folium_map,
    width="100%",
    height=620,
    returned_objects=[],
    key=map_key
)