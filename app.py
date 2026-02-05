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
    .status-box { text-align: center; font-weight: bold; padding: 10px; margin-bottom: 20px; border-radius: 10px; font-size: 0.9em; }
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

# EXPANDED ALIAS LIST (Applied to DB and Search)
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
                source = f"Local File"
            except: 
                try: df = pd.read_csv(possible_files[0], encoding='latin1')
                except: pass

    if df is None or df.empty:
        return {}, {}, {}, "Failed", []

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

    found_cols = []
    if c_school: found_cols.append("School")
    if c_email: found_cols.append("Email")
    if c_twitter: found_cols.append("Twitter")

    lookup, name_lookup, lastname_lookup = {}, {}, {}

    for _, row in df.iterrows():
        raw_school = str(row[c_school]).strip() if c_school and pd.notna(row[c_school]) else ""
        
        # APPLY ALIASES TO DB (Crucial for FSU -> Florida State)
        for alias, real in SCHOOL_ALIASES.items():
            if alias.lower() == raw_school.lower(): raw_school = real
        
        first = str(row[c_first]).strip() if c_first and pd.notna(row[c_first]) else ""
        last = str(row[c_last]).strip() if c_last and pd.notna(row[c_last]) else ""
        
        if raw_school and (first or last):
            full_name = f"{first} {last}".strip()
            email = str(row[c_email]).strip() if c_email and pd.notna(row[c_email]) else ""
            twitter = str(row[c_twitter]).strip() if c_twitter and pd.notna(row[c_twitter]) else ""
            title = str(row[c_title]).strip() if c_title and pd.notna(row[c_title]) else ""
            
            rec = {'email': email, 'twitter': twitter, 'title': title, 'school': raw_school, 'name': full_name}
            
            s_key = normalize_text(raw_school)
            n_key = normalize_text(full_name)
            l_key = normalize_text(last)
            
            lookup[(s_key, n_key)] = rec
            
            if n_key not in name
