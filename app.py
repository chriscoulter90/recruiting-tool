import streamlit as st
import pandas as pd
import os
import glob
import gc
import re
import io
from datetime import datetime
import requests

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Recruiting Search Debugger", page_icon="🛠️", layout="wide")

st.title("🛠️ Diagnostic Mode")
st.write("If you see this, the App has started successfully!")

# --- 2. CHECKPOINT: FILES ---
st.write("### Step 1: Checking Files...")
chunk_files = glob.glob("chunk_*.csv")
st.write(f"Found {len(chunk_files)} chunk files in the main folder.")

if len(chunk_files) == 0:
    st.error("❌ CRITICAL: No 'chunk_*.csv' files found. Please upload them to the main folder.")
    st.stop()
else:
    st.success(f"✅ Found {len(chunk_files)} chunks (e.g., {chunk_files[0]})")

# --- 3. CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Fix regex with raw strings (r"")
ROLE_PATTERNS = [
    (r"Title[:\s]+Tight Ends Coach", "Tight Ends Coach"),
    (r"Title[:\s]+Linebackers Coach", "Linebackers Coach"),
    (r"Title[:\s]+Quarterbacks Coach", "Quarterbacks Coach"),
    (r"Head Coach", "Head Coach"),
    (r"Defensive Coordinator", "Defensive Coordinator"),
    (r"Offensive Coordinator", "Offensive Coordinator"),
    (r"Special Teams Coordinator", "Special Teams Coordinator"),
    (r"Linebackers", "Linebackers Coach"),
    (r"Quarterbacks", "Quarterbacks Coach"),
    (r"Running Backs", "Running Backs Coach"),
    (r"Wide Receivers", "Wide Receivers Coach"),
    (r"Defensive Line", "Defensive Line Coach"),
    (r"Offensive Line", "Offensive Line Coach"),
    (r"Tight Ends", "Tight Ends Coach"),
    (r"Defensive Backs", "Defensive Backs Coach"),
    (r"Safeties", "Safeties Coach"),
    (r"Cornerbacks", "Cornerbacks Coach"),
    (r"General Manager", "General Manager"),
    (r"Director of Player Personnel", "Director of Player Personnel"),
    (r"Director of Recruiting", "Director of Recruiting"),
    (r"Recruiting Coordinator", "Recruiting Coordinator"),
    (r"Analyst", "Analyst"),
    (r"Graduate Assistant", "Graduate Assistant")
]

FORBIDDEN_SPORTS = [
    "Volleyball", "Baseball", "Softball", "Soccer", "Tennis", "Golf", 
    "Swimming", "Lacrosse", "Hockey", "Wrestling", "Gymnastics", 
    "Basketball", "Track & Field", "Crew", "Rowing", "Sailing", 
    "Acrobatics", "Tumbling", "Cheerleading", "Fencing", "Spirit Squad",
    "Women's Basketball", "Men's Basketball"
]

GARBAGE_NAMES = [
    "Skip To", "Main Content", "Print=True", "Schedule", "2024", "2025", "2026",
    "Football Roster", "Statistics", "Contact Ticket Office", "Gameday App", 
    "Ticket Office", "Roster", "Staff Directory", "Composite"
]

SCHOOL_CORRECTIONS = {
    "Boston": "Boston College",
    "Miami": "Miami (FL)",
    "Ole": "Ole Miss",
    "Central Methodist": "Central Methodist University",
    "University of Auburn": "Auburn University"
}

GOLD_CONTEXT_TERMS = ["native of", "hometown", "born in", "raised in", "from", "attended", "graduate of", "graduated from", "high school", "coached at", "recruiting"]

# --- 4. FUNCTIONS ---

def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data
def load_master_lookup():
    try:
        if not os.path.exists(MASTER_DB_FILE):
            try:
                r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=5)
                with open(MASTER_DB_FILE, 'wb') as f: f.write(r.content)
            except: pass
        
        try:
            master_df = pd.read_csv(MASTER_DB_FILE, encoding='utf-8')
        except UnicodeDecodeError:
            master_df = pd.read_csv(MASTER_DB_FILE, encoding='latin1')
            
        lookup = {}
        name_lookup = {} 
        
        email_col = next((c for c in master_df.columns if 'Email' in c), None)
        twitter_col = next((c for c in master_df.columns if 'Twitter' in c), None)
        title_col = next((c for c in master_df.columns if 'Title' in c or 'Position' in c or 'Role' in c), None)

        for _, row in master_df.iterrows():
            s_key = normalize_text(row.get('School', ''))
            n_key = normalize_text(f"{row.get('First name', '')}{row.get('Last name', '')}")
            if n_key:
                record = {
                    'email': str(row.get(email_col, '')).strip() if email_col else "",
                    'twitter': str(row.get(twitter_col, '')).strip() if twitter_col else "",
                    'title': str(row.get(title_col, '')).strip() if title_col else "",
                    'school': str(row.get('School', '')).strip()
                }
                lookup[(s_key, n_key)] = record
                if n_key not in name_lookup: name_lookup[n_key] = []
                name_lookup[n_key].append(record)
        return lookup, name_lookup
    except Exception as e:
        return {}, {}

def get_snippet(text, keyword):
    if pd.isna(text) or text == "": return ""
    clean_text = str(text).replace('\n', ' ').replace('\r', ' ')
    for term in GOLD_CONTEXT_TERMS:
        pattern = re.compile(f"({term}.{{0,60}}{re.escape(keyword)}|{re.escape(keyword)}.{{0,60}}{term})", re.IGNORECASE)
        m = pattern.search(clean_text)
        if m:
            s, e = max(0, m.start()-40), min(len(clean_text), m.end()+40)
            return f"...{clean_text[s:e].strip()}..."
    m = re.search(re.escape(keyword), clean_text, re.IGNORECASE)
    if m:
        s, e = max(0, m.start()-70), min(len(clean_text), m.end()+70)
        return f"...{clean_text[s:e].strip()}..."
    return f"...{clean_text[:140]}..."

def clean_row_logic(row):
    for col in row.index:
        if isinstance(row[col], str):
            row[col] = str(row[col]).replace('’', "'").replace('‘', "'").replace('\n', ' ').replace('\r', ' ').strip()
    
    name = str(row.get('Name', '')).strip()
    title = str(row.get('Title', '')).strip()
    school = str(row.get('School', '')).strip()
    bio = str(row.get('Full_Bio', '')).strip()
    role = str(row.get('Role', '')).strip().upper()

    if name.isdigit() or "Skip To Main Content" in title or any(g in name for g in GARBAGE_NAMES):
        row['Name'] = "DELETE_ME"; return row

    # Fix School
    if school in SCHOOL_CORRECTIONS: school = SCHOOL_CORRECTIONS[school]
    
    # Fix Role
    GENERIC_TITLES = ["Football Coach", "Coach", "Staff", "Assistant Coach", "Football Staff", "Bio", "Profile", "Football", "", "Unknown"]
    if role != "PLAYER":
        if not title or any(g.lower() == title.lower() for g in GENERIC_TITLES):
            found_role = False
            for pat, rep in ROLE_PATTERNS:
                if re.search(pat, bio[:3000], re.IGNORECASE):
                    title = rep; found_role = True; break
            if not found_role: title = "Football Staff"

    t_low = title.lower()
    if role == "UNCERTAIN" or role == "NAN" or not role:
        if any(x in t_low for x in ["coach", "coordinator", "director", "assistant", "staff", "analyst", "manager"]): role = "COACH/STAFF"
        elif any(x in t_low for x in ["roster", "player"]): role = "PLAYER"
        elif t_low == "unknown": role = "UNCERTAIN"
        else: role = "COACH/STAFF"

    row['Role'] = role
    row['Name'], row['Title'], row['School'] = name.title(), title, school
    return row

def process_search_streaming(master_lookup, name_lookup, keywords):
    chunk_files = glob.glob("chunk_*.csv")
    try:
        chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
    except:
        pass 

    all_clean = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_chunks = len(chunk_files)

    for i, filename in enumerate(chunk_files):
        status_text.text(f"Scanning chunk {i+1} of {total_chunks} ({filename})...")
        progress_bar.progress((i + 1) / total_chunks)
        
        try:
            # OPTIMIZATION: Read only strictly necessary columns to save RAM
            # We don't know exact column names, so we read header first
            header_df = pd.read_csv(filename, nrows=0)
            clean_cols = [c.strip() for c in header_df.columns]
            
            # Map weird column names to standard ones
            col_map = {}
            possible_bios = ['Bio', 'bio', 'Full Bio', 'Description', 'About', 'Full_Bio']
            for c in clean_cols:
                if c in possible_bios: col_map[c] = 'Full_Bio'
                if c.lower() == 'name': col_map[c] = 'Name'
                if c.lower() == 'school': col_map[c] = 'School'
                if c.lower() == 'title': col_map[c] = 'Title'
            
            # Only load what we need
            use_cols = list(col_map.keys())
            if not use_cols:
                # Fallback: Read everything if we can't guess (riskier for memory)
                df_chunk = pd.read_csv(filename, header=0).fillna("")
            else:
                df_chunk = pd.read_csv(filename, usecols=use_cols, header=0).fillna("")
            
            # Rename columns
            df_chunk.columns = [c.strip() for c in df_chunk.columns]
            df_chunk.rename(columns=col_map, inplace=True)
            
            if 'Full_Bio' not in df_chunk.columns:
                del df_chunk; gc.collect(); continue

            # Create missing columns if needed
            if 'Name' not in df_chunk.columns: df_chunk['Name'] = "Unknown"
            if 'School' not in df_chunk.columns: df_chunk['School'] = "Unknown"
            if 'Title' not in df_chunk.columns: df_chunk['Title'] = "Unknown"
            if 'Role' not in df_chunk.columns: df_chunk['Role'] = "UNCERTAIN"

            # SEARCH
            for key in keywords:
                mask = df_chunk['Full_Bio'].str.contains(key, case=False, na=False)
                results = df_chunk[mask].copy()
                
                if not results.empty:
                    results = results.apply(clean_row_logic, axis=1)
                    results = results[results['Name'] != "DELETE_ME"]
                    results['Context_Snippet'] = results['Full_Bio'].apply(lambda x: get_snippet(x, key))
                    
                    # Enrich (Simplified for speed)
                    def enrich(row):
                        s_key, n_key = normalize_text(row['School']), normalize_text(row['Name'])
                        match = master_lookup.get((s_key, n_key))
                        if match:
                            if not row.get('Email'): row['Email'] = match['email']
                            if not row.get('Twitter'): row['Twitter'] = match['twitter']
                        if not row.get('Twitter'):
                             tw_match = re.search(r"twitter\.com/([a-zA-Z0-9_]+)", str(row['Full_Bio']), re.IGNORECASE)
                             if tw_match: row['Twitter'] = f"@{tw_match.group(1)}"
                        return row

                    if 'Email' not in results.columns: results['Email'] = ""
                    if 'Twitter' not in results.columns: results['Twitter'] = ""
                    
                    results = results.apply(enrich, axis=1)
                    clean_df = results.copy()
                    
                    if not clean_df.empty:
                        clean_df['Search_Term'] = key
                        all_clean.append(clean_df)

            del df_chunk
            gc.collect()

        except Exception as e:
            print(f"Skipping bad chunk {filename}: {e}")
            continue

    status_text.empty()
    progress_bar.empty()

    if all_clean:
        final_df = pd.concat(all_clean)
        final_df.drop_duplicates(subset=['Name', 'School'], keep='first', inplace=True)
        cols_to_keep = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
        final_cols = [c for c in cols_to_keep if c in final_df.columns]
        return final_df[final_cols]
    
    return pd.DataFrame()

# --- 5. SEARCH INTERFACE ---
st.write("### Step 2: Search Engine")

master_lookup, name_lookup = load_master_lookup()
st.write("✅ Reference data loaded.")

search_input = st.text_input("Enter Keywords (comma separated):", placeholder="e.g. tallahassee, atlanta, dallas")

if st.button("Run Search"):
    if not search_input:
        st.warning("Please enter at least one keyword.")
    else:
        keywords = [k.strip() for k in search_input.split(',') if k.strip()]
        
        with st.spinner(f"Searching for: {', '.join(keywords)}..."):
            results_df = process_search_streaming(master_lookup, name_lookup, keywords)
        
        if not results_df.empty:
            st.subheader(f"Found {len(results_df)} Matches")
            st.dataframe(results_df)
            
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                results_df.to_excel(writer, index=False, sheet_name="Results")
            
            st.download_button(
                label="💾 Download Excel File",
                data=buffer.getvalue(),
                file_name=f"Search_Results_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.info("No matches found.")
