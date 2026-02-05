import streamlit as st
import os
import glob
import re
import gc
import io
import requests
import pandas as pd
from datetime import datetime
from collections import Counter

# --- 1. UI CONFIGURATION ---
st.set_page_config(page_title="Coulter Recruiting", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #F5F5F7; 
        color: #1D1D1F;
    }
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    .header-container {
        background: linear-gradient(90deg, #002B5C 0%, #003B7E 100%);
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        margin-bottom: 40px;
        border-bottom: 5px solid #4CAF50;
    }
    .main-title { font-size: 3rem; font-weight: 800; color: #FFFFFF; margin: 0; letter-spacing: -1px; }
    .sub-title { font-size: 1.2rem; font-weight: 400; color: #A3C9F7; margin-top: 5px; text-transform: uppercase; letter-spacing: 2px; }

    .stTextInput > div > div > input {
        border-radius: 12px; border: 1px solid #D1D1D6; padding: 15px 20px; font-size: 18px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    }
    .stButton > button {
        background-color: #1D1D1F; color: white; border-radius: 12px; padding: 15px 30px; font-weight: 600; border: none; width: 100%;
    }
    .stButton > button:hover { transform: scale(1.02); background-color: #333; }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div class="header-container">
        <div class="main-title">COULTER RECRUITING</div>
        <div class="sub-title">Elite Football Search Engine</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# A. KEYWORDS FOR CONTEXT SCANNING
FOOTBALL_INDICATORS = [
    "football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", 
    "offensive", "defensive", "special teams", "recruiting", "fbs", "fcs",
    "interception", "tackle", "gridiron", "playoff", "super bowl", "pro bowl"
]

NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero", "dig", "kill", "block"],
    "Baseball": ["baseball", "inning", "homerun", "pitcher", "dugout", "mlb", "batting"],
    "Basketball": ["basketball", "nba", "dunk", "rebound", "three-pointer", "court"],
    "Soccer": ["soccer", "goal", "midfielder", "striker", "goalkeeper", "fifa"],
    "Softball": ["softball", "pitcher", "inning"],
    "Track": ["track", "sprint", "hurdle", "relay", "marathon"],
    "Swimming": ["swim", "dive", "freestyle", "breaststroke", "pool"],
    "Lacrosse": ["lacrosse", "stick", "goalie", "crease"]
}

GARBAGE_PHRASES = [
    "Official Athletics Website", "Official Website", "Composite", 
    "Javascript is required", "Skip To Main Content", "Official Football Roster",
    "View Full Profile", "Related Headlines", "Source:", "https://"
]

# STRICT JUNK NAME FILTER
BAD_NAMES = [
    "Football Roster", "Football Schedule", "Men's Basketball", "Women's Basketball", 
    "Composite Schedule", "Game Recap", "Box Score", "Statistic", "Menu", "Search",
    "Tickets", "Donate", "Camps", "Facilities", "Staff Directory", "2024", "2025", "2026"
]

# TITLE SCAVENGER LIST (Priority Order)
JOB_TITLES = [
    "Head Coach", "Defensive Coordinator", "Offensive Coordinator", "Special Teams Coordinator",
    "Recruiting Coordinator", "Director of Player Personnel", "Director of Football Operations",
    "General Manager", "Assistant Coach", "Associate Head Coach", "Run Game Coordinator", "Pass Game Coordinator",
    "Quarterbacks Coach", "Linebackers Coach", "Wide Receivers Coach", "Offensive Line Coach",
    "Defensive Line Coach", "Cornerbacks Coach", "Safeties Coach", "Tight Ends Coach", "Running Backs Coach",
    "Graduate Assistant", "Analyst", "Quality Control", "Director of Scouting"
]

# DOMAIN & ALIAS MAPPING
DOMAIN_MAP = {
    "thesundevils.com": "Arizona State", "rolltide.com": "Alabama", "auburntigers.com": "Auburn",
    "uclabruins.com": "UCLA", "usctrojans.com": "USC", "seminoles.com": "Florida State",
    "gatorssports.com": "Florida", "floridagators.com": "Florida", "georgiadogs.com": "Georgia",
    "lsusports.net": "LSU", "olemisssports.com": "Ole Miss", "hailstate.com": "Mississippi State",
    "mutigers.com": "Missouri", "gamecocksonline.com": "South Carolina", "utsports.com": "Tennessee",
    "12thman.com": "Texas A&M", "arkansasrazorbacks.com": "Arkansas", "ukathletics.com": "Kentucky",
    "vucommodores.com": "Vanderbilt", "ohiostatebuckeyes.com": "Ohio State", "mgoblue.com": "Michigan",
    "gopsusports.com": "Penn State", "uwbadgers.com": "Wisconsin", "huskers.com": "Nebraska",
    "hawkeyesports.com": "Iowa", "msuspartans.com": "Michigan State", "gophersports.com": "Minnesota",
    "fightingillini.com": "Illinois", "purduesports.com": "Purdue", "iuhoosiers.com": "Indiana",
    "scarletknights.com": "Rutgers", "umterps.com": "Maryland", "virginiasports.com": "Virginia",
    "hokieSports.com": "Virginia Tech", "theacc.com": "ACC", "clemsontigers.com": "Clemson",
    "gopack.com": "NC State", "bceagles.com": "Boston College", "cuse.com": "Syracuse",
    "godeacs.com": "Wake Forest", "ramblinwreck.com": "Georgia Tech", "pittsburghpanthers.com": "Pittsburgh",
    "gostanford.com": "Stanford", "calbears.com": "California", "goducks.com": "Oregon",
    "gohuskies.com": "Washington", "cubuffs.com": "Colorado", "utahutes.com": "Utah",
    "arizonawildcats.com": "Arizona", "texassports.com": "Texas", "soonersports.com": "Oklahoma",
    "gofrogs.com": "TCU", "baylorbears.com": "Baylor", "texastech.com": "Texas Tech",
    "kuathletics.com": "Kansas", "kstatesports.com": "Kansas State", "okstate.com": "Oklahoma State",
    "cyclones.com": "Iowa State", "wvusports.com": "West Virginia", "ucfknights.com": "UCF",
    "gobearcats.com": "Cincinnati", "uhcougars.com": "Houston", "byucougars.com": "BYU",
    "bamastatesports.com": "Alabama State", "famuathletics.com": "Florida A&M", "bcwildcats.com": "Bethune-Cookman"
}

SCHOOL_ALIASES = {
    "ASU": "Arizona State", "Arizona State University": "Arizona State", "Sun Devils": "Arizona State",
    "UCF": "Central Florida", "Central Florida": "UCF", "Knights": "Central Florida",
    "Ole Miss": "Mississippi", "Mississippi": "Ole Miss", "Rebels": "Mississippi",
    "SMU": "Southern Methodist", "Southern Methodist": "SMU", "Mustangs": "Southern Methodist",
    "USC": "Southern California", "Southern California": "USC", "Trojans": "Southern California",
    "LSU": "Louisiana State", "Louisiana State": "LSU", "Tigers": "Louisiana State",
    "TCU": "Texas Christian", "Texas Christian": "TCU", "Horned Frogs": "Texas Christian",
    "BYU": "Brigham Young", "Brigham Young": "BYU", "Cougars": "Brigham Young",
    "FSU": "Florida State", "Florida State": "FSU", "Seminoles": "Florida State",
    "Miami (FL)": "Miami", "Miami": "Miami (FL)", "Hurricanes": "Miami (FL)",
    "UNC": "North Carolina", "Tar Heels": "North Carolina",
    "UGA": "Georgia", "Bulldogs": "Georgia",
    "Bama": "Alabama", "Crimson Tide": "Alabama",
    "UCLA": "UCLA", "Bruins": "UCLA"
}

# --- 4. DATA PROCESSING FUNCTIONS ---

def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup():
    try:
        if not os.path.exists(MASTER_DB_FILE):
            r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=5)
            with open(MASTER_DB_FILE, 'wb') as f: f.write(r.content)
        
        try: df = pd.read_csv(MASTER_DB_FILE, encoding='utf-8')
        except: df = pd.read_csv(MASTER_DB_FILE, encoding='latin1')
        
        lookup, name_lookup = {}, {}
        cols = df.columns
        email_col = next((c for c in cols if 'Email' in c), None)
        twitter_col = next((c for c in cols if 'Twitter' in c), None)
        title_col = next((c for c in cols if 'Title' in c), None)
        
        for _, row in df.iterrows():
            s_raw = str(row.get('School', '')).strip()
            s_key = normalize_text(s_raw)
            n_key = normalize_text(f"{row.get('First name', '')}{row.get('Last name', '')}")
            
            if n_key:
                rec = {
                    'email': str(row.get(email_col, '')).strip() if email_col else "",
                    'twitter': str(row.get(twitter_col, '')).strip() if twitter_col else "",
                    'title': str(row.get(title_col, '')).strip() if title_col else "",
                    'school': s_raw 
                }
                lookup[(s_key, n_key)] = rec
                for alias, real_name in SCHOOL_ALIASES.items():
                    if s_raw == real_name:
                         lookup[(normalize_text(alias), n_key)] = rec
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
                
        return lookup, name_lookup
    except: return {}, {}

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

def detect_school_from_url(bio_text):
    match = re.search(r"SOURCE: https?://(www\.)?([a-zA-Z0-9.-]+)", str(bio_text))
    if match:
        domain = match.group(2).lower()
        if domain in DOMAIN_MAP: return DOMAIN_MAP[domain]
        for key, school in DOMAIN_MAP.items():
            if key in domain: return school
    return None

def detect_sport_context(bio):
    if pd.isna(bio): return "Uncertain"
    text = str(bio)
    analysis_text = text[200:].lower() if len(text) > 500 else text.lower()

    fb_score = sum(analysis_text.count(w) for w in FOOTBALL_INDICATORS)
    max_other_score = 0
    likely_other_sport = None
    
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        score = sum(analysis_text.count(w) for w in keywords)
        if score > max_other_score:
            max_other_score = score
            likely_other_sport = sport

    if fb_score >= max_other_score: return "Football"
    elif max_other_score > fb_score and max_other_score > 2: return likely_other_sport
    else: return "Football" if "football" in text[:300].lower() else "Uncertain"

def detect_player_by_context(bio):
    """
    Checks bio for player indicators (height, weight, class year) to prevent
    players from being mislabeled as staff.
    """
    text = str(bio).lower()[:600]
    
    # 1. Class Year Indicators
    if any(x in text for x in ["freshman", "sophomore", "junior", "senior", "redshirt", "class of 20"]):
        return True
    
    # 2. Physical Stats (e.g. 6-2, 200 lbs)
    if re.search(r"\d['’]-?\d+\"?\s+\d{2,3}\s?lbs", text):
        return True
        
    # 3. Position Abbreviations (QB, WR, LB, etc) followed by height/weight
    if re.search(r"\b(qb|wr|rb|te|ol|dl|lb|db|saf|cb|pk|p|ls)\b", text) and "lbs" in text:
        return True
        
    return False

def extract_title_from_text(bio):
    bio_intro = str(bio)[:500] 
    for title in JOB_TITLES:
        if re.search(r"\b" + re.escape(title) + r"\b", bio_intro, re.IGNORECASE):
            return title
    return "Staff"

def parse_header_smart(bio):
    extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
    
    url_school = detect_school_from_url(bio)
    if url_school: extracted['School'] = url_school

    clean_text = str(bio).replace('\r', '\n').replace('–', '-').replace('—', '-')
    lines = [L.strip() for L in clean_text.split('\n') if L.strip()]
    
    header = None
    for line in lines[:8]:
        if " - " in line and "http" not in line and "SOURCE" not in line:
            header = line
            break
            
    if header:
        parts = [p.strip() for p in header.split(' - ')]
        clean_parts = [p for p in parts if not any(g.lower() in p.lower() for g in GARBAGE_PHRASES)]
        
        if len(clean_parts) >= 3:
            extracted['Name'], extracted['Title'] = clean_parts[0], clean_parts[1]
            if not extracted['School']: extracted['School'] = clean_parts[2]
        elif len(clean_parts) == 2:
            extracted['Name'] = clean_parts[0]
            if not extracted['School']: extracted['School'] = clean_parts[1]
            extracted['Title'] = "Staff"
        elif len(clean_parts) == 1:
            extracted['Name'] = clean_parts[0]

        # Alias Correction
        raw_school = str(extracted['School']).strip()
        for alias, real_name in SCHOOL_ALIASES.items():
            if alias.lower() in raw_school.lower():
                extracted['School'] = real_name
                break
        
        # Player Check
        for val in [str(extracted['Title']), str(extracted['School'])]:
            if "202" in val or "203" in val:
                extracted['Role'] = "PLAYER"
                extracted['Title'] = "Roster Member"
                
    return extracted

def get_snippet(text, keyword):
    if pd.isna(text): return ""
    clean = str(text).replace('\n', ' ').replace('\r', ' ')
    m = re.search(re.escape(keyword), clean, re.IGNORECASE)
    if m:
        s, e = max(0, m.start()-60), min(len(clean), m.end()+60)
        return f"...{clean[s:e].strip()}..."
    return f"...{clean[:100]}..."

# --- 5. SEARCH LOGIC ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    keywords_str = st.text_input("", placeholder="🔍 Search Database (e.g. Tallahassee, Quarterback)...")
    run_search = st.button("RUN SEARCH", use_container_width=True)

if run_search or keywords_str:
    if not keywords_str:
        st.warning("⚠️ Please enter a keyword.")
    else:
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        chunk_files = glob.glob("chunk_*.csv")
        
        if not chunk_files:
            st.error("❌ Critical Error: No database files found.")
        else:
            try: chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
            except: pass
            
            results = []
            progress_bar = st.progress(0)
            
            for i, file in enumerate(chunk_files):
                progress_bar.progress((i + 1) / len(chunk_files))
                try:
                    df_iter = pd.read_csv(file, chunksize=1000, on_bad_lines='skip', dtype=str)
                    for chunk in df_iter:
                        chunk.fillna("", inplace=True)
                        col_map = {}
                        for c in chunk.columns:
                            c_clean = c.strip()
                            if c_clean.lower() in ['bio', 'full_bio', 'description', 'full bio']: col_map[c_clean] = 'Full_Bio'
                            elif c_clean.lower() == 'name': col_map[c_clean] = 'Name'
                            elif c_clean.lower() == 'school': col_map[c_clean] = 'School'
                            elif c_clean.lower() == 'title': col_map[c_clean] = 'Title'
                        chunk.rename(columns=col_map, inplace=True)
                        
                        if 'Full_Bio' not in chunk.columns: continue
                        
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            
                            def enrich_row(row):
                                # 1. Parse Header
                                meta = parse_header_smart(row['Full_Bio'])
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] or name
                                
                                # 2. JUNK FILTER (Fix for "Roster" names)
                                if any(bad.lower() in str(name).lower() for bad in BAD_NAMES): return None
                                if len(str(name)) > 40 or len(str(name)) < 3: return None

                                school = row.get('School', '')
                                if not school or school == "Unknown": school = meta['School'] or school
                                    
                                title = row.get('Title', '')
                                if not title or title == "Unknown": title = meta['Title'] or title
                                
                                role = meta['Role']

                                # 3. Player Detector (Fix for Alabama Players)
                                if role == "COACH/STAFF":
                                    if detect_player_by_context(row['Full_Bio']):
                                        role = "PLAYER"
                                        title = "Roster Member"

                                # 4. Sport Siphon
                                detected_sport = detect_sport_context(row['Full_Bio'])
                                if detected_sport != "Football" and detected_sport != "Uncertain":
                                    return None 

                                # 5. Title Scavenger
                                if title == "Staff" or title == "Unknown":
                                    scavenged_title = extract_title_from_text(row['Full_Bio'])
                                    if scavenged_title != "Staff": title = scavenged_title

                                # 6. Matchmaking
                                match = master_lookup.get((normalize_text(school), normalize_text(name)))
                                if not match:
                                    cands = name_lookup.get(normalize_text(name), [])
                                    if len(cands) == 1: 
                                        match = cands[0]
                                    elif len(cands) > 1:
                                        ns = normalize_text(school)
                                        for c in cands:
                                            if normalize_text(c['school']) in ns or ns in normalize_text(c['school']):
                                                match = c; break
                                
                                email = row.get('Email', '')
                                twitter = row.get('Twitter', '')
                                sport_val = "Football"
                                
                                if match:
                                    if not email: email = match['email']
                                    if not twitter: twitter = match['twitter']
                                    if title in ["Staff", "Unknown", "Football"]: title = match['title']
                                    school = match['school']
                                
                                flat_bio = str(row['Full_Bio']).replace('\n', ' ').replace('\r', ' ').strip()
                                flat_bio = re.sub(r'\s+', ' ', flat_bio)
                                
                                return pd.Series([role, name, title, school, sport_val, email, twitter, flat_bio])

                            enriched = found.apply(enrich_row, axis=1)
                            enriched.dropna(how='all', inplace=True)
                            
                            if not enriched.empty:
                                enriched.columns = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Full_Bio']
                                enriched['Context_Snippet'] = enriched['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                                results.append(enriched)
                    del chunk; gc.collect()
                except: continue

            progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                final_df = final_df[~final_df['Name'].str.contains("Skip To|Official|Javascript", case=False, na=False)]
                final_df.dropna(subset=['Name'], inplace=True)
                
                final_df['Role_Sort'] = final_df['Role'].apply(lambda x: 1 if "PLAYER" in str(x).upper() else 0)
                final_df.sort_values(by=['Role_Sort', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                
                cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_df = final_df[cols]
                
                st.success(f"🎉 Found {len(final_df)} matches.")
                st.dataframe(final_df, use_container_width=True)
                
                safe_kw = keywords[0].replace(' ', '_')
                date_str = datetime.now().strftime("%Y-%m-%d")
                file_name = f"{safe_kw}_{date_str}.xlsx"

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name="Results")
                    workbook = writer.book
                    worksheet = writer.sheets["Results"]
                    cell_format = workbook.add_format({'text_wrap': False, 'valign': 'top'})
                    worksheet.set_column('A:I', 25, cell_format)
                    
                st.download_button("💾 DOWNLOAD RESULTS (EXCEL)", buffer.getvalue(), file_name, "application/vnd.ms-excel", type="primary")
            else:
                st.warning("No matches found.")
