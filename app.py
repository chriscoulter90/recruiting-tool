import streamlit as st
import os
import glob
import re
import gc
import io
import requests
import pandas as pd
from datetime import datetime

# --- 1. APPLE + FOOTBALL UI CONFIGURATION ---
st.set_page_config(page_title="Coulter Recruiting", page_icon="🏈", layout="wide")

# Custom CSS for the "Apple Clean" look with Football accents
st.markdown("""
    <style>
    /* Global Font - San Francisco Style */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #F5F5F7; /* Apple Off-White */
        color: #1D1D1F;
    }
    
    /* Hide Streamlit Header/Footer */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    /* HEADER: The "Football Field" Effect */
    .header-container {
        background: linear-gradient(90deg, #002B5C 0%, #003B7E 100%);
        padding: 40px;
        border-radius: 20px;
        text-align: center;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        margin-bottom: 40px;
        border-bottom: 5px solid #4CAF50; /* Turf Green Accent */
    }
    .main-title {
        font-size: 3rem;
        font-weight: 800;
        color: #FFFFFF;
        margin: 0;
        letter-spacing: -1px;
    }
    .sub-title {
        font-size: 1.2rem;
        font-weight: 400;
        color: #A3C9F7;
        margin-top: 5px;
        text-transform: uppercase;
        letter-spacing: 2px;
    }

    /* SEARCH BAR: Clean & Minimal */
    .stTextInput > div > div > input {
        border-radius: 12px;
        border: 1px solid #D1D1D6;
        padding: 15px 20px;
        font-size: 18px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
    }
    .stTextInput > div > div > input:focus {
        border-color: #007AFF; /* Apple Blue */
        box-shadow: 0 0 0 3px rgba(0,122,255,0.2);
    }

    /* BUTTON: Premium Feel */
    .stButton > button {
        background-color: #1D1D1F;
        color: white;
        border-radius: 12px;
        padding: 15px 30px;
        font-weight: 600;
        border: none;
        width: 100%;
        transition: transform 0.1s ease;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        background-color: #333;
    }
    
    /* DATAFRAME: Clean Table */
    .stDataFrame {
        border-radius: 15px;
        overflow: hidden;
        border: 1px solid #E5E5EA;
    }
    </style>
    """, unsafe_allow_html=True)

# Render Header
st.markdown("""
    <div class="header-container">
        <div class="main-title">COULTER RECRUITING</div>
        <div class="sub-title">Elite Football Search Engine</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# STRICT Forbidden List (Matches Local)
FORBIDDEN_SPORTS = [
    "Volleyball", "Baseball", "Softball", "Soccer", "Tennis", "Golf", 
    "Swimming", "Lacrosse", "Hockey", "Wrestling", "Gymnastics", 
    "Basketball", "Track & Field", "Crew", "Rowing", "Sailing", 
    "Acrobatics", "Tumbling", "Cheerleading", "Fencing", "Spirit Squad",
    "Women's Basketball", "Men's Basketball"
]

GARBAGE_PHRASES = [
    "Official Athletics Website", "Official Website", "Composite", 
    "Javascript is required", "Skip To Main Content", "Official Football Roster",
    "View Full Profile", "Related Headlines", "Source:", "https://"
]

# THE TRANSLATOR (Fixes the Handshake Issue)
SCHOOL_ALIASES = {
    "ASU": "Arizona State", "Arizona State University": "Arizona State",
    "UCF": "Central Florida", "Central Florida": "UCF",
    "Ole Miss": "Mississippi", "Mississippi": "Ole Miss",
    "SMU": "Southern Methodist", "Southern Methodist": "SMU",
    "USC": "Southern California", "Southern California": "USC",
    "LSU": "Louisiana State", "Louisiana State": "LSU",
    "TCU": "Texas Christian", "Texas Christian": "TCU",
    "BYU": "Brigham Young", "Brigham Young": "BYU",
    "FSU": "Florida State", "Florida State": "FSU",
    "Miami (FL)": "Miami", "Miami": "Miami (FL)"
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
                # Index by School+Name
                lookup[(s_key, n_key)] = rec
                
                # Also index by Alias+Name
                for alias, real_name in SCHOOL_ALIASES.items():
                    if s_raw == real_name:
                        lookup[(normalize_text(alias), n_key)] = rec
                
                # Index by Name Only
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
                
        return lookup, name_lookup
    except: return {}, {}

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

def parse_header_exact(bio):
    extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
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
            extracted['Name'], extracted['Title'], extracted['School'] = clean_parts[0], clean_parts[1], clean_parts[2]
        elif len(clean_parts) == 2:
            extracted['Name'], extracted['School'] = clean_parts[0], clean_parts[1]
            extracted['Title'] = "Staff"
        elif len(clean_parts) == 1:
            extracted['Name'] = clean_parts[0]

        # Fix Swaps
        if extracted['Title'] and any(x in str(extracted['Title']) for x in ["University", "College", "Athletics"]):
            extracted['School'], extracted['Title'] = extracted['Title'], extracted['School'] or "Staff"

        # Alias Correction (e.g., ASU -> Arizona State)
        clean_school = str(extracted['School']).strip()
        if clean_school in SCHOOL_ALIASES:
            extracted['School'] = SCHOOL_ALIASES[clean_school]
        
        # Role Detection
        for val in [str(extracted['Title']), str(extracted['School'])]:
            if "202" in val or "203" in val:
                extracted['Role'] = "PLAYER"
                extracted['Title'] = "Roster Member"
            if "Football" == val and extracted['Role'] == "COACH/STAFF":
                 extracted['Title'] = "Staff"
    return extracted

def get_snippet(text, keyword):
    if pd.isna(text): return ""
    clean = str(text).replace('\n', ' ').replace('\r', ' ')
    m = re.search(re.escape(keyword), clean, re.IGNORECASE)
    if m:
        s, e = max(0, m.start()-60), min(len(clean), m.end()+60)
        return f"...{clean[s:e].strip()}..."
    return f"...{clean[:100]}..."

# --- 4. SEARCH INTERFACE ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    keywords_str = st.text_input("", placeholder="🔍 Search Database (e.g. Tallahassee, Quarterback)...")
    run_search = st.button("RUN SEARCH", use_container_width=True)

if run_search or keywords_str:
    if not keywords_str:
        st.warning("⚠️ Please enter a keyword to search.")
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
                        # Normalize Columns
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
                                meta = parse_header_exact(row['Full_Bio'])
                                
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] or name
                                
                                school = row.get('School', '')
                                if not school or school == "Unknown": school = meta['School'] or school
                                    
                                title = row.get('Title', '')
                                if not title or title == "Unknown": title = meta['Title'] or title
                                
                                role = meta['Role']

                                # Forbidden Sport Filter
                                blob = (str(title) + " " + str(school) + " " + str(row['Full_Bio'])[:200]).lower()
                                for sport in FORBIDDEN_SPORTS:
                                    if sport.lower() in blob and "football" not in blob: return None

                                # Master Lookup (With Alias Support)
                                match = master_lookup.get((normalize_text(school), normalize_text(name)))
                                
                                # Fallback: Name Only Match
                                if not match:
                                    cands = name_lookup.get(normalize_text(name), [])
                                    if len(cands) == 1: match = cands[0]
                                    elif len(cands) > 1:
                                        # Fuzzy School Check
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
                                    # Fix generic titles using Master DB
                                    if title in ["Staff", "Unknown", "Football"]: title = match['title']
                                    school = match['school'] # Use Clean School Name
                                
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
                
                # Sort: Role -> School -> Name
                final_df['Role_Sort'] = final_df['Role'].apply(lambda x: 1 if "PLAYER" in str(x).upper() else 0)
                final_df.sort_values(by=['Role_Sort', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                
                # Column Order: Snippet BEFORE Full Bio
                cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_df = final_df[cols]
                
                st.success(f"🎉 Found {len(final_df)} matches.")
                st.dataframe(final_df, use_container_width=True)
                
                # Filename: tallahassee_2026-02-05.xlsx
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
