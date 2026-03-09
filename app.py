import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import unicodedata
import os

# Configuració de la pàgina Web
st.set_page_config(page_title="Scouting FCBQ", page_icon="🏀", layout="wide")

# ==========================================
# FUNCIONS DE BASE DE DADES I SCRAPING
# ==========================================
def treure_accents(text):
    if not text: return ""
    return ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')

def llegir_base_dades(nom_club_buscat):
    nom_club_net = treure_accents(nom_club_buscat.upper())
    arxiu = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clubs_catalunya.txt")
    
    if not os.path.exists(arxiu):
        return None, f"❌ ERROR: No s'ha trobat l'arxiu 'clubs_catalunya.txt'. Assegura't que està al mateix repositori que app.py."
        
    with open(arxiu, "r", encoding="utf-8") as f:
        for linia in f:
            if "|" in linia:
                parts = linia.split("|")
                nom_club_arxiu = parts[0].strip()
                url_club = parts[1].strip()
                
                if nom_club_net in treure_accents(nom_club_arxiu.upper()):
                    return url_club, None
    return None, f"❌ No s'ha trobat el club '{nom_club_buscat}' a la base de dades local."

def processar_estadistiques_a_dataframe(diccionari_stats):
    """Transforma el diccionari brut en una taula interactiva (DataFrame)"""
    if not diccionari_stats:
        return pd.DataFrame()
        
    df = pd.DataFrame.from_dict(diccionari_stats, orient='index').reset_index()
    df.rename(columns={'index': 'JUGADORA', 'dorsal': 'DOR', 'pj': 'PJ', 'min': 'MIN', 'pts': 'PTS', 
                       't2': 'T2', 't3': 'T3', 'tlt': 'TLT', 'tla': 'TLA', 'f': 'F', 'val': 'VAL', 'mas_menos': '+/-'}, inplace=True)
    
    # Càlcul de mitjanes
    df['M/P'] = (df['MIN'] / df['PJ']).round(1).fillna(0)
    df['P/P'] = (df['PTS'] / df['PJ']).round(1).fillna(0)
    
    # Ordenar i netejar
    df['DOR_NUM'] = pd.to_numeric(df['DOR'], errors='coerce').fillna(999)
    df = df.sort_values(by='DOR_NUM').drop(columns=['DOR_NUM'])
    
    # Reordenar columnes perquè quedi professional
    columnes_ordre = ['DOR', 'JUGADORA', 'PJ', 'MIN', 'M/P', 'PTS', 'P/P', 'T2', 'T3', 'TLT', 'TLA', 'F', 'VAL', '+/-']
    return df[columnes_ordre]

# ==========================================
# INTERFÍCIE WEB (FRONTEND)
# ==========================================
st.title("🏀 Eina de Scouting - FCBQ")
st.markdown("Busca qualsevol equip de Catalunya i n'extraurem les estadístiques oficials a l'instant.")

# Creem un panell de control amb columnes
col1, col2, col3, col4 = st.columns(4)

with col1:
    club_input = st.text_input("Paraula clau del Club", value="PEDAGOGIUM")
with col2:
    equip_input = st.text_input("Nom exacte de l'Equip", value="CB PEDAGOGIUM")
with col3:
    # AQUI HEM AFEGIT LES NOVES CATEGORIES!
    categoria_input = st.selectbox("Categoria", [
        "PRE-MINI", 
        "MINI", 
        "PRE-INFANTIL", 
        "INFANTIL", 
        "CADET", 
        "JUNIOR", 
        "SOTS-21", 
        "SÈNIOR"
    ])
with col4:
    genere_input = st.selectbox("Gènere", ["FEMENÍ", "MASCULÍ"])

# Botó gegant per iniciar la màgia
if st.button("📊 Analitzar Equip", type="primary"):
    
    amb_progres = st.status("Iniciant el radar i connectant amb la base de dades...", expanded=True)
    
    with amb_progres:
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # 1. Buscar Club
        st.write("🏢 Buscant el club a la base de dades local...")
        url_club, error = llegir_base_dades(club_input)
        if error:
            st.error(error)
            st.stop()
            
        st.success(f"Club trobat! {url_club}")
        
        # 2. Buscar Equip
        st.write(f"👕 Buscant l'equip {equip_input}...")
        try:
            res_equip = requests.get(url_club, headers=headers, timeout=10)
            soup_equip = BeautifulSoup(res_equip.text, 'html.parser')
        except:
            st.error("Error de connexió a la FCBQ.")
            st.stop()
            
        url_equip = None
        for a in soup_equip.find_all('a', href=True):
            if '/equip/' in a['href']:
                text_linia = treure_accents(a.parent.text.upper())
                text_enllac = treure_accents(a.text.upper())
                if (treure_accents(categoria_input.upper()) in text_linia and 
                    treure_accents(genere_input.upper()) in text_linia and 
                    treure_accents(equip_input.upper()) in text_enllac):
                    url_equip = "https://www.basquetcatala.cat" + a['href'] if a['href'].startswith('/') else a['href']
                    break
                    
        if not url_equip:
            st.error("No s'ha trobat l'equip a la fitxa del club. Revisa el nom exacte o la categoria.")
            st.stop()
            
        # 3. Buscar Fases
        st.write("🏆 Extraient les competicions...")
        res_fases = requests.get(url_equip, headers=headers)
        soup_fases = BeautifulSoup(res_fases.text, 'html.parser')
        urls_fases = []
        for a in soup_fases.find_all('a', href=True):
            if '/competicions/resultats/' in a['href']:
                url = "https://www.basquetcatala.cat" + a['href'] if a['href'].startswith('/') else a['href']
                if url not in urls_fases: urls_fases.append(url)
                
        if not urls_fases:
            st.error("No hi ha calendaris per aquest equip.")
            st.stop()
            
        # 4. Descarregar Actes
        st.write(f"📥 Descarregant estadístiques de {len(urls_fases)} fases. Això trigarà uns segons...")
        
        estadistiques_temporada = {}
        taules_fases = {}
        
        for index, url_fase in enumerate(urls_fases, 1):
            ids_partits_fase = set()
            buides = 0
            for jornada in range(1, 36):
                res_html = requests.get(f"{url_fase}/{jornada}", headers=headers)
                soup = BeautifulSoup(res_html.text, 'html.parser')
                partits_ok = 0
                for a in soup.find_all('a', href=True):
                    if '/estadistiques/' in a['href']:
                        ids_partits_fase.add(a['href'].split('/')[-1])
                        partits_ok += 1
                if partits_ok == 0: buides += 1
                else: buides = 0
                if buides >= 3: break 
                    
            est_fase_actual = {}
            for id_partit in ids_partits_fase:
                try:
                    res_api = requests.get(f"https://msstats.optimalwayconsulting.com/v1/fcbq/getJsonWithMatchStats/{id_partit}?currentSeason=true", headers=headers)
                    if res_api.status_code != 200: continue
                    equips = res_api.json().get('teams', [])
                    equip_trobat = None
                    for equip in equips:
                        if treure_accents(equip_input.upper()) in treure_accents(equip.get('name', '').upper()):
                            equip_trobat = equip
                            break
                    if not equip_trobat: continue
                    
                    for jug in equip_trobat.get('players', []):
                        nom = jug.get('name', 'Desc')
                        dorsal = jug.get('dorsal', '-')
                        for d_stats in [est_fase_actual, estadistiques_temporada]:
                            if nom not in d_stats: d_stats[nom] = {'dorsal': dorsal, 'pj': 0, 'min': 0, 'pts': 0, 't2': 0, 't3': 0, 'tlt': 0, 'tla': 0, 'f': 0, 'val': 0, 'mas_menos': 0}
                        minuts = jug.get('timePlayed', 0)
                        if minuts > 0:
                            est_fase_actual[nom]['pj'] += 1
                            estadistiques_temporada[nom]['pj'] += 1
                        d_est = jug.get('data', {})
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
                except: pass
                time.sleep(0.1)
                
            if est_fase_actual:
                taules_fases[f"Fase {index}"] = processar_estadistiques_a_dataframe(est_fase_actual)

        df_total = processar_estadistiques_a_dataframe(estadistiques_temporada)
        amb_progres.update(label="✅ Anàlisi completat amb èxit!", state="complete", expanded=False)

    # ==========================================
    # PRESENTACIÓ DE DADES VISUALS
    # ==========================================
    if not df_total.empty:
        st.divider()
        st.subheader("🏆 RESUM ACUMULAT DE TOTA LA TEMPORADA")
        
        st.dataframe(df_total, use_container_width=True, hide_index=True)
        
        if taules_fases:
            st.write("### 📊 Desglossament per Fases")
            pestanyes = st.tabs(list(taules_fases.keys()))
            
            for i, nom_fase in enumerate(taules_fases.keys()):
                with pestanyes[i]:
                    st.dataframe(taules_fases[nom_fase], use_container_width=True, hide_index=True)
