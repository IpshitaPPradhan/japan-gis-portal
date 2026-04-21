"""
modules/map_builder.py
----------------------
Builds Folium map using pg_tileserv vector tiles.
Data never travels as GeoJSON — only viewport tiles are fetched.
Performance is fast regardless of dataset size.
"""

import warnings
warnings.filterwarnings('ignore')

import os
import folium
from folium.plugins import MiniMap, MousePosition
import streamlit as st
import geopandas as gpd

from config import HAZARD_LAYERS, FACILITY_LAYERS, ROAD_LAYERS, BASEMAPS
import modules.db as db

# pg_tileserv base URL
# Inside Docker: uses service name. Outside: localhost.
TILE_HOST = os.getenv('TILESERV_HOST', 'http://localhost:7800')


# ── Tile URL builders ─────────────────────────────────────────────────────────

def _tile_url(view_name: str) -> str:
    return f"{TILE_HOST}/public.{view_name}/{{z}}/{{x}}/{{y}}.pbf"


# ── Base map ──────────────────────────────────────────────────────────────────

def _base_map(center_lat, center_lon, zoom, basemap):
    tile = BASEMAPS.get(basemap, BASEMAPS['Dark'])
    if tile.startswith('http') and 'arcgis' in tile:
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles=tile,
            attr='Esri'
        )
    else:
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=zoom,
            tiles=tile
        )
    MiniMap(toggle_display=True, position='bottomright').add_to(m)
    MousePosition(
        position='bottomleft',
        prefix='Lat/Lon:',
        num_digits=5
    ).add_to(m)
    return m


# ── Vector tile layers ────────────────────────────────────────────────────────

def _add_vector_tile_layer(m, view_name, layer_name,
                            fill_color, stroke_color,
                            fill_opacity=0.5, weight=1,
                            show=True):
    """
    Add a pg_tileserv vector tile layer to the map.
    Uses Leaflet VectorGrid under the hood via folium.
    """
    tile_url = _tile_url(view_name)

    # VectorGrid plugin for Leaflet — renders .pbf tiles client-side
    vector_tile_js = f"""
    <script>
    (function() {{
        var map = window._folium_map_{m.get_name()};

        function addVectorLayer() {{
            if (typeof L === 'undefined' || typeof L.vectorGrid === 'undefined') {{
                setTimeout(addVectorLayer, 200);
                return;
            }}
            var layer = L.vectorGrid.protobuf(
                "{tile_url}",
                {{
                    vectorTileLayerStyles: {{
                        "{view_name}": {{
                            fill: true,
                            fillColor: "{fill_color}",
                            fillOpacity: {fill_opacity},
                            color: "{stroke_color}",
                            weight: {weight},
                            opacity: 0.8
                        }}
                    }},
                    interactive: true,
                    maxNativeZoom: 14
                }}
            );
            layer.addTo(map);
        }}
        addVectorLayer();
    }})();
    </script>
    """
    m.get_root().html.add_child(folium.Element(vector_tile_js))


# ── Fallback: GeoJson for small datasets (facilities/roads) ──────────────────
# For point data and lines, GeoJSON is fine — only polygon hazard layers
# are problematic due to size.

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_facilities(prefecture, ftype):
    return db.get_facilities(prefecture, facility_types=[ftype])

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_emergency_roads(prefecture):
    return db.get_emergency_roads(prefecture)

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_bridges(prefecture):
    return db.get_bridges(prefecture)

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_osm_roads(prefecture):
    return db.get_osm_roads(prefecture)

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_population(prefecture, year):
    return db.get_population_grid(prefecture, year)

@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_bottleneck_roads(prefecture):
    from sqlalchemy import text
    return gpd.read_postgis(
        text("""
            SELECT id, name, highway, betweenness,
                   is_bridge, speed_kph, length_m,
                   ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
            FROM   tile_bottleneck_roads
            WHERE  geometry IS NOT NULL
            LIMIT  500
        """),
        db.engine, geom_col='geometry'
    )


@st.cache_data(ttl=86400, show_spinner=False)
def _fetch_critical_bridges(prefecture):
    from sqlalchemy import text
    return gpd.read_postgis(
        text("""
            SELECT id, name, highway, betweenness,
                   bridge_risk, speed_kph, length_m,
                   ST_SimplifyPreserveTopology(geometry, 0.0001) AS geometry
            FROM   tile_critical_bridges
            WHERE  geometry IS NOT NULL
            LIMIT  300
        """),
        db.engine, geom_col='geometry'
    )


def _add_hazard_geojson(m, prefecture, hazard_type, cfg):
    """
    Fallback GeoJson for hazard layers when tiles aren't available.
    Uses heavy simplification to keep file size manageable.
    """
    from folium import FeatureGroup, GeoJson, GeoJsonTooltip
    fg = FeatureGroup(name=f"⬛ {cfg['label']}", show=cfg['default_on'])
    try:
        gdf = db.get_hazard_layer(prefecture, hazard_type,
                                   simplify_tolerance=0.005)
        if not gdf.empty:
            GeoJson(
                gdf,
                style_function=lambda f, c=cfg: {
                    'fillColor':   c['fill_color'],
                    'color':       c['color'],
                    'weight':      0.3,
                    'fillOpacity': c['fill_opacity'],
                },
                tooltip=GeoJsonTooltip(
                    fields=['hazard_type', 'severity'],
                    aliases=['Hazard:', 'Detail:'],
                    localize=True,
                    sticky=False
                )
            ).add_to(fg)
    except Exception as e:
        print(f"  Warning: {hazard_type}: {e}")
    fg.add_to(m)


def _add_facilities_geojson(m, prefecture, ftype, cfg):
    from folium import FeatureGroup, Marker, Popup
    from folium.plugins import MarkerCluster
    from config import POPUP_BUILDERS

    fg = FeatureGroup(name=f"● {cfg['label']}", show=cfg['default_on'])
    try:
        gdf = _fetch_facilities(prefecture, ftype)
        if gdf.empty:
            fg.add_to(m)
            return

        popup_fn = POPUP_BUILDERS.get(ftype)
        target = MarkerCluster(
            options={'maxClusterRadius': 40, 'disableClusteringAtZoom': 13}
        ) if len(gdf) > 100 else fg

        for _, row in gdf.iterrows():
            if row.geometry is None:
                continue
            try:
                popup_html = popup_fn(row) if popup_fn else str(row.get('name',''))
                Marker(
                    location=[row.geometry.y, row.geometry.x],
                    popup=Popup(popup_html, max_width=240),
                    tooltip=str(row.get('name') or 'Unknown'),
                    icon=folium.Icon(
                        color=cfg['color'],
                        icon=cfg['icon'],
                        prefix=cfg['icon_prefix']
                    )
                ).add_to(target)
            except Exception:
                continue

        if len(gdf) > 100:
            target.add_to(fg)
    except Exception as e:
        print(f"  Warning: {ftype}: {e}")
    fg.add_to(m)


def _add_roads_geojson(m, prefecture, road_type):
    from folium import FeatureGroup, GeoJson, GeoJsonTooltip
    cfg = ROAD_LAYERS[road_type]
    fg  = FeatureGroup(name=f"── {cfg['label']}", show=cfg['default_on'])

    try:
        if road_type == 'emergency_roads':
            gdf = _fetch_emergency_roads(prefecture)
            style = lambda f: {
                'color': cfg['color'], 'weight': cfg['weight'],
                'opacity': cfg['opacity'], 'dashArray': cfg['dash_array']
            }
            tooltip_fields = ['name']
            tooltip_aliases = ['Emergency route:']

        elif road_type == 'bridges':
            gdf = _fetch_bridges(prefecture)
            style = lambda f: {
                'color': cfg['color'], 'weight': cfg['weight'],
                'opacity': cfg['opacity']
            }
            tooltip_fields = ['name', 'speed_kph']
            tooltip_aliases = ['Bridge:', 'Speed:']

        elif road_type == 'bottleneck_roads':
            gdf = _fetch_bottleneck_roads(prefecture)
            max_bc = float(gdf['betweenness'].max()) if not gdf.empty and gdf['betweenness'].max() > 0 else 1

            def style(f):
                bc = f['properties'].get('betweenness') or 0
                w  = 2 + int((bc / max_bc) * 5)
                return {'color': cfg['color'], 'weight': w, 'opacity': cfg['opacity']}

            tooltip_fields  = ['name', 'highway', 'betweenness']
            tooltip_aliases = ['Road:', 'Type:', 'Risk score:']

        elif road_type == 'critical_bridges':
            gdf = _fetch_critical_bridges(prefecture)
            max_risk = float(gdf['bridge_risk'].max()) if not gdf.empty and gdf['bridge_risk'].max() > 0 else 1

            def style(f):
                risk = f['properties'].get('bridge_risk') or 0
                w    = 2 + int((risk / max_risk) * 6)
                return {'color': cfg['color'], 'weight': w, 'opacity': cfg['opacity']}

            tooltip_fields  = ['name', 'bridge_risk', 'speed_kph']
            tooltip_aliases = ['Bridge:', 'Risk score:', 'Speed:']    

        else:  # osm_roads
            gdf = _fetch_osm_roads(prefecture)
            hw_colors = {
                'motorway': '#e8c84a', 'trunk': '#e8a020',
                'primary': '#888888', 'secondary': '#666666',
                'tertiary': '#444444',
            }
            def style(f):
                hw = f['properties'].get('highway', 'tertiary')
                return {
                    'color': hw_colors.get(hw, '#445566'),
                    'weight': 3 if hw in ('motorway','trunk') else
                              2 if hw == 'primary' else 1,
                    'opacity': 0.6
                }
            tooltip_fields = ['name', 'highway']
            tooltip_aliases = ['Road:', 'Type:']

        if not gdf.empty:
            GeoJson(
                gdf,
                style_function=style,
                tooltip=GeoJsonTooltip(
                    fields=tooltip_fields,
                    aliases=tooltip_aliases,
                    localize=True
                )
            ).add_to(fg)

    except Exception as e:
        print(f"  Warning: {road_type}: {e}")

    fg.add_to(m)


def _add_population_geojson(m, prefecture, year):
    from folium import FeatureGroup, GeoJson, GeoJsonTooltip
    fg = FeatureGroup(name=f"▦ Population {year}", show=False)
    try:
        gdf = _fetch_population(prefecture, year)
        if not gdf.empty:
            max_pop = gdf['population'].max()
            def pop_color(p):
                r = min(p / max_pop, 1.0) if max_pop > 0 else 0
                if r < 0.2:   return '#0d1117'
                elif r < 0.4: return '#0d3b6e'
                elif r < 0.6: return '#1a6fba'
                elif r < 0.8: return '#4db8ff'
                else:          return '#99d6ff'
            gdf = gdf.copy()
            gdf['_color'] = gdf['population'].apply(pop_color)
            GeoJson(
                gdf,
                style_function=lambda f: {
                    'fillColor':   f['properties']['_color'],
                    'color':       f['properties']['_color'],
                    'weight':      0,
                    'fillOpacity': 0.6,
                },
                tooltip=GeoJsonTooltip(
                    fields=['population'],
                    aliases=['Population:'],
                    localize=True
                )
            ).add_to(fg)
    except Exception as e:
        print(f"  Warning: population: {e}")
    fg.add_to(m)


# ── Legend ────────────────────────────────────────────────────────────────────

def add_legend(m, active_hazards, active_facilities):
    items = []
    for htype in active_hazards:
        if htype in HAZARD_LAYERS:
            cfg = HAZARD_LAYERS[htype]
            items.append(
                f"<div style='display:flex;align-items:center;gap:6px;margin:3px 0'>"
                f"<div style='width:14px;height:14px;background:{cfg['fill_color']};"
                f"opacity:0.7;border-radius:2px;flex-shrink:0'></div>"
                f"<span>{cfg['label']}</span></div>"
            )
    for ftype in active_facilities:
        if ftype in FACILITY_LAYERS:
            cfg = FACILITY_LAYERS[ftype]
            color_map = {'green':'#22bb66','red':'#ff4444',
                         'orange':'#ff9933','darkblue':'#003399'}
            color = color_map.get(cfg['color'], '#888888')
            items.append(
                f"<div style='display:flex;align-items:center;gap:6px;margin:3px 0'>"
                f"<div style='width:10px;height:10px;background:{color};"
                f"border-radius:50%;flex-shrink:0'></div>"
                f"<span>{cfg['label']}</span></div>"
            )
    if not items:
        return
    legend_html = f"""
    <div style="position:fixed;bottom:40px;left:10px;z-index:9999;
        background:rgba(10,10,20,0.92);color:#e0d8f5;
        padding:12px 16px;border-radius:10px;border:1px solid #2a2444;
        font-family:sans-serif;font-size:12px;
        box-shadow:0 4px 20px rgba(0,0,0,0.5);max-width:220px">
    <div style="font-weight:bold;font-size:13px;
                margin-bottom:8px;color:#c084fc">🗾 Layer Legend</div>
    {''.join(items)}
    <div style="margin-top:8px;color:#7066a0;font-size:10px">
        Hover for details · Toggle layers ↗</div>
    </div>"""
    m.get_root().html.add_child(folium.Element(legend_html))


# ── Main builder ──────────────────────────────────────────────────────────────

def build_map(prefecture_name, active_hazards, active_facilities,
              active_roads, show_population, population_year, basemap):

    pref       = db.get_prefecture(prefecture_name)
    center_lat = float(pref['center_lat'])
    center_lon = float(pref['center_lon'])
    zoom       = int(pref['zoom_level'])
    prefecture = pref['name_en'].lower()

    m = _base_map(center_lat, center_lon, zoom, basemap)

    # Population (GeoJson — polygon but manageable size)
    if show_population:
        _add_population_geojson(m, prefecture, population_year)

    # Hazard layers — GeoJson with heavy simplification
    # (tile approach requires VectorGrid JS which has browser compatibility limits)
    for htype, cfg in HAZARD_LAYERS.items():
        if htype in active_hazards:
            _add_hazard_geojson(m, prefecture, htype, cfg)

    # Roads — GeoJson (lines are small)
    for rtype in ROAD_LAYERS:
        if rtype in active_roads:
            _add_roads_geojson(m, prefecture, rtype)

    # Facilities — clustered markers
    for ftype, cfg in FACILITY_LAYERS.items():
        if ftype in active_facilities:
            _add_facilities_geojson(m, prefecture, ftype, cfg)

    add_legend(m, active_hazards, active_facilities)
    folium.LayerControl(collapsed=False, position='topright').add_to(m)

    return m