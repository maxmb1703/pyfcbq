import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import unicodedata
import os
import re
import concurrent.futures

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

# NOU: Funció Intel·ligent de Colors
def obtenir_color_equip(equip):
    color = equip.get('colorRgb') or equip.get('primaryColor')
    nom_net = treure_accents(equip.get('name', '')).upper()
    
    # Si la federació no ha posat color (buit, null) o ha deixat el blanc (#FFFFFF) per defecte
    if not color or color.upper() in ['#FFFFFF', '#FFF', 'WHITE', 'NULL', 'NONE', '']:
        # DEDUCTOR INTEL·LIGENT BASAT EN EL NOM DE L'EQUIP
        if 'BLAU' in nom_net: return '#3b82f6'
        if 'VERD' in nom_net: return '#22c55e'
        if 'NEGRE' in nom_net: return '#a1a1aa' # Posem un gris clar perquè el negre sobre el fons de la web no es veuria
        if 'VERMELL' in nom_net or 'ROIG' in nom_net: return '#ef4444'
        if 'GROC' in nom_net: return '#eab308'
        if 'TARONJA' in nom_net: return '#f97316'
        if 'ROSA' in nom_net: return '#ec4899'
        if 'LILA' in nom_net or 'MORAT' in nom_net: return '#a855f7'
        if 'GRANA' in nom_net: return '#9f1239'
        if 'BLANC' in nom_net: return '#f8fafc'
        
        return '#ffffff' # Si no troba cap paraula clau, el deixem blanc
        
    return color

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
    
    df['PPP'] = (df['PTS'] / df['PJ']).round(1).fillna(0)
    df['TL (A/T)'] = df['TLA'].astype(int).astype(str) + '/' + df['TLT'].astype(int).astype(str)
    df['% TL'] = df.apply(lambda row: round((row['TLA'] / row['TLT'] * 100), 1) if row['TLT'] > 0 else 0.0, axis=1)
    
    df['DOR_NUM'] = pd.to_numeric(df['Dor'], errors='coerce').fillna(999)
    df = df.sort_values(by='DOR_NUM').drop(columns=['DOR_NUM'])
    
    columnes_ordre = ['Dor', 'Jugadora', 'PJ', 'Min', 'PTS', 'PPP', 'Val', '+/-', 'TL (A/T)', '% TL', 'T2', 'T3', 'F']
    return df[columnes_ordre]

def formatar_dataframe_boxscore(diccionari_stats):
    if not diccionari_stats:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(diccionari_stats, orient='index').reset_index()
    df.rename(columns={'index': 'Jugadora'}, inplace=True)
    df['DOR_NUM'] = pd.to_numeric(df['Dor'], errors='coerce').fillna(999)
    df = df.sort_values(by='DOR_NUM').drop(columns=['DOR_NUM'])
    columnes_ordre = ['Dor', 'Jugadora', 'Min', 'PTS', 'Val', '+/-', 'TL (A/T)', '% TL', 'T2', 'T3', 'F']
    return df[columnes_ordre]

def estilitzar_taula(df, es_partit=False):
    format_dict = {}
    if '% TL' in df.columns:
        format_dict['% TL'] = "{:.1f}%"
    if 'PPP' in df.columns:
        format_dict['PPP'] = "{:.1f}"
        
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
# PREPARACIÓ DE DADES PER A LA INTERFÍCIE
# ==========================================
diccionari_clubs = carregar_diccionari_clubs()
llista_noms_clubs = list(diccionari_clubs.keys())

if not llista_noms_clubs:
    llista_noms_clubs = ["⚠️ Arxiu 'clubs_catalunya.txt' no trobat"]

index_defecte = 0
for i, nom in enumerate(llista_noms_clubs):
    if "PEDAGOGIUM" in nom.upper():
        index_defecte = i
        break

# ==========================================
# INTERFÍCIE WEB (FRONTEND)
# ==========================================
st.markdown('<div class="titol-principal">🏀 BÀSQUET STATS PRO</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitol">GESTOR D\'ESTADÍSTIQUES AVANÇAT FCBQ</div>', unsafe_allow_html=True)

with st.container():
    st.markdown("### ⚙️ Configuració de l'Equip")
    col1, col3, col4 = st.columns([1.5, 1, 1])

    with col1:
        club_seleccionat = st.selectbox("Selecciona el Club", options=llista_noms_clubs, index=index_defecte)
    with col3:
        categoria_input = st.selectbox("Categoria", [
            "PRE-MINI", "MINI", "PRE-INFANTIL", "INFANTIL", 
            "CADET", "JUNIOR", "SOTS-21", "SÈNIOR"
        ])
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
            "SOTS-21": {"inc": ["SOTS-21", "SOTS 21", "SUB-21", "SUB 21", "SOTS21"], "exc": []},
            "SÈNIOR": {"inc": ["SENIOR", "COPA", "PRIMERA", "SEGONA", "TERCERA", "QUARTA", "LLIGA", "NACIONAL", "EBA", "1A", "2A", "3A"], "exc": []}
        }
        dicc_generes = {"FEMENÍ": ["FEMENI", "FEM"], "MASCULÍ": ["MASCULI", "MASC"]}
        
        filtre_cat = dicc_categories.get(categoria_input, {"inc": [treure_accents(categoria_input.upper())], "exc": []})
        variants_cat = filtre_cat["inc"]
        exclusions_cat = filtre_cat["exc"]
        variants_gen = dicc_generes.get(genere_input, [treure_accents(genere_input.upper())])
        
        for eq in tots_equips:
            text_linia = eq['linia_cerca']
            te_categoria = any(variant in text_linia for variant in variants_cat)
            if te_categoria and any(exc in text_linia for exc in exclusions_cat): te_categoria = False
            te_genere = any(variant in text_linia for variant in variants_gen)
            
            if te_categoria and te_genere:
                equips_disponibles[eq['linia_mostrar']] = {'url': eq['url'], 'nom_curt': eq['nom_curt']}

    noms_filtrats = list(equips_disponibles.keys())
    paraula_clau_club = " ".join([p for p in club_seleccionat.replace("CLUB", "").replace("BASQUET", "").replace("ASSOCIACIO", "").replace("ESPORTIVA", "").replace("BOL", "").split() if len(p) > 2])

    if noms_filtrats:
        equip_seleccionat = st.selectbox("Equip trobat (Automàtic)", options=noms_filtrats)
    else:
        equip_seleccionat = st.selectbox("Equip trobat (Automàtic)", options=["Cap equip actiu trobat amb aquests filtres"])

st.write("") 

# ========================================================
# CÀRREGA DE DADES
# ========================================================
if st.button("📊 GENERAR INFORME ESTADÍSTIC", type="primary"):
    
    if equip_seleccionat == "Cap equip actiu trobat amb aquests filtres":
        st.error(f"❌ El {club_seleccionat} no té cap equip competint actiu que encaixi amb els filtres.")
        st.stop()
        
    dades_equip = equips_disponibles[equip_seleccionat]
    url_equip_final = dades_equip['url']
    nom_curt_api = dades_equip['nom_curt']  
    
    amb_progres = st.status(f"📡 Connectant directament amb l'equip...", expanded=True)
    
    with amb_progres:
        headers = {"User-Agent": "Mozilla/5.0"}
        res_fases = requests.get(url_equip_final, headers=headers)
        soup_fases = BeautifulSoup(res_fases.text, 'html.parser')
        urls_fases = []
        for a in soup_fases.find_all('a', href=True):
            if '/competicions/resultats/' in a['href']:
                url = "https://www.basquetcatala.cat" + a['href'] if a['href'].startswith('/') else a['href']
                if url not in urls_fases: urls_fases.append(url)
                
        if not urls_fases:
            st.error("L'equip està inscrit però no ha començat la lliga ni té partits.")
            st.stop()
            
        st.write(f"📥 Descarregant dades amb Motor de Càrrega Ràpida...")
        
        estadistiques_temporada = {}
        taules_fases = {}
        historial_partits_jugadora = {} 
        historial_boxscores = {} 
        
        for index, url_fase in enumerate(urls_fases, 1):
            nom_fase_actual = f"Fase {index}"
            ids_partits_fase = set()
            
            def buscar_ids_en_jornada(jornada):
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
                futurs = [executor.submit(buscar_ids_en_jornada, j) for j in range(1, 36)]
                for futur in concurrent.futures.as_completed(futurs):
                    per_jornada = futur.result()
                    for id_p in per_jornada:
                        ids_partits_fase.add(id_p)
                    
            est_fase_actual = {}
            st.write(f"S'han trobat {len(ids_partits_fase)} actes al Grup {index}. Analitzant...")
            
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
                    
                    # APLICACIÓ DEL NOU DEDUCTOR DE COLORS
                    color_local = obtenir_color_equip(equip_local)
                    color_visitant = obtenir_color_equip(equip_visitant)
                    
                    score_local = equip_local.get('score', sum([p.get('data',{}).get('score',0) for p in equip_local.get('players', [])]))
                    score_visitant = equip_visitant.get('score', sum([p.get('data',{}).get('score',0) for p in equip_visitant.get('players', [])]))

                    es_local = False
                    equip_nostre_dades = None
                    equip_rival_dades = None
                    equip_rival_nom = ""
                    
                    if treure_accents(nom_curt_api.upper()) in treure_accents(nom_local.upper()) or treure_accents(paraula_clau_club.upper()) in treure_accents(nom_local.upper()):
                        es_local = True
                        equip_nostre_dades = equip_local
                        equip_rival_dades = equip_visitant
                        equip_rival_nom = nom_visitant
                    elif treure_accents(nom_curt_api.upper()) in treure_accents(nom_visitant.upper()) or treure_accents(paraula_clau_club.upper()) in treure_accents(nom_visitant.upper()):
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
                                'Dor': dorsal,
                                'Min': minuts,
                                'PTS': d_est.get('score', 0),
                                'Val': d_est.get('valoration', 0),
                                '+/-': jug.get('inOut', 0),
                                'TL (A/T)': f"{int(tla)}/{int(tlt)}",
                                '% TL': pct_tl,
                                'T2': d_est.get('shotsOfTwoSuccessful', 0),
                                'T3': d_est.get('shotsOfThreeSuccessful', 0),
                                'F': d_est.get('faults', 0)
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
                                'Dor': dorsal,
                                'Min': minuts,
                                'PTS': d_est.get('score', 0),
                                'Val': d_est.get('valoration', 0),
                                '+/-': jug.get('inOut', 0),
                                'TL (A/T)': f"{int(tla)}/{int(tlt)}",
                                '% TL': pct_tl,
                                'T2': d_est.get('shotsOfTwoSuccessful', 0),
                                'T3': d_est.get('shotsOfThreeSuccessful', 0),
                                'F': d_est.get('faults', 0)
                            }
                            
                    if est_partit_actual_equip:
                        clau_partit = f"{nom_fase_actual} | {localia_icona} 🆚 {equip_rival_nom}"
                        df_nostre = formatar_dataframe_boxscore(est_partit_actual_equip)
                        df_rival = formatar_dataframe_boxscore(est_partit_rival)
                        
                        historial_boxscores[clau_partit] = {
                            'nom_local': nom_local,
                            'nom_visitant': nom_visitant,
                            'score_local': score_local,
                            'score_visitant': score_visitant,
                            'color_local': color_local,
                            'color_visitant': color_visitant,
                            'df_nostre': df_nostre,
                            'df_rival': df_rival,
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
            amb_progres.update(label="✅ Anàlisi completat amb èxit!", state="complete", expanded=False)

        st.session_state.df_total = df_total
        st.session_state.taules_fases = taules_fases
        st.session_state.historial = historial_partits_jugadora
        st.session_state.historial_boxscores = historial_boxscores
        st.session_state.equip_nom = equip_seleccionat
        st.session_state.dades_carregades = True


# ========================================================
# MOSTRAR RESULTATS 
# ========================================================
if st.session_state.get("dades_carregades", False) and not st.session_state.df_total.empty:
    
    df_total_mem = st.session_state.df_total
    taules_fases_mem = st.session_state.taules_fases
    historial_mem = st.session_state.historial
    boxscores_mem = st.session_state.historial_boxscores
    equip_nom_mem = st.session_state.equip_nom

    st.divider()
    st.markdown(f"<h2>🏆 {equip_nom_mem}</h2>", unsafe_allow_html=True)
    st.dataframe(estilitzar_taula(df_total_mem), use_container_width=True, hide_index=True)
    
    if taules_fases_mem:
        st.markdown("<h3>📊 DESGLOSSAMENT PER FASES</h3>", unsafe_allow_html=True)
        pestanyes = st.tabs(list(taules_fases_mem.keys()))
        
        for i, nom_fase in enumerate(taules_fases_mem.keys()):
            with pestanyes[i]:
                st.dataframe(estilitzar_taula(taules_fases_mem[nom_fase]), use_container_width=True, hide_index=True)

    # ----------------------------------------------------
    # PANELL D'ANÀLISI PER PARTIT SENCER (MARCADOR DE TELEVISIÓ)
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
            with tab_rival:
                st.dataframe(estilitzar_taula(dades_partit['df_rival'], es_partit=True), use_container_width=True, hide_index=True)

    # ----------------------------------------------------
    # PANELL D'ANÀLISI INDIVIDUAL (Jugadora per Jugadora)
    # ----------------------------------------------------
    if historial_mem:
        st.divider()
        st.markdown("<h2>👤 ANÀLISI INDIVIDUAL (TOTA LA TEMPORADA)</h2>", unsafe_allow_html=True)
        
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
