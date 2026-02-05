import streamlit as st
import pandas as pd
import io
import requests
import os
import re
from datetime import datetime
import glob
import gc  # Garbage Collector for memory management

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Recruiting Search Pro", page_icon="🏈", layout="wide")

# --- CONFIGURATION ---
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# --- CONSTANTS ---
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

BAD_NAME_INDICATORS = [
    "University", "Bio", "Stats", "Roster", "Team", "All-Freshman", 
    "All-American", "Football", "Player", "Coach", "Staff", "Men's", 
    "Women's", "View Full", "Profile", "Year", "Season", "Experience", 
    "th Year", "nd Year", "st Year", "rd Year", "File", "History",
    "As A", "Carolina", "High School", "Personal Data", "(", 
    "Played", "Joined", "Began His", "General Manager", "Graduate Assistant", "Coordinator"
]

SCHOOL_CORRECTIONS = {
    "Boston": "Boston College",
    "Miami": "Miami (FL)",
    "Ole": "Ole Miss",
    "Central Methodist": "Central Methodist University",
    "University of Auburn": "Auburn University"
}

GOLD_CONTEXT_TERMS = ["native of", "hometown", "born in", "raised in", "from", "attended", "graduate of", "graduated from", "high school", "coached at", "recruiting"]

TITLE_MAP = {
    "LB": "Linebackers", "DB": "Defensive Backs", "WR": "Wide Receivers",
    "QB": "Quarterbacks", "RB": "Running Backs", "DL": "Defensive Line",
    "OL": "Offensive Line", "TE": "Tight Ends", "ST": "Special Teams",
    "COORD": "Coordinator", "ASST": "Assistant", "DIR": "Director",
    "HC": "Head Coach", "ASSOC": "Associate", "GM": "General Manager"
}

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

# --- HELPER FUNCTIONS ---
def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

@st.cache_data
def load_master_lookup():
    # Only loads the small 10k list into memory
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
    except:
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
    # --- 0. PRE-CLEAN ---
    for col in row.index:
        if isinstance(row[col], str):
            row[col] = str(row[col]).replace('’', "'").replace('‘', "'").replace('\n', ' ').replace('\r', ' ').strip()
    
    name = str(row.get('Name', '')).strip()
    title = str(row.get('Title', '')).strip()
    school = str(row.get('School', '')).strip()
    bio = str(row.get('Full_Bio', '')).strip()
    role = str(row.get('Role', '')).strip().upper()

    # --- 1. GARBAGE COLLECTOR ---
    if name.isdigit() or "Skip To Main Content" in title or any(g in name for g in GARBAGE_NAMES):
        row['Name'] = "DELETE_ME"; return row

    # --- 2. BIO PREP ---
    clean_bio = bio
    if "Close Announce Block" in bio:
        parts = bio.split("Close Announce Block")
        if len(parts) > 1: clean_bio = parts[1]
    
    for split_term in ["Skip To Main Content", "Navigation Menu", "related stories", "Composite"]:
         parts = re.split(re.escape(split_term), clean_bio, flags=re.IGNORECASE)
         if len(parts) > 1: clean_bio = parts[0]; break

    # --- 3. NAME CLEANUP ---
    if "?" in name: name = name.split("?")[0].strip()
    if name.lower().startswith("tech "): name = name[5:].strip()
    while "  " in name: name = name.replace("  ", " ")

    # --- 4. SCHOOL FIXER ---
    if school in SCHOOL_CORRECTIONS: school = SCHOOL_CORRECTIONS[school]
    elif school == "Boston" and "College" not in school: school = "Boston College"

    # --- 5. PLAYER CARD SCANNER ---
    is_player_card = False
    pos_match = re.search(r"(?:Position|Pos)[:\s]+([A-Za-z0-9/]+)", bio[:5000], re.IGNORECASE)
    class_match = re.search(r"(?:Class|Cl\.)[:\s]+([A-Za-z\.]+)", bio[:5000], re.IGNORECASE)
    hs_match = re.search(r"High School:", bio[:5000], re.IGNORECASE)

    if pos_match or (class_match and hs_match) or re.search(r"Height:.*Weight:", bio[:5000], re.IGNORECASE):
        is_player_card = True; role = "PLAYER"
        if pos_match: title = pos_match.group(1).strip()
        else: title = "Roster Member"

    # --- 6. BROADENED SPORT ASSASSIN ---
    if not is_player_card and name != "Dabo Swinney":
        header = clean_bio[:1000].lower()
        has_football = "football" in header or "football" in title.lower()
        for sport in FORBIDDEN_SPORTS:
            if sport.lower() in header:
                if not has_football: 
                    row['Name'] = "DELETE_ME"; return row

    # --- 7. SPECIAL CLEMSON/DABO FIX ---
    if "dabo" in name.lower() and "clemson" in school.lower():
        name = "Dabo Swinney"; title = "Head Coach"; role = "COACH/STAFF"

    # --- 8. SCHOOL CLEANUP 2 ---
    if school.endswith("-"): school = school[:-1].strip()
    if school.lower() in ["university of", "university", "the university of"]:
        match = re.search(r"(?:University of|at)\s+([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)", title + " | " + bio)
        if match: school = match.group(0).replace("at ", "University of ")

    # --- 9. NAME CLEANUP & RESCUE ---
    if name.lower().startswith(school.lower()):
        name = name[len(school):].strip()
    elif school.split()[0].lower() in name.lower():
        name = re.sub(f"^{re.escape(school.split()[0])}\\s+", "", name, flags=re.IGNORECASE)

    name = re.sub(r"^(University|Coach|Staff|The|Profile|View)\s+", "", name, flags=re.IGNORECASE)
    if "-" in name and not any(x in name for x in ["Sr.", "Jr.", "III"]): name = name.replace("-", " ")
    
    is_digit_name = any(char.isdigit() for char in name)
    is_single_word = " " not in name.strip() and len(name) > 1
    
    is_junk_name = any(ind.lower() in name.lower() for ind in BAD_NAME_INDICATORS) or \
                   len(name) < 3 or is_digit_name or "(" in name or is_single_word
    
    if is_junk_name:
        rescued_name = None
        if is_single_word and not is_digit_name:
            sm = re.search(rf"\b{re.escape(name)}\s+([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?)", bio[:300])
            if sm: 
                pot = sm.group(1)
                if pot.lower() not in ["bio", "profile", "football", "coach", "staff", "university"]: rescued_name = f"{name} {pot}"

        if not rescued_name:
            parts = title.split()
            if len(parts) >= 2 and parts[0].lower() not in ["head", "assistant", "associate", "football"]:
                 pot = f"{parts[0]} {parts[1]}"
                 if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS): rescued_name = pot

        if not rescued_name:
            bm = re.search(r"([A-Z][a-z\.]+(?:\s+[A-Z][a-z\.]+)+)\s+-\s+", clean_bio[:3000])
            if bm: 
                pot = bm.group(1).strip()
                if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS): rescued_name = pot
            
        if not rescued_name:
            bp = re.search(r"([A-Z][a-z\.]+(?:\s+[A-Z][a-z\.]+)+)\s+\|\s+", clean_bio[:3000])
            if bp: 
                pot = bp.group(1).strip()
                if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS): rescued_name = pot
        
        if not rescued_name:
            sm = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+) (?:is|joined|starts|begins|enters|was named|returned)", clean_bio[:1000])
            if sm:
                pot = sm.group(1).strip()
                if "The " not in pot and "He " not in pot: rescued_name = pot

        if rescued_name: name = rescued_name
        elif is_digit_name or "Skip To" in title: row['Name'] = "DELETE_ME"; return row

    # --- 10. SUFFIX SAVER ---
    suffix_match = re.match(r"^([A-Z][a-z]+\s+)?(Sr\.|Jr\.|II|III|IV|V)$", title, re.IGNORECASE)
    if suffix_match: name = f"{name} {title}"; title = ""

    # --- 11. TITLE PURGE ---
    if re.fullmatch(r"20\d\d", title) or "Roster" in title:
        role = "PLAYER"
        pm = re.search(r"(?:Position|Pos)[:\s]+([A-Za-z0-9/]+)", bio[:5000], re.IGNORECASE)
        if pm: title = pm.group(1).strip()
        else: title = "Roster Member"
    
    if normalize_text(title) == normalize_text(school): title = ""
    if " | " in title:
        parts = title.split(" | ")
        if normalize_text(parts[0]) == normalize_text(name): parts.pop(0)
        title = " - ".join(parts)
    if " - " in title:
        parts = title.split(" - ")
        if normalize_text(parts[0]) == normalize_text(name): parts.pop(0)
        title = " - ".join(parts)
    if name.lower() in title.lower():
         title = re.sub(f"^{re.escape(name)}", "", title, flags=re.IGNORECASE).strip()
         title = re.sub(f"^{re.escape(name)}[\s\-]+", "", title, flags=re.IGNORECASE).strip()
    if len(name.split()) > 0:
        last_name = name.split()[-1]
        title = re.sub(f"Coach {re.escape(last_name)}", "", title, flags=re.IGNORECASE).strip()
    if " - " in title:
        parts = title.split(" - ")
        cp = [p for p in parts if normalize_text(p) != normalize_text(school) and "University" not in p and "Athletics" not in p]
        if cp: title = cp[0]
    
    words = title.split()
    new_words = []
    for w in words:
        cw = w.upper().replace(".", "").replace(",", "")
        if cw in TITLE_MAP: new_words.append(TITLE_MAP[cw])
        else: new_words.append(w)
    title = " ".join(new_words)
    title = re.sub(r"^[^a-zA-Z0-9]+", "", title).strip()

    # --- 12. ROLE HUNTER ---
    GENERIC_TITLES = ["Football Coach", "Coach", "Staff", "Assistant Coach", "Football Staff", "Bio", "Profile", "Football", "", "Unknown"]
    
    if role != "PLAYER":
        if not title or any(g.lower() == title.lower() for g in GENERIC_TITLES):
            found_role = False
            for pat, rep in ROLE_PATTERNS:
                if re.search(pat, bio[:3000], re.IGNORECASE):
                    title = rep; found_role = True; break
            if not found_role: title = "Football Staff"

    # --- 13. ROLE SYNCHRONIZER ---
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
    # This is the Low-Memory Magic: Search files one by one
    chunk_files = glob.glob("chunk_*.csv")
    chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
    
    all_clean = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    total_chunks = len(chunk_files)

    for i, filename in enumerate(chunk_files):
        status_text.text(f"Scanning chunk {i+1} of {total_chunks}...")
        progress_bar.progress((i + 1) / total_chunks)
        
        try:
            df_chunk = pd.read_csv(filename, index_col=None, header=0).fillna("")
            
            # Smart Column Detection per chunk
            df_chunk.columns = [c.strip() for c in df_chunk.columns]
            if 'Full_Bio' not in df_chunk.columns:
                 possible = ['Bio', 'bio', 'Full Bio', 'Description', 'About']
                 for c in possible:
                     if c in df_chunk.columns: df_chunk.rename(columns={c: 'Full_Bio'}, inplace=True); break
            
            if 'Name' not in df_chunk.columns and 'name' in df_chunk.columns: df_chunk.rename(columns={'name': 'Name'}, inplace=True)
            if 'School' not in df_chunk.columns and 'school' in df_chunk.columns: df_chunk.rename(columns={'school': 'School'}, inplace=True)
            
            if 'Full_Bio' not in df_chunk.columns: continue

            # SEARCH
            for key in keywords:
                mask = df_chunk['Full_Bio'].str.contains(key, case=False, na=False)
                results = df_chunk[mask].copy()
                
                if not results.empty:
                    # Clean Matching Rows
                    results = results.apply(clean_row_logic, axis=1)
                    results = results[results['Name'] != "DELETE_ME"]
                    results['Context_Snippet'] = results['Full_Bio'].apply(lambda x: get_snippet(x, key))
                    
                    # Enrich with Master Data
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

            # Free memory immediately
            del df_chunk
            gc.collect()

        except Exception as e:
            continue

    status_text.empty()
    progress_bar.empty()

    if all_clean:
        final_df = pd.concat(all_clean)
        final_df.drop_duplicates(subset=['Name', 'School'], keep='first', inplace=True)
        role_map = {'COACH/STAFF': 1, 'PLAYER': 2, 'UNCERTAIN': 3}
        final_df['Role_Rank'] = final_df['Role'].map(role_map).fillna(3)
        final_df.sort_values(by=['Role_Rank', 'School', 'Name'], inplace=True)
        cols_to_keep = ['Role', 'Name', 'Title', 'School', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']
        return final_df[cols_to_keep]
    return pd.DataFrame()

# --- STREAMLIT APP LAYOUT ---

st.title("🏈 Recruiting Search Pro")
st.markdown("Search the database of **57,000+ Profiles**.")

# Initialize Data (Lightweight)
master_lookup, name_lookup = load_master_lookup()
chunk_count = len(glob.glob("chunk_*.csv"))

if chunk_count == 0:
    st.error("❌ No database chunks found. Please upload `chunk_*.csv` files to GitHub.")
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
