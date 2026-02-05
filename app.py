import streamlit as st
import os
import glob
import re
import gc
import io
import requests
import pandas as pd
from datetime import datetime

# --- 1. APPLE ELITE UI CONFIGURATION ---
st.set_page_config(page_title="Coulter Recruiting", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    /* Global Apple Font & Light Gray Background */
    html, body, [class*="css"] {
        font-family: -apple-system, system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background-color: #F2F2F7; /* Apple System Gray 6 */
        color: #1D1D1F;
    }
    
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    /* HEADER: High-End Gradient */
    .header-container {
        background: linear-gradient(135deg, #000000 0%, #333333 100%);
        padding: 50px 20px;
        border-radius: 24px;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        margin-bottom: 40px;
        color: white;
    }
    .main-title { 
        font-size: 3.2rem; 
        font-weight: 700; 
        color: #FFFFFF; 
        margin: 0; 
        letter-spacing: -1.5px;
    }
    .sub-title { 
        font-size: 1.1rem; 
        font-weight: 500; 
        color: #8E8E93; 
        margin-top: 8px; 
        text-transform: uppercase; 
        letter-spacing: 4px; 
    }

    /* SEARCH BAR: Oval & Clean */
    .stTextInput > div > div > input {
        border-radius: 20px; 
        border: 1px solid #D1D1D6; 
        padding: 18px 25px; 
        font-size: 17px; 
        color: #1D1D1F;
        background-color: #FFFFFF;
        box-shadow: 0 2px 10px rgba(0,0,0,0.02);
        transition: all 0.2s ease;
    }
    .stTextInput > div > div > input:focus {
        border-color: #007AFF;
        box-shadow: 0 0 0 4px rgba(0,122,255,0.1);
    }

    /* BUTTON: The Apple "Oval" */
    .stButton > button {
        background: #000000;
        color: white; 
        border-radius: 30px; /* Fully Oval */
        padding: 12px 40px; 
        font-weight: 600; 
        font-size: 16px;
        border: none; 
        width: auto;
        display: block;
        margin: 0 auto;
        transition: all 0.2s ease;
    }
    .stButton > button:hover {
        background: #333333;
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(0,0,0,0.15);
    }
    .stButton > button:active {
        transform: translateY(0);
    }
    
    /* TABLE STYLING */
    .stDataFrame { 
        background-color: white;
        border-radius: 20px;
        padding: 10px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.05);
    }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div class="header-container">
        <div class="main-title">🏈 COULTER RECRUITING</div>
        <div class="sub-title">Football Search Engine</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# KEYWORDS
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

POISON_PILLS_TEXT = ["Women's Flag", "Flag Football"]

POISON_PILLS_HEADER = [
    "Flag", "Volleyball", "Baseball", "Softball", "Soccer", "Tennis", "Golf", 
    "Swimming", "Lacrosse", "Hockey", "Wrestling", "Gymnastics", "Basketball", 
    "Track & Field", "Crew", "Rowing", "Sailing", "Cheerleading", "Fencing"
]

BAD_NAMES = ["Football Roster", "Football Schedule", "Composite Schedule", "Game Recap", "Menu", "Search", "Tickets"]

JOB_TITLES = [
    "Head Coach", "Defensive Coordinator", "Offensive Coordinator", "Special Teams Coordinator",
    "Recruiting Coordinator", "Director of Player Personnel", "Director of Football Operations",
    "Assistant Coach", "Graduate Assistant", "Analyst", "Quality Control"
]

SCHOOL_ALIASES = {
    "ASU": "Arizona State", "Sun Devils": "Arizona State",
    "UCF": "Central Florida", "Knights": "Central Florida",
    "Ole Miss": "Mississippi", "Rebels": "Mississippi",
    "FSU": "Florida State", "Seminoles": "Florida State",
    "Miami": "Miami (FL)", "Hurricanes": "Miami (FL)"
}

# --- 3. HELPER FUNCTIONS ---
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
        for _, row in df.iterrows():
            s_raw = str(row.get('School', '')).strip()
            s_key, n_key = normalize_text(s_raw), normalize_text(f"{row.get('First name', '')}{row.get('Last name', '')}")
            if n_key:
                rec = {'email': str(row.get('Email address', '')).strip(), 'twitter': str(row.get('Twitter', '')).strip(), 'title': str(row.get('Title', '')).strip(), 'school': s_raw}
                lookup[(s_key, n_key)] = rec
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
        return lookup, name_lookup
    except: return {}, {}

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

def detect_sport_context(bio):
    if pd.isna(bio): return "Uncertain"
    text = str(bio)
    
    # Ignore personal favorites (Fix for Row 171/174 Soccer players who like the Falcons)
    bio_clean = re.sub(r"Favorite sports team.*", "", text, flags=re.IGNORECASE)
    bio_clean = re.sub(r"Hobbies include.*", "", bio_clean, flags=re.IGNORECASE)
    
    # 1. Clean Menu Junk
    clean_text = re.sub(r"Choose a Player.*", "", bio_clean, flags=re.IGNORECASE)
    
    # 2. Poison Pill
    intro_text = clean_text[:1000].lower()
    for poison in POISON_PILLS_TEXT:
        if poison.lower() in intro_text: return None 

    # 3. Score
    analysis_text = clean_text[500:].lower() if len(clean_text) > 800 else clean_text.lower()
    fb_score = sum(analysis_text.count(w) for w in FOOTBALL_INDICATORS)
    max_other_score = 0
    likely_other_sport = None
    
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        score = sum(analysis_text.count(w) for w in keywords)
        if score > max_other_score:
            max_other_score = score
            likely_other_sport = sport

    # 4. Weight Check
    weight_match = re.search(r"Weight\s*(\d{2,3})", text, re.IGNORECASE)
    if weight_match and int(weight_match.group(1)) < 160 and fb_score < 2: return None 

    if fb_score > 0: return "Football"
    if max_other_score > 2: return likely_other_sport
    return "Football" if "football" in text[:300].lower() else "Uncertain"

def detect_player_by_context(bio, title):
    text = str(bio).lower()[:2000]
    if any(x in str(title).lower() for x in ["roster", "football", "athlete", "player"]): return True
    if any(x in text for x in ["freshman", "sophomore", "junior", "senior", "redshirt", "son of", "daughter of"]): return True
    if re.search(r"\d['’]-?\d+\"?\s+\d{2,3}\s?lbs", text): return True
    return False

def extract_title_from_text(bio):
    text = str(bio)[:1000]
    for title in JOB_TITLES:
        if re.search(r"\b" + re.escape(title) + r"\b", text, re.IGNORECASE): return title
    return "Staff"

def parse_header_smart(bio):
    extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
    clean_text = str(bio).replace('\r', '\n').replace('–', '-').replace('—', '-')
    lines = [L.strip() for L in clean_text.split('\n') if L.strip()]
    header = None
    for line in lines[:8]:
        if " - " in line and "http" not in line and "SOURCE" not in line:
            header = line; break
            
    if header:
        parts = [p.strip() for p in header.split(' - ')]
        clean_parts = [p for p in parts if not any(g.lower() in p.lower() for g in GARBAGE_PHRASES)]
        if len(clean_parts) >= 3: extracted['Name'], extracted['Title'] = clean_parts[0], clean_parts[1]; extracted['School'] = clean_parts[2]
        elif len(clean_parts) == 2: extracted['Name'] = clean_parts[0]; extracted['School'] = clean_parts[1]; extracted['Title'] = "Staff"
        elif len(clean_parts) == 1: extracted['Name'] = clean_parts[0]

        raw_school = str(extracted['School']).strip()
        for alias, real_name in SCHOOL_ALIASES.items():
            if alias.lower() in raw_school.lower(): extracted['School'] = real_name; break
        for val in [str(extracted['Title']), str(extracted['School'])]:
            if "202" in val or "203" in val: extracted['Role'] = "PLAYER"; extracted['Title'] = "Roster Member"
    return extracted

def get_snippet(text, keyword):
    if pd.isna(text): return ""
    clean = str(text).replace('\n', ' ').replace('\r', ' ')
    m = re.search(re.escape(keyword), clean, re.IGNORECASE)
    if m: s, e = max(0, m.start()-60), min(len(clean), m.end()+60); return f"...{clean[s:e].strip()}..."
    return f"...{clean[:100]}..."

# --- 4. SESSION STATE ---
if 'search_results' not in st.session_state: st.session_state.search_results = None
if 'search_filename' not in st.session_state: st.session_state.search_filename = None

# --- 5. SEARCH INTERFACE ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.form(key='search_form'):
        keywords_str = st.text_input("", placeholder="🔍 Search Database...")
        submit_button = st.form_submit_button(label='RUN SEARCH')

if submit_button:
    if not keywords_str: st.warning("⚠️ Please enter a keyword.")
    else:
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        chunk_files = glob.glob("chunk_*.csv")
        if not chunk_files: st.error("❌ Critical Error: No database files found.")
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
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            def enrich_row(row):
                                meta = parse_header_smart(row['Full_Bio'])
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] or name
                                if any(bad.lower() in str(name).lower() for bad in BAD_NAMES): return None
                                
                                title, school = meta['Title'] or "Staff", meta['School'] or "Unknown"
                                header_check = (str(title) + " " + str(school)).lower()
                                for poison in POISON_PILLS_HEADER:
                                    if poison.lower() in header_check: return None

                                detected_sport = detect_sport_context(row['Full_Bio'])
                                if detected_sport != "Football" and detected_sport != "Uncertain": return None 

                                role = meta['Role']
                                if role == "COACH/STAFF" and detect_player_by_context(row['Full_Bio'], title):
                                    role = "PLAYER"; title = "Roster Member"

                                if title in ["Staff", "Unknown"]:
                                    scavenged = extract_title_from_text(row['Full_Bio'])
                                    if scavenged != "Staff": title = scavenged

                                match = master_lookup.get((normalize_text(school), normalize_text(name)))
                                if not match:
                                    cands = name_lookup.get(normalize_text(name), [])
                                    if len(cands) == 1: match = cands[0]
                                
                                email, twitter, sport_val = "", "", "Football"
                                if match:
                                    email, twitter, title, school = match['email'], match['twitter'], match['title'], match['school']
                                
                                return pd.Series([role, name, title, school, sport_val, email, twitter, row['Full_Bio']])

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
                final_df = pd.concat(results).drop_duplicates(subset=['Name', 'School'])
                final_df['Role_Sort'] = final_df['Role'].apply(lambda x: 1 if "PLAYER" in str(x).upper() else 0)
                final_df.sort_values(by=['Role_Sort', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                st.session_state.search_results = final_df[cols]
                st.session_state.search_filename = f"{keywords[0].replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
            else:
                st.session_state.search_results = None; st.warning("No matches found.")

# --- 6. DISPLAY ---
if st.session_state.search_results is not None:
    st.success(f"🎉 Found {len(st.session_state.search_results)} matches.")
    st.dataframe(st.session_state.search_results, use_container_width=True)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        st.session_state.search_results.to_excel(writer, index=False, sheet_name="Results")
        cell_format = writer.book.add_format({'text_wrap': False, 'valign': 'top'})
        writer.sheets["Results"].set_column('A:I', 25, cell_format)
    st.download_button("💾 DOWNLOAD RESULTS (EXCEL)", buffer.getvalue(), st.session_state.search_filename, "application/vnd.ms-excel", type="primary")
