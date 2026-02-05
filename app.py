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
MASTER_DB_FILE = None
possible_names = ['REC_CONS_MASTER.csv', 'rec_cons_master.csv', 'Rec_Cons_Master.csv']
for name in possible_names:
    if os.path.exists(name):
        MASTER_DB_FILE = name
        break

GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Keywords & Filters
FOOTBALL_INDICATORS = ["football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", "recruiting", "fbs", "fcs", "interception", "tackle", "gridiron"]
NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero"], "Baseball": ["baseball", "inning", "homerun", "pitcher"],
    "Basketball": ["basketball", "nba", "dunk", "rebound"], "Soccer": ["soccer", "goal", "striker", "fifa"],
    "Softball": ["softball"], "Track": ["track", "sprint"], "Swimming": ["swim", "dive"], "Lacrosse": ["lacrosse"]
}
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
    df = None
    try:
        # 1. Try Google Sheet
        try:
            r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=5)
            if r.ok:
                df = pd.read_csv(io.BytesIO(r.content), encoding='utf-8')
        except: pass
        
        # 2. Try Local File
        if (df is None or df.empty) and MASTER_DB_FILE:
            try: df = pd.read_csv(MASTER_DB_FILE, encoding='utf-8')
            except: df = pd.read_csv(MASTER_DB_FILE, encoding='latin1')
            
        if df is None or df.empty: return {}, {}

        # --- SMART COLUMN DETECTION ---
        cols_lower = {c.lower().strip(): c for c in df.columns}
        
        def find_col(*keywords):
            for k in keywords:
                if k in cols_lower: return cols_lower[k]
                for actual_col in cols_lower:
                    if k in actual_col: return cols_lower[actual_col]
            return None

        col_school = find_col('school', 'institution')
        col_first = find_col('first name', 'first')
        col_last = find_col('last name', 'last')
        col_email = find_col('email', 'e-mail')
        col_twitter = find_col("individual's twitter", 'twitter', 'social', 'x.com')
        col_title = find_col('title', 'position')

        lookup, name_lookup = {}, {}

        for _, row in df.iterrows():
            school = str(row[col_school]).strip() if col_school and pd.notna(row[col_school]) else ""
            first = str(row[col_first]).strip() if col_first and pd.notna(row[col_first]) else ""
            last = str(row[col_last]).strip() if col_last and pd.notna(row[col_last]) else ""
            
            if school and (first or last):
                full_name = f"{first} {last}".strip()
                email = str(row[col_email]).strip() if col_email and pd.notna(row[col_email]) else ""
                twitter = str(row[col_twitter]).strip() if col_twitter and pd.notna(row[col_twitter]) else ""
                title = str(row[col_title]).strip() if col_title and pd.notna(row[col_title]) else ""
                
                rec = {'email': email, 'twitter': twitter, 'title': title, 'school': school, 'name': full_name}
                s_key = normalize_text(school)
                n_key = normalize_text(full_name)
                
                lookup[(s_key, n_key)] = rec
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
        return lookup, name_lookup
    except Exception as e:
        print(f"DB Load Error: {e}")
        return {}, {}

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
    clean_text = str(text).replace(chr(10), ' ').replace(chr(13), ' ')
    m = re.search(re.escape(keyword), clean_text, re.IGNORECASE)
    if m: 
        s, e = max(0, m.start()-50), min(len(clean_text), m.end()+50)
        return f"...{clean_text[s:e]}..."
    return clean_text[:100] + "..."

# --- 4. SEARCH LOGIC ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.form(key='search_form'):
        keywords_str = st.text_input("", placeholder="🔍 Search Database (e.g., Atlanta)")
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
                
                del df_chunk
                gc.collect()
            except Exception: continue
            progress_bar.progress((i + 1) / len(chunk_files))

        progress_bar.empty()

        if results_found:
            df_res = pd.DataFrame(results_found).drop_duplicates(subset=['Name', 'School'])
            # Flatten rows
            df_res['Full_Bio'] = df_res['Full_Bio'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
            # Sort: Staff First
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
        
        # --- CUSTOM COLUMN WIDTHS ---
        worksheet.set_column(0, 0, 15)  # Role (Narrower)
        worksheet.set_column(1, 5, 30)  # Name, Title, School, Email, Twitter (Wide)
        worksheet.set_column(6, 6, 50)  # Context (Extra Wide)
    
    st.download_button("💾 DOWNLOAD EXCEL", buffer.getvalue(), file_name_dynamic, "application/vnd.ms-excel")
