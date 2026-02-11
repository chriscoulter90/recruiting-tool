import streamlit as st
import os
import glob
import re
import gc
import io
import requests
import pandas as pd
from datetime import datetime
import time

# --- 1. CONFIGURATION & STYLES ---
st.set_page_config(page_title="Coulter Recruiting v1.22", page_icon="🏈", layout="wide")

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
    .version-tag { 
        position: absolute; top: 10px; right: 20px; 
        font-size: 0.8rem; color: #8E8E93; font-weight: bold; 
        background: #eee; padding: 4px 8px; border-radius: 8px;
    }
    .instruction-text { text-align: center; color: #555; font-size: 1.1em; margin-bottom: 20px; }
    
    /* TABLE */
    .stDataFrame { background-color: white; border-radius: 20px; padding: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

st.markdown("""
    <div class="header-container">
        <div class="version-tag">v1.22</div>
        <div class="main-title">🏈 COULTER RECRUITING</div>
        <div class="sub-title">Football Search Engine</div>
    </div>
    """, unsafe_allow_html=True)

# --- 2. CONSTANTS & FILES ---
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# STRICT LISTS
FOOTBALL_INDICATORS = ["football", "quarterback", "linebacker", "touchdown", "nfl", "bowl", "recruiting", "fbs", "fcs", "interception", "tackle", "gridiron"]

# V1.19: Expanded Non-Football List
NON_FOOTBALL_INDICATORS = {
    "Volleyball": ["volleyball", "set", "spike", "libero"], 
    "Baseball": ["baseball", "inning", "homerun", "pitcher", "dugout"],
    "Basketball": ["basketball", "nba", "dunk", "rebound", "hoop"], 
    "Soccer": ["soccer", "goal", "striker", "fifa"],
    "Softball": ["softball"], 
    "Track": ["track", "sprint", "marathon"], 
    "Swimming": ["swim", "dive", "pool", "breaststroke"], 
    "Lacrosse": ["lacrosse", "stick"],
    "Equestrian": ["equestrian", "horse", "rider", "hunt seat"], 
    "Rowing": ["rowing", "crew", "coxswain", "regatta"],
    "Field Hockey": ["field hockey"], 
    "Water Polo": ["water polo"],
    "Fencing": ["fencing", "foil", "saber", "epee"],
    "Pistol": ["pistol", "shooting", "rifle", "smallbore"],
    "Gymnastics": ["gymnastics", "vault", "beam"],
    "Skiing": ["skiing", "slalom", "nordic", "alpine"],
    "Bowling": ["bowling", "kegler"],
    "Wrestling": ["wrestling", "grapple", "mat"] 
}

# V1.22: BANNED SCHOOL NAMES (Junk Headers)
BANNED_SCHOOL_NAMES = [
    "official site", "official website", "copyright", "powered by", "terms of service",
    "privacy policy", "accessibility", "sidearm sports", "ad blocker", "main navigation",
    "skip to main", "pause all rotators", "composite calendar", "related videos"
]

POISON_PILLS_TEXT = ["Women's Flag", "Flag Football"]
BAD_NAMES = [
    "Football Roster", "Football Schedule", "Composite Schedule", "Game Recap", 
    "Menu", "Search", "Tickets", "Clemson Tiger Football", "University Athletics",
    "National Champions", "Athletics Website", "Skip To Main Content", 
    "Pause All Rotators", "Scoreboard", "Main Baseball", "Main Basketball",
    "Story Links", "Related Videos", "Related News", "Composite Calendar",
    "Official Site", "Official Website", "Copyright", "Terms of Service"
]

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
def normalize_text_v1_22(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    text = text.replace('.', '').replace("'", "").strip()
    # Explicitly remove 'athletics'
    for word in ['university', 'univ', 'college', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup_v1_22():
    """Load coach database with TEAM PHOBIC COLUMN DETECTION."""
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

    # --- SMART COLUMN FINDER ---
    def get_smart_col(keywords, data_type='text', bad_words=None):
        if bad_words is None: bad_words = []
        candidates = []
        for col in df.columns:
            c_lower = str(col).lower().strip()
            if any(k in c_lower for k in keywords):
                candidates.append(col)
        
        if not candidates: return None
        
        best_col = None
        max_score = -9999
        
        for col in candidates:
            score = 0
            col_lower = str(col).lower()
            if any(bad in col_lower for bad in ['sent', 'verify', 'check', 'status', 'date', 'time']): score -= 100
            if any(bad in col_lower for bad in bad_words): score -= 100
            if "individual" in col_lower or "personal" in col_lower or "coach" in col_lower: score += 50
            if col_lower in keywords: score += 10
            
            sample = df[col].dropna().astype(str).head(100).tolist()
            if not sample: score -= 10
            else:
                valid_count = 0
                for val in sample:
                    v = val.strip().lower()
                    if v in ['x', 'y', 'n', 'yes', 'no', 'true', 'false', 'done']: valid_count -= 1 
                    elif data_type == 'email' and '@' in v: valid_count += 2
                    elif data_type == 'twitter' and len(v) > 2: valid_count += 1
                score += valid_count
            
            if score > max_score:
                max_score = score
                best_col = col
                
        return best_col

    c_school = get_smart_col(['school', 'institution'])
    c_first = get_smart_col(['first name', 'first'])
    c_last = get_smart_col(['last name', 'last'])
    c_email = get_smart_col(['email', 'e-mail', 'mail'], 'email')
    c_twitter = get_smart_col(["individual's twitter", "twitter", "x.com", "social"], 'twitter', bad_words=['team', 'general', 'program', 'athletics'])
    c_title = get_smart_col(['title', 'position', 'role'])

    lookup, global_name_lookup, lastname_lookup = {}, {}, {}

    for _, row in df.iterrows():
        raw_school = str(row[c_school]).strip() if c_school and pd.notna(row[c_school]) else ""
        for alias, real in SCHOOL_ALIASES.items():
            if alias.lower() == raw_school.lower(): raw_school = real
        
        # --- HANDLE SPLIT OR SINGLE COLUMNS ---
        first = str(row[c_first]).strip() if c_first and pd.notna(row[c_first]) else ""
        last = str(row[c_last]).strip() if c_last and pd.notna(row[c_last]) else ""
        
        full_name = ""
        if first and last: full_name = f"{first} {last}".strip()
        elif first: full_name = first
        elif last: full_name = last
            
        if full_name:
            email = str(row[c_email]).strip() if c_email and pd.notna(row[c_email]) else ""
            twitter = str(row[c_twitter]).strip() if c_twitter and pd.notna(row[c_twitter]) else ""
            title = str(row[c_title]).strip() if c_title and pd.notna(row[c_title]) else ""
            
            # Clean junk data
            if email.lower() in ['x', 'y', 'yes', 'no', '-']: email = ""
            if twitter.lower() in ['x', 'y', 'yes', 'no', '-']: twitter = ""

            rec = {'email': email, 'twitter': twitter, 'title': title, 'school': raw_school, 'name': full_name}
            
            s_key = normalize_text_v1_22(raw_school)
            n_key = normalize_text_v1_22(full_name)
            l_key = normalize_text_v1_22(last)
            
            if s_key: lookup[(s_key, n_key)] = rec
            if n_key not in global_name_lookup: global_name_lookup[n_key] = rec
            if len(l_key) > 3:
                if (s_key, l_key) not in lastname_lookup: lastname_lookup[(s_key, l_key)] = []
                lastname_lookup[(s_key, l_key)].append(rec)
            
    return lookup, global_name_lookup, lastname_lookup, "Success"

# *** V1.22: Cache Clear ***
if "master_data_v1_22" not in st.session_state:
    with st.status("Initializing Recruiting Engine...", expanded=True) as status:
        st.write("📂 Connecting to Master Database...")
        data_tuple = load_lookup_v1_22()
        st.write("✅ Database Loaded!")
        st.session_state["master_data_v1_22"] = data_tuple
        status.update(label="System Ready!", state="complete", expanded=False)

master_lookup, global_name_lookup, lastname_lookup, db_status = st.session_state["master_data_v1_22"]

def detect_sport(bio):
    text = str(bio).lower()
    if any(p.lower() in text[:1000] for p in POISON_PILLS_TEXT): return None
    
    # Check for Non-Football Sports
    fb_score = sum(text.count(w) for w in FOOTBALL_INDICATORS)
    for sport, keywords in NON_FOOTBALL_INDICATORS.items():
        # Strict check for other sports
        sport_score = sum(text.count(w) for w in keywords)
        if sport_score > fb_score + 1: return None
        
    return "Football"

def clean_player_title(title, bio_text):
    t_clean = str(title).strip().lower()
    if "assistant" in t_clean or "coach" in t_clean or "manager" in t_clean: return title
    return "Football"

def determine_role_v1_22(title, bio_text):
    title_lower = str(title).lower()
    if "coach" in title_lower: return "COACH/STAFF"

    strong_staff = ["coordinator", "director", "manager", "analyst", "assistant", "specialist", "trainer", "video", "recruiting", "personnel", "chief", "scout", "dietitian", "nutrition", "ga", "grad assistant", "intern", "fellow", "admin", "strength", "conditioning", "performance", "player dev", "exec", "head", "gm", "ops"]
    if any(k in title_lower for k in strong_staff): return "COACH/STAFF"

    strong_player = ["quarterback", "running back", "wide receiver", "tight end", "offensive line", "defensive line", "linebacker", "defensive back", "cornerback", "safety", "kicker", "punter", "snapper", "qb", "rb", "wr", "te", "ol", "dl", "lb", "db", "cb", "s", "k", "p", "ls", "athlete", "edge", "rush", "tackle", "guard", "center"]
    if any(p in title_lower for p in strong_player): return "PLAYER"
    
    bio_sample = str(bio_text)[:800].lower()
    if any(f in bio_sample for f in ["class:", "height:", "weight:", "hometown:", "lbs"]): return "PLAYER"
    return "PLAYER"

def parse_header_v1_22(bio):
    lines = [L.strip() for L in str(bio).split('\n') if L.strip()][:15]
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
            
    # --- V1.22: ADVANCED JUNK ROW DETECTION ---
    name_check = extracted['Name'].lower() if extracted['Name'] else ""
    title_check = extracted['Title'].lower() if extracted['Title'] else ""
    school_check = extracted['School'].lower() if extracted['School'] else ""

    # 1. Kill bullet points and verbs
    if any(x in name_check for x in ["•", "*", "caught", "played", "appeared", "recorded", "started"]): return None
    
    # 2. Kill sport names in the NAME column
    for sport in NON_FOOTBALL_INDICATORS:
        if sport.lower() in name_check: return None

    # 3. Kill "Official Site" or "Powered By" masquerading as School/Name
    for ban in BANNED_SCHOOL_NAMES:
        if ban in school_check or ban in name_check: return None

    # 4. Kill overly long "names" (paragraphs)
    if len(name_check) > 40: return None
    
    # 5. Kill school names masquerading as people
    if ("university" in name_check or "college" in name_check) and \
       ("unknown" in title_check or "athletics" in title_check):
        return None 
    
    if "University" in extracted['Title'] or "Athletics" in extracted['Title'] or extracted['Title'] == "Unknown":
        match = re.search(r'(?:Title|Position)[:\s]+([A-Za-z \-\&]+?)(?=\n|Email|Phone|Bio)', str(bio), re.IGNORECASE)
        if match: extracted['Title'] = match.group(1).strip()

    # --- v1.17: CLEAN SCHOOL NAME (REMOVE 'ATHLETICS') ---
    if extracted['School']:
        extracted['School'] = extracted['School'].replace("Athletics", "").strip()

    for alias, real in SCHOOL_ALIASES.items():
        if alias.lower() in extracted['School'].lower(): extracted['School'] = real
        
    extracted['Role'] = determine_role_v1_22(extracted['Title'], bio)
    
    # --- V1.8: FORCE FOOTBALL TITLE FOR PLAYERS ---
    if extracted['Role'] == 'PLAYER':
        extracted['Title'] = "Football"
        
    return extracted

def get_smart_snippet(text, keyword):
    """V1.22: ULTRA-SMART SNIPPET (Context Hunter)."""
    clean_text = str(text).replace(chr(10), ' ').replace(chr(13), ' ')
    
    # 1. Look for Matches
    matches = list(re.finditer(re.escape(keyword), clean_text, re.IGNORECASE))
    
    if not matches:
        return clean_text[:120] + "..."
    
    best_snippet = None
    max_score = -1
    priority_words = ["hometown", "native", "high school", "born", "raised", "from", "attended", "product of"]
    
    for m in matches:
        start = max(0, m.start() - 60)
        end = min(len(clean_text), m.end() + 60)
        snippet = clean_text[start:end]
        
        score = 0
        snippet_lower = snippet.lower()
        
        # Boost for hometown context
        for p in priority_words:
            if p in snippet_lower: score += 10
            
        # V1.22: Penalize generic lists
        if "roster" in snippet_lower or "schedule" in snippet_lower or "statistics" in snippet_lower:
            score -= 15
        
        # V1.22: Penalize very short snippets
        if len(snippet) < 30: score -= 5
        
        if score > max_score:
            max_score = score
            best_snippet = f"...{snippet}..."
            
    return best_snippet

# --- 4. SEARCH LOGIC ---
st.markdown('<p class="instruction-text">Type in keywords to search college football webpage bios.<br>Put a comma between keywords for multiple searches (e.g., "Tallahassee, San Antonio").</p>', unsafe_allow_html=True)

if db_status == "Failed":
    st.error("❌ Master Database Not Found. Contact info will be empty.")

col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    with st.form(key='search_form'):
        keywords_str = st.text_input("", placeholder="🔍 Enter keywords...")
        submit_button = st.form_submit_button(label='Search')

if 'search_results' not in st.session_state:
    st.session_state['search_results'] = {} # Dict for multiple sheets
if 'last_keywords' not in st.session_state:
    st.session_state['last_keywords'] = ""

if submit_button and keywords_str:
    # SPLIT KEYWORDS for Tabs
    keywords_list = [k.strip() for k in keywords_str.split(',') if k.strip()]
    st.session_state['last_keywords'] = keywords_str
    
    chunk_files = glob.glob("chunk_*.csv")
    chunk_files.sort()
    
    all_results = {} # Store DF for each keyword
    
    if not chunk_files:
        st.error("❌ No database files found on server.")
    else:
        progress_bar = st.progress(0)
        
        # Run search for EACH keyword separately
        for k_idx, kw in enumerate(keywords_list):
            results_found = []
            pattern = re.escape(kw) # Search JUST this keyword
            
            for i, file in enumerate(chunk_files):
                try:
                    df_chunk = pd.read_csv(file, usecols=['Full_Bio'], dtype=str, on_bad_lines='skip').fillna("")
                    mask = df_chunk['Full_Bio'].str.contains(pattern, case=False, na=False, regex=True)
                    
                    if mask.any():
                        matches = df_chunk[mask].copy()
                        for idx, row in matches.iterrows():
                            meta = parse_header_v1_22(row['Full_Bio'])
                            
                            # --- V1.22: SKIP BAD ROWS ---
                            if meta is None: continue

                            name = meta['Name'] or "Unknown"
                            
                            if any(b.lower() in str(name).lower() for b in BAD_NAMES): continue
                            if "football" in str(name).lower() or "athletics" in str(name).lower(): continue
                            
                            # --- V1.19: STRICT SPORT SANITATION ---
                            school_check = str(meta['School']).lower()
                            title_check = str(meta['Title']).lower()
                            is_poisoned = False
                            for sport in NON_FOOTBALL_INDICATORS:
                                if sport.lower() in school_check or sport.lower() in title_check:
                                    is_poisoned = True
                                    break
                            if is_poisoned: continue

                            if detect_sport(row['Full_Bio']) != "Football": continue
                            
                            s_key = normalize_text_v1_22(meta['School'])
                            n_key = normalize_text_v1_22(name)
                            l_key = normalize_text_v1_22(meta['Last'])
                            
                            match = {}
                            match_source = None
                            
                            # --- v1.13 MATCHING LOGIC ---
                            if (s_key, n_key) in master_lookup:
                                match = master_lookup[(s_key, n_key)]
                                match_source = 'exact'
                            elif n_key in global_name_lookup:
                                match = global_name_lookup[n_key]
                                match_source = 'global'
                            elif (s_key, l_key) in lastname_lookup:
                                match = lastname_lookup[(s_key, l_key)][0]
                                match_source = 'fuzzy'

                            # --- PLAYER PROTECTION PROTOCOL ---
                            if match and match_source != 'exact':
                                if meta['Role'] == 'PLAYER':
                                    match = {} # Discard dangerous match
                            
                            # Apply Coach Data
                            has_twitter = match.get('twitter') and len(str(match['twitter'])) > 3
                            has_email = match.get('email') and len(str(match['email'])) > 3
                            if has_twitter or has_email:
                                meta['Role'] = 'COACH/STAFF'

                            snippet = get_smart_snippet(row['Full_Bio'], kw)

                            results_found.append({
                                'Role': meta['Role'],
                                'Name': name,
                                'Title': match.get('title') or meta['Title'],
                                'School': match.get('school') or meta['School'],
                                'Email': match.get('email', ''),
                                'Twitter': match.get('twitter', ''),
                                'Context': snippet,
                                'Full_Bio': row['Full_Bio']
                            })
                    del df_chunk
                    gc.collect()
                except Exception: continue
                # Shared progress bar
                progress_bar.progress((i + 1 + (k_idx * len(chunk_files))) / (len(chunk_files) * len(keywords_list)))

            if results_found:
                df_res = pd.DataFrame(results_found).drop_duplicates(subset=['Name', 'School'])
                df_res['Full_Bio'] = df_res['Full_Bio'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
                df_res['Context'] = df_res['Context'].astype(str).str.replace(r'[\r\n]+', ' ', regex=True)
                df_res.sort_values(by=['Role', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                all_results[kw] = df_res
            
        progress_bar.empty()
        st.session_state['search_results'] = all_results

if st.session_state['search_results']:
    results = st.session_state['search_results']
    # --- V1.15 NEW TOTAL COUNT UI ---
    total_count = sum(len(df) for df in results.values())
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #d9d9d9 0%, #f2f2f2 100%); 
                color: #1D1D1F; 
                padding: 20px; 
                border-radius: 12px; 
                font-family: -apple-system, system-ui, sans-serif;
                font-size: 1.1rem; 
                font-weight: 600; 
                margin-bottom: 25px; 
                display: flex;
                align-items: center;
                box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
        <span style="font-size: 1.4rem; margin-right: 12px;">✔️</span>
        Found {total_count} matches across {len(results)} keywords: {', '.join(results.keys())}
    </div>
    """, unsafe_allow_html=True)
    
    # Display Tabs
    tabs = st.tabs(list(results.keys()))
    for i, kw in enumerate(results.keys()):
        with tabs[i]:
            st.dataframe(results[kw], column_config={"Full_Bio": None}, use_container_width=True, hide_index=True)

    # Clean Filename
    safe_kw = re.sub(r'[^a-zA-Z0-9]', '_', st.session_state['last_keywords'][:30])
    file_name_dynamic = f"{safe_kw}_{datetime.now().date()}.xlsx"
    
    # Multi-Sheet Excel Writer
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        for kw, df in results.items():
            sheet_name = re.sub(r'[^a-zA-Z0-9 ]', '', kw)[:30]
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            worksheet = writer.sheets[sheet_name]
            worksheet.set_column(0, 0, 15)
            worksheet.set_column(1, 5, 25)
            worksheet.set_column(6, 6, 50)
            worksheet.set_column(7, 7, 50)
    
    st.download_button("💾 DOWNLOAD EXCEL", buffer.getvalue(), file_name_dynamic, "application/vnd.ms-excel")
