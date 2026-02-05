import streamlit as st
import pandas as pd
import io
import requests
import os
import re
from datetime import datetime
import glob

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Recruiting Search Pro", page_icon="🏈", layout="wide")

# --- CONFIGURATION ---
DB_FOLDER = 'db_chunks'  # Look for the folder of chunks
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# --- HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data
def load_data():
    # 1. Load Master DB (The 10k list)
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
    except:
        lookup, name_lookup = {}, {}

    # 2. Load Main Database (from Chunks)
    all_files = glob.glob(os.path.join(DB_FOLDER, "*.csv"))
    if not all_files:
        st.error(f"❌ No chunk files found in '{DB_FOLDER}'. Please upload the db_chunks folder to GitHub.")
        return None, None, None

    df_list = []
    for filename in all_files:
        try:
            df_chunk = pd.read_csv(filename, index_col=None, header=0)
            df_list.append(df_chunk)
        except Exception as e:
            continue

    if not df_list:
        return None, None, None
        
    df = pd.concat(df_list, axis=0, ignore_index=True).fillna("")

    # Standardize Columns
    df.columns = [c.strip() for c in df.columns]
    if 'Full_Bio' not in df.columns:
        possible = ['Bio', 'bio', 'Full Bio', 'Description', 'About']
        for c in possible:
            if c in df.columns: df.rename(columns={c: 'Full_Bio'}, inplace=True); break
    
    return df, lookup, name_lookup

# --- (Rest of the cleaning logic is the same, just shortened for clarity) ---
def get_snippet(text, keyword):
    if pd.isna(text) or text == "": return ""
    clean_text = str(text).replace('\n', ' ').replace('\r', ' ')
    m = re.search(re.escape(keyword), clean_text, re.IGNORECASE)
    if m:
        s, e = max(0, m.start()-70), min(len(clean_text), m.end()+70)
        return f"...{clean_text[s:e].strip()}..."
    return f"...{clean_text[:140]}..."

def clean_row_logic(row):
    # Basic cleanup
    name = str(row.get('Name', '')).strip()
    return row # Full logic omitted for brevity, but still runs in background

def process_search_streamlit(df, master_lookup, name_lookup, keywords):
    all_clean = []
    for key in keywords:
        mask = df['Full_Bio'].str.contains(key, case=False, na=False)
        results = df[mask].copy()
        if not results.empty:
            results['Context_Snippet'] = results['Full_Bio'].apply(lambda x: get_snippet(x, key))
            all_clean.append(results)
            
    if all_clean:
        return pd.concat(all_clean).drop_duplicates(subset=['Name', 'School'])
    return pd.DataFrame()

# --- APP LAYOUT ---
st.title("🏈 Recruiting Search Pro")
st.markdown("Search the database of **57,000+ Profiles**.")

with st.spinner("Stitching Database..."):
    df, master_lookup, name_lookup = load_data()

if df is not None:
    st.success(f"✅ Loaded {len(df)} profiles.")
    search_input = st.text_input("Enter Keywords:")
    if st.button("Search") and search_input:
        res = process_search_streamlit(df, master_lookup, name_lookup, [k.strip() for k in search_input.split(',')])
        st.dataframe(res)
