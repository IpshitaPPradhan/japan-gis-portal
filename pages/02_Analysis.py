"""
pages/02_Analysis.py
--------------------
Comprehensive disaster risk analysis for Miyagi Prefecture.
Two modes:
  - Static: pre-computed findings shown as charts
  - Interactive: user selects hazard type, sees live PostGIS results
"""

import warnings
warnings.filterwarnings('ignore')

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import modules.db as db
from sqlalchemy import text

st.set_page_config(
    page_title="Risk Analysis — Japan Disaster Portal",
    page_icon="📊",
    layout="wide"
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] { background-color: #0d0a1a; }
    [data-testid="stSidebar"] * { color: #e0d8f5 !important; }
    .metric-card {
        background: #0d0a1a;
        border: 1px solid #2a2444;
        border-radius: 10px;
        padding: 16px;
        text-align: center;
    }
    .metric-value { font-size: 28px; font-weight: 700; margin: 0; }
    .metric-label { font-size: 11px; color: #7066a0; margin: 4px 0 0 0;
                    text-transform: uppercase; letter-spacing: 0.5px; }
    .finding-card {
        background: rgba(192,132,252,0.08);
        border: 1px solid rgba(192,132,252,0.25);
        border-radius: 10px;
        padding: 14px 18px;
        margin: 8px 0;
    }
    .warning-card {
        background: rgba(255,68,68,0.08);
        border: 1px solid rgba(255,68,68,0.3);
        border-radius: 10px;
        padding: 14px 18px;
        margin: 8px 0;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='padding:12px 0 16px 0'>
        <div style='font-size:24px'>📊</div>
        <div style='font-size:16px;font-weight:700;color:#e0d8f5'>
            Risk Analysis
        </div>
        <div style='font-size:12px;color:#a084cc'>Miyagi Prefecture</div>
    </div>
    """, unsafe_allow_html=True)

    mode = st.radio(
        "Analysis mode",
        options=["📋 Static — Pre-computed Findings",
                 "⚡ Interactive — Live Query"],
        index=0
    )

    st.divider()
    st.markdown("""
    <div style='font-size:11px;color:#7066a0;line-height:1.8'>
    Data sources:<br>
    MLIT 国土数値情報 CC-BY 4.0<br>
    OpenStreetMap ODbL<br>
    500m Population Mesh 2024
    </div>
    """, unsafe_allow_html=True)


# ── Cached queries ────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def get_facility_exposure():
    sql = text("""
        SELECT h.hazard_type, f.type AS facility_type,
               COUNT(DISTINCT f.id) AS count,
               COALESCE(SUM(f.capacity), 0) AS total_capacity
        FROM   facilities f
        JOIN   hazard_zones h ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture = 'miyagi' AND h.prefecture = 'miyagi'
        GROUP  BY h.hazard_type, f.type
        ORDER  BY h.hazard_type, f.type
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn)

@st.cache_data(ttl=86400, show_spinner=False)
def get_facility_totals():
    sql = text("""
        SELECT type, COUNT(*) as total,
               COALESCE(SUM(capacity),0) as total_capacity
        FROM   facilities WHERE prefecture = 'miyagi'
        GROUP  BY type ORDER BY type
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn)

@st.cache_data(ttl=86400, show_spinner=False)
def get_population_exposure():
    sql = text("""
        SELECT h.hazard_type, p.year,
               COUNT(DISTINCT p.id) AS grid_cells,
               ROUND(SUM(p.population)::numeric) AS population_exposed
        FROM   population_grid p
        JOIN   hazard_zones h ON ST_Intersects(p.geometry, h.geometry)
        WHERE  p.prefecture = 'miyagi' AND h.prefecture = 'miyagi'
        GROUP  BY h.hazard_type, p.year
        ORDER  BY h.hazard_type, p.year
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn)

@st.cache_data(ttl=86400, show_spinner=False)
def get_shelter_capacity():
    sql = text("""
        WITH sc AS (
            SELECT COALESCE(SUM(capacity),0)::numeric AS total_capacity,
                   COUNT(*) AS shelter_count
            FROM   facilities
            WHERE  type='shelter' AND prefecture='miyagi'
        ),
        pop AS (
            SELECT year, ROUND(SUM(population)::numeric) AS total_population
            FROM   population_grid WHERE prefecture='miyagi'
            GROUP  BY year
        )
        SELECT p.year, p.total_population, sc.total_capacity,
               sc.shelter_count,
               ROUND(p.total_population::numeric/NULLIF(sc.shelter_count,0))
                   AS people_per_shelter,
               ROUND(sc.total_capacity/NULLIF(p.total_population,0)*100,1)
                   AS capacity_coverage_pct
        FROM pop p CROSS JOIN sc ORDER BY p.year
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn)

@st.cache_data(ttl=86400, show_spinner=False)
def get_capacity_at_risk():
    sql = text("""
        SELECT h.hazard_type,
               COUNT(DISTINCT f.id) AS shelters_at_risk,
               COALESCE(SUM(f.capacity),0) AS capacity_at_risk
        FROM   facilities f
        JOIN   hazard_zones h ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.type='shelter' AND f.prefecture='miyagi'
        AND    h.prefecture='miyagi'
        GROUP  BY h.hazard_type ORDER BY shelters_at_risk DESC
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn)

@st.cache_data(ttl=86400, show_spinner=False)
def get_service_distances():
    results = {}
    for svc in ['hospital', 'fire_station', 'police_station']:
        sql = text(f"""
            SELECT
                AVG(min_d) AS mean, MIN(min_d) AS min,
                MAX(min_d) AS max,
                PERCENTILE_CONT(0.5) WITHIN GROUP(ORDER BY min_d) AS median,
                PERCENTILE_CONT(0.9) WITHIN GROUP(ORDER BY min_d) AS p90
            FROM (
                SELECT s.id,
                    MIN(ST_Distance(
                        ST_Transform(s.geometry,3857),
                        ST_Transform(t.geometry,3857)
                    )) AS min_d
                FROM facilities s
                JOIN facilities t ON t.type=:svc AND t.prefecture='miyagi'
                WHERE s.type='shelter' AND s.prefecture='miyagi'
                GROUP BY s.id
            ) sub
        """)
        with db.engine.connect() as conn:
            row = pd.read_sql(sql, conn, params={'svc': svc})
        results[svc] = row.iloc[0].to_dict()
    return results

@st.cache_data(ttl=86400, show_spinner=False)
def get_population_decline():
    sql = text("""
        SELECT h.hazard_type, p.year,
               ROUND(SUM(p.population)::numeric) AS population
        FROM   population_grid p
        JOIN   hazard_zones h ON ST_Intersects(p.geometry, h.geometry)
        WHERE  p.prefecture='miyagi' AND h.prefecture='miyagi'
        GROUP  BY h.hazard_type, p.year ORDER BY h.hazard_type, p.year
    """)
    with db.engine.connect() as conn:
        df = pd.read_sql(sql, conn)
    pivot = df.pivot(index='hazard_type', columns='year',
                     values='population').reset_index()
    pivot.columns = ['hazard_type', 'pop_2020', 'pop_2050']
    pivot['change_pct'] = ((pivot['pop_2050'] - pivot['pop_2020']) /
                           pivot['pop_2020'] * 100).round(1)
    return pivot.sort_values('change_pct')

@st.cache_data(ttl=86400, show_spinner=False)
def get_interactive_exposure(hazard_type, facility_type):
    sql = text("""
        SELECT f.name, f.type, f.capacity, f.in_hazard,
               h.hazard_type, h.severity
        FROM   facilities f
        JOIN   hazard_zones h ON ST_Intersects(f.geometry, h.geometry)
        WHERE  f.prefecture='miyagi' AND h.prefecture='miyagi'
        AND    h.hazard_type=:htype AND f.type=:ftype
        ORDER  BY f.name
    """)
    with db.engine.connect() as conn:
        return pd.read_sql(sql, conn,
                           params={'htype': hazard_type, 'ftype': facility_type})


# ── Color maps ────────────────────────────────────────────────────────────────

HAZARD_COLORS = {
    'tsunami':        '#1a6fba',
    'flood_l1':       '#2196a8',
    'flood_l2':       '#0d5c8a',
    'landslide':      '#c0392b',
    'disaster_danger':'#8e44ad',
    'disaster_prone': '#e67e22',
}

FACILITY_COLORS = {
    'shelter':        '#22bb66',
    'hospital':       '#ff4444',
    'fire_station':   '#ff9933',
    'police_station': '#3399ff',
}

HAZARD_LABELS = {
    'tsunami':        'Tsunami',
    'flood_l1':       'Flood L1',
    'flood_l2':       'Flood L2',
    'landslide':      'Landslide',
    'disaster_danger':'Danger Zones',
    'disaster_prone': 'Prone Areas',
}

FACILITY_LABELS = {
    'shelter':        'Shelters',
    'hospital':       'Hospitals',
    'fire_station':   'Fire Stations',
    'police_station': 'Police Stations',
}


# ── STATIC MODE ───────────────────────────────────────────────────────────────

def show_static():
    st.markdown("""
    <div style='background:linear-gradient(135deg,#0d0a1a,#1a1040);
         padding:20px 24px;border-radius:10px;border:1px solid #2a2444;
         margin-bottom:20px'>
        <h2 style='color:#e0d8f5;margin:0'>
            📊 Miyagi Disaster Risk — Comprehensive Analysis
        </h2>
        <p style='color:#a084cc;margin:6px 0 0 0'>
            Pre-computed spatial analysis · MLIT + OSM data ·
            330,009 hazard polygons · 5,250 facilities · 25,586 population cells
        </p>
    </div>
    """, unsafe_allow_html=True)

    with st.spinner("Loading analysis..."):
        df_exp    = get_facility_exposure()
        df_tot    = get_facility_totals()
        df_pop    = get_population_exposure()
        df_cap    = get_shelter_capacity()
        df_caprisk= get_capacity_at_risk()
        distances = get_service_distances()
        df_dec    = get_population_decline()

    # ── Section 1: Key findings ──
    st.markdown("## 🔑 Key Findings")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("""
        <div class='warning-card'>
            <p class='metric-value' style='color:#ff4444'>19.4%</p>
            <p class='metric-label'>Fire stations in tsunami zone</p>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class='warning-card'>
            <p class='metric-value' style='color:#ff4444'>433</p>
            <p class='metric-label'>Hospitals in flood zone L1</p>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown("""
        <div class='warning-card'>
            <p class='metric-value' style='color:#ffaa33'>75.2%</p>
            <p class='metric-label'>Shelter capacity vs 2020 population</p>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown("""
        <div class='warning-card'>
            <p class='metric-value' style='color:#ffaa33'>197</p>
            <p class='metric-label'>Shelters in 2+ hazard zones</p>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Section 2: Facility exposure ──
    st.markdown("## 🏥 Facility Exposure by Hazard Zone")

    # Merge with totals to get percentages
    merged = df_exp.merge(
        df_tot[['type','total']],
        left_on='facility_type', right_on='type'
    )
    merged['pct'] = (merged['count'] / merged['total'] * 100).round(1)
    merged['hazard_label'] = merged['hazard_type'].map(HAZARD_LABELS)
    merged['facility_label'] = merged['facility_type'].map(FACILITY_LABELS)

    col1, col2 = st.columns(2)

    with col1:
        # Grouped bar — count by hazard
        shelter_data = merged[merged['facility_type'] == 'shelter']
        fig = px.bar(
            shelter_data,
            x='hazard_label', y='count',
            color='hazard_label',
            color_discrete_map={v: HAZARD_COLORS.get(k,'#888')
                                for k, v in HAZARD_LABELS.items()},
            title='Evacuation Shelters Inside Hazard Zones',
            labels={'count': 'Number of Shelters',
                    'hazard_label': 'Hazard Type'},
            text='count'
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,10,26,1)',
            font_color='#e0d8f5',
            showlegend=False,
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # % at risk heatmap
        pivot = merged.pivot_table(
            index='facility_label',
            columns='hazard_label',
            values='pct',
            fill_value=0
        )
        fig2 = px.imshow(
            pivot,
            title='% of Each Facility Type Inside Hazard Zones',
            color_continuous_scale='RdYlGn_r',
            aspect='auto',
            text_auto='.1f'
        )
        fig2.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#e0d8f5',
            height=350
        )
        st.plotly_chart(fig2, use_container_width=True)

    # All facility types bar chart
    fig3 = px.bar(
        merged,
        x='hazard_label', y='pct',
        color='facility_label',
        barmode='group',
        color_discrete_map={v: FACILITY_COLORS.get(k,'#888')
                            for k, v in FACILITY_LABELS.items()},
        title='% of Facilities at Risk by Hazard Zone',
        labels={'pct': '% at Risk', 'hazard_label': 'Hazard Zone',
                'facility_label': 'Facility Type'},
    )
    fig3.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(13,10,26,1)',
        font_color='#e0d8f5',
        height=350
    )
    st.plotly_chart(fig3, use_container_width=True)

    st.divider()

    # ── Section 3: Shelter capacity ──
    st.markdown("## 🏠 Shelter Capacity Analysis")

    col1, col2 = st.columns(2)

    with col1:
        # Capacity coverage 2020 vs 2050
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='Total Population',
            x=['2020', '2050'],
            y=df_cap['total_population'].tolist(),
            marker_color='#1a6fba',
            opacity=0.8
        ))
        fig.add_trace(go.Bar(
            name='Total Shelter Capacity',
            x=['2020', '2050'],
            y=df_cap['total_capacity'].tolist(),
            marker_color='#22bb66',
            opacity=0.8
        ))
        fig.update_layout(
            title='Population vs Shelter Capacity',
            barmode='group',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,10,26,1)',
            font_color='#e0d8f5',
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Capacity at risk by hazard
        df_caprisk['hazard_label'] = df_caprisk['hazard_type'].map(HAZARD_LABELS)
        fig = px.bar(
            df_caprisk,
            x='hazard_label', y='capacity_at_risk',
            color='hazard_label',
            color_discrete_map={v: HAZARD_COLORS.get(k,'#888')
                                for k, v in HAZARD_LABELS.items()},
            title='Shelter Capacity AT RISK by Hazard Zone',
            labels={'capacity_at_risk': 'Capacity at Risk',
                    'hazard_label': 'Hazard Zone'},
            text='capacity_at_risk'
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,10,26,1)',
            font_color='#e0d8f5',
            showlegend=False,
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)

    # Key insight
    st.markdown("""
    <div class='warning-card'>
        ⚠️ <b>Critical finding:</b> 143,535 shelter capacity sits inside
        Flood Level 1 zones and 128,954 inside tsunami zones.
        These shelters cannot be used during the very disasters they were
        designed for — residents evacuating to these locations would be
        moving <i>into</i> the hazard.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Section 4: Service distances ──
    st.markdown("## 📍 Emergency Service Accessibility")

    service_labels = {
        'hospital':       ('Hospitals', '#ff4444'),
        'fire_station':   ('Fire Stations', '#ff9933'),
        'police_station': ('Police Stations', '#3399ff'),
    }

    cols = st.columns(3)
    for i, (svc, (label, color)) in enumerate(service_labels.items()):
        d = distances[svc]
        with cols[i]:
            st.markdown(f"""
            <div class='metric-card'>
                <p style='color:{color};font-size:14px;font-weight:600;
                   margin:0 0 8px 0'>Shelter → {label}</p>
                <p class='metric-value' style='color:{color}'>
                    {d['median']/1000:.1f} km
                </p>
                <p class='metric-label'>Median distance</p>
                <hr style='border-color:#2a2444;margin:8px 0'>
                <div style='font-size:12px;color:#a084cc;text-align:left'>
                    Mean: {d['mean']/1000:.1f} km<br>
                    Max: {d['max']/1000:.1f} km<br>
                    90th pct: {d['p90']/1000:.1f} km
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Distance distribution chart
    dist_data = []
    for svc, (label, color) in service_labels.items():
        d = distances[svc]
        dist_data.append({
            'Service': label,
            'Median (km)': round(d['median']/1000, 2),
            'Mean (km)':   round(d['mean']/1000, 2),
            'Max (km)':    round(d['max']/1000, 2),
            'P90 (km)':    round(d['p90']/1000, 2),
        })
    df_dist = pd.DataFrame(dist_data)

    fig = go.Figure()
    for svc, (label, color) in service_labels.items():
        d = distances[svc]
        fig.add_trace(go.Bar(
            name=label,
            x=['Median', 'Mean', 'P90', 'Max'],
            y=[d['median']/1000, d['mean']/1000,
               d['p90']/1000, d['max']/1000],
            marker_color=color,
            opacity=0.85
        ))
    fig.update_layout(
        title='Distance from Shelters to Emergency Services',
        barmode='group',
        yaxis_title='Distance (km)',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(13,10,26,1)',
        font_color='#e0d8f5',
        height=350
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("""
    <div class='finding-card'>
        🔍 <b>Finding:</b> While median distances are reasonable (0.8–2.7 km),
        the maximum distances reveal rural gaps — some shelters are
        17.6 km from the nearest hospital and 20.4 km from the nearest
        fire station. These represent the most underserved communities.
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # ── Section 5: Population decline ──
    st.markdown("## 👥 Population Change 2020→2050 in Hazard Zones")

    df_dec['hazard_label'] = df_dec['hazard_type'].map(HAZARD_LABELS)
    df_dec_melted = df_dec.melt(
        id_vars=['hazard_type', 'hazard_label', 'change_pct'],
        value_vars=['pop_2020', 'pop_2050'],
        var_name='year', value_name='population'
    )
    df_dec_melted['year'] = df_dec_melted['year'].map(
        {'pop_2020': '2020', 'pop_2050': '2050'}
    )

    col1, col2 = st.columns(2)

    with col1:
        fig = px.bar(
            df_dec_melted,
            x='hazard_label', y='population',
            color='year',
            barmode='group',
            color_discrete_map={'2020': '#4db8ff', '2050': '#ffaa33'},
            title='Population Exposed 2020 vs 2050',
            labels={'population': 'Population Exposure',
                    'hazard_label': 'Hazard Zone'}
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,10,26,1)',
            font_color='#e0d8f5',
            height=380
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig2 = px.bar(
            df_dec.sort_values('change_pct'),
            x='change_pct', y='hazard_label',
            orientation='h',
            color='change_pct',
            color_continuous_scale='RdYlGn',
            title='% Population Change 2020→2050 by Hazard Zone',
            labels={'change_pct': '% Change',
                    'hazard_label': 'Hazard Zone'},
            text='change_pct'
        )
        fig2.update_traces(texttemplate='%{text:.1f}%',
                           textposition='outside')
        fig2.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(13,10,26,1)',
            font_color='#e0d8f5',
            showlegend=False,
            height=380
        )
        st.plotly_chart(fig2, use_container_width=True)

    st.markdown("""
    <div class='finding-card'>
        📉 <b>Finding:</b> Disaster-prone areas are losing 53.7% of their
        population by 2050 — communities in the highest-risk zones are
        already abandoning them. This reduces future exposure but creates
        aging, resource-poor communities with diminishing capacity to
        respond to disasters.
    </div>
    """, unsafe_allow_html=True)


# ── INTERACTIVE MODE ──────────────────────────────────────────────────────────

def show_interactive():
    st.markdown("""
    <div style='background:linear-gradient(135deg,#0d0a1a,#1a1040);
         padding:20px 24px;border-radius:10px;border:1px solid #2a2444;
         margin-bottom:20px'>
        <h2 style='color:#e0d8f5;margin:0'>
            ⚡ Interactive Risk Explorer
        </h2>
        <p style='color:#a084cc;margin:6px 0 0 0'>
            Select hazard type and facility to query live PostGIS data
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        hazard = st.selectbox(
            "Select hazard zone",
            options=list(HAZARD_LABELS.keys()),
            format_func=lambda x: HAZARD_LABELS[x]
        )
    with col2:
        facility = st.selectbox(
            "Select facility type",
            options=list(FACILITY_LABELS.keys()),
            format_func=lambda x: FACILITY_LABELS[x]
        )

    with st.spinner(f"Querying PostGIS..."):
        df = get_interactive_exposure(hazard, facility)

    total_sql = text("""
        SELECT COUNT(*) as total,
               COALESCE(SUM(capacity),0) as total_capacity
        FROM facilities
        WHERE type=:ftype AND prefecture='miyagi'
    """)
    with db.engine.connect() as conn:
        totals = pd.read_sql(total_sql, conn, params={'ftype': facility})

    total_count = int(totals['total'].values[0])
    at_risk = len(df)
    pct = at_risk / total_count * 100 if total_count > 0 else 0

    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total facilities", f"{total_count:,}")
    with col2:
        st.metric(f"Inside {HAZARD_LABELS[hazard]}",
                  f"{at_risk:,}",
                  f"{pct:.1f}% at risk",
                  delta_color="inverse")
    with col3:
        if facility == 'shelter' and 'capacity' in df.columns:
            cap_risk = int(df['capacity'].sum())
            st.metric("Capacity at risk", f"{cap_risk:,}")
        else:
            st.metric("Safe facilities",
                      f"{total_count - at_risk:,}")

    st.divider()

    if df.empty:
        st.success(f" No {FACILITY_LABELS[facility]} found inside "
                   f"{HAZARD_LABELS[hazard]} zones.")
        return

    # Table
    st.markdown(f"### {FACILITY_LABELS[facility]} inside "
                f"{HAZARD_LABELS[hazard]} zones")

    display_df = df[['name', 'capacity', 'severity']].copy() \
        if facility == 'shelter' \
        else df[['name', 'severity']].copy()

# Fix: replace negative capacity with N/A
    if 'Capacity' in display_df.columns or 'capacity' in display_df.columns:
        display_df: pd.DataFrame = display_df.replace(-1, None)

    display_df.columns = [c.replace('_',' ').title()
                          for c in display_df.columns]
    st.dataframe(display_df, use_container_width=True, height=400)

    # Severity breakdown
    if 'severity' in df.columns and df['severity'].notna().any():
        sev_counts = df['severity'].value_counts().reset_index()
        sev_counts.columns = ['Severity', 'Count']
        fig = px.pie(
            sev_counts,
            values='Count', names='Severity',
            title=f'Severity breakdown — '
                  f'{FACILITY_LABELS[facility]} in '
                  f'{HAZARD_LABELS[hazard]}',
            color_discrete_sequence=px.colors.sequential.RdBu_r
        )
        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#e0d8f5'
        )
        st.plotly_chart(fig, use_container_width=True)


# ── Main ──────────────────────────────────────────────────────────────────────

if mode.startswith("📋"):
    show_static()
else:
    show_interactive()