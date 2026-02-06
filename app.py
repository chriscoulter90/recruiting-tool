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

# EXPANDED STAFF LIST
STAFF_KEYWORDS = [
    "coach", "director", "coordinator", "assistant", "manager", "analyst", 
    "specialist", "trainer", "video", "operations", "quality control", "qc",
    "recruiting", "personnel", "chief of staff", "scout", "dietitian", "nutrition",
    "ga", "grad assistant", "graduate assistant", "intern", "fellow", "admin",
    "s&c", "strength", "conditioning", "performance", "player dev", "development",
    "exec", "executive", "sr.", "jr.", "head", "asst", "tech", "media", "creative"
]

PLAYER_BIO_KEYWORDS = ["height:", "weight:", "class:", "hometown:", "high school:", "lbs", "freshman", "sophomore", "junior", "senior"]
FOOTBALL_INDICATORS = ["football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", "recruiting", "fbs", "fcs", "interception", "tackle", "gridiron"]
NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero"], "Baseball": ["baseball", "inning", "homerun", "pitcher"],
    "Basketball": ["basketball", "nba", "dunk", "rebound"], "Soccer": ["soccer", "goal", "striker", "fifa"],
    "Softball": ["softball"], "Track": ["track", "sprint"], "Swimming": ["swim", "dive"], "Lacrosse": ["lacrosse"]
}
POISON_PILLS_TEXT = ["Women's Flag", "Flag Football"]
BAD_NAMES = ["Football Roster", "Football Schedule", "Composite Schedule", "Game Recap", "Menu", "Search", "Tickets"]

SCHOOL_ALIASES = {
    "ASU": "Arizona State", "UCF": "Central Florida", "Ole Miss": "Mississippi", 
    "FSU": "Florida State", "Miami": "Miami (FL)", "UConn": "Connecticut",
    "LSU": "Louisiana State", "USC": "Southern California", "SMU": "Southern Methodist",
    "TCU": "Texas Christian", "BYU": "Brigham Young", "FAU": "Florida Atlantic",
    "FIU": "Florida International", "USF": "South Florida", "UNC": "North Carolina",
    "NC State": "North Carolina State", "UVA": "Virginia", "VT": "Virginia Tech",
    "GT": "Georgia Tech", "Pitt": "Pittsburgh", "Wash St": "Washington State",
    "Miss St": "Mississippi State", "Okla St": "Oklahoma State", "Mich St": "Michigan State"
}

# --- 3. HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup():
    """Load coach database safely."""
    df = None
    try:
        r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=3)
        if r.ok:
            df = pd.read_csv(io.BytesIO(r.content), encoding='utf-8')
    except: pass
    
    if df is None or df.empty:
        possible_files = glob.glob("*master*.csv") + glob.glob("*MASTER*.csv")
        if possible_files:
            try: df = pd.read_csv(possible_files[0], encoding='utf-8')
            except: 
                try: df = pd.read_csv(possible_files[0], encoding='latin1')
                except: pass

    if df is None or df.empty: return {}, {}, {}, "Failed"

    cols_lower = {c.lower().strip(): c for c in df.columns}
    def get_col_name(*candidates):
        for c in candidates:
            if c.lower() in cols_lower: return cols_lower[c.lower()]
        for c in candidates:
            for actual in cols_lower:
                if c.lower() in actual: return cols_lower[actual]
        return None

    c_school = get_col_name('school', 'institution')
    c_first = get_col_name('first name', 'first')
    c_last = get_col_name('last name', 'last')
    c_email = get_col_name('email', 'e-mail')
    c_twitter = get_col_name("individual's twitter", "twitter", "x.com", "social")
    c_title = get_col_name('title', 'position', 'role')

    lookup, name_lookup, lastname_lookup = {}, {}, {}

    for _, row in df.iterrows():
        raw_school = str(row[c_school]).strip() if c_school and pd.notna(row[c_school]) else ""
        for alias, real in SCHOOL_ALIASES.items():
            if alias.lower() == raw_school.lower(): raw_school = real
        
        first = str(row[c_first]).strip() if c_first and pd.notna(row[c_first]) else ""
        last = str(row[c_last]).strip() if c_last and pd.notna(row[c_last]) else ""
        
        if first or last:
            full_name = f"{first} {last}".strip()
            email = str(row[c_email]).strip() if c_email and pd.notna(row[c_email]) else ""
            twitter = str(row[c_twitter]).strip() if c_twitter and pd.notna(row[c_twitter]) else ""
            title = str(row[c_title]).strip() if c_title and pd.notna(row[c_title]) else ""
            
            rec = {'email': email, 'twitter': twitter, 'title': title, 'school': raw_school, 'name': full_name}
            
            s_key = normalize_text(raw_school)
            n_key = normalize_text(full_name)
            l_key = normalize_text(last)
            
            if s_key: lookup[(s_key, n_key)] = rec
            if n_key not in name_lookup: name_lookup[n_key] = []
            name_lookup[n_key].append(rec)
            if s_key:
                if (s_key, l_key) not in lastname_lookup: lastname_lookup[(s_key, l_key)] = []
                lastname_lookup[(s_key, l_key)].append(rec)
            
    return lookup, name_lookup, lastname_lookup, "Success"

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup, lastname_lookup, db_status = st.session_state["master_data"]

def detect_sport(bio):
    text = str(bio).lower()
    if any(p.lower() in text[:1000] for p in POISON_PILLS_TEXT): return None
    fb_score = sum(text.count(w) for w in FOOTBALL_INDICATORS)
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        if sum(text.count(w) for w in keywords) > fb_score + 1: return None
    return "Football"

def determine_role(title, bio_text):
    # 1. Check Bio for Player Signs (Strongest Indicator for Players)
    bio_sample = str(bio_text)[:600].lower()
    if any(k in bio_sample for k in PLAYER_BIO_KEYWORDS):
        return "PLAYER"
    
    # 2. Check Title for Expanded Staff Keywords
    title_lower = str(title).lower()
    if any(k in title_lower for k in STAFF_KEYWORDS):
        return "COACH/STAFF"
        
    # 3. Double Check Bio for Staff Titles (Fix for Travis Fisher)
    if any(k in bio_sample for k in STAFF_KEYWORDS):
        return "COACH/STAFF"
    
    return "PLAYER"

def extract_real_title(bio):
    # Try to find a better title in the body text if the header failed
    # Look for "Title: X" or "Position: X"
    match = re.search(r'(?:Title|Position)[:\s]+([A-Za-z \-\&]+?)(?=\n|Email|Phone|Bio)', str(bio), re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def parse_header(bio):
    lines = [L.strip() for L in str(bio).split('\n') if L.strip()][:10]
    header = None
    for delimiter in [" - ", " | ", " : "]:
        header = next((L for L in lines if delimiter in L and "http" not in L), None)
        if header: break
        
    extracted = {'Name': None, 'Title': "Unknown", 'School': "Unknown", 'Role': 'PLAYER', 'Last': ''}
    
    if header:
        parts = re.split(r' - | \| | : ', header)
        if len(parts) >= 2:
            extracted['Name'] = parts[0].strip()
            extracted['Last'] = parts[0].strip().split(' ')[-1]
            extracted['School'] = parts[-1].strip()
            if len(parts) > 2: extracted['Title'] = parts[1].strip()
    
    # IMPROVED: If Title looks like a school name or is generic, scan the bio for the REAL title
    if "University" in extracted['Title'] or "Athletics" in extracted['Title'] or extracted['Title'] == "Unknown":
        better_title = extract_real_title(bio)
        if better_title:
            extracted['Title'] = better_title

    # Normalize School
    for alias, real in SCHOOL_ALIASES.items():
        if alias.lower() in extracted['School'].lower(): extracted['School'] = real
        
    extracted['Role'] = determine_role(extracted['Title'], bio)
    
    return extracted

def get_snippet(text, keyword):
    # Clean text for CSV safety
    clean_text = str(text).replace(chr(10), ' ').replace(chr(13), ' ')
    m = re.search(re.escape(keyword), clean_text, re.IGNORECASE)
    if m: 
        s, e = max(0, m.start()-50), min(len(clean_text), m.end()+50)
        return f"...{clean_text[s:e]}..."
    return clean_text[:100] + "..."

# --- 4. SEARCH LOGIC ---
st.markdown('<p class="instruction-text">Type in keywords to search college football webpage bios.<br>Put a comma between keywords for multiple searches (e.g., "Linebacker, Recruiting").</p>', unsafe_allow_html=True)

if db_status == "Failed":
    st.error("❌ Master Database Not Found. Contact info will be empty.")

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
                        
                        match = {}
                        if (s_key, n_key) in master_lookup:
                            match = master_lookup[(s_key, n_key)]
                        elif n_key in name_lookup:
                            match = name_lookup[n_key][0]
                        elif (s_key, l_key) in lastname_lookup:
                            match = lastname_lookup[(s_key, l_key)][0]

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
            # FLATTEN BIO AND CONTEXT FOR EXCEL
            df_res['Full_Bio'] = df_res['Full_Bio'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
            df_res['Context'] = df_res['Context'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
            
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
        # EXCEL COLUMN WIDTHS
        worksheet.set_column(0, 0, 15) # Role
        worksheet.set_column(1, 5, 25) # Name, Title, School, Email, Twitter
        worksheet.set_column(6, 6, 50) # Context
        worksheet.set_column(7, 7, 50) # Full Bio
    
    st.download_button("💾 DOWNLOAD EXCEL", buffer.getvalue(), file_name_dynamic, "application/vnd.ms-excel")
