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

    /* FORM & BUTTONS */
    .stTextInput > div > div > input {
        border-radius: 20px; border: 1px solid #D1D1D6; padding: 18px 25px; font-size: 17px;
    }
    .stButton > button {
        background: #000000; color: white; border-radius: 30px; padding: 12px 40px; font-weight: 600; border: none; width: auto; display: block; margin: 0 auto;
    }
    .stButton > button:hover { background: #333333; }

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

# --- 2. CONSTANTS ---
# Use flexible filename check to prevent Linux crashes
if os.path.exists('REC_CONS_MASTER.csv'):
    MASTER_DB_FILE = 'REC_CONS_MASTER.csv'
elif os.path.exists('rec_cons_master.csv'):
    MASTER_DB_FILE = 'rec_cons_master.csv'
else:
    MASTER_DB_FILE = None

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Keywords & Filters
FOOTBALL_INDICATORS = ["football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", "recruiting", "fbs", "fcs", "interception", "tackle", "gridiron"]
NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero"], "Baseball": ["baseball", "inning", "homerun", "pitcher"],
    "Basketball": ["basketball", "nba", "dunk", "rebound"], "Soccer": ["soccer", "goal", "striker", "fifa"],
    "Softball": ["softball"], "Track": ["track", "sprint"], "Swimming": ["swim", "dive"], "Lacrosse": ["lacrosse"]
}
GARBAGE_PHRASES = ["Official Athletics Website", "Composite", "Javascript is required", "Skip To Main Content", "View Full Profile"]
POISON_PILLS_TEXT = ["Women's Flag", "Flag Football"]
BAD_NAMES = ["Football Roster", "Football Schedule", "Composite Schedule", "Game Recap", "Menu", "Search", "Tickets"]
SCHOOL_ALIASES = {"ASU": "Arizona State", "UCF": "Central Florida", "Ole Miss": "Mississippi", "FSU": "Florida State", "Miami": "Miami (FL)"}

# --- 3. HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup():
    """Load coach database safely on demand."""
    try:
        # 1. Try Google Sheet first
        try:
            r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=5)
            if r.ok:
                df = pd.read_csv(io.BytesIO(r.content), encoding='utf-8')
        except: df = None
        
        # 2. Try local file if Sheet fails
        if (df is None or df.empty) and MASTER_DB_FILE:
            try: df = pd.read_csv(MASTER_DB_FILE, encoding='utf-8')
            except: df = pd.read_csv(MASTER_DB_FILE, encoding='latin1')
            
        if df is None or df.empty: return {}, {}

        # Build Lookup
        lookup, name_lookup = {}, {}
        col_map = {str(c).strip().lower(): c for c in df.columns}
        
        def get_val(row, *keys):
            for k in keys:
                if k.lower() in col_map: return str(row[col_map[k.lower()]]).strip()
            return ""

        for _, row in df.iterrows():
            school = get_val(row, 'school')
            first = get_val(row, 'first name', 'first')
            last = get_val(row, 'last name', 'last')
            email = get_val(row, 'email', 'email address')
            twitter = get_val(row, 'twitter', 'x', 'twitter handle')
            title = get_val(row, 'title')
            
            if school and (first or last):
                full_name = f"{first} {last}".strip()
                rec = {'email': email, 'twitter': twitter, 'title': title, 'school': school, 'name': full_name}
                s_key = normalize_text(school)
                n_key = normalize_text(full_name)
                lookup[(s_key, n_key)] = rec
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
        return lookup, name_lookup
    except: return {}, {}

# Lazy load master data so app doesn't crash on boot
if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

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
    extracted = {'Name': None, 'Title': "Staff", 'School': "Unknown", 'Role': 'COACH/STAFF'}
    if header:
        parts = header.split(' - ')
        if len(parts) >= 2:
            extracted['Name'] = parts[0].strip()
            extracted['School'] = parts[-1].strip()
            if len(parts) > 2: extracted['Title'] = parts[1].strip()
    for alias, real in SCHOOL_ALIASES.items():
        if alias.lower() in extracted['School'].lower(): extracted['School'] = real
    if "202" in extracted['Title'] or "Roster" in extracted['Title']:
        extracted['Role'] = "PLAYER"; extracted['Title'] = "Roster Member"
    return extracted

def get_snippet(text, keyword):
    m = re.search(re.escape(keyword), str(text), re.IGNORECASE)
    if m: 
        s, e = max(0, m.start()-60), min(len(text), m.end()+60)
        return f"...{text[s:e]}..."
    return text[:150] + "..."

# --- 4. SEARCH LOGIC (LOW MEMORY MODE) ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.form(key='search_form'):
        keywords_str = st.text_input("", placeholder="🔍 Search Database (e.g., Atlanta)")
        submit_button = st.form_submit_button(label='Search')

if submit_button and keywords_str:
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    pattern = '|'.join([re.escape(k) for k in keywords])
    
    # 1. Get files but DO NOT load them yet
    chunk_files = glob.glob("chunk_*.csv")
    chunk_files.sort()
    
    if not chunk_files:
        st.error("❌ No database files found on server.")
    else:
        results_found = []
        progress_bar = st.progress(0)
        
        # 2. Loop through files one by one (Low Memory)
        for i, file in enumerate(chunk_files):
            try:
                # Load ONE chunk, search it, then delete it immediately
                df_chunk = pd.read_csv(file, dtype=str, on_bad_lines='skip').fillna("")
                mask = df_chunk['Full_Bio'].str.contains(pattern, case=False, na=False, regex=True)
                
                if mask.any():
                    matches = df_chunk[mask].copy()
                    
                    for idx, row in matches.iterrows():
                        meta = parse_header(row['Full_Bio'])
                        name = meta['Name'] or row.get('Name', 'Unknown')
                        
                        if any(b.lower() in str(name).lower() for b in BAD_NAMES): continue
                        if detect_sport(row['Full_Bio']) != "Football": continue
                        
                        # Master DB Match
                        s_key = normalize_text(meta['School'])
                        n_key = normalize_text(name)
                        match = master_lookup.get((s_key, n_key), {})
                        if not match and n_key in name_lookup: match = name_lookup[n_key][0]
                            
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
                
                # Free memory instantly
                del df_chunk
                gc.collect()
                
            except Exception: continue
            
            # Update progress
            progress_bar.progress((i + 1) / len(chunk_files))

        progress_bar.empty()

        # 3. Display Results
        if results_found:
            final_df = pd.DataFrame(results_found).drop_duplicates(subset=['Name', 'School'])
            st.success(f"🎉 Found {len(final_df)} matches.")
            st.dataframe(final_df.drop(columns=['Full_Bio']), use_container_width=True, hide_index=True)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, index=False, sheet_name="Results")
            st.download_button("💾 DOWNLOAD EXCEL", buffer.getvalue(), f"Search_{datetime.now().date()}.xlsx", "application/vnd.ms-excel")
        else:
            st.warning("No matches found.")