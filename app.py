import streamlit as st
import os
import glob
import re
import gc
import io
import requests

# --- 1. PROFESSIONAL UI CONFIGURATION ---
st.set_page_config(page_title="Recruiting Search Engine", page_icon="🏈", layout="wide")

# Custom CSS to hide technical details and make it look clean
st.markdown("""
    <style>
    .stProgress > div > div > div > div { background-color: #1f77b4; }
    .reportview-container { margin-top: -2em; }
    header {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

st.title("🏈 Football Recruiting Search Engine")
st.markdown("### National Coaching & Roster Database")

# --- 2. CONSTANTS & SETUP ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Verify Database (Silently)
chunk_files = glob.glob("chunk_*.csv")
if not chunk_files:
    st.error("⚠️ Database Error: Source files not found.")
    st.stop()

# --- 3. LAZY LOADING (The "Start Engine" Button) ---
if "engine_loaded" not in st.session_state:
    st.session_state["engine_loaded"] = False

if not st.session_state["engine_loaded"]:
    st.info("Database is offline. Click below to initialize the search engine.")
    if st.button("🚀 Initialize Database"):
        st.session_state["engine_loaded"] = True
        st.rerun()

# --- 4. CORE SEARCH LOGIC (Hidden until active) ---
if st.session_state["engine_loaded"]:
    import pandas as pd
    
    # --- A. MASTER DATABASE LOOKUP ---
    @st.cache_data(show_spinner=False)
    def load_master_lookup():
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
            
            def norm(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())

            for _, row in df.iterrows():
                s_key = norm(row.get('School', ''))
                n_key = norm(f"{row.get('First name', '')}{row.get('Last name', '')}")
                if n_key:
                    rec = {
                        'email': str(row.get(email_col, '')).strip() if email_col else "",
                        'twitter': str(row.get(twitter_col, '')).strip() if twitter_col else "",
                        'title': str(row.get(title_col, '')).strip() if title_col else "",
                        'school': str(row.get('School', '')).strip()
                    }
                    lookup[(s_key, n_key)] = rec
                    if n_key not in name_lookup: name_lookup[n_key] = []
                    name_lookup[n_key].append(rec)
            return lookup, name_lookup
        except: return {}, {}

    # --- B. SMART PARSER (The "Unknown" Killer) ---
    def parse_title_line(bio):
        """
        Extracts metadata from the 'Name - Title - School' line found in scraped bios.
        """
        extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
        
        # 1. Clean up bio to find the header line
        # The header usually comes right after the URL
        clean_bio = str(bio).replace('\r', '\n')
        lines = [L.strip() for L in clean_bio.split('\n') if L.strip()]
        
        # Look for the line with hyphens that isn't the URL
        header_line = None
        for line in lines[:10]: # Check first 10 lines only
            if " - " in line and "SOURCE" not in line and "http" not in line:
                header_line = line
                break
        
        if header_line:
            parts = [p.strip() for p in header_line.split(' - ')]
            
            # PATTERN 1: Name - Title - School (3 parts)
            if len(parts) >= 3:
                extracted['Name'] = parts[0]
                extracted['Title'] = parts[1]
                extracted['School'] = parts[2]
            
            # PATTERN 2: Name - School (2 parts)
            elif len(parts) == 2:
                extracted['Name'] = parts[0]
                extracted['School'] = parts[1]
                
            # SPECIAL: Player Pattern (Name - Year - Football - School)
            if "202" in str(extracted['Title']) or "Football" == extracted['Title']:
                extracted['Role'] = "PLAYER"
                extracted['Title'] = "Roster Member"
                
        return extracted

    def get_snippet(text, keyword):
        if pd.isna(text): return ""
        clean = str(text).replace('\n', ' ').replace('\r', ' ')
        m = re.search(re.escape(keyword), clean, re.IGNORECASE)
        if m:
            s, e = max(0, m.start()-60), min(len(clean), m.end()+60)
            return f"...{clean[s:e].strip()}..."
        return f"...{clean[:100]}..."

    # --- MAIN INTERFACE ---
    master_lookup, name_lookup = load_master_lookup()
    st.success("✅ Database Online & Ready")
    
    keywords_str = st.text_input("Enter Search Keywords:", placeholder="e.g. tallahassee, area recruiter, quarterback")
    
    if st.button("Run Search"):
        if not keywords_str:
            st.warning("Please enter a keyword to search.")
        else:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            results = []
            
            # Professional Progress Bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try: chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
            except: pass

            total_chunks = len(chunk_files)
            
            for i, file in enumerate(chunk_files):
                # Generic progress update
                status_text.caption(f"Scanning database sector {i+1}/{total_chunks}...")
                progress_bar.progress((i + 1) / total_chunks)
                
                try:
                    # Optimized Read
                    df_iter = pd.read_csv(file, chunksize=1000, on_bad_lines='skip') 
                    
                    for chunk in df_iter:
                        chunk.columns = [c.strip() for c in chunk.columns]
                        
                        # Normalize Columns
                        for c in chunk.columns:
                            if c.lower() in ['bio', 'full_bio', 'description', 'full bio']: 
                                chunk.rename(columns={c: 'Full_Bio'}, inplace=True)
                            if c.lower() == 'name': chunk.rename(columns={c: 'Name'}, inplace=True)
                            if c.lower() == 'school': chunk.rename(columns={c: 'School'}, inplace=True)
                            if c.lower() == 'title': chunk.rename(columns={c: 'Title'}, inplace=True)
                        
                        if 'Full_Bio' not in chunk.columns: continue
                        
                        # Search
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            
                            # --- ENRICHMENT LOGIC ---
                            def enrich_row(row):
                                # 1. Parse the Header Line (The fix for "Unknown")
                                meta = parse_title_line(row['Full_Bio'])
                                
                                # Only overwrite if current is Unknown/Empty
                                if pd.isna(row.get('Name')) or str(row.get('Name')) == "Unknown" or len(str(row.get('Name'))) < 3:
                                    if meta['Name']: row['Name'] = meta['Name']
                                
                                if pd.isna(row.get('School')) or str(row.get('School')) == "Unknown":
                                    if meta['School']: row['School'] = meta['School']
                                    
                                if pd.isna(row.get('Title')) or str(row.get('Title')) == "Unknown":
                                    if meta['Title']: row['Title'] = meta['Title']
                                
                                if meta['Role'] == "PLAYER": row['Role'] = "PLAYER"
                                else: row['Role'] = "COACH/STAFF"

                                # 2. Master DB Lookup
                                def n(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())
                                
                                s_norm = n(row.get('School', ''))
                                n_norm = n(row.get('Name', ''))
                                
                                match = master_lookup.get((s_norm, n_norm))
                                
                                # Backup Lookup
                                if not match:
                                    candidates = name_lookup.get(n_norm, [])
                                    # If extracted school is in bio, assume match
                                    if len(candidates) == 1: match = candidates[0]
                                
                                if match:
                                    row['School'] = match['school']
                                    row['Title'] = match['title']
                                    row['Email'] = match['email']
                                    row['Twitter'] = match['twitter']
                                
                                return row

                            found = found.apply(enrich_row, axis=1)
                            
                            # Clean up garbage rows
                            found = found[~found['Name'].str.contains("Skip To|Official|Website", case=False, na=False)]
                            
                            found['Context_Snippet'] = found['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                            results.append(found)
                        
                        del chunk
                    gc.collect()

                except: continue

            status_text.empty(); progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                
                # Selection & Ordering
                cols = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_cols = [c for c in cols if c in final_df.columns]
                final_df = final_df[final_cols]
                
                # Remove duplicates
                final_df.drop_duplicates(subset=['Name', 'School'], inplace=True)
                
                st.success(f"🎉 Found {len(final_df)} matches found.")
                st.dataframe(final_df)
                
                # Excel Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name="Results")
                st.download_button("💾 Download Results (Excel)", buffer.getvalue(), "Search_Results.xlsx", "application/vnd.ms-excel")
            else:
                st.warning("No matches found for your criteria.")
