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
    /* Make all table columns the same width - no text wrapping, normal row height */
    .stDataFrame table {
        table-layout: fixed;
        width: 100%;
    }
    .stDataFrame table th,
    .stDataFrame table td {
        width: 12.5%; /* Equal width for 8 display columns */
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        max-height: 30px !important;
        height: 30px !important;
        line-height: 30px !important;
        padding: 5px 8px !important;
        vertical-align: middle !important;
    }
    .stDataFrame table tr {
        height: 30px !important;
        max-height: 30px !important;
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

# Load all chunk files into a single DataFrame
@st.cache_data(show_spinner=False)
def load_chunk_data():
    """Load all chunk_*.csv files and merge them into one DataFrame"""
    chunk_files = glob.glob("chunk_*.csv")
    if not chunk_files:
        return pd.DataFrame()
    
    # Sort files numerically
    try:
        chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
    except:
        chunk_files.sort()
    
    all_chunks = []
    for file in chunk_files:
        try:
            df = pd.read_csv(file, dtype=str, on_bad_lines='skip')
            all_chunks.append(df)
        except Exception as e:
            st.warning(f"⚠️ Error loading {file}: {str(e)}")
            continue
    
    if all_chunks:
        merged_df = pd.concat(all_chunks, ignore_index=True)
        merged_df.fillna("", inplace=True)
        return merged_df
    return pd.DataFrame()

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
    "FSU": "Florida State", "Seminoles": "Florida State", "Florida St": "Florida State",
    "Miami": "Miami (FL)", "Hurricanes": "Miami (FL)"
}

def normalize_school_for_match(school):
    """Normalize school name, applying aliases, for better matching."""
    if not school or school == "Unknown": return ""
    s = str(school).strip()
    # Apply aliases
    for alias, real_name in SCHOOL_ALIASES.items():
        if alias.lower() in s.lower(): return real_name
    return s

# --- 3. HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data(show_spinner=False)
def load_lookup():
    """Load 10k coach database from live Google Sheet (preferred) or local CSV."""
    try:
        df = None
        # Prefer live 10k coach database from Google Sheet
        try:
            r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=15)
            if r.ok and len(r.content) > 100:
                df = pd.read_csv(io.BytesIO(r.content), encoding='utf-8')
        except Exception:
            pass
        if df is None and os.path.exists(MASTER_DB_FILE):
            try: df = pd.read_csv(MASTER_DB_FILE, encoding='utf-8')
            except: df = pd.read_csv(MASTER_DB_FILE, encoding='latin1')
        if df is None:
            return {}, {}
        # Case-insensitive column map (10k sheet may use "First Name", "Twitter", etc.)
        col_map = {str(c).strip().lower(): c for c in df.columns}
        def get_col(row, *names):
            for n in names:
                k = str(n).strip().lower()
                if k in col_map:
                    return row.get(col_map[k], '')
                if n in row: return row.get(n, '')
            return ''
        lookup, name_lookup = {}, {}
        # Find Twitter/X handle column - avoid column literally named "X" (single letter)
        twitter_col = None
        for col in df.columns:
            c = str(col).strip()
            if len(c) == 1: continue  # Skip column literally named "X"
            if c.lower() in ('twitter', 'twitter handle', 'x handle', 'x (twitter)'):
                twitter_col = col
                break
            if 'twitter' in c.lower() or ('handle' in c.lower() and 'x' in c.lower()):
                twitter_col = col
                break
        if not twitter_col:
            for col in df.columns:
                if len(str(col).strip()) > 1 and 'twitter' in str(col).lower():
                    twitter_col = col
                    break
        if not twitter_col:
            twitter_col = 'Twitter'
        
        for _, row in df.iterrows():
            s_raw = clean_master_value(get_col(row, 'School', 'school'), min_len=2) or str(get_col(row, 'School', 'school')).strip()
            first = clean_master_value(get_col(row, 'First name', 'First Name', 'first name')) or str(get_col(row, 'First name', 'First Name')).strip()
            last = clean_master_value(get_col(row, 'Last name', 'Last Name', 'last name')) or str(get_col(row, 'Last name', 'Last Name')).strip()
            n_key = normalize_text(first + last)
            if n_key:
                raw_twitter = row.get(twitter_col, '')
                twitter_val = clean_master_value(raw_twitter, min_len=3)  # Real handles are at least 3 chars
                if not twitter_val and raw_twitter is not None:
                    t = str(raw_twitter).strip()
                    if t and t.lower() not in ('nan', 'na', 'x', '-') and len(t) >= 3:
                        if t.startswith('@'): t = t[1:]
                        if t: twitter_val = t
                email_val = clean_master_value(get_col(row, 'Email address', 'Email', 'email'), min_len=5)
                title_val = clean_master_value(get_col(row, 'Title', 'title'), min_len=2)
                name_val = f"{first} {last}".strip() if (first or last) else None
                school_raw = s_raw or str(get_col(row, 'School', 'school')).strip()
                rec = {'email': email_val, 'twitter': twitter_val, 'title': title_val, 'school': school_raw, 'name': name_val}
                s_key = normalize_text(s_raw)
                lookup[(s_key, n_key)] = rec
                lookup[(s_key, normalize_text(last + first))] = rec  # "Last First" variant
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(rec)
                if normalize_text(last + first) != n_key:
                    if normalize_text(last + first) not in name_lookup: name_lookup[normalize_text(last + first)] = []
                    name_lookup[normalize_text(last + first)].append(rec)
        return lookup, name_lookup
    except: return {}, {}

def clean_master_value(val, min_len=1):
    """Return cleaned value from master DB; treat NaN, 'nan', 'X', 'N/A', etc. as empty."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    s = str(val).strip()
    if not s or len(s) < min_len:
        return ""
    lower = s.lower()
    if lower in ("nan", "na", "n/a", "none", "-", "x", "xx", "xxx", ".", "—", "–"):
        return ""
    if lower == "x" or (len(s) == 1 and s.isalpha()):
        return ""
    return s

def name_variants(name):
    """Return list of normalized name variants to try (e.g. 'John Smith' -> ['johnsmith', 'smithjohn'])."""
    if not name or pd.isna(name): return []
    s = str(name).strip()
    parts = re.split(r'[\s,]+', s)
    parts = [p for p in parts if p]
    if not parts: return [normalize_text(s)]
    variants = [normalize_text(s), normalize_text(''.join(parts))]
    if len(parts) >= 2:
        variants.append(normalize_text(parts[-1] + parts[0]))  # LastFirst
        variants.append(normalize_text(''.join(reversed(parts))))
        # Also try just last name (for cases where first name might be missing or different)
        if len(parts[-1]) > 2:  # Last name is substantial
            variants.append(normalize_text(parts[-1]))  # Just last name
    return list(dict.fromkeys(variants))

def best_match_from_master(school, name, lookup, name_lookup):
    """Best match from master DB: try (school, name variants), then name-only with school match. Returns rec dict or None."""
    if not name: return None
    # Normalize school and apply aliases
    normalized_school = normalize_school_for_match(school)
    s_key = normalize_text(normalized_school if normalized_school else school)
    
    # Get all name variants to try
    name_vars = name_variants(name)
    
    # Try exact (school, name) matches first - most reliable
    for n_var in name_vars:
        rec = lookup.get((s_key, n_var))
        if rec: return rec
    
    # If school is Unknown or empty, try name-only match
    if not school or school == "Unknown":
        for n_var in name_vars:
            cands = name_lookup.get(n_var, [])
            if cands: return cands[0]  # Return first if no school to match
        return None
    
    # Try name-only matches, prefer school match
    best_match = None
    for n_var in name_vars:
        cands = name_lookup.get(n_var, [])
        if cands:
            # Prefer exact school match
            for rec in cands:
                rec_school_raw = rec.get('school', '')
                rec_school_normalized = normalize_school_for_match(rec_school_raw)
                rec_s_key = normalize_text(rec_school_normalized if rec_school_normalized else rec_school_raw)
                if rec_s_key == s_key: return rec  # Exact match - return immediately
            # Try partial school match (e.g., "Florida State" matches "FSU")
            for rec in cands:
                rec_school_raw = rec.get('school', '')
                rec_school_normalized = normalize_school_for_match(rec_school_raw)
                rec_s_key = normalize_text(rec_school_normalized if rec_school_normalized else rec_school_raw)
                if rec_s_key and (rec_s_key in s_key or s_key in rec_s_key):
                    if not best_match: best_match = rec  # Keep first partial match
            # If no match yet, keep first candidate as fallback
            if not best_match and cands:
                best_match = cands[0]
    
    return best_match

if "master_data" not in st.session_state:
    st.session_state["master_data"] = load_lookup()
master_lookup, name_lookup = st.session_state["master_data"]

# Load chunk data into session state
if "chunk_data" not in st.session_state:
    with st.spinner("Loading database files..."):
        st.session_state["chunk_data"] = load_chunk_data()
chunk_data = st.session_state["chunk_data"]

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

def collapse_to_one_line(text):
    """Collapse all newlines, carriage returns, and multiple spaces to a single line."""
    if pd.isna(text): return ""
    s = str(text).replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    s = re.sub(r'\s+', ' ', s)  # multiple spaces/tabs -> single space
    return s.strip()

def get_snippet(text, keyword):
    if pd.isna(text): return ""
    clean = str(text).replace('\n', ' ').replace('\r', ' ')
    clean = re.sub(r'\s+', ' ', clean)
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
        submit_button = st.form_submit_button(label='Search')

# Only run search when button is clicked
if submit_button:
    if not keywords_str or not keywords_str.strip():
        st.warning("⚠️ Please enter a keyword.")
        st.session_state.search_results = None
    elif chunk_data.empty:
        st.error("❌ Critical Error: No database files found.")
        st.session_state.search_results = None
    else:
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        if not keywords:
            st.warning("⚠️ Please enter a valid keyword.")
            st.session_state.search_results = None
        else:
            # Show loading spinner immediately
            with st.spinner("🔍 Searching database..."):
                # Search in the pre-loaded DataFrame
                progress_bar = st.progress(0)
                try:
                    # Create search pattern - escape special regex characters and join with |
                    search_pattern = '|'.join([re.escape(k) for k in keywords])
                    mask = chunk_data['Full_Bio'].str.contains(search_pattern, case=False, na=False, regex=True)
                    
                    if mask.any():
                        found = chunk_data[mask].copy()
                        progress_bar.progress(0.5)
                        
                        def enrich_row(row):
                            meta = parse_header_smart(row['Full_Bio'])
                            name = row.get('Name', '')
                            if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] or name
                            if any(bad.lower() in str(name).lower() for bad in BAD_NAMES): return None
                            
                            title, school = meta['Title'] or "Staff", meta['School'] or "Unknown"
                            header_check = (str(title) + " " + str(school)).lower()
                            for poison in POISON_PILLS_HEADER:
                                if poison.lower() in header_check: return None

                            # Only include Football (exclude other sports)
                            detected_sport = detect_sport_context(row['Full_Bio'])
                            if detected_sport != "Football" and detected_sport != "Uncertain": return None

                            # Classify role: COACH/STAFF first, PLAYER second, Uncertain last
                            role = meta['Role']
                            is_player = (role == "PLAYER" or detect_player_by_context(row['Full_Bio'], title))
                            if is_player:
                                role = "PLAYER"
                                if title in ["Staff", "Unknown"] or not title: title = "Roster Member"
                            else:
                                # Extract title from bio if not found in header
                                if title in ["Staff", "Unknown"] or not title:
                                    scavenged = extract_title_from_text(row['Full_Bio'])
                                    title = scavenged if scavenged != "Staff" else "Staff"
                                if title in ["Staff", "Unknown"] or not title:
                                    role = "Uncertain"
                                else:
                                    role = "COACH/STAFF"

                            # Fill gaps from master DB (10k coaches: titles, emails, X/Twitter handles, names)
                            match = best_match_from_master(school, name, master_lookup, name_lookup)
                            email = ""
                            twitter = ""
                            if match:
                                # Only fill with real values - never "X", "nan", "N/A", etc.
                                master_email = clean_master_value(match.get('email', ''), min_len=5)
                                if master_email: email = master_email
                                master_twitter = clean_master_value(match.get('twitter', ''), min_len=3)
                                if master_twitter: twitter = master_twitter
                                if not title or title in ["Staff", "Unknown"]:
                                    master_title = clean_master_value(match.get('title', ''), min_len=2)
                                    if master_title: title = master_title
                                if not school or school == "Unknown":
                                    master_school = clean_master_value(match.get('school', ''), min_len=2)
                                    if master_school: school = master_school
                                if not name or len(name) < 3:
                                    master_name = clean_master_value(match.get('name', ''), min_len=2)
                                    if master_name: name = master_name
                            # Fallback: try bio for title again if still missing
                            if title in ["Staff", "Unknown"] or not title:
                                scavenged = extract_title_from_text(row['Full_Bio'])
                                if scavenged != "Staff": title = scavenged

                            sport_val = "Football"
                            return pd.Series([role, name, title, school, sport_val, email, twitter, row['Full_Bio']])

                        enriched = found.apply(enrich_row, axis=1)
                        enriched.dropna(how='all', inplace=True)
                        progress_bar.progress(0.9)
                        
                        if not enriched.empty:
                            enriched.columns = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Full_Bio']
                            # Collapse Full_Bio to one line (no newlines/spaces) so Excel rows stay normal height
                            enriched['Full_Bio'] = enriched['Full_Bio'].apply(collapse_to_one_line)
                            enriched['Context_Snippet'] = enriched['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                            final_df = enriched.drop_duplicates(subset=['Name', 'School'])
                            # Never export "nan" or "X" in Email/Twitter - fill with empty string
                            for col in ('Email', 'Twitter'):
                                if col in final_df.columns:
                                    final_df[col] = final_df[col].apply(
                                        lambda v: "" if (pd.isna(v) or str(v).strip().lower() in ('nan', 'na', 'x', '-')) else str(v).strip()
                                    )
                            # Sort by role: coaches/staff first, players second, uncertain last; then School, Name
                            role_order = {"COACH/STAFF": 0, "PLAYER": 1, "Uncertain": 2}
                            final_df["_role_sort"] = final_df["Role"].map(lambda r: role_order.get(str(r).upper(), 2))
                            final_df.sort_values(by=["_role_sort", "School", "Name"], ascending=[True, True, True], inplace=True)
                            final_df.drop(columns=["_role_sort"], inplace=True)
                            # Display columns without Full_Bio (but keep it for Excel export)
                            display_cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet']
                            st.session_state.search_results = final_df[display_cols + ['Full_Bio']]  # Keep Full_Bio for export
                            st.session_state.search_results_display = final_df[display_cols]  # Display without Full_Bio
                            st.session_state.search_filename = f"{keywords[0].replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
                        else:
                            st.session_state.search_results = None
                            st.warning("No matches found.")
                    else:
                        st.session_state.search_results = None
                        st.warning("No matches found.")
                    
                    progress_bar.progress(1.0)
                    progress_bar.empty()
                except Exception as e:
                    st.error(f"❌ Error during search: {str(e)}")
                    st.session_state.search_results = None
                    progress_bar.empty()

# --- 6. DISPLAY ---
if st.session_state.search_results is not None:
    st.success(f"🎉 Found {len(st.session_state.search_results)} matches.")
    # Display dataframe without Full_Bio column, with uniform column widths
    display_df = st.session_state.get('search_results_display', st.session_state.search_results.drop(columns=['Full_Bio'], errors='ignore'))
    st.dataframe(
        display_df, 
        use_container_width=True,
        hide_index=True
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        # Export with Full_Bio but set equal column widths for display columns
        export_df = st.session_state.search_results.copy()
        export_df.to_excel(writer, index=False, sheet_name="Results")
        worksheet = writer.sheets["Results"]
        
        # Set equal column widths for all display columns
        display_cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet']
        col_width = 15  # Equal width for all display columns (smaller to prevent wrapping)
        
        # Create format without text wrapping - single line height
        cell_format = writer.book.add_format({
            'text_wrap': False, 
            'valign': 'top',
            'shrink': True  # Shrink text to fit
        })
        
        # Set equal widths for display columns
        for col in display_cols:
            if col in export_df.columns:
                col_idx = list(export_df.columns).index(col)
                worksheet.set_column(col_idx, col_idx, col_width, cell_format)
        
        # Set Full_Bio column to wider width if it exists (but still no wrap)
        if 'Full_Bio' in export_df.columns:
            full_bio_idx = list(export_df.columns).index('Full_Bio')
            worksheet.set_column(full_bio_idx, full_bio_idx, 30, cell_format)
        
        # Set row heights to normal size (15 = normal height)
        for row_num in range(1, len(export_df) + 1):
            worksheet.set_row(row_num, 15)
        
    st.download_button("💾 DOWNLOAD RESULTS (EXCEL)", buffer.getvalue(), st.session_state.search_filename, "application/vnd.ms-excel", type="primary")
