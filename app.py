import streamlit as st
import os
import glob
import re
import gc
import io
import requests

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Recruiting Search", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1rem;}
    </style>
    """, unsafe_allow_html=True)

st.title("🏈 Recruiting Search Engine")

# --- 2. CONSTANTS ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Garbage phrases to strip out
GARBAGE_PHRASES = [
    "Official Athletics Website", "Official Website", "Composite", 
    "Javascript is required", "Skip To Main Content", "Official Football Roster"
]

# --- 3. AUTO-LOAD MASTER DATA ---
if "master_data" not in st.session_state:
    import pandas as pd
    
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
    
    st.session_state["master_data"] = load_lookup()

master_lookup, name_lookup = st.session_state["master_data"]

# --- 4. SMART PARSER ---
def parse_header_smart(bio):
    extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
    
    # Flatten bio to single line for easier searching
    clean_bio_text = str(bio).replace('\n', ' ').replace('\r', ' ')
    
    # Try to find header line in original formatting
    lines = [L.strip() for L in str(bio).replace('\r', '\n').split('\n') if L.strip()]
    header = None
    for line in lines[:6]:
        if " - " in line and "http" not in line and "SOURCE" not in line:
            header = line
            break
            
    if header:
        parts = [p.strip() for p in header.split(' - ')]
        clean_parts = []
        for p in parts:
            is_garbage = False
            for g in GARBAGE_PHRASES:
                if g.lower() in p.lower(): is_garbage = True
            if not is_garbage: clean_parts.append(p)
        
        if len(clean_parts) >= 3:
            extracted['Name'] = clean_parts[0]
            extracted['Title'] = clean_parts[1]
            extracted['School'] = clean_parts[2]
        elif len(clean_parts) == 2:
            extracted['Name'] = clean_parts[0]
            extracted['School'] = clean_parts[1]
            extracted['Title'] = "Staff"
        elif len(clean_parts) == 1:
            extracted['Name'] = clean_parts[0]

        # Fix Titles/Schools swaps
        if extracted['Title'] and "University" in extracted['Title']:
            temp = extracted['School']
            extracted['School'] = extracted['Title']
            extracted['Title'] = temp if temp else "Staff"

        # Player Detection
        for val in [str(extracted['Title']), str(extracted['School'])]:
            if "202" in val or "203" in val:
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

# --- 5. SEARCH LOGIC ---
keywords_str = st.text_input("Enter Search Keywords:", placeholder="e.g. tallahassee, area recruiter")

if st.button("Run Search") or keywords_str:
    if not keywords_str:
        st.warning("Please enter a keyword.")
    else:
        import pandas as pd
        
        keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        chunk_files = glob.glob("chunk_*.csv")
        
        if not chunk_files:
            st.error("System Error: No database files found.")
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
                        chunk.columns = [c.strip() for c in chunk.columns]
                        
                        col_map = {}
                        for c in chunk.columns:
                            if c.lower() in ['bio', 'full_bio', 'description', 'full bio']: col_map[c] = 'Full_Bio'
                            elif c.lower() == 'name': col_map[c] = 'Name'
                            elif c.lower() == 'school': col_map[c] = 'School'
                            elif c.lower() == 'title': col_map[c] = 'Title'
                        chunk.rename(columns=col_map, inplace=True)
                        
                        if 'Full_Bio' not in chunk.columns: continue
                        
                        mask = chunk['Full_Bio'].str.contains('|'.join(keywords), case=False, na=False)
                        if mask.any():
                            found = chunk[mask].copy()
                            
                            def clean_and_fill(row):
                                meta = parse_header_smart(row['Full_Bio'])
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] if meta['Name'] else name
                                
                                school = row.get('School', '')
                                if not school or school == "Unknown": school = meta['School'] if meta['School'] else school
                                    
                                title = row.get('Title', '')
                                if not title or title == "Unknown": title = meta['Title'] if meta['Title'] else title
                                
                                role = meta['Role']

                                # Master Lookup
                                def n(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())
                                match = master_lookup.get((n(school), n(name)))
                                if not match:
                                    candidates = name_lookup.get(n(name), [])
                                    if len(candidates) == 1: match = candidates[0]
                                
                                email = row.get('Email', '')
                                twitter = row.get('Twitter', '')
                                
                                if match:
                                    if not email: email = match['email']
                                    if not twitter: twitter = match['twitter']
                                    if title in ["Staff", "Unknown", "Football"]: title = match['title']
                                    school = match['school']
                                
                                # Flatten Bio to prevent massive rows
                                flat_bio = str(row['Full_Bio']).replace('\n', ' ').replace('\r', ' ')
                                flat_bio = re.sub(r'\s+', ' ', flat_bio).strip()
                                
                                return pd.Series([role, name, title, school, email, twitter, flat_bio])

                            enriched = found.apply(clean_and_fill, axis=1)
                            enriched.columns = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Full_Bio']
                            enriched['Context_Snippet'] = enriched['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                            results.append(enriched)
                            
                    del chunk
                    gc.collect()
                except: continue

            progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                
                # 1. Clean Garbage
                final_df = final_df[~final_df['Name'].str.contains("Skip To|Official|Javascript", case=False, na=False)]
                final_df.dropna(subset=['Name'], inplace=True)
                
                # 2. SORTING: Role -> School -> Name
                # To make Coaches appear before Players, we can map them
                final_df['Role_Sort'] = final_df['Role'].apply(lambda x: 0 if "COACH" in str(x).upper() else 1)
                final_df.sort_values(by=['Role_Sort', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                final_df.drop(columns=['Role_Sort'], inplace=True)

                # 3. Final Columns
                cols = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_df = final_df[cols]
                
                st.success(f"🎉 Found {len(final_df)} matches.")
                st.dataframe(final_df)
                
                # Excel Export with Fixed Row Heights
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name="Results")
                    workbook = writer.book
                    worksheet = writer.sheets["Results"]
                    # Format: No text wrap to keep rows small
                    cell_format = workbook.add_format({'text_wrap': False, 'valign': 'top'})
                    worksheet.set_column('A:H', 20, cell_format)
                    
                st.download_button("💾 Download Results (Excel)", buffer.getvalue(), "Search_Results.xlsx", "application/vnd.ms-excel")
            else:
                st.warning("No matches found.")
