import streamlit as st
import os
import glob
import re
import gc
import io
from datetime import datetime
import requests

# 1. LIGHTWEIGHT STARTUP
st.set_page_config(page_title="Recruiting Search", layout="wide")
st.title("🏈 Recruiting Tool - Deep Extraction Mode")
st.write("### ✅ System Status: ONLINE")

# 2. CONSTANTS
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# 3. VERIFY FILES
chunk_files = glob.glob("chunk_*.csv")
if not chunk_files:
    st.error("❌ No chunk files found.")
    st.stop()
else:
    st.info(f"📂 Ready to scan {len(chunk_files)} database chunks.")

# 4. LAZY LOAD BUTTON
if "engine_loaded" not in st.session_state:
    st.session_state["engine_loaded"] = False

if not st.session_state["engine_loaded"]:
    if st.button("🚀 CLICK TO ACTIVATE SEARCH ENGINE"):
        st.session_state["engine_loaded"] = True
        st.rerun()

# 5. SEARCH ENGINE LOGIC
if st.session_state["engine_loaded"]:
    import pandas as pd
    
    # --- HELPER: MASTER DB LOOKUP ---
    @st.cache_data
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

    # --- HELPER: DEEP NAME EXTRACTOR ---
    def extract_identity_from_bio(bio):
        """
        Extracts Name from the 'SOURCE:' URL found in the bio.
        """
        extracted_name = None
        extracted_role = "COACH/STAFF"
        
        # 1. Find URL in bio
        url_match = re.search(r"SOURCE: (https?://[^\s]+)", str(bio))
        if url_match:
            url = url_match.group(1)
            # Remove trailing extracted numbers/garbage
            clean_url = url.split('?')[0].rstrip('/')
            parts = clean_url.split('/')
            
            # The name is usually the last part (e.g. /staff/bryan-harmon)
            # OR the second to last if there is an ID (e.g. /roster/joe-smith/1234)
            slug = parts[-1]
            if slug.isdigit() or len(slug) < 3:
                slug = parts[-2]
            
            if '-' in slug:
                # Remove digits (e.g. joe-smith-2)
                slug = re.sub(r'\d+', '', slug).strip('-')
                extracted_name = slug.replace('-', ' ').title()

        # 2. Guess Role from Bio text
        bio_lower = str(bio).lower()
        if "roster" in bio_lower or "player" in bio_lower or re.search(r"\b202[0-9]\b", bio_lower):
            extracted_role = "PLAYER"
            
        return extracted_name, extracted_role

    def get_snippet(text, keyword):
        if pd.isna(text): return ""
        clean = str(text).replace('\n', ' ').replace('\r', ' ')
        m = re.search(re.escape(keyword), clean, re.IGNORECASE)
        if m:
            s, e = max(0, m.start()-60), min(len(clean), m.end()+60)
            return f"...{clean[s:e].strip()}..."
        return f"...{clean[:100]}..."

    # --- MAIN SEARCH UI ---
    master_lookup, name_lookup = load_master_lookup()
    st.success("✅ Smart Extractor Loaded")
    
    keywords_str = st.text_input("Enter Keywords (comma separated):", placeholder="e.g. tallahassee, atlanta")
    
    if st.button("Run Search"):
        if not keywords_str:
            st.warning("Please enter a keyword.")
        else:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            results = []
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try: chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
            except: pass

            for i, file in enumerate(chunk_files):
                status_text.text(f"Scanning file {i+1} of {len(chunk_files)}...")
                progress_bar.progress((i + 1) / len(chunk_files))
                
                try:
                    # Low-Memory Read
                    df_iter = pd.read_csv(file, chunksize=500, on_bad_lines='skip') 
                    
                    for chunk in df_iter:
                        # Fix Columns
                        chunk.columns = [c.strip() for c in chunk.columns]
                        for c in chunk.columns:
                            if c.lower() in ['bio', 'full_bio', 'description', 'full bio']: 
                                chunk.rename(columns={c: 'Full_Bio'}, inplace=True)
                            if c.lower() == 'name': chunk.rename(columns={c: 'Name'}, inplace=True)
                            if c.lower() == 'school': chunk.rename(columns={c: 'School'}, inplace=True)
                            if c.lower() == 'title': chunk.rename(columns={c: 'Title'}, inplace=True)
                        
                        if 'Full_Bio' not in chunk.columns: continue
                        
                        # Ensure columns exist
                        if 'Name' not in chunk.columns: chunk['Name'] = "Unknown"
                        if 'School' not in chunk.columns: chunk['School'] = "Unknown"
                        if 'Title' not in chunk.columns: chunk['Title'] = "Unknown"

                        # Search
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            
                            # --- DEEP EXTRACTION LOGIC ---
                            def repair_row(row):
                                # 1. Extract Name from URL if missing
                                if row['Name'] in ["Unknown", "", "nan"] or len(str(row['Name'])) < 3:
                                    ex_name, ex_role = extract_identity_from_bio(row['Full_Bio'])
                                    if ex_name:
                                        row['Name'] = ex_name
                                        row['Role'] = ex_role
                                
                                # 2. Master DB Lookup to fill blanks
                                def n(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())
                                
                                s_norm = n(row['School'])
                                n_norm = n(row['Name'])
                                
                                match = master_lookup.get((s_norm, n_norm))
                                
                                # If no match, try fuzzy name match
                                if not match:
                                    candidates = name_lookup.get(n_norm, [])
                                    # Try to find a school match in the bio text
                                    bio_lower = str(row['Full_Bio']).lower()
                                    for cand in candidates:
                                        cand_school_norm = n(cand['school'])
                                        # If candidate school is in the bio, assume it's them
                                        if cand_school_norm and cand_school_norm in bio_lower:
                                            match = cand
                                            break
                                
                                if match:
                                    row['School'] = match['school']
                                    row['Title'] = match['title']
                                    row['Email'] = match['email']
                                    row['Twitter'] = match['twitter']
                                    row['Role'] = "COACH/STAFF"
                                
                                return row

                            found['Role'] = "COACH/STAFF" # Default
                            found['Email'] = ""
                            found['Twitter'] = ""
                            
                            found = found.apply(repair_row, axis=1)
                            found['Context_Snippet'] = found['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                            
                            results.append(found)
                        
                        del chunk
                    gc.collect()

                except Exception as e:
                    print(f"Skipped {file}: {e}")
                    continue

            status_text.empty(); progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                
                # Filter final columns
                cols = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_cols = [c for c in cols if c in final_df.columns]
                final_df = final_df[final_cols]
                
                st.subheader(f"🎉 Found {len(final_df)} Matches!")
                st.dataframe(final_df)
                
                # Excel Download
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name="Results")
                st.download_button("💾 Download Excel", buffer.getvalue(), "Search_Results.xlsx", "application/vnd.ms-excel")
            else:
                st.warning("No matches found.")
