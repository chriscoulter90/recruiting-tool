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
    /* Global Font */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        background-color: #F5F5F7; 
        color: #1D1D1F;
    }
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    /* HEADER */
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

    /* INPUT & BUTTONS */
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
    "interception", "sackle", "gridiron", "playoff", "super bowl", "pro bowl"
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

# THE TRANSLATOR (Maps Scraped Names to Master DB Names)
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
    "Bama": "Alabama", "Crimson Tide": "Alabama"
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
                        # Add lookup for "ASU"+Name -> Record
                        lookup[(normalize_text(alias), n_key)] = rec
                
                # Name only lookup (for safety check later)
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
                
        return lookup, name_lookup
    except: return {}, {}

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

def detect_sport_context(bio):
    """
    Siphons through junk text and scans the history for sport keywords.
    Returns: 'Football', 'Other', or 'Uncertain'
    """
    if pd.isna(bio): return "Uncertain"
    
    # 1. Clean Junk (Skip first 200 chars if they are just menus)
    text = str(bio)
    if len(text) > 500:
        # Heuristic: The narrative usually starts after the header "junk"
        # We search the middle-to-end of the text for keywords
        analysis_text = text[200:].lower()
    else:
        analysis_text = text.lower()

    # 2. Count Keywords
    fb_score = sum(analysis_text.count(w) for w in FOOTBALL_INDICATORS)
    
    max_other_score = 0
    likely_other_sport = None
    
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        score = sum(analysis_text.count(w) for w in keywords)
        if score > max_other_score:
            max_other_score = score
            likely_other_sport = sport

    # 3. Decision
    if fb_score > max_other_score:
        return "Football"
    elif max_other_score > fb_score and max_other_score > 2:
        return likely_other_sport # e.g., "Volleyball"
    else:
        # If ambiguous, check if "Football" is in the title/header explicitly
        if "football" in text[:300].lower():
            return "Football"
        return "Uncertain"

def parse_header_smart(bio):
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

        # Alias Correction (The "Bridge")
        # Check if "ASU Sun Devils" contains "ASU", if so, map to "Arizona State"
        raw_school = str(extracted['School']).strip()
        for alias, real_name in SCHOOL_ALIASES.items():
            if alias.lower() in raw_school.lower():
                extracted['School'] = real_name
                break
        
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
                                # 1. Parse & Normalize Header
                                meta = parse_header_smart(row['Full_Bio'])
                                
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] or name
                                
                                school = row.get('School', '')
                                if not school or school == "Unknown": school = meta['School'] or school
                                    
                                title = row.get('Title', '')
                                if not title or title == "Unknown": title = meta['Title'] or title
                                
                                role = meta['Role']

                                # 2. CONTENT-BASED SPORT DETECTION (The "Siphon")
                                detected_sport = detect_sport_context(row['Full_Bio'])
                                if detected_sport != "Football" and detected_sport != "Uncertain":
                                    return None # Skip Non-Football

                                # 3. Safe Handshake (Name + School)
                                # Try Strict Match first (Normalized)
                                match = master_lookup.get((normalize_text(school), normalize_text(name)))
                                
                                # If no strict match, check if we have a valid Alias in the school name
                                if not match:
                                    cands = name_lookup.get(normalize_text(name), [])
                                    # Loop through candidates for this name
                                    for c in cands:
                                        # Check if the Master DB school is "inside" the scraped school
                                        # e.g. "Arizona State" is inside "ASU Sun Devils" (because we Aliased it)
                                        # or "Arizona State" is inside "Arizona State University"
                                        n_master = normalize_text(c['school'])
                                        n_scraped = normalize_text(school)
                                        
                                        if n_master in n_scraped or n_scraped in n_master:
                                            match = c
                                            break
                                
                                email = row.get('Email', '')
                                twitter = row.get('Twitter', '')
                                sport_val = "Football"
                                
                                if match:
                                    if not email: email = match['email']
                                    if not twitter: twitter = match['twitter']
                                    if title in ["Staff", "Unknown", "Football"]: title = match['title']
                                    school = match['school'] # Canonical Name
                                
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
