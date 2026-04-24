# =============================================================================
# agua_brecha_app.py
# Dashboard interactivo: Brecha en acceso a fuente de agua mejorada
# Cabeceras vs. Centros poblados y rural disperso — Colombia 2018-2025
#
# Materia   : Storytelling con datos
# Herramientas: Python · Dash · Plotly · GeoPandas
# Datos     : DANE — Encuesta Nacional de Calidad de Vida (ECV) 2018-2025
# =============================================================================

import os
import json
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

# =============================================================================
# CONFIGURACION GLOBAL
# =============================================================================

EXCEL_PATH = "anex-PMultidimensional-Departamental-2025.xlsx"
ZIP_PATH   = "MGN2024_DPTO_POLITICO.zip"
SHP_DIR    = "shp_departamentos"
YEARS      = [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

# Paleta de color — psicologia del color aplicada a brechas de desigualdad
# Brecha baja (acceso mas igualitario) -> Azul oscuro (profundidad, equidad hidrica)
# Brecha alta (desigualdad territorial grave) -> Ambar dorado (aridez, privacion rural)
COLOR_CABECERAS = "#1a3a6b"          # azul oscuro — acceso urbano, equidad
COLOR_RURAL     = "#FFB300"          # ambar — privacion rural, desigualdad
COLOR_FILL      = "rgba(255,179,0,0.15)"  # fill area brecha — translucido calido
COLOR_PAGE_BG   = "#f7f5f0"          # fondo pagina — neutro calido
COLOR_CARD_BG   = "#ffffff"
COLOR_TEXT_DARK = "#0a1628"
COLOR_TEXT_MID  = "#4a5568"

# Colorscale del mapa: brecha baja=azul oscuro (equidad), brecha alta=ambar dorado (desigualdad)
MAP_COLORSCALE = [
    [0.00, "#0a1628"],   # brecha muy baja  -> azul casi negro (equidad)
    [0.08, "#1a3a6b"],   # brecha baja      -> azul oscuro
    [0.20, "#4a7ab5"],   # brecha media     -> azul medio
    [0.40, "#8a9ab5"],   # brecha moderada  -> gris azulado
    [0.65, "#c4a35a"],   # brecha alta      -> oro transicional
    [1.00, "#FFB300"],   # brecha extrema   -> ambar (desigualdad extrema)
]

# Diccionario de equivalencias entre nombres del shapefile DANE y del Excel
NOMBRE_MAP = {
    "BOGOTA, D.C."               : "Bogota",
    "BOGOTA D.C."                : "Bogota",
    "BOGOTA"                     : "Bogota",
    "NORTE DE SANTANDER"         : "Norte de Santander",
    "VALLE DEL CAUCA"            : "Valle del Cauca",
    "SAN ANDRES, PROVIDENCIA Y SANTA CATALINA": "San Andres",
    "ARCHIPIELAGO DE SAN ANDRES, PROVIDENCIA Y SANTA CATALINA": "San Andres",
    "QUINDIIO"                   : "Quindio",
    "QUINDIO"                    : "Quindio",
    "NARINO"                     : "Narino",
    "CHOCO"                      : "Choco",
    "ANTIOQUIA"                  : "Antioquia",
    "ATLANTICO"                  : "Atlantico",
    "BOLIVAR"                    : "Bolivar",
    "BOYACA"                     : "Boyaca",
    "CALDAS"                     : "Caldas",
    "CAQUETA"                    : "Caqueta",
    "CAUCA"                      : "Cauca",
    "CESAR"                      : "Cesar",
    "CORDOBA"                    : "Cordoba",
    "CUNDINAMARCA"               : "Cundinamarca",
    "HUILA"                      : "Huila",
    "LA GUAJIRA"                 : "La Guajira",
    "MAGDALENA"                  : "Magdalena",
    "META"                       : "Meta",
    "RISARALDA"                  : "Risaralda",
    "SANTANDER"                  : "Santander",
    "SUCRE"                      : "Sucre",
    "TOLIMA"                     : "Tolima",
    "ARAUCA"                     : "Arauca",
    "CASANARE"                   : "Casanare",
    "PUTUMAYO"                   : "Putumayo",
    "AMAZONAS"                   : "Amazonas",
    "GUAINIA"                    : "Guainia",
    "GUAVIARE"                   : "Guaviare",
    "VAUPES"                     : "Vaupes",
    "VICHADA"                    : "Vichada",
}

# Equivalencia inversa: nombres del Excel -> nombre normalizado
EXCEL_NAME_NORM = {
    "Bogota"               : "Bogota",
    "Bogota, D.C."         : "Bogota",
    "Bogota D.C."          : "Bogota",
    "Bogota D. C."         : "Bogota",
    "Bogota D.C"           : "Bogota",
    "Valle del Cauca"      : "Valle del Cauca",
    "Norte de Santander"   : "Norte de Santander",
    "San Andres"           : "San Andres",
    "San Andres, Prov..."  : "San Andres",
    "Quindio"              : "Quindio",
    "Quindiio"             : "Quindio",
    "Narino"               : "Narino",
    "Nari\u00f1o"         : "Narino",
    "Choco"                : "Choco",
    "Choc\u00f3"          : "Choco",
}

def normalize_name(name: str) -> str:
    """Normalize a department name by removing accents and converting to title case."""
    import unicodedata
    name = str(name).strip()
    # Remove accents
    nfkd = unicodedata.normalize("NFD", name)
    name_no_accent = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Title case
    return name_no_accent.strip().title()


# =============================================================================
# CARGA Y LIMPIEZA DE DATOS
# =============================================================================

def load_agua_data() -> pd.DataFrame:
    """
    Load and clean 'Sin acceso a fuente de agua mejorada' indicator
    from DANE IPM Excel, sheet IPM_Indicadores_Departamento.

    Returns a DataFrame with columns:
        Departamento, Departamento_norm,
        Cabeceras_YYYY, Rural_YYYY, Brecha_YYYY  for each year in YEARS
    """
    raw = pd.read_excel(
        EXCEL_PATH,
        sheet_name="IPM_Indicadores_Departamento ",  # trailing space in sheet name
        header=None,
        skiprows=12,   # skip decorative header rows; data starts row 13 (0-indexed 12)
    )

    # Build column names: Departamento, Variable, then 3 cols per year
    col_names = ["Departamento", "Variable"]
    for y in YEARS:
        col_names += [f"Total_{y}", f"Cabeceras_{y}", f"Rural_{y}"]
    raw.columns = col_names

    # Forward-fill department name (merged cells in Excel leave NaN rows)
    raw["Departamento"] = raw["Departamento"].ffill()

    # Keep only the water indicator rows
    agua = raw[raw["Variable"] == "Sin acceso a fuente de agua mejorada"].copy()
    agua = agua[agua["Departamento"] != "Departamento"].reset_index(drop=True)

    # Convert all numeric columns
    for y in YEARS:
        for domain in ["Total", "Cabeceras", "Rural"]:
            agua[f"{domain}_{y}"] = pd.to_numeric(agua[f"{domain}_{y}"], errors="coerce")

    # Compute brecha (gap) = Rural - Cabeceras for each year
    for y in YEARS:
        agua[f"Brecha_{y}"] = agua[f"Rural_{y}"] - agua[f"Cabeceras_{y}"]

    # Normalize department names for geo-join
    agua["Departamento_norm"] = agua["Departamento"].apply(normalize_name)

    # Fix known edge cases
    agua["Departamento_norm"] = agua["Departamento_norm"].replace(
        {normalize_name(k): normalize_name(v) for k, v in EXCEL_NAME_NORM.items()}
    )

    return agua


def load_geodata(agua: pd.DataFrame):
    """
    Load Colombia department shapefile and merge with agua DataFrame.
    Returns a GeoDataFrame with the geometry and water access data.
    Requires MGN2024_DPTO_POLITICO.zip in the working directory.
    """
    if not os.path.exists(SHP_DIR):
        with zipfile.ZipFile(ZIP_PATH, "r") as z:
            z.extractall(SHP_DIR)

    shp_files = [f for f in os.listdir(SHP_DIR) if f.endswith(".shp")]
    assert shp_files, "No .shp file found. Check MGN2024_DPTO_POLITICO.zip"
    gdf = gpd.read_file(os.path.join(SHP_DIR, shp_files[0]))

    # Normalize shapefile department names
    name_col = "DeNombre" if "DeNombre" in gdf.columns else gdf.columns[1]
    gdf["dpto_norm"] = gdf[name_col].apply(
        lambda x: normalize_name(NOMBRE_MAP.get(str(x).strip().upper(), str(x)))
    )

    # Ensure CRS is WGS84
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(epsg=4326)

    # Merge
    merged = gdf.merge(agua, left_on="dpto_norm", right_on="Departamento_norm", how="left")
    return merged


def compute_national(agua: pd.DataFrame) -> dict:
    """Compute national averages (mean across departments) for each year."""
    nacional = {}
    for y in YEARS:
        nacional[y] = {
            "cabeceras": round(float(agua[f"Cabeceras_{y}"].mean()), 1),
            "rural":     round(float(agua[f"Rural_{y}"].mean()), 1),
            "brecha":    round(float(agua[f"Brecha_{y}"].mean()), 1),
        }
    return nacional


# =============================================================================
# CONSTRUCCION DE FIGURAS
# =============================================================================

def build_map(gdf, year: int, selected_dpto: str = None) -> go.Figure:
    """
    Build choropleth map of brecha (Rural - Cabeceras) for a given year.

    Color encodes the gap in percentage points:
    - Low gap (near zero) -> dark blue    (#0a1628): more equal territory (equidad)
    - High gap (>70pp)    -> amber gold   (#FFB300): deep structural inequality
    """
    brecha_col = f"Brecha_{year}"

    geojson = GLOBAL_GEOJSON
    ids     = GLOBAL_IDS

    # Hover text
    hover_texts = []
    for _, row in gdf.iterrows():
        dpto = row.get("Departamento", row.get("dpto_norm", ""))
        cab  = row.get(f"Cabeceras_{year}", np.nan)
        rur  = row.get(f"Rural_{year}", np.nan)
        bre  = row.get(brecha_col, np.nan)
        if pd.isna(bre):
            hover_texts.append(f"<b>{dpto}</b><br>Sin datos")
        else:
            hover_texts.append(
                f"<b>{dpto}</b><br>"
                f"<span style='color:{COLOR_CABECERAS}'>&#9632;</span> Cabeceras: {cab:.1f}%<br>"
                f"<span style='color:{COLOR_RURAL}'>&#9632;</span> Rural disperso: {rur:.1f}%<br>"
                f"<b>Brecha: {bre:.1f} pp</b><br>"
                f"<i>Haz click para ver la serie completa</i>"
            )

    # Highlight selected department
    line_widths = []
    line_colors = []
    for _, row in gdf.iterrows():
        dpto = row.get("Departamento", row.get("dpto_norm", ""))
        if selected_dpto and normalize_name(str(dpto)) == normalize_name(str(selected_dpto)):
            line_widths.append(3)
            line_colors.append(COLOR_RURAL)
        else:
            line_widths.append(0.5)
            line_colors.append("#ffffff")

    brecha_vals = gdf[brecha_col].fillna(-1).tolist()
    valid_vals  = [v for v in brecha_vals if v >= 0]
    vmin = 0
    vmax = max(valid_vals) if valid_vals else 100

    fig = go.Figure(go.Choroplethmapbox(
        geojson=geojson,
        locations=ids,
        z=brecha_vals,
        featureidkey="id",
        colorscale=MAP_COLORSCALE,
        zmin=vmin,
        zmax=vmax,
        marker_line_width=line_widths,
        marker_line_color=line_colors,
        text=hover_texts,
        hovertemplate="%{text}<extra></extra>",
        colorbar=dict(
            title=dict(
                text="Brecha<br>(pp)",
                font=dict(size=11, color=COLOR_TEXT_DARK),
            ),
            tickfont=dict(size=10, color=COLOR_TEXT_MID),
            len=0.6,
            thickness=14,
            x=1.01,
            ticksuffix=" pp",
        ),
    ))

    fig.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        mapbox_style="carto-positron",
        mapbox_zoom=4.2,
        mapbox_center={"lat": 4.5709, "lon": -74.2973},
    )
    return fig


def build_national_chart(nacional: dict, selected_year: int) -> go.Figure:
    """
    Line chart showing national average Cabeceras vs Rural for all years,
    with shaded area representing the gap. Highlights the selected year.
    Used in the side block.
    """
    years_list   = YEARS
    cab_vals     = [nacional[y]["cabeceras"] for y in years_list]
    rural_vals   = [nacional[y]["rural"]     for y in years_list]
    brecha_vals  = [nacional[y]["brecha"]    for y in years_list]

    fig = go.Figure()

    # Fill area between rural and cabeceras (the gap)
    fig.add_trace(go.Scatter(
        x=years_list + years_list[::-1],
        y=rural_vals + cab_vals[::-1],
        fill="toself",
        fillcolor=COLOR_FILL,
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False,
        hoverinfo="skip",
        name="Brecha",
    ))

    # Rural line
    fig.add_trace(go.Scatter(
        x=years_list, y=rural_vals,
        mode="lines+markers",
        name="Rural disperso",
        line=dict(color=COLOR_RURAL, width=2.5),
        marker=dict(size=7, color=COLOR_RURAL),
        hovertemplate="Rural %{x}: <b>%{y:.1f}%</b><extra></extra>",
    ))

    # Cabeceras line
    fig.add_trace(go.Scatter(
        x=years_list, y=cab_vals,
        mode="lines+markers",
        name="Cabeceras",
        line=dict(color=COLOR_CABECERAS, width=2.5),
        marker=dict(size=7, color=COLOR_CABECERAS),
        hovertemplate="Cabeceras %{x}: <b>%{y:.1f}%</b><extra></extra>",
    ))

    # Vertical line for selected year
    sel_rural = nacional[selected_year]["rural"]
    sel_cab   = nacional[selected_year]["cabeceras"]
    sel_brecha = nacional[selected_year]["brecha"]

    fig.add_vline(
        x=selected_year,
        line_dash="dot",
        line_color="#888888",
        line_width=1.5,
        annotation_text=f"Brecha {selected_year}<br><b>{sel_brecha:.1f} pp</b>",
        annotation_position="top right",
        annotation_font_size=10,
        annotation_font_color=COLOR_TEXT_DARK,
    )

    fig.update_layout(
        margin=dict(l=30, r=10, t=10, b=30),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickvals=YEARS,
            tickfont=dict(size=9, color=COLOR_TEXT_MID),
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="%", font=dict(size=9, color=COLOR_TEXT_MID)),
            tickfont=dict(size=9, color=COLOR_TEXT_MID),
            gridcolor="rgba(0,0,0,0.06)",
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=9, color=COLOR_TEXT_MID),
        ),
        height=220,
    )
    return fig


def build_dept_modal_chart(dept_row: pd.Series, dept_name: str) -> go.Figure:
    """
    Line chart for modal/popup showing Cabeceras vs Rural time series
    for a specific department, with shaded gap area.
    """
    cab_vals   = [float(dept_row[f"Cabeceras_{y}"]) for y in YEARS]
    rural_vals = [float(dept_row[f"Rural_{y}"])     for y in YEARS]
    brecha_max = max([float(dept_row[f"Brecha_{y}"]) for y in YEARS])
    brecha_2025 = float(dept_row["Brecha_2025"])
    brecha_2018 = float(dept_row["Brecha_2018"])

    fig = go.Figure()

    # Shaded gap area
    fig.add_trace(go.Scatter(
        x=YEARS + YEARS[::-1],
        y=rural_vals + cab_vals[::-1],
        fill="toself",
        fillcolor=COLOR_FILL,
        line=dict(color="rgba(0,0,0,0)"),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Rural line with value annotations
    fig.add_trace(go.Scatter(
        x=YEARS, y=rural_vals,
        mode="lines+markers+text",
        name="Rural disperso",
        line=dict(color=COLOR_RURAL, width=2.5, dash="dot"),
        marker=dict(size=8, color=COLOR_RURAL),
        text=[f"{v:.1f}%" for v in rural_vals],
        textposition="top center",
        textfont=dict(size=9, color=COLOR_RURAL),
        hovertemplate="Rural %{x}: <b>%{y:.1f}%</b><extra></extra>",
    ))

    # Cabeceras line with value annotations
    fig.add_trace(go.Scatter(
        x=YEARS, y=cab_vals,
        mode="lines+markers+text",
        name="Cabeceras",
        line=dict(color=COLOR_CABECERAS, width=2.5),
        marker=dict(size=8, color=COLOR_CABECERAS),
        text=[f"{v:.1f}%" for v in cab_vals],
        textposition="bottom center",
        textfont=dict(size=9, color=COLOR_CABECERAS),
        hovertemplate="Cabeceras %{x}: <b>%{y:.1f}%</b><extra></extra>",
    ))

    # Annotate max gap
    max_year = YEARS[int(np.argmax([float(dept_row[f"Brecha_{y}"]) for y in YEARS]))]
    max_rural = float(dept_row[f"Rural_{max_year}"])
    max_cab   = float(dept_row[f"Cabeceras_{max_year}"])
    midpoint  = (max_rural + max_cab) / 2
    max_brecha = float(dept_row[f"Brecha_{max_year}"])
    fig.add_annotation(
        x=max_year,
        y=midpoint,
        text=f"Brecha maxima<br><b>{max_brecha:.1f} pp</b>",
        showarrow=False,
        font=dict(size=10, color=COLOR_TEXT_DARK),
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="#cccccc",
        borderwidth=1,
        borderpad=4,
    )

    fig.update_layout(
        margin=dict(l=40, r=10, t=20, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            title=dict(text="AÑO", font=dict(size=10, color=COLOR_TEXT_MID)),
            tickvals=YEARS,
            tickfont=dict(size=10, color=COLOR_TEXT_MID),
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text="% hogares sin acceso a agua mejorada", font=dict(size=10, color=COLOR_TEXT_MID)),
            tickfont=dict(size=10, color=COLOR_TEXT_MID),
            gridcolor="rgba(0,0,0,0.06)",
            ticksuffix="%",
            zeroline=False,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10, color=COLOR_TEXT_MID),
        ),
        height=320,
    )
    return fig


def generate_dept_paragraph(dept_row: pd.Series, dept_name: str) -> list:
    """
    Generate a reflexive HTML paragraph for a department,
    with colored inline words as pre-attentive legend elements.
    Returns a list of Dash HTML components.
    """
    brecha_2025 = float(dept_row["Brecha_2025"])
    brecha_2018 = float(dept_row["Brecha_2018"])
    cab_2025    = float(dept_row["Cabeceras_2025"])
    rur_2025    = float(dept_row["Rural_2025"])
    cambio      = brecha_2025 - brecha_2018

    if brecha_2025 >= 50:
        nivel_texto = "una de las brechas mas profundas del pais"
        reflexion   = ("Esta cifra revela que nacer en la zona rural de este departamento "
                       "implica una desventaja estructural severa en el acceso a agua potable. "
                       "La brecha persiste como una deuda historica con las comunidades rurales.")
    elif brecha_2025 >= 30:
        nivel_texto = "una brecha significativa que supera el promedio nacional"
        reflexion   = ("La diferencia entre vivir en la ciudad y en el campo es aqui palpable "
                       "y cotidiana. Reducir esta brecha requiere inversion focalizada "
                       "en infraestructura hidrica rural.")
    elif brecha_2025 >= 15:
        nivel_texto = "una brecha moderada pero que sigue siendo injusta"
        reflexion   = ("Aunque el indicador ha mejorado, la distancia entre el acceso urbano y rural "
                       "muestra que la equidad territorial aun no es una realidad para todos. "
                       "Cada punto porcentual representa miles de hogares sin agua segura.")
    else:
        nivel_texto = "una de las brechas mas bajas del pais"
        reflexion   = ("Este departamento muestra que es posible reducir la desigualdad en acceso "
                       "al agua. Sin embargo, incluso brechas pequenas afectan a comunidades reales "
                       "que merecen los mismos derechos que los ciudadanos urbanos.")

    cambio_texto = (
        f"redujo en {abs(cambio):.1f} puntos porcentuales" if cambio < 0
        else f"aumento en {cambio:.1f} puntos porcentuales"
    )

    return [
        html.P([
            f"En {dept_name}, el ",
            html.Span("acceso a agua mejorada en cabeceras", style={"color": COLOR_CABECERAS, "fontWeight": "bold"}),
            f" alcanza el {cab_2025:.1f}%, mientras que en ",
            html.Span("centros poblados y rural disperso", style={"color": COLOR_RURAL, "fontWeight": "bold"}),
            f" solo el {rur_2025:.1f}% de los hogares cuenta con este servicio basico. "
            f"Esto representa {nivel_texto}: ",
            html.Strong(f"{brecha_2025:.1f} puntos porcentuales"),
            f" de diferencia. Entre 2018 y 2025, esta brecha se {cambio_texto}.",
        ], style={"fontSize": "13px", "color": COLOR_TEXT_MID, "lineHeight": "1.7", "marginBottom": "8px"}),
        html.P(reflexion,
               style={"fontSize": "12px", "color": COLOR_TEXT_MID,
                      "fontStyle": "italic", "lineHeight": "1.6"}),
    ]


# =============================================================================
# CARGA INICIAL
# =============================================================================

agua   = load_agua_data()
gdf    = load_geodata(agua)
nac    = compute_national(agua)

gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.01, preserve_topology=True)
GLOBAL_GEOJSON  = json.loads(gdf.to_json())
GLOBAL_IDS      = list(range(len(gdf)))

# =============================================================================
# LAYOUT DEL DASHBOARD
# =============================================================================

app = Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
app.title = "Brecha de Agua — Colombia"

# ── Estilos de texto reusables ──────────────────────────────────────────────
STYLE_TITLE = {
    "fontSize": "26px",
    "fontWeight": "900",
    "color": COLOR_TEXT_DARK,
    "lineHeight": "1.2",
    "marginBottom": "6px",
    "letterSpacing": "-0.3px",
}
STYLE_SUBTITLE = {
    "fontSize": "14px",
    "color": COLOR_TEXT_MID,
    "fontStyle": "italic",
    "lineHeight": "1.5",
    "marginBottom": "0",
}
STYLE_SECTION_LABEL = {
    "fontSize": "11px",
    "fontWeight": "700",
    "letterSpacing": "1.5px",
    "textTransform": "uppercase",
    "color": COLOR_TEXT_MID,
    "marginBottom": "4px",
}
STYLE_CARD = {
    "backgroundColor": COLOR_CARD_BG,
    "borderRadius": "10px",
    "padding": "16px",
    "boxShadow": "0 1px 6px rgba(0,0,0,0.07)",
}

app.layout = html.Div(
    style={"backgroundColor": COLOR_PAGE_BG, "minHeight": "100vh", "fontFamily": "Inter, Arial, sans-serif"},
    children=[

        # ── ENCABEZADO ──────────────────────────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "24px 32px 0"}, children=[
            dbc.Row([
                dbc.Col([
                    # Etiqueta previa al titulo (elemento preatentivo: color y uppercase)
                    html.P("INDICADOR DE VIVIENDA — IPM COLOMBIA",
                           style=STYLE_SECTION_LABEL),

                    # Titulo principal: elemento preatentivo — tipografia grande y negrita
                    html.H1(
                        "¿Avanzamos hacia la equidad hídrica? La persistencia de la brecha territorial en Colombia",
                        style=STYLE_TITLE,
                    ),

                    # Subtitulo reflexivo
                    html.P(
                        "Mientras en las ciudades casi todos tienen acceso a una fuente de agua mejorada, "
                        "en los centros poblados y el rural disperso una fraccion significativa de hogares "
                        "sigue enfrentando esta privacion basica. Esta brecha no es geografica — es politica. "
                        "Explora como varia por departamento y como ha cambiado entre 2018 y 2025.",
                        style=STYLE_SUBTITLE,
                    ),
                ], md=9),

                dbc.Col([
                    # Indicador de brecha nacional actual
                    html.Div(style={**STYLE_CARD, "textAlign": "center", "marginTop": "8px"}, children=[
                        html.P("BRECHA NACIONAL 2025", style={**STYLE_SECTION_LABEL, "marginBottom": "2px"}),
                        html.P(
                            f"{nac[2025]['brecha']:.1f} pp",
                            style={"fontSize": "38px", "fontWeight": "900",
                                   "color": COLOR_RURAL, "marginBottom": "0"},
                        ),
                        html.P(
                            f"Rural: {nac[2025]['rural']:.1f}%  vs  Cabeceras: {nac[2025]['cabeceras']:.1f}%",
                            style={"fontSize": "11px", "color": COLOR_TEXT_MID},
                        ),
                    ]),
                ], md=3),
            ], className="align-items-center"),
        ]),

        # ── SEPARADOR ──────────────────────────────────────────────────────
        html.Hr(style={"margin": "16px 32px", "borderColor": "rgba(0,0,0,0.1)"}),

        # ── CONTROLES ──────────────────────────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "0 32px"}, children=[
            dbc.Row([
                dbc.Col([
                    html.P("SELECCIONA EL AÑO", style={**STYLE_SECTION_LABEL, "marginBottom": "4px"}),
                    dcc.Slider(
                        id="year-slider",
                        min=2018, max=2025, step=1, value=2025,
                        marks={y: str(y) for y in YEARS},
                        tooltip={"always_visible": False},
                        className="mb-1",
                    ),
                ], md=7),
                dbc.Col([
                    html.P(
                        [html.Span("Haz click", style={"color": COLOR_CABECERAS, "fontWeight": "700"}),
                         " en cualquier departamento del mapa para ver su serie temporal completa."],
                        style={"fontSize": "12px", "color": COLOR_TEXT_MID, "marginTop": "28px"},
                    ),
                ], md=5),
            ]),
        ]),

        # ── MAPA + PANEL BRECHA NACIONAL ──────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "8px 32px"}, children=[
            dbc.Row([
                # Mapa choropleth
                dbc.Col([
                    html.Div(style=STYLE_CARD, children=[
                        dcc.Graph(
                            id="mapa-agua",
                            style={"height": "560px"},
                            config={"displayModeBar": True, "scrollZoom": True},
                        ),
                    ]),
                ], md=8),

                # Panel brecha nacional
                dbc.Col([
                    html.Div(style={**STYLE_CARD, "height": "100%"}, children=[
                        html.P("EVOLUCION NACIONAL DE LA BRECHA", style=STYLE_SECTION_LABEL),
                        html.P(
                            [html.Span("Cabeceras", style={"color": COLOR_CABECERAS, "fontWeight": "700"}),
                             " vs ",
                             html.Span("Rural disperso", style={"color": COLOR_RURAL, "fontWeight": "700"}),
                             " — promedio de los 33 departamentos"],
                            style={"fontSize": "11px", "color": COLOR_TEXT_MID, "marginBottom": "4px"},
                        ),
                        dcc.Graph(
                            id="chart-nacional",
                            config={"displayModeBar": False},
                        ),
                        html.Hr(style={"margin": "10px 0", "borderColor": "rgba(0,0,0,0.08)"}),
                        html.P("QUE SIGNIFICA LA BRECHA", style={**STYLE_SECTION_LABEL, "marginTop": "6px"}),
                        html.P(
                            "El area sombreada representa los hogares que viven esa diferencia "
                            "cada dia: sin agua de red, sin agua de pozo protegido, "
                            "sin agua segura para beber. Cada punto porcentual en la brecha "
                            "representa miles de familias rurales invisibilizadas.",
                            style={"fontSize": "11px", "color": COLOR_TEXT_MID,
                                   "lineHeight": "1.6", "fontStyle": "italic"},
                        ),
                        html.Hr(style={"margin": "10px 0", "borderColor": "rgba(0,0,0,0.08)"}),
                        html.P("LECTURA DEL MAPA", style=STYLE_SECTION_LABEL),
                        html.Div([
                            html.Div(style={"display": "flex", "alignItems": "center",
                                           "marginBottom": "4px"}, children=[
                                html.Div(style={"width": "14px", "height": "14px",
                                               "backgroundColor": COLOR_CABECERAS,
                                               "borderRadius": "3px", "marginRight": "8px"}),
                                html.P("Brecha baja — mayor equidad",
                                       style={"fontSize": "11px", "color": COLOR_TEXT_MID, "margin": 0}),
                            ]),
                            html.Div(style={"display": "flex", "alignItems": "center",
                                           "marginBottom": "4px"}, children=[
                                html.Div(style={"width": "14px", "height": "14px",
                                               "backgroundColor": "#8a9ab5",
                                               "borderRadius": "3px", "marginRight": "8px"}),
                                html.P("Brecha media — alerta territorial",
                                       style={"fontSize": "11px", "color": COLOR_TEXT_MID, "margin": 0}),
                            ]),
                            html.Div(style={"display": "flex", "alignItems": "center"}, children=[
                                html.Div(style={"width": "14px", "height": "14px",
                                               "backgroundColor": COLOR_RURAL,
                                               "borderRadius": "3px", "marginRight": "8px"}),
                                html.P("Brecha alta — desigualdad estructural",
                                       style={"fontSize": "11px", "color": COLOR_TEXT_MID, "margin": 0}),
                            ]),
                        ]),
                    ]),
                ], md=4),
            ]),
        ]),

        # ── PARRAFO CONCLUSION ──────────────────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "16px 32px 8px"}, children=[
            html.Div(style={**STYLE_CARD, "borderLeft": f"4px solid {COLOR_RURAL}"}, children=[
                html.P("REFLEXION SOBRE LOS DATOS", style=STYLE_SECTION_LABEL),
                html.P([
                    "El acceso a ",
                    html.Strong("fuentes de agua mejorada"),
                    " es uno de los 15 indicadores que componen el Indice de Pobreza "
                    "Multidimensional del DANE. Su ausencia no es un problema menor: "
                    "es una privacion que afecta la salud, la dignidad y las oportunidades "
                    "de miles de hogares colombianos. Lo que este mapa revela es que la "
                    "desigualdad en este acceso no es aleatoria: sigue un patron territorial "
                    "sistematico. Los departamentos de la Amazonia, la Orinoquia y el Pacifico "
                    "concentran las brechas mas profundas entre sus zonas urbanas y rurales, "
                    "mientras que las ciudades del interior andino muestran indicadores "
                    "considerablemente mejores. Entre 2018 y 2025 la brecha nacional se redujo, "
                    "pero de forma insuficiente y desigual. ",
                    html.Strong(
                        f"En 2025, un hogar rural colombiano tiene en promedio "
                        f"{nac[2025]['rural']:.1f}% de probabilidad de carecer de agua "
                        f"mejorada, frente al {nac[2025]['cabeceras']:.1f}% en las cabeceras "
                        f"municipales. Una brecha de {nac[2025]['brecha']:.1f} puntos "
                        "porcentuales que el tiempo no ha logrado cerrar."
                    ),
                ], style={"fontSize": "13px", "color": COLOR_TEXT_MID, "lineHeight": "1.8"}),
            ]),
        ]),

        # ── FUENTES ──────────────────────────────────────────────────────
        dbc.Container(fluid=True, style={"padding": "8px 32px 24px"}, children=[
            html.Hr(style={"borderColor": "rgba(0,0,0,0.1)"}),
            html.Small([
                html.Strong("Fuente: "),
                "DANE — Encuesta Nacional de Calidad de Vida (ECV) 2018-2025. "
                "Indicador: Privaciones por hogar segun variable, hoja IPM_Indicadores_Departamento. "
                "Cartografia: Marco Geoestadistico Nacional DANE 2024 (MGN2024_DPTO_POLITICO). "
                "Nota: Los valores de 2020 y 2021 incorporan ajustes metodologicos del DANE "
                "derivados de la pandemia COVID-19. "
                "Elaboracion propia con Python, Dash y Plotly.",
            ], style={"color": "#999", "fontSize": "10px", "lineHeight": "1.5"}),
        ]),

        # ── STORE: departamento seleccionado ────────────────────────────────
        dcc.Store(id="selected-dept-store"),

        # ── MODAL: panel desplegable por departamento ───────────────────────
        dbc.Modal(
            id="modal-dept",
            size="lg",
            is_open=False,
            backdrop=True,
            scrollable=True,
            children=[
                dbc.ModalHeader(
                    html.H5(id="modal-titulo",
                            style={"fontWeight": "800", "color": COLOR_TEXT_DARK,
                                   "fontSize": "18px"}),
                    close_button=True,
                ),
                dbc.ModalBody([
                    html.P(id="modal-subtitulo",
                           style={"fontSize": "11px", "color": COLOR_TEXT_MID,
                                  "letterSpacing": "1px", "textTransform": "uppercase",
                                  "marginBottom": "4px"}),
                    dcc.Graph(
                        id="chart-modal",
                        config={"displayModeBar": False},
                        style={"height": "340px"},
                    ),
                    html.Hr(style={"margin": "12px 0"}),
                    html.P("SITUACION DEL DEPARTAMENTO",
                           style={**STYLE_SECTION_LABEL, "marginBottom": "6px"}),
                    html.Div(id="modal-parrafo"),
                ]),
            ],
        ),
    ],
)


# =============================================================================
# CALLBACKS
# =============================================================================

@app.callback(
    Output("mapa-agua",    "figure"),
    Output("chart-nacional", "figure"),
    Input("year-slider",   "value"),
    Input("selected-dept-store", "data"),
)
def update_main_charts(year, selected_dept):
    """Update choropleth map and national chart when year or selection changes."""
    fig_map = build_map(gdf, year, selected_dpto=selected_dept)
    fig_nac = build_national_chart(nac, year)
    return fig_map, fig_nac


@app.callback(
    Output("selected-dept-store", "data"),
    Output("modal-dept",     "is_open"),
    Output("modal-titulo",   "children"),
    Output("modal-subtitulo","children"),
    Output("chart-modal",    "figure"),
    Output("modal-parrafo",  "children"),
    Input("mapa-agua",       "clickData"),
    State("year-slider",     "value"),
    prevent_initial_call=True,
)
def open_dept_modal(click_data, year):
    """
    When user clicks on a department in the map:
    - Store selected department name
    - Open modal with department-specific line chart and reflexive paragraph
    """
    if not click_data:
        return None, False, "", "", go.Figure(), []

    # Get department index from click (choropleth uses location index)
    point_idx = click_data["points"][0]["location"]

    # Retrieve department row from gdf
    row_gdf   = gdf.iloc[point_idx]
    dept_name = str(row_gdf.get("Departamento", row_gdf.get("dpto_norm", "")))

    # Find matching row in agua DataFrame
    dept_norm = normalize_name(dept_name)
    match = agua[agua["Departamento_norm"] == dept_norm]

    if match.empty:
        return dept_name, False, "", "", go.Figure(), []

    dept_row = match.iloc[0]

    # Build modal content
    titulo    = f"{dept_row['Departamento']} — Acceso a agua mejorada 2018-2025"
    subtitulo = (f"Brecha en 2025: {dept_row['Brecha_2025']:.1f} pp  |  "
                 f"Cabeceras: {dept_row['Cabeceras_2025']:.1f}%  |  "
                 f"Rural: {dept_row['Rural_2025']:.1f}%")
    fig_modal  = build_dept_modal_chart(dept_row, dept_row["Departamento"])
    parrafo    = generate_dept_paragraph(dept_row, dept_row["Departamento"])

    return dept_name, True, titulo, subtitulo, fig_modal, parrafo


# =============================================================================
# EXPORTACION A HTML ESTATICO
# =============================================================================

def export_static_html(output_path: str = "agua_brecha_mapa.html"):
    """
    Export a static (non-interactive callbacks) version of the map + national chart
    to a standalone HTML file using plotly.io.write_html.
    The static export includes the choropleth and national trend chart for year 2025.
    Note: modal interactivity requires the Dash server (app.run).
    """
    import plotly.io as pio
    from plotly.subplots import make_subplots

    fig_map = build_map(gdf, 2025)
    fig_nac = build_national_chart(nac, 2025)

    # Combine into a single figure using subplots
    combined = make_subplots(
        rows=1, cols=2,
        column_widths=[0.65, 0.35],
        specs=[[{"type": "mapbox"}, {"type": "xy"}]],
        subplot_titles=[
            "Brecha en acceso a agua mejorada por departamento (2025)",
            "Evolucion nacional 2018-2025",
        ],
    )

    for trace in fig_map.data:
        combined.add_trace(trace, row=1, col=1)

    for trace in fig_nac.data:
        combined.add_trace(trace, row=1, col=2)

    combined.update_layout(
        mapbox_style="carto-positron",
        mapbox_zoom=4.2,
        mapbox_center={"lat": 4.5709, "lon": -74.2973},
    )
    combined.update_layout(
        title=dict(
            text=(
                "<b>El campo sigue sin agua: la desigualdad que divide a Colombia</b><br>"
                "<span style='font-size:12px;color:#4a5568;font-style:italic;'>"
                "Brecha en % de hogares sin acceso a fuente de agua mejorada — "
                "Cabeceras vs. Rural disperso — DANE ECV 2018-2025"
                "</span>"
            ),
            x=0.02,
            font=dict(size=16),
        ),
        paper_bgcolor=COLOR_PAGE_BG,
        plot_bgcolor=COLOR_PAGE_BG,
        height=620,
        margin=dict(l=20, r=20, t=90, b=40),
        showlegend=True,
        legend=dict(
            orientation="h",
            y=-0.08,
            font=dict(size=10),
        ),
        annotations=[
            dict(
                xref="paper", yref="paper",
                x=0.02, y=-0.12,
                text=(
                    "Fuente: DANE — ECV 2018-2025. Cartografia: MGN2024 DANE. "
                    "Nota: Color del mapa = brecha (Rural - Cabeceras). "
                    "Azul oscuro = menor brecha. Dorado = mayor desigualdad."
                ),
                showarrow=False,
                font=dict(size=9, color="#999"),
                align="left",
            )
        ],
    )

    pio.write_html(
        combined,
        file=output_path,
        full_html=True,
        include_plotlyjs=True,
        config={"displayModeBar": True, "scrollZoom": False},
    )
    print(f"Exported static HTML -> {output_path}")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================

if __name__ == "__main__":
    # Export static HTML first
    export_static_html("agua_brecha_mapa.html")

    # Run interactive Dash app
    app.run(debug=False, host="0.0.0.0", port=8050)
