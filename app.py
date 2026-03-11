import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import unicodedata
import os
import re
import concurrent.futures
import io
import plotly.express as px

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# 1. CONFIGURACIÓ DE LA PÀGINA WEB
st.set_page_config(page_title="BàsquetStats - FCBQ", page_icon="🏀", layout="wide")

# ---------------------------------------------------------
# INICIALITZAR LA MEMÒRIA DE LA SESSIÓ
# ---------------------------------------------------------
if "dades_carregades" not in st.session_state:
    st.session_state.dades_carregades = False
    st.session_state.df_total = pd.DataFrame()
    st.session_state.taules_fases = {}
    st.session_state.historial = {}
    st.session_state.historial_boxscores = {}
    st.session_state.equip_nom = ""

# 2. INJECCIÓ DE CSS
estil_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;600&family=DM+Mono:wght@400&display=swap');

    html, body, [class*="css"], .stMarkdown, p, div {
        font-family: 'DM Sans', sans-serif;
    }

    h1, h2, h3, h4, h5, h6 {
        font-family: 'Bebas Neue', sans-serif !important;
        letter-spacing: 1.5px !important;
    }

    .titol-principal {
        font-family: 'Bebas Neue', sans-serif;
        font-size: 4rem;
        color: #fca311; 
        text-align: center;
        margin-bottom: 0px;
    }
    
    .subtitol {
        text-align: center;
        color: #8d99ae;
        margin-bottom: 40px;
        font-size: 1.2rem;
    }

    .stButton>button {
        font-family: 'DM Sans', sans-serif !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        width: 100%;
        height: 50px;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(252, 163, 17, 0.4);
    }
    
    .marcador-caixa {
        background-color: #1e1e24;
        border-radius: 12px;
        border: 2px solid #333;
        margin-bottom: 20px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.4);
    }
</style>
"""
st.markdown(estil_css, unsafe_allow_html=True)

# ==========================================
# FUNCIONS DE BASE DE DADES I SCRAPING
# ==========================================
def treure_accents(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

def netejar_puntuacio(text):
    """Elimina punts, guions i caràcters estranys per evitar errors per culpa d'abreviatures"""
    return re.sub(r'[^A-Z0-9\s]', '', text.upper())

def obtenir_color_equip(equip):
    color = equip.get('colorRgb') or equip.get('primaryColor')
    nom_net = treure_accents(equip.get('name', '')).upper()
    
    if not color or color.upper() in ['#FFFFFF', '#FFF', 'WHITE', 'NULL', 'NONE', '']:
        if 'BLAU' in nom_net: return '#3b82f6'
        if 'VERD' in nom_net: return '#22c55e'
        if 'NEGRE' in nom_net: return '#a1a1aa'
        if 'VERMELL' in nom_net or 'ROIG' in nom_net: return '#ef4444'
        if 'GROC' in nom_net: return '#eab308'
        if 'TARONJA' in nom_net: return '#f97316'
        if 'ROSA' in nom_net: return '#ec4899'
        if 'LILA' in nom_net or 'MORAT' in nom_net: return '#a855f7'
        if 'GRANA' in nom_net: return '#9f1239'
        if 'BLANC' in nom_net: return '#f8fafc'
        return '#ffffff' 
    return color

def generar_arxiu_pdf(df, titol, es_partit=False):
    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(A4), topMargin=30, bottomMargin=30)
    elements = []
    
    styles = getSampleStyleSheet()
    titol_estil = styles['Heading1']
    titol_estil.alignment = 1 
    
    titol_net = titol.replace("🏀", "").replace("🛡️", "").replace("🏆", "").replace("📥", "").strip()
    titol_net = unicodedata.normalize('NFKD', titol_net).encode('latin-1', 'ignore').decode('latin-1')
    
    elements.append(Paragraph(titol_net, titol_estil))
    elements.append(Spacer(1, 20))

    df_pdf = df.copy()
    
    def format_pct(x):
        try: return f"{float(x):.1f}%"
        except: return str(x)
        
    def format_ppp_mpp(x):
        try: return f"{float(x):.1f}"
        except: return str(x)

    if '% TL' in df_pdf.columns:
        df_pdf['% TL'] = df_pdf['% TL'].apply(format_pct)
    if 'PPP' in df_pdf.columns:
        df_pdf['PPP'] = df_pdf['PPP'].apply(format_ppp_mpp)
    # FORMAT PER LA NOVA COLUMNA AL PDF
    if 'MPP' in df_pdf.columns:
        df_pdf['MPP'] = df_pdf['MPP'].apply(format_ppp_mpp)

    data = []
    col_names = [unicodedata.normalize('NFKD', str(col)).encode('latin-1', 'ignore').decode('latin-1') for col in df_pdf.columns]
    data.append(col_names)
    
    for index, row in df_pdf.iterrows():
        fila_neta = [unicodedata.normalize('NFKD', str(x)).encode('latin-1', 'ignore').decode('latin-1') for x in row.to_list()]
        data.append(fila_neta)

    table = Table(data)

    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])
    ])

    try: col_pm = df_pdf.columns.to_list().index('+/-')
    except: col_pm = -1
    try: col_val = df_pdf.columns.to_list().index('Val')
    except: col_val = -1
    try: col_f = df_pdf.columns.to_list().index('F')
    except: col_f = -1

    for num_fila, (index_pandas, row) in enumerate(df_pdf.iterrows()):
        r = num_fila + 1 
        if col_pm != -1:
            try:
                v = float(row['+/-'])
                if v > 0: style.add('TEXTCOLOR', (col_pm, r), (col_pm, r), colors.HexColor("#16a34a"))
                elif v < 0: style.add('TEXTCOLOR', (col_pm, r), (col_pm, r), colors.HexColor("#dc2626"))
            except: pass
            
        if col_val != -1:
            try:
                v = float(row['Val'])
                if v > 0: style.add('TEXTCOLOR', (col_val, r), (col_val, r), colors.HexColor("#16a34a"))
                elif v < 0: style.add('TEXTCOLOR', (col_val, r), (col_val, r), colors.HexColor("#dc2626"))
            except: pass
            
        if col_f != -1 and es_partit:
            try:
                v = int(row['F'])
                if v >= 5: style.add('TEXTCOLOR', (col_f, r), (col_f, r), colors.HexColor("#dc2626"))
                elif v == 4: style.add('TEXTCOLOR', (col_f, r), (col_f, r), colors.HexColor("#ea580c"))
                elif v in [2, 3]: style.add('TEXTCOLOR', (col_f, r), (col_f, r), colors.HexColor("#ca8a04"))
            except: pass

    table.setStyle(style)
    elements.append(table)
    doc.build(elements)
    
    return output.getvalue(), "pdf", "application/pdf"

@st.cache_data
def carregar_diccionari_clubs():
    arxiu = "clubs_catalunya.txt"
    clubs = {}
    if os.path.exists(arxiu):
        with open(arxiu, "r", encoding="utf-8") as f:
            for linia in f:
                if "|" in linia:
                    parts = linia.split("|")
                    nom = parts[0].strip()
                    url = parts[1].strip()
                    clubs[nom] = url
    return clubs

@st.cache_data(ttl=3600) 
def obtenir_tots_els_equips_del_club(url_club):
    headers = {"User-Agent": "Mozilla/5.0"}
    equips_club = []
    try:
        res = requests.get(url_club, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                if '/equip/' in a['href']:
                    text_linia_net = treure_accents(a.parent.text.upper())
                    linia_bruta = a.parent.text.strip().replace('\n', ' ').replace('\r', '').replace('\t', '')
                    linia_neta_espais = re.sub(' +', ' ', linia_bruta) 
                    nom_equip = a.text.strip()
                    nom_lliga = linia_neta_espais.split('|')[0].strip() if '|' in linia_neta_espais else "Lliga"
                    linia_original = f"{nom_lliga} | {nom_equip}"
                    url_equip = "https://www.basquetcatala.cat" + a['href'] if a['href'].startswith('/') else a['href']
                    
                    equips_club.append({
                        'nom_curt': nom_equip,
                        'linia_cerca': text_linia_net,
                        'linia_mostrar': linia_original,
                        'url': url_equip
                    })
    except:
        pass
    return equips_club

def processar_estadistiques_a_dataframe(diccionari_stats):
    if not diccionari_stats:
        return pd.DataFrame()
        
    df = pd.DataFrame.from_dict(diccionari_stats, orient='index').reset_index()
    df.rename(columns={'index': 'Jugadora', 'dorsal': 'Dor', 'pj': 'PJ', 'min': 'Min', 'pts': 'PTS', 
                       't2': 'T2', 't3': 'T3', 'tlt': 'TLT', 'tla': 'TLA', 'f': 'F', 'val': 'Val', 'mas_menos': '+/-'}, inplace=True)
    
    # Càlcul de PPP i TL
    df['PPP'] = (df['PTS'] / df['PJ']).round(1).fillna(0)
    
    # NOU CÀLCUL: Minuts per partit (MPP)
    df['MPP'] = (df['Min'] / df['PJ']).round(1).fillna(0)
    
    df['TL (A/T)'] = df['TLA'].astype(int).astype(str) + '/' + df['TLT'].astype(int).astype(str)
    df['% TL'] = df.apply(lambda row: round((row['TLA'] / row['TLT'] * 100), 1) if row['TLT'] > 0 else 0.0, axis=1)
    
    df['DOR_NUM'] = pd.to_numeric(df['Dor'], errors='coerce').fillna(999)
    df = df.sort_values(by='DOR_NUM').drop(columns=['DOR_NUM'])
    
    # NOVA ORDENACIÓ: MPP entre Min i PTS
    columnes_ordre = ['Dor', 'Jugadora', 'PJ', 'Min', 'MPP', 'PTS', 'PPP', 'Val', '+/-', 'TL (A/T)', '% TL', 'T2', 'T3', 'F']
    return df[columnes_ordre]

def formatar_dataframe_boxscore(diccionari_stats):
    if not diccionari_stats:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(diccionari_stats, orient='index').reset_index()
    df.rename(columns={'index': 'Jugadora'}, inplace=True)
    df['DOR_NUM'] = pd.to_numeric(df['Dor'], errors='coerce').fillna(999)
    df = df.sort_values(by='DOR_NUM').drop(columns=['DOR_NUM'])
    # Al BoxScore (un sol partit) no té sentit parlar de MPP o PPP, només els totals del dia
    columnes_ordre = ['Dor', 'Jugadora', 'Min', 'PTS', 'Val', '+/-', 'TL (A/T)', '% TL', 'T2', 'T3', 'F']
    return df[columnes_ordre]

def estilitzar_taula(df, es_partit=False):
    format_dict = {}
    if '% TL' in df.columns:
        format_dict['% TL'] = "{:.1f}%"
    if 'PPP' in df.columns:
        format_dict['PPP'] = "{:.1f}"
    # NOVA FORMATACIÓ VISUAL
    if 'MPP' in df.columns:
        format_dict['MPP'] = "{:.1f}"
        
    def pintar_pos_neg(val):
        try:
            v = float(val)
            if v > 0: return 'color: #4ade80; font-weight: bold;' 
            elif v < 0: return 'color: #f87171; font-weight: bold;' 
            else: return 'color: #9ca3af;'
        except:
            return ''

    def pintar_faltes(val):
        try:
            v = int(val)
            if v >= 5: return 'color: #ef4444; font-weight: bold;' 
            elif v == 4: return 'color: #f97316; font-weight: bold;' 
            elif v in [2, 3]: return 'color: #facc15;' 
            else: return 'color: #9ca3af;'
        except:
            return ''
            
    estil = df.style.format(format_dict)
    
    if '+/-' in df.columns:
        estil = estil.map(pintar_pos_neg, subset=['+/-']) if hasattr(estil, "map") else estil.applymap(pintar_pos_neg, subset=['+/-'])
    if 'Val' in df.columns:
        estil = estil.map(pintar_pos_neg, subset=['Val']) if hasattr(estil, "map") else estil.applymap(pintar_pos_neg, subset=['Val'])
    if 'F' in df.columns and es_partit:
        estil = estil.map(pintar_faltes, subset=['F']) if hasattr(estil, "map") else estil.applymap(pintar_faltes, subset=['F'])
            
    return estil

# ==========================================
# INTERFÍCIE WEB (FRONTEND)
# ==========================================
diccionari_clubs = carregar_diccionari_clubs()
llista_noms_clubs = list(diccionari_clubs.keys()) if diccionari_clubs else ["⚠️ Arxiu no trobat"]
index_defecte = next((i for i, nom in enumerate(llista_noms_clubs) if "PEDAGOGIUM" in nom.upper()), 0)

st.markdown('<div class="titol-principal">🏀 BÀSQUET STATS PRO</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitol">GESTOR D\'ESTADÍSTIQUES AVANÇAT FCBQ</div>', unsafe_allow_html=True)

with st.container():
    st.markdown("### ⚙️ Configuració de l'Equip")
    col1, col3, col4 = st.columns([1.5, 1, 1])

    with col1:
        club_seleccionat = st.selectbox("Selecciona el Club", options=llista_noms_clubs, index=index_defecte)
    with col3:
        categoria_input = st.selectbox("Categoria", ["PRE-MINI", "MINI", "PRE-INFANTIL", "INFANTIL", "CADET", "JUNIOR", "SOTS-20", "SOTS-25", "SÈNIOR"])
    with col4:
        genere_input = st.selectbox("Gènere", ["FEMENÍ", "MASCULÍ"])

    url_club = diccionari_clubs.get(club_seleccionat, "")
    equips_disponibles = {}
    
    if url_club and "⚠️" not in club_seleccionat:
        tots_equips = obtenir_tots_els_equips_del_club(url_club)
        
        dicc_categories = {
            "PRE-MINI": {"inc": ["PRE-MINI", "PREMINI", "PRE MINI"], "exc": []},
            "MINI": {"inc": ["MINI"], "exc": ["PRE-MINI", "PREMINI", "PRE MINI"]},
            "PRE-INFANTIL": {"inc": ["PRE-INFANTIL", "PREINFANTIL", "PRE INFANTIL"], "exc": []},
            "INFANTIL": {"inc": ["INFANTIL"], "exc": ["PRE-INFANTIL", "PREINFANTIL", "PRE INFANTIL"]},
            "CADET": {"inc": ["CADET"], "exc": []},
            "JUNIOR": {"inc": ["JUNIOR"], "exc": []},
            "SOTS-20": {"inc": ["SOTS-20", "SOTS 20", "SUB-20", "SUB 20", "SOTS20", "U20"], "exc": []},
            "SOTS-25": {"inc": ["SOTS-25", "SOTS 25", "SUB-25", "SUB 25", "SOTS25", "U25"], "exc": []},
            "SÈNIOR": {"inc": ["SENIOR", "COPA", "PRIMERA", "SEGONA", "TERCERA", "QUARTA", "LLIGA", "NACIONAL", "EBA", "1A", "2A", "3A"], "exc": []}
        }
        dicc_generes = {"FEMENÍ": ["FEMENI", "FEM"], "MASCULÍ": ["MASCULI", "MASC"]}
        
        filtre_cat = dicc_categories.get(categoria_input, {"inc": [treure_accents(categoria_input.upper())], "exc": []})
        variants_cat = filtre_cat["inc"]
        exclusions_cat = filtre_cat["exc"]
        variants_gen = dicc_generes.get(genere_input, [treure_accents(genere_input.upper())])
        
        for eq in tots_equips:
            text_linia = eq['linia_cerca']
            if any(variant in text_linia for variant in variants_cat) and not any(exc in text_linia for exc in exclusions_cat) and any(variant in text_linia for variant in variants_gen):
                equips_disponibles[eq['linia_mostrar']] = {'url': eq['url'], 'nom_curt': eq['nom_curt']}

    noms_filtrats = list(equips_disponibles.keys())
    paraula_clau_club = " ".join([p for p in club_seleccionat.replace("CLUB", "").replace("BASQUET", "").replace("ASSOCIACIO", "").replace("ESPORTIVA", "").replace("BOL", "").split() if len(p) > 2])

    if noms_filtrats:
        equip_seleccionat = st.selectbox("Equip trobat (Automàtic)", options=noms_filtrats)
    else:
        equip_seleccionat = st.selectbox("Equip trobat (Automàtic)", options=["Cap equip actiu trobat amb aquests filtres"])

st.write("") 

# ========================================================
# CÀRREGA DE DADES AMB SISTEMA FAIL-SAFE INCORPORAT
# ========================================================
if st.button("📊 GENERAR INFORME ESTADÍSTIC", type="primary"):
    if equip_seleccionat == "Cap equip actiu trobat amb aquests filtres":
        st.error(f"❌ El {club_seleccionat} no té cap equip competint actiu que encaixi amb els filtres.")
        st.stop()
        
    dades_equip = equips_disponibles[equip_seleccionat]
    url_equip_final = dades_equip['url']
    nom_curt_api = dades_equip['nom_curt']  
    equip_id_matricula = url_equip_final.rstrip('/').split('/')[-1]
    
    # Neteja de text extrema
    nom_c = netejar_puntuacio(treure_accents(nom_curt_api))
    paraula_clau_club_neta = netejar_puntuacio(treure_accents(club_seleccionat))
    paraules_equip = [p for p in nom_c.split() if p not in ["CLUB", "BASQUET", "ASSOCIACIO", "ESPORTIVA", "BOL", "CB", "BC", "CE", "AE"] and len(p) > 2]
    paraula_json_final = " ".join([p for p in paraula_clau_club_neta.split() if p not in ["CLUB", "BASQUET", "ASSOCIACIO", "ESPORTIVA", "BOL", "CB", "BC", "CE", "AE"] and len(p) > 2])
    
    amb_progres = st.status(f"📡 Connectant directament amb l'equip...", expanded=True)
    
    with amb_progres:
        headers = {"User-Agent": "Mozilla/5.0"}
        res_fases = requests.get(url_equip_final, headers=headers)
        soup_fases = BeautifulSoup(res_fases.text, 'html.parser')
        urls_fases = [("https://www.basquetcatala.cat" + a['href'] if a['href'].startswith('/') else a['href']) for a in soup_fases.find_all('a', href=True) if '/competicions/resultats/' in a['href']]
        urls_fases = list(dict.fromkeys(urls_fases))
                
        if not urls_fases:
            st.error("L'equip està inscrit però no ha començat la lliga ni té partits.")
            st.stop()
            
        st.write(f"📥 Rastrejador Ascendent: Analitzant les capses d'HTML reals...")
        estadistiques_temporada = {}
        taules_fases = {}
        historial_partits_jugadora = {} 
        historial_boxscores = {} 
        
        for index, url_fase in enumerate(urls_fases, 1):
            nom_fase_actual = f"Fase {index}"
            ids_partits_fase = set()
            
            def buscar_ids_per_capsa(jornada):
                partits_trobats = []
                try:
                    r = requests.get(f"{url_fase}/{jornada}", headers=headers, timeout=5)
                    s = BeautifulSoup(r.text, 'html.parser')
                    
                    for a in s.find_all('a', href=True):
                        if '/estadistiques/' in a['href']:
                            capsa = a.parent
                            
                            while capsa and capsa.name not in ['body', 'html']:
                                if capsa.name == 'tr': 
                                    break
                                if len(capsa.find_all('a', href=re.compile(r'/club/|/equip/'))) >= 2:
                                    break
                                capsa = capsa.parent
                                
                            if capsa:
                                text_capsa = netejar_puntuacio(treure_accents(capsa.get_text(separator=' ')))
                                html_capsa = str(capsa)
                                equip_juga_aqui = False
                                
                                if equip_id_matricula and len(equip_id_matricula) > 2 and (f"/{equip_id_matricula}" in html_capsa):
                                    equip_juga_aqui = True
                                elif nom_c in text_capsa:
                                    equip_juga_aqui = True
                                elif len(paraules_equip) > 0 and all(p in text_capsa for p in paraules_equip):
                                    equip_juga_aqui = True
                                elif paraula_json_final and paraula_json_final in text_capsa:
                                    equip_juga_aqui = True
                                    
                                if equip_juga_aqui:
                                    partits_trobats.append(a['href'].split('/')[-1])
                except: pass
                return partits_trobats

            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                futurs = [executor.submit(buscar_ids_per_capsa, j) for j in range(1, 41)]
                for futur in concurrent.futures.as_completed(futurs):
                    for id_p in futur.result():
                        ids_partits_fase.add(id_p)
            
            if len(ids_partits_fase) == 0:
                st.write(f"⚠️ Activant Cerca Profunda d'emergència pel Grup {index}...")
                def buscar_tots_ids(jornada):
                    partits_trobats = []
                    try:
                        r = requests.get(f"{url_fase}/{jornada}", headers=headers, timeout=5)
                        s = BeautifulSoup(r.text, 'html.parser')
                        for a in s.find_all('a', href=True):
                            if '/estadistiques/' in a['href']:
                                partits_trobats.append(a['href'].split('/')[-1])
                    except: pass
                    return partits_trobats
                    
                with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                    futurs = [executor.submit(buscar_tots_ids, j) for j in range(1, 36)]
                    for futur in concurrent.futures.as_completed(futurs):
                        for id_p in futur.result():
                            ids_partits_fase.add(id_p)
                            
            st.write(f"✅ S'han aïllat {len(ids_partits_fase)} actes al Grup {index}. Processant dades...")
            
            est_fase_actual = {}
            for id_partit in ids_partits_fase:
                try:
                    res_api = requests.get(f"https://msstats.optimalwayconsulting.com/v1/fcbq/getJsonWithMatchStats/{id_partit}?currentSeason=true", headers=headers, timeout=5)
                    if res_api.status_code != 200: continue
                    equips = res_api.json().get('teams', [])
                    if len(equips) < 2: continue
                    
                    equip_local = equips[0]
                    equip_visitant = equips[1]
                    
                    nom_local = equip_local.get('name', 'Local')
                    nom_visitant = equip_visitant.get('name', 'Visitant')
                    
                    nom_local_net = netejar_puntuacio(treure_accents(nom_local))
                    nom_visitant_net = netejar_puntuacio(treure_accents(nom_visitant))
                    
                    color_local = obtenir_color_equip(equip_local)
                    color_visitant = obtenir_color_equip(equip_visitant)
                    
                    score_local = equip_local.get('score', sum([p.get('data',{}).get('score',0) for p in equip_local.get('players', [])]))
                    score_visitant = equip_visitant.get('score', sum([p.get('data',{}).get('score',0) for p in equip_visitant.get('players', [])]))

                    es_local = False
                    equip_nostre_dades = None
                    equip_rival_dades = None
                    equip_rival_nom = ""
                    
                    if nom_c in nom_local_net or (paraula_json_final and paraula_json_final in nom_local_net):
                        es_local = True
                        equip_nostre_dades = equip_local
                        equip_rival_dades = equip_visitant
                        equip_rival_nom = nom_visitant
                    elif nom_c in nom_visitant_net or (paraula_json_final and paraula_json_final in nom_visitant_net):
                        es_local = False
                        equip_nostre_dades = equip_visitant
                        equip_rival_dades = equip_local
                        equip_rival_nom = nom_local
                    else:
                        continue

                    localia_icona = "🏠 LOCAL" if es_local else "✈️ VISITANT"
                    rival_amb_localia = f"{equip_rival_nom} ({'Casa' if es_local else 'Fora'})"
                    
                    est_partit_actual_equip = {} 
                    est_partit_rival = {}
                    
                    for jug in equip_nostre_dades.get('players', []):
                        nom = jug.get('name', 'Desc')
                        dorsal = jug.get('dorsal', '-')
                        
                        for d_stats in [est_fase_actual, estadistiques_temporada]:
                            if nom not in d_stats: d_stats[nom] = {'dorsal': dorsal, 'pj': 0, 'min': 0, 'pts': 0, 't2': 0, 't3': 0, 'tlt': 0, 'tla': 0, 'f': 0, 'val': 0, 'mas_menos': 0}
                        
                        minuts = jug.get('timePlayed', 0)
                        d_est = jug.get('data', {})
                        
                        if minuts > 0:
                            est_fase_actual[nom]['pj'] += 1
                            estadistiques_temporada[nom]['pj'] += 1
                            
                            tla = d_est.get('shotsOfOneSuccessful', 0)
                            tlt = d_est.get('shotsOfOneAttempted', 0)
                            pct_tl = round((tla / tlt * 100), 1) if tlt > 0 else 0.0
                            
                            if nom not in historial_partits_jugadora:
                                historial_partits_jugadora[nom] = []
                            
                            historial_partits_jugadora[nom].append({
                                'Fase': nom_fase_actual,
                                'Rival': rival_amb_localia,
                                'Min': minuts,
                                'PTS': d_est.get('score', 0),
                                'T2': d_est.get('shotsOfTwoSuccessful', 0),
                                'T3': d_est.get('shotsOfThreeSuccessful', 0),
                                'TL (A/T)': f"{int(tla)}/{int(tlt)}",
                                '% TL': pct_tl,
                                'F': d_est.get('faults', 0),
                                '+/-': jug.get('inOut', 0),
                                'Val': d_est.get('valoration', 0)
                            })
                            
                            est_partit_actual_equip[nom] = {
                                'Dor': dorsal, 'Min': minuts, 'PTS': d_est.get('score', 0), 'Val': d_est.get('valoration', 0),
                                '+/-': jug.get('inOut', 0), 'TL (A/T)': f"{int(tla)}/{int(tlt)}", '% TL': pct_tl,
                                'T2': d_est.get('shotsOfTwoSuccessful', 0), 'T3': d_est.get('shotsOfThreeSuccessful', 0), 'F': d_est.get('faults', 0)
                            }
                            
                        for d_stats in [est_fase_actual, estadistiques_temporada]:
                            d_stats[nom]['min'] += minuts
                            d_stats[nom]['mas_menos'] += jug.get('inOut', 0)
                            d_stats[nom]['pts'] += d_est.get('score', 0)
                            d_stats[nom]['t2'] += d_est.get('shotsOfTwoSuccessful', 0)
                            d_stats[nom]['t3'] += d_est.get('shotsOfThreeSuccessful', 0)
                            d_stats[nom]['tlt'] += d_est.get('shotsOfOneAttempted', 0)
                            d_stats[nom]['tla'] += d_est.get('shotsOfOneSuccessful', 0)
                            d_stats[nom]['f'] += d_est.get('faults', 0)
                            d_stats[nom]['val'] += d_est.get('valoration', 0)
                            
                    for jug in equip_rival_dades.get('players', []):
                        nom = jug.get('name', 'Desc')
                        dorsal = jug.get('dorsal', '-')
                        minuts = jug.get('timePlayed', 0)
                        d_est = jug.get('data', {})
                        
                        if minuts > 0:
                            tla = d_est.get('shotsOfOneSuccessful', 0)
                            tlt = d_est.get('shotsOfOneAttempted', 0)
                            pct_tl = round((tla / tlt * 100), 1) if tlt > 0 else 0.0
                            
                            est_partit_rival[nom] = {
                                'Dor': dorsal, 'Min': minuts, 'PTS': d_est.get('score', 0), 'Val': d_est.get('valoration', 0),
                                '+/-': jug.get('inOut', 0), 'TL (A/T)': f"{int(tla)}/{int(tlt)}", '% TL': pct_tl,
                                'T2': d_est.get('shotsOfTwoSuccessful', 0), 'T3': d_est.get('shotsOfThreeSuccessful', 0), 'F': d_est.get('faults', 0)
                            }
                            
                    if est_partit_actual_equip:
                        clau_partit = f"{nom_fase_actual} | {localia_icona} 🆚 {equip_rival_nom}"
                        historial_boxscores[clau_partit] = {
                            'nom_local': nom_local,
                            'nom_visitant': nom_visitant,
                            'score_local': score_local,
                            'score_visitant': score_visitant,
                            'color_local': color_local,
                            'color_visitant': color_visitant,
                            'df_nostre': formatar_dataframe_boxscore(est_partit_actual_equip),
                            'df_rival': formatar_dataframe_boxscore(est_partit_rival),
                            'es_local_nostre': es_local
                        }
                except: pass
                
            if est_fase_actual:
                taules_fases[f"Fase {index}"] = processar_estadistiques_a_dataframe(est_fase_actual)

        df_total = processar_estadistiques_a_dataframe(estadistiques_temporada)
        
        if df_total.empty:
            amb_progres.update(label="⚠️ Hem llegit tots els partits però no hem trobat minuts de les teves jugadores.", state="error", expanded=True)
            st.stop()
        else:
            amb_progres.update(label="✅ Anàlisi completat a màxima velocitat!", state="complete", expanded=False)

        st.session_state.df_total = df_total
        st.session_state.taules_fases = taules_fases
        st.session_state.historial = historial_partits_jugadora
        st.session_state.historial_boxscores = historial_boxscores
        st.session_state.equip_nom = equip_seleccionat
        st.session_state.dades_carregades = True


# ========================================================
# MOSTRAR RESULTATS I BOTONS DE DESCÀRREGA EN PDF
# ========================================================
if st.session_state.get("dades_carregades", False) and not st.session_state.df_total.empty:
    
    df_total_mem = st.session_state.df_total
    taules_fases_mem = st.session_state.taules_fases
    historial_mem = st.session_state.historial
    boxscores_mem = st.session_state.historial_boxscores
    equip_nom_mem = st.session_state.equip_nom

    st.divider()
    st.markdown(f"<h2>🏆 {equip_nom_mem} (Totals)</h2>", unsafe_allow_html=True)
    st.dataframe(estilitzar_taula(df_total_mem), use_container_width=True, hide_index=True)
    
    arx_total, ext_total, mime_total = generar_arxiu_pdf(df_total_mem, f"Totals - {equip_nom_mem}", es_partit=False)
    st.download_button("📥 Descarregar Taula Global (PDF)", data=arx_total, file_name=f"Totals_{equip_nom_mem}.{ext_total}", mime=mime_total)
    
    if taules_fases_mem:
        st.markdown("<h3>📊 DESGLOSSAMENT PER FASES</h3>", unsafe_allow_html=True)
        pestanyes = st.tabs(list(taules_fases_mem.keys()))
        
        for i, nom_fase in enumerate(taules_fases_mem.keys()):
            with pestanyes[i]:
                st.dataframe(estilitzar_taula(taules_fases_mem[nom_fase]), use_container_width=True, hide_index=True)
                arx_fase, ext_fase, mime_fase = generar_arxiu_pdf(taules_fases_mem[nom_fase], f"{nom_fase} - {equip_nom_mem}", es_partit=False)
                st.download_button(f"📥 Descarregar {nom_fase} (PDF)", data=arx_fase, file_name=f"{nom_fase}_{equip_nom_mem}.{ext_fase}", mime=mime_fase, key=f"btn_{nom_fase}")

    # ----------------------------------------------------
    # PANELL D'ANÀLISI PER PARTIT SENCER (BOX SCORE)
    # ----------------------------------------------------
    if boxscores_mem:
        st.divider()
        st.markdown("<h2>🏟️ ANÀLISI PER PARTIT (BOX SCORE)</h2>", unsafe_allow_html=True)
        
        llista_partits = sorted(list(boxscores_mem.keys()))
        partit_sel = st.selectbox("Selecciona quin partit vols analitzar:", options=llista_partits)
        
        if partit_sel:
            dades_partit = boxscores_mem[partit_sel]
            s_local = dades_partit['score_local']
            s_vis = dades_partit['score_visitant']
            
            color_puntuacio_l = "#4ade80" if s_local > s_vis else ("#f87171" if s_local < s_vis else "#fca311")
            color_puntuacio_v = "#4ade80" if s_vis > s_local else ("#f87171" if s_vis < s_local else "#fca311")
            
            html_marcador = f"<div class='marcador-caixa' style='display: flex; justify-content: center; align-items: center; gap: 20px; padding: 25px 10px; flex-wrap: wrap;'><div style='text-align: right; flex: 1; min-width: 150px;'><div style='color: #8d99ae; font-size: 0.9em; font-family: \"Bebas Neue\", sans-serif; letter-spacing: 1px;'>LOCAL</div><div style='color: {dades_partit['color_local']}; font-size: 1.8em; font-family: \"Bebas Neue\", sans-serif; letter-spacing: 1px; line-height: 1.1; text-shadow: 1px 1px 2px rgba(0,0,0,0.8);'>{dades_partit['nom_local']}</div></div><div style='font-size: 3.5em; font-weight: bold; font-family: \"Bebas Neue\", sans-serif; padding: 0 15px; text-shadow: 2px 2px 4px rgba(0,0,0,0.5); white-space: nowrap;'><span style='color: {color_puntuacio_l};'>{s_local}</span><span style='color: #ffffff; padding: 0 10px;'>-</span><span style='color: {color_puntuacio_v};'>{s_vis}</span></div><div style='text-align: left; flex: 1; min-width: 150px;'><div style='color: #8d99ae; font-size: 0.9em; font-family: \"Bebas Neue\", sans-serif; letter-spacing: 1px;'>VISITANT</div><div style='color: {dades_partit['color_visitant']}; font-size: 1.8em; font-family: \"Bebas Neue\", sans-serif; letter-spacing: 1px; line-height: 1.1; text-shadow: 1px 1px 2px rgba(0,0,0,0.8);'>{dades_partit['nom_visitant']}</div></div></div>"
            st.markdown(html_marcador, unsafe_allow_html=True)
            
            nom_rival_pestanya = dades_partit['nom_visitant'] if dades_partit['es_local_nostre'] else dades_partit['nom_local']
            tab_nostre, tab_rival = st.tabs([f"🏀 EL NOSTRE EQUIP ({equip_nom_mem})", f"🛡️ EL RIVAL ({nom_rival_pestanya})"])
            
            with tab_nostre:
                st.dataframe(estilitzar_taula(dades_partit['df_nostre'], es_partit=True), use_container_width=True, hide_index=True)
                arx_nostre, ext_nostre, mime_nostre = generar_arxiu_pdf(dades_partit['df_nostre'], f"BoxScore Equip - {partit_sel}", es_partit=True)
                st.download_button("📥 Descarregar Actuació Equip (PDF)", data=arx_nostre, file_name=f"BoxScore_Equip_{partit_sel[:10]}.{ext_nostre}", mime=mime_nostre, key="btn_nostre")
                
            with tab_rival:
                st.dataframe(estilitzar_taula(dades_partit['df_rival'], es_partit=True), use_container_width=True, hide_index=True)
                arx_rival, ext_rival, mime_rival = generar_arxiu_pdf(dades_partit['df_rival'], f"BoxScore Rival - {partit_sel}", es_partit=True)
                st.download_button("📥 Descarregar Actuació Rival (PDF)", data=arx_rival, file_name=f"BoxScore_Rival_{partit_sel[:10]}.{ext_rival}", mime=mime_rival, key="btn_rival")

    # ----------------------------------------------------
    # PANELL D'ANÀLISI INDIVIDUAL AMB GRÀFICS D'EVOLUCIÓ
    # ----------------------------------------------------
    if historial_mem:
        st.divider()
        st.markdown("<h2>👤 ANÀLISI INDIVIDUAL I GRÀFICS D'EVOLUCIÓ</h2>", unsafe_allow_html=True)
        
        dorsals_dict = {row['Jugadora']: row['Dor'] for index, row in df_total_mem.iterrows()}
        jugadores_ordenades = sorted(
            list(historial_mem.keys()), 
            key=lambda x: int(dorsals_dict.get(x, 999)) if str(dorsals_dict.get(x, '')).isdigit() else 999
        )
        
        col_sel1, col_sel2 = st.columns(2)
        with col_sel1:
            jugadora_sel = st.selectbox("Selecciona una Jugadora:", options=jugadores_ordenades)
        with col_sel2:
            opcions_fases_indiv = ["Totes les Fases"] + list(taules_fases_mem.keys())
            fase_sel = st.selectbox("Filtra per Fase:", options=opcions_fases_indiv)
            
        df_indiv = pd.DataFrame(historial_mem[jugadora_sel])
        
        if fase_sel != "Totes les Fases":
            df_indiv = df_indiv[df_indiv['Fase'] == fase_sel]
            
        if df_indiv.empty:
            st.info(f"La jugadora no ha jugat cap partit a la {fase_sel}.")
        else:
            st.dataframe(estilitzar_taula(df_indiv, es_partit=True), use_container_width=True, hide_index=True)
            
            arx_indiv, ext_indiv, mime_indiv = generar_arxiu_pdf(df_indiv, f"Analisi Individual: {jugadora_sel}", es_partit=True)
            st.download_button(f"📥 Descarregar PDF de {jugadora_sel}", data=arx_indiv, file_name=f"{jugadora_sel}_Temporada.{ext_indiv}", mime=mime_indiv)
            
            st.markdown(f"### 📈 Evolució de Punts i Valoració ({jugadora_sel})")
            
            df_plot = df_indiv.copy()
            df_plot['Jornada'] = [f"P{i+1}" for i in range(len(df_plot))]
            
            fig = px.line(
                df_plot, 
                x='Jornada', 
                y=['PTS', 'Val'], 
                markers=True,
                hover_data={"Rival": True},
                labels={'value': 'Quantitat', 'variable': 'Estadística'},
                color_discrete_map={'PTS': '#fca311', 'Val': '#4ade80'} 
            )
            
            fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)', 
                paper_bgcolor='rgba(0,0,0,0)', 
                font_color='#ffffff',
                xaxis=dict(showgrid=True, gridcolor='#333333'),
                yaxis=dict(showgrid=True, gridcolor='#333333')
            )
            
            st.plotly_chart(fig, use_container_width=True)
