import streamlit as st
import os
import glob
import re
import gc
import io
import requests
import pandas as pd
from datetime import datetime

# --- 1. CONFIGURATION & STYLES ---
st.set_page_config(page_title="Coulter Recruiting", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    html, body, [class*="css"] {
        font-family: -apple-system, system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background-color: #F2F2F7;
        color: #1D1D1F;
    }
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}
    
    .header-container {
        background: linear-gradient(135deg, #000000 0%, #333333 100%);
        padding: 50px 20px;
        border-radius: 24px;
        text-align: center;
        box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        margin-bottom: 40px;
        color: white;
    }
    .main-title { font-size: 3.2rem; font-weight: 700; color: #FFFFFF; margin: 0; letter-spacing: -1.5px; }
    .sub-title { font-size: 1.1rem; font-weight: 500; color: #8E8E93; margin-top: 8px; text-transform: uppercase; letter-spacing: 4px; }
    .instruction-text { text-align: center; color: #555; font-size: 1.1em; margin-bottom: 20px; }
    .status-box { text-align: center; font-weight: bold; padding: 10px; margin-bottom: 20px; border-radius: 10px; }
    .status-success { background-color: #d4edda; color: #155724; }
    .status-fail { background-color: #f8d7da; color: #721c24; }
    
    /* TABLE */
    .stDataFrame { background-color: white; border-radius: 20px; padding: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div class="header-container">
        <div class="main-title">🏈 COULTER RECRUITING</div>
        <div class="sub-title">Football Search Engine</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. CONSTANTS & FILES ---
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

FOOTBALL_INDICATORS = ["football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", "recruiting", "fbs", "fcs", "interception", "tackle", "gridiron"]
NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero"], "Baseball": ["baseball", "inning", "homerun", "pitcher"],
    "Basketball": ["basketball", "nba", "dunk", "rebound"], "Soccer": ["soccer", "goal", "striker", "fifa"],
    "Softball": ["softball"], "Track": ["track", "sprint"], "Swimming": ["swim", "dive"], "Lacrosse": ["lacrosse"]
}
POISON_PILLS_TEXT = ["Women's Flag", "Flag Football"]
BAD_NAMES = ["Football Roster", "Football Schedule", "Composite Schedule", "Game Recap", "Menu", "Search", "Tickets"]
SCHOOL_ALIASES = {"ASU": "Arizona State", "UCF": "Central Florida", "Ole Miss": "Mississippi", "FSU": "Florida State", "Miami": "Miami (FL)", "UConn": "Connecticut"}

# --- 3. HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst', 'tech', 'a&m']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup():
    """Load coach database safely."""
    df = None
    source = "None"
    
    # 1. Try Google Sheet (Best source)
    try:
        r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=3)
        if r.ok:
            df = pd.read_csv(io.BytesIO(r.content), encoding='utf-8')
            source = "Google Sheet"
    except: pass
    
    # 2. Try Local File (Fallback)
    if df is None or df.empty:
        possible_files = glob.glob("*master*.csv") + glob.glob("*MASTER*.csv")
        if possible_files:
            try: 
                df = pd.read_csv(possible_files[0], encoding='utf-8')
                source = f"Local File ({possible_files[0]})"
            except: 
                try: df = pd.read_csv(possible_files[0], encoding='latin1')
                except: pass

    if df is None or df.empty:
        return {}, {}, {}, "Failed"

    # --- AGGRESSIVE COLUMN FINDER ---
    cols_lower = {c.lower().strip(): c for c in df.columns}
    
    def get_col_name(*candidates):
        for c in candidates:
            if c.lower() in cols_lower: return cols_lower[c.lower()]
        for c in candidates:
            for actual in cols_lower:
                if c.lower() in actual: return cols_lower[actual]
        return None

    c_school = get_col_name('school', 'institution', 'university')
    c_first = get_col_name('first name', 'first')
    c_last = get_col_name('last name', 'last')
    c_email = get_col_name('email', 'e-mail', 'mail')
    c_twitter = get_col_name("individual's twitter", "twitter", "x.com", "social")
    c_title = get_col_name('title', 'position', 'role')

    lookup, name_lookup, lastname_lookup = {}, {}, {}

    for _, row in df.iterrows():
        school = str(row[c_school]).strip() if c_school and pd.notna(row[c_school]) else ""
        last = str(row[c_last]).strip() if c_last and pd.notna(row[c_last]) else ""
        first = str(row[c_first]).strip() if c_first and pd.notna(row[c_first]) else ""
        
        if school and (first or last):
            full_name = f"{first} {last}".strip()
            email = str(row[c_email]).strip() if c_email and pd.notna(row[c_email]) else ""
            twitter = str(row[c_twitter]).strip() if c_twitter and pd.notna(row[c_twitter]) else ""
            title = str(row[c_title]).strip() if c_title and pd.notna(row[c_title]) else ""
            
            rec = {'email': email, 'twitter': twitter, 'title': title, 'school': school, 'name': full_name}
            
            s_key = normalize_text(school)
            n_key = normalize_text(full_name)
            l_key = normalize_text(last)
            
            # Exact Match Key
            lookup[(s_key, n_key)] = rec
            
            # Name Only Key (Fallback)
            if n_key not in name_lookup: name_lookup[n_key] = []
            name_lookup[n_key].append(rec)
            
            # Last Name + School Key (Deep Fallback for "Mike" vs "Michael")
            if (s_key, l_key) not in lastname_lookup: lastname_lookup[(s_key, l_key)] = []
            lastname_lookup[(s_key, l_key)].append(rec)
            
    return lookup, name_lookup, lastname_lookup, source

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup, lastname_lookup, db_source = st.session_state["master_data"]

def detect_sport(bio):
    text = str(bio).lower()
    if any(p.lower() in text[:1000] for p in POISON_PILLS_TEXT): return None
    fb_score = sum(text.count(w) for w in FOOTBALL_INDICATORS)
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        if sum(text.count(w) for w in keywords) > fb_score + 1: return None
    return "Football"

def parse_header(bio):
    lines = [L.strip() for L in str(bio).split('\n') if L.strip()][:8]
    header = next((L for L in lines if " - " in L and "http" not in L), None)
    extracted = {'Name': None, 'Title': "Staff", 'School': "Unknown", 'Role': 'COACH/STAFF', 'Last': ''}
    if header:
        parts = header.split(' - ')
        if len(parts) >= 2:
            extracted['Name'] = parts[0].strip()
            extracted['Last'] = parts[0].strip().split(' ')[-1] # Guess last name
            extracted['School'] = parts[-1].strip()
            if len(parts) > 2: extracted['Title'] = parts[1].strip()
    for alias, real in SCHOOL_ALIASES.items():
        if alias.lower() in extracted['School'].lower(): extracted['School'] = real
    if "202" in extracted['Title'] or "Roster" in extracted['Title']:
        extracted['Role'] = "PLAYER"; extracted['Title'] = "Roster Member"
    return extracted

def get_snippet(text, keyword):
    clean_text = str(text).replace(chr(10), ' ').replace(chr(13), ' ')
    m = re.search(re.escape(keyword), clean_text, re.IGNORECASE)
    if m: 
        s, e = max(0, m.start()-50), min(len(clean_text), m.end()+50)
        return f"...{clean_text[s:e]}..."
    return clean_text[:100] + "..."

# --- 4. SEARCH LOGIC ---
st.markdown('<p class="instruction-text">Type in keywords to search college football webpage bios.<br>Put a comma between keywords for multiple searches (e.g., "Linebacker, Recruiting").</p>', unsafe_allow_html=True)

# DIAGNOSTIC BOX
if db_source == "Failed":
    st.markdown(f'<div class="status-box status-fail">❌ Master Database Not Found. Contact info will be empty.</div>', unsafe_allow_html=True)
else:
    count = len(master_lookup)
    st.markdown(f'<div class="status-box status-success">✅ Master Database Active ({count} coaches loaded from {db_source})</div>', unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.form(key='search_form'):
        keywords_str = st.text_input("", placeholder="🔍 Enter keywords...")
        submit_button = st.form_submit_button(label='Search')

if 'search_results' not in st.session_state:
    st.session_state['search_results'] = pd.DataFrame()
if 'last_keywords' not in st.session_state:
    st.session_state['last_keywords'] = ""

if submit_button and keywords_str:
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    pattern = '|'.join([re.escape(k) for k in keywords])
    st.session_state['last_keywords'] = keywords_str
    
    chunk_files = glob.glob("chunk_*.csv")
    chunk_files.sort()
    
    if not chunk_files:
        st.error("❌ No database files found on server.")
    else:
        results_found = []
        progress_bar = st.progress(0)
        
        for i, file in enumerate(chunk_files):
            try:
                df_chunk = pd.read_csv(file, usecols=['Full_Bio'], dtype=str, on_bad_lines='skip').fillna("")
                mask = df_chunk['Full_Bio'].str.contains(pattern, case=False, na=False, regex=True)
                
                if mask.any():
                    matches = df_chunk[mask].copy()
                    
                    for idx, row in matches.iterrows():
                        meta = parse_header(row['Full_Bio'])
                        name = meta['Name'] or "Unknown"
                        
                        if any(b.lower() in str(name).lower() for b in BAD_NAMES): continue
                        if detect_sport(row['Full_Bio']) != "Football": continue
                        
                        s_key = normalize_text(meta['School'])
                        n_key = normalize_text(name)
                        l_key = normalize_text(meta['Last'])
                        
                        # MATCHING LOGIC (Cascading Fallbacks)
                        match = {}
                        # 1. Exact Match (School + Full Name)
                        if (s_key, n_key) in master_lookup:
                            match = master_lookup[(s_key, n_key)]
                        # 2. Last Name Match (School + Last Name) - fixes "Mike" vs "Michael"
                        elif (s_key, l_key) in lastname_lookup:
                            match = lastname_lookup[(s_key, l_key)][0]
                        # 3. Name Only (Full Name) - fixes School mismatches
                        elif n_key in name_lookup:
                            match = name_lookup[n_key][0]

                        results_found.append({
                            'Role': meta['Role'],
                            'Name': name,
                            'Title': match.get('title') or meta['Title'],
                            'School': match.get('school') or meta['School'],
                            'Email': match.get('email', ''),
                            'Twitter': match.get('twitter', ''),
                            'Context': get_snippet(row['Full_Bio'], keywords[0]),
                            'Full_Bio': row['Full_Bio']
                        })
                
                del df_chunk
                gc.collect()
            except Exception: continue
            progress_bar.progress((i + 1) / len(chunk_files))

        progress_bar.empty()

        if results_found:
            df_res = pd.DataFrame(results_found).drop_duplicates(subset=['Name', 'School'])
            df_res['Full_Bio'] = df_res['Full_Bio'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
            df_res.sort_values(by=['Role', 'Name'], ascending=[True, True], inplace=True)
            st.session_state['search_results'] = df_res
        else:
            st.session_state['search_results'] = pd.DataFrame()
            st.warning("No matches found.")

if not st.session_state['search_results'].empty:
    final_df = st.session_state['search_results']
    st.success(f"🎉 Found {len(final_df)} matches.")
    
    st.dataframe(final_df, column_config={"Full_Bio": None}, use_container_width=True, hide_index=True)
    
    safe_kw = re.sub(r'[^a-zA-Z0-9]', '_', st.session_state['last_keywords'][:20])
    file_name_dynamic = f"Search_{safe_kw}_{datetime.now().date()}.xlsx"
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        final_df.to_excel(writer, index=False, sheet_name="Results")
        worksheet = writer.sheets['Results']
        worksheet.set_column(0, 0, 15)  # Role
        worksheet.set_column(1, 5, 30)  # Info
        worksheet.set_column(6, 6, 50)  # Context
    
    st.download_button("💾 DOWNLOAD EXCEL", buffer.getvalue(), file_name_dynamic, "application/vnd.ms-excel")
