import streamlit as st
import os
import glob
import re
import gc
import io
import requests

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Coulter Recruiting", page_icon="🏈", layout="wide")

st.markdown("""
    <style>
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .block-container {padding-top: 1rem;}
    .title-text { text-align: center; font-size: 3rem; font-weight: 700; color: #002B5C; margin-bottom: 0; }
    .subtitle-text { text-align: center; font-size: 1.2rem; color: #666; margin-top: -10px; margin-bottom: 30px; }
    </style>
    """, unsafe_allow_html=True)

st.markdown('<div class="title-text">COULTER RECRUITING</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">FOOTBALL SEARCH ENGINE</div>', unsafe_allow_html=True)

# --- 2. CONSTANTS (MATCHING LOCAL SCRIPT) ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# Exact list from your local script
FORBIDDEN_SPORTS = [
    "Volleyball", "Baseball", "Softball", "Soccer", "Tennis", "Golf", 
    "Swimming", "Lacrosse", "Hockey", "Wrestling", "Gymnastics", 
    "Basketball", "Track & Field", "Crew", "Rowing", "Sailing", 
    "Acrobatics", "Tumbling", "Cheerleading", "Fencing", "Spirit Squad",
    "Women's Basketball", "Men's Basketball"
]

GARBAGE_PHRASES = [
    "Official Athletics Website", "Official Website", "Composite", 
    "Javascript is required", "Skip To Main Content", "Official Football Roster",
    "View Full Profile", "Related Headlines", "Source:", "https://"
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

# --- 4. LOGIC FUNCTIONS (MAC PARITY) ---
def parse_header_exact(bio):
    extracted = {'Name': None, 'Title': None, 'School': None, 'Role': 'COACH/STAFF'}
    
    # Normalize Dashes (Mac vs Cloud Fix)
    clean_text = str(bio).replace('\r', '\n').replace('–', '-').replace('—', '-')
    
    lines = [L.strip() for L in clean_text.split('\n') if L.strip()]
    header = None
    for line in lines[:8]:
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

        if extracted['Title'] and ("University" in extracted['Title'] or "College" in extracted['Title']):
            temp = extracted['School']
            extracted['School'] = extracted['Title']
            extracted['Title'] = temp if temp else "Staff"

        for val in [str(extracted['Title']), str(extracted['School'])]:
            if "202" in val or "203" in val:
                extracted['Role'] = "PLAYER"
                extracted['Title'] = "Roster Member"
            if "Football" == val:
                 if extracted['Role'] == "COACH/STAFF": extracted['Title'] = "Staff"
                
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
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    keywords_str = st.text_input("", placeholder="🔍 Enter keywords (e.g. Tallahassee, Quarterback)...")
    run_search = st.button("SEARCH DATABASE", use_container_width=True)

if run_search or keywords_str:
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
                                # 1. Parse Header
                                meta = parse_header_exact(row['Full_Bio'])
                                
                                name = row.get('Name', '')
                                if not name or name == "Unknown" or len(name) < 3: name = meta['Name'] if meta['Name'] else name
                                
                                school = row.get('School', '')
                                if not school or school == "Unknown": school = meta['School'] if meta['School'] else school
                                    
                                title = row.get('Title', '')
                                if not title or title == "Unknown": title = meta['Title'] if meta['Title'] else title
                                
                                role = meta['Role']

                                # 2. Forbidden Sport Check (From Local Script)
                                header_check = (str(title) + " " + str(school) + " " + str(row['Full_Bio'])[:200]).lower()
                                for sport in FORBIDDEN_SPORTS:
                                    if sport.lower() in header_check and "football" not in header_check:
                                        return None # DROP ROW

                                # 3. Master Lookup
                                def n(t): return re.sub(r'[^a-z0-9]', '', str(t).lower())
                                match = master_lookup.get((n(school), n(name)))
                                if not match:
                                    candidates = name_lookup.get(n(name), [])
                                    if len(candidates) == 1: match = candidates[0]
                                    elif len(candidates) > 1:
                                        for cand in candidates:
                                            if n(cand['school']) in n(school) or n(school) in n(cand['school']):
                                                match = cand; break
                                
                                email = row.get('Email', '')
                                twitter = row.get('Twitter', '')
                                
                                if match:
                                    if not email: email = match['email']
                                    if not twitter: twitter = match['twitter']
                                    if title in ["Staff", "Unknown", "Football"]: title = match['title']
                                    school = match['school']
                                
                                flat_bio = str(row['Full_Bio']).replace('\n', ' ').replace('\r', ' ').strip()
                                flat_bio = re.sub(r'\s+', ' ', flat_bio)
                                
                                return pd.Series([role, name, title, school, "Football", email, twitter, flat_bio])

                            enriched = found.apply(clean_and_fill, axis=1)
                            
                            # Drop None rows (Forbidden sports)
                            enriched.dropna(how='all', inplace=True) 
                            
                            if not enriched.empty:
                                enriched.columns = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Full_Bio']
                                enriched['Context_Snippet'] = enriched['Full_Bio'].apply(lambda x: get_snippet(x, keywords[0]))
                                results.append(enriched)
                            
                    del chunk
                    gc.collect()
                except: continue

            progress_bar.empty()

            if results:
                final_df = pd.concat(results)
                
                # Cleanup
                final_df = final_df[~final_df['Name'].str.contains("Skip To|Official|Javascript", case=False, na=False)]
                final_df.dropna(subset=['Name'], inplace=True)
                
                # Sort: Role -> School -> Name
                final_df['Role_Sort'] = final_df['Role'].apply(lambda x: 1 if "PLAYER" in str(x).upper() else 0)
                final_df.sort_values(by=['Role_Sort', 'School', 'Name'], ascending=[True, True, True], inplace=True)
                final_df.drop(columns=['Role_Sort'], inplace=True)
                
                # Column Order (MATCHING LOCAL EXACTLY)
                cols = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
                final_df = final_df[cols]
                
                st.success(f"🎉 Found {len(final_df)} matches.")
                st.dataframe(final_df, use_container_width=True)
                
                # Excel Export
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                    final_df.to_excel(writer, index=False, sheet_name="Results")
                    workbook = writer.book
                    worksheet = writer.sheets["Results"]
                    cell_format = workbook.add_format({'text_wrap': False, 'valign': 'top'})
                    worksheet.set_column('A:I', 25, cell_format)
                    
                st.download_button("💾 DOWNLOAD RESULTS (EXCEL)", buffer.getvalue(), "Coulter_Recruiting_Results.xlsx", "application/vnd.ms-excel", type="primary")
            else:
                st.warning("No matches found.")
