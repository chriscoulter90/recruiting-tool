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
st.title("🏈 Recruiting Tool - Pro Mode")
st.write("### ✅ System Status: ONLINE")

# 2. CONSTANTS & CLEANING LISTS (The "Brains" of the operation)
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

GARBAGE_NAMES = ["Skip To", "Main Content", "Print=True", "Schedule", "2024", "2025", "Ticket Office", "Roster", "Staff Directory"]
BAD_NAME_INDICATORS = ["University", "Bio", "Stats", "Roster", "Team", "Football", "Player", "Coach", "Staff", "View Full", "Profile"]
SCHOOL_CORRECTIONS = {"Boston": "Boston College", "Miami": "Miami (FL)", "Ole": "Ole Miss"}
TITLE_MAP = {"LB": "Linebackers", "DB": "Defensive Backs", "WR": "Wide Receivers", "QB": "Quarterbacks", "RB": "Running Backs", "DL": "Defensive Line", "OL": "Offensive Line", "TE": "Tight Ends", "HC": "Head Coach"}

# 3. VERIFY FILES
chunk_files = glob.glob("chunk_*.csv")
if not chunk_files:
    st.error("❌ No chunk files found.")
    st.stop()
else:
    st.info(f"📂 Detected {len(chunk_files)} database chunks ready for scanning.")

# 4. LAZY LOAD BUTTON
if "engine_loaded" not in st.session_state:
    st.session_state["engine_loaded"] = False

if not st.session_state["engine_loaded"]:
    if st.button("🚀 CLICK TO ACTIVATE SEARCH ENGINE"):
        st.session_state["engine_loaded"] = True
        st.rerun()

# 5. HEAVY LOGIC (Only runs after activation)
if st.session_state["engine_loaded"]:
    import pandas as pd
    
    # --- HELPER FUNCTIONS ---
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

    def get_snippet(text, keyword):
        if pd.isna(text): return ""
        clean = str(text).replace('\n', ' ').replace('\r', ' ')
        m = re.search(re.escape(keyword), clean, re.IGNORECASE)
        if m:
            s, e = max(0, m.start()-60), min(len(clean), m.end()+60)
            return f"...{clean[s:e].strip()}..."
        return f"...{clean[:100]}..."

    def clean_row_logic(row):
        # Basic cleanup
        name = str(row.get('Name', '')).strip()
        title = str(row.get('Title', '')).strip()
        school = str(row.get('School', '')).strip()
        bio = str(row.get('Full_Bio', '')).strip()

        # 1. Garbage Collection
        if name.isdigit() or any(g in name for g in GARBAGE_NAMES):
            row['Name'] = "DELETE_ME"; return row

        # 2. Bio Cleanup (Remove headers)
        for split in ["Skip To Main Content", "Navigation Menu", "Composite"]:
             parts = re.split(re.escape(split), bio, flags=re.IGNORECASE)
             if len(parts) > 1: bio = parts[0]; row['Full_Bio'] = bio

        # 3. Name Rescue (If Name is "Unknown" or junk, try to find it in Bio)
        if name == "Unknown" or any(b in name for b in BAD_NAME_INDICATORS):
            # Try to find "First Last" at start of bio
            match = re.search(r"^([A-Z][a-z]+ [A-Z][a-z]+)", bio[:50])
            if match: name = match.group(1)
        
        # 4. Title Cleanup
        words = title.split()
        new_words = [TITLE_MAP.get(w.upper(), w) for w in words]
        title = " ".join(new_words)
        
        # 5. Role Determination
        role = "COACH/STAFF"
        if "Roster" in title or "Player" in title or re.search(r"Position:", bio): role = "PLAYER"
        
        row['Name'] = name
        row['Title'] = title
        row['Role'] = role
        return row

    # --- MAIN SEARCH UI ---
    master_lookup, name_lookup = load_master_lookup()
    st.success("✅ Search Engine Active & Logic Loaded")
    
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
                        chunk.columns = [c.strip() for c in chunk.columns]
                        
                        # Fix Columns
                        for c in chunk.columns:
                            if c.lower() in ['bio', 'full_bio', 'description', 'full bio']: 
                                chunk.rename(columns={c: 'Full_Bio'}, inplace=True)
                            if c.lower() == 'name': chunk.rename(columns={c: 'Name'}, inplace=True)
                            if c.lower() == 'school': chunk.rename(columns={c: 'School'}, inplace=True)
                            if c.lower() == 'title': chunk.rename(columns={c: 'Title'}, inplace=True)
                        
                        if 'Full_Bio' not in chunk.columns: continue
                        if 'Name' not in chunk.columns: chunk['Name'] = "Unknown"
                        if 'School' not in chunk.columns: chunk['School'] = "Unknown"
                        if 'Title' not in chunk.columns: chunk['Title'] = "Unknown"

                        # Search
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            
                            # CLEANING & ENRICHMENT
                            found = found.apply(clean_row_logic, axis=1)
                            found = found[found['Name'] != "DELETE_ME"]
                            found['Context_Snippet'] = found['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                            
                            def enrich(row):
                                def n(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())
                                s, nm = n(row['School']), n(row['Name'])
                                match = master_lookup.get((s, nm))
                                if not match:
                                    pots = name_lookup.get(nm, [])
                                    for p in pots:
                                        if s in n(p['school']): match = p; break
                                if match:
                                    if not row.get('Email'): row['Email'] = match['email']
                                    if not row.get('Twitter'): row['Twitter'] = match['twitter']
                                return row
                            
                            if not found.empty:
                                if 'Email' not in found.columns: found['Email'] = ""
                                if 'Twitter' not in found.columns: found['Twitter'] = ""
                                found = found.apply(enrich, axis=1)
                                results.append(found)
                        
                        del chunk
                    gc.collect()

                except Exception as e:
                    print(f"Skipped {file}: {e}")
                    continue

            status_text.empty(); progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                # Final Clean Layout
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
