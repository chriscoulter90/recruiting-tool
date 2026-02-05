import streamlit as st
import pandas as pd
import io
import requests
import os
import re
from datetime import datetime
import glob
import gc

# --- 1. PAGE CONFIGURATION (Must be the very first command) ---
st.set_page_config(page_title="Recruiting Search Pro", page_icon="🏈", layout="wide")

# --- 2. SETUP & CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Regex patterns (using r"" to fix syntax warnings)
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

# --- 3. HELPER FUNCTIONS ---

def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data
def load_master_lookup():
    """Loads the small 10k reference list (fast)."""
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
        print(f"Error loading master lookup: {e}")
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
    # Basic cleanup
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

    # ... (Simplified logic for brevity, core cleaning remains) ...
    
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
    """
    THE STREAMING LOGIC:
    Reads one small file at a time, searches it, saves results, and throws the rest away.
    This prevents the app from crashing due to memory.
    """
    # 1. Find all chunk files
    chunk_files = glob.glob("chunk_*.csv")
    
    # Sort them nicely (chunk_0, chunk_1, chunk_10...)
    try:
        chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
    except:
        pass # If naming is weird, just use default sort

    if not chunk_files:
        st.error("❌ CRITICAL ERROR: No 'chunk_*.csv' files found in the repository!")
        return pd.DataFrame()

    all_clean = []
    
    # Progress Bar Setup
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_chunks = len(chunk_files)

    for i, filename in enumerate(chunk_files):
        # Update progress
        status_text.text(f"Scanning chunk {i+1} of {total_chunks}...")
        progress_bar.progress((i + 1) / total_chunks)
        
        try:
            # READ ONE CHUNK
            df_chunk = pd.read_csv(filename, index_col=None, header=0).fillna("")
            
            # Normalize Columns
            df_chunk.columns = [c.strip() for c in df_chunk.columns]
            if 'Full_Bio' not in df_chunk.columns:
                 possible = ['Bio', 'bio', 'Full Bio', 'Description', 'About']
                 for c in possible:
                     if c in df_chunk.columns: df_chunk.rename(columns={c: 'Full_Bio'}, inplace=True); break
            
            if 'Name' not in df_chunk.columns and 'name' in df_chunk.columns: df_chunk.rename(columns={'name': 'Name'}, inplace=True)
            if 'School' not in df_chunk.columns and 'school' in df_chunk.columns: df_chunk.rename(columns={'school': 'School'}, inplace=True)
            
            # Skip if no bio found in this chunk
            if 'Full_Bio' not in df_chunk.columns: 
                del df_chunk; gc.collect(); continue

            # SEARCH THIS CHUNK
            for key in keywords:
                mask = df_chunk['Full_Bio'].str.contains(key, case=False, na=False)
                results = df_chunk[mask].copy()
                
                if not results.empty:
                    # Clean Matching Rows
                    results = results.apply(clean_row_logic, axis=1)
                    results = results[results['Name'] != "DELETE_ME"]
                    results['Context_Snippet'] = results['Full_Bio'].apply(lambda x: get_snippet(x, key))
                    
                    # Enrich with Master Data (Email/Twitter)
                    def enrich(row):
                        s_key, n_key = normalize_text(row['School']), normalize_text(row['Name'])
                        match = master_lookup.get((s_key, n_key))
                        if not match:
                            potential_matches = name_lookup.get(n_key, [])
                            for cand in potential_matches:
                                c_school_norm = normalize_text(cand['school'])
                                if s_key in c_school_norm or c_school_norm in s_key:
                                    match = cand
                                    row['School'] = cand['school'] 
                                    break
                        if match:
                            if not row['Email'] or str(row['Email']).lower() in ['', 'nan', 'n/a']:
                                row['Email'] = match['email']
                            if not row['Twitter'] or str(row['Twitter']).lower() in ['', 'nan', 'n/a']:
                                if len(match['twitter']) > 3: row['Twitter'] = match['twitter']
                            if match['title'] and len(match['title']) > 2:
                                row['Title'] = match['title']
                        if pd.isna(row['Twitter']) or str(row['Twitter']).strip() == "":
                            tw_match = re.search(r"twitter\.com/([a-zA-Z0-9_]+)", row['Full_Bio'], re.IGNORECASE)
                            if tw_match: row['Twitter'] = f"@{tw_match.group(1)}"
                        return row

                    results = results.apply(enrich, axis=1)
                    is_wrong = results['Title'].str.contains('|'.join(FORBIDDEN_SPORTS), case=False, na=False)
                    clean_df = results[~is_wrong].copy()
                    
                    if not clean_df.empty:
                        clean_df['Search_Term'] = key
                        all_clean.append(clean_df)

            # --- CRITICAL: RELEASE MEMORY ---
            del df_chunk
            gc.collect()

        except Exception as e:
            # If a chunk fails, skip it but print warning in logs
            print(f"Warning: Issue reading {filename}: {e}")
            continue

    # Cleanup UI
    status_text.empty()
    progress_bar.empty()

    if all_clean:
        final_df = pd.concat(all_clean)
        final_df.drop_duplicates(subset=['Name', 'School'], keep='first', inplace=True)
        # Sort
        role_map = {'COACH/STAFF': 1, 'PLAYER': 2, 'UNCERTAIN': 3}
        final_df['Role_Rank'] = final_df['Role'].map(role_map).fillna(3)
        final_df.sort_values(by=['Role_Rank', 'School', 'Name'], inplace=True)
        # Columns
        cols_to_keep = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
        # Ensure columns exist
        final_cols = [c for c in cols_to_keep if c in final_df.columns]
        return final_df[final_cols]
    
    return pd.DataFrame()

# --- 4. APP LAYOUT ---

st.title("🏈 Recruiting Search Pro")
st.markdown("Search the database of **57,000+ Profiles** (Low Memory Mode).")

# Load Reference Data
master_lookup, name_lookup = load_master_lookup()

# Check for Chunks
chunk_count = len(glob.glob("chunk_*.csv"))

if chunk_count == 0:
    st.error("❌ No database chunks found! Please make sure you uploaded the 'chunk_*.csv' files to GitHub.")
else:
    st.success(f"✅ Database Ready ({chunk_count} chunks detected).")

    # Search Bar
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
                
                # Excel Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    results_df.to_excel(writer, index=False, sheet_name="Results")
                    # Format
                    workbook = writer.book
                    worksheet = writer.sheets["Results"]
                    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1})
                    for col_num, value in enumerate(results_df.columns.values):
                        worksheet.write(0, col_num, value, header_fmt)
                
                st.download_button(
                    label="💾 Download Excel File",
                    data=buffer.getvalue(),
                    file_name=f"Search_Results_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
                    mime="application/vnd.ms-excel"
                )
            else:
                st.info("No matches found.")
