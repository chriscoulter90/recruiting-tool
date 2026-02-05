import pandas as pd
import sys
import os
import re
import shutil
import tempfile
import requests
from datetime import datetime

# --- CONFIGURATION ---
DB_FILE = 'football_master_db.csv'
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"
MASTER_DB_FILE = 'REC CONS OUTLINE - MASTER EMAIL LIST (1).csv'
RESULTS_FOLDER = 'Search_Results'
REJECTED_FOLDER = 'Rejected_Bios'

# --- ANSI VISUALS ---
RESET, BOLD, GREEN, CYAN, MAGENTA, RED = "\033[0m", "\033[1m", "\033[92m", "\033[96m", "\033[95m", "\033[91m"
HEADER_BG = "\033[44m\033[97m" 

COLUMN_ORDER = ['Role', 'Name', 'Title', 'School', 'Sport', 'Email', 'Twitter', 'Context_Snippet', 'Full_Bio']

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

# Manual School Corrections
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

def normalize_text(text):
    if pd.isna(text): return ""
    text = str(text).lower()
    for word in ['university', 'univ', 'college', 'state', 'the', 'of', 'athletics', 'inst']:
        text = text.replace(word, '')
    return re.sub(r'[^a-z0-9]', '', text).strip()

def load_master_db():
    print(f"{MAGENTA}🌐 Syncing with Live Google Sheet...{RESET}")
    try:
        r = requests.get(GOOGLE_SHEET_CSV_URL, timeout=10)
        with open(MASTER_DB_FILE, 'wb') as f: f.write(r.content)
    except: print(f"{RED}⚠️ Sync failed. Using local master list.{RESET}")

    if not os.path.exists(MASTER_DB_FILE): return {}, {}
    print(f"{MAGENTA}⏳ Indexing Master Coaches...{RESET}")
    try:
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
    except: return {}, {}

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
    # --- 0. PRE-CLEAN: REPLACE SMART QUOTES GLOBALLY ---
    for col in row.index:
        if isinstance(row[col], str):
            row[col] = str(row[col]).replace('’', "'").replace('‘', "'").replace('\n', ' ').replace('\r', ' ').strip()
    
    name = str(row.get('Name', '')).strip()
    title = str(row.get('Title', '')).strip()
    school = str(row.get('School', '')).strip()
    bio = str(row.get('Full_Bio', '')).strip()
    role = str(row.get('Role', '')).strip().upper()

    # --- 1. GARBAGE COLLECTOR ---
    if name.isdigit() or \
       "Skip To Main Content" in title or \
       any(garbage in name for garbage in GARBAGE_NAMES):
        row['Name'] = "DELETE_ME"
        return row

    # --- 2. BIO PREP ---
    clean_bio = bio
    if "Close Announce Block" in bio:
        parts = bio.split("Close Announce Block")
        if len(parts) > 1: clean_bio = parts[1]
    
    for split_term in ["Skip To Main Content", "Navigation Menu", "related stories", "Composite"]:
         parts = re.split(re.escape(split_term), clean_bio, flags=re.IGNORECASE)
         if len(parts) > 1: 
             clean_bio = parts[0]
             break

    # --- 3. NAME CLEANUP ---
    # Fix URL junk: "Name?View=Bio" -> "Name"
    if "?" in name:
        name = name.split("?")[0].strip()
    # Fix "Tech Name"
    if name.lower().startswith("tech "):
        name = name[5:].strip()
    # Fix Double Spaces
    while "  " in name:
        name = name.replace("  ", " ")

    # --- 4. SCHOOL FIXER ---
    # Manual Override for known bad schools
    if school in SCHOOL_CORRECTIONS:
        school = SCHOOL_CORRECTIONS[school]
    # "Boston" check if not caught by exact match
    elif school == "Boston" and "College" not in school:
        school = "Boston College"

    # --- 5. PLAYER CARD SCANNER ---
    is_player_card = False
    pos_match = re.search(r"(?:Position|Pos)[:\s]+([A-Za-z0-9/]+)", bio[:5000], re.IGNORECASE)
    class_match = re.search(r"(?:Class|Cl\.)[:\s]+([A-Za-z\.]+)", bio[:5000], re.IGNORECASE)
    hs_match = re.search(r"High School:", bio[:5000], re.IGNORECASE)

    if pos_match or (class_match and hs_match) or re.search(r"Height:.*Weight:", bio[:5000], re.IGNORECASE):
        is_player_card = True
        role = "PLAYER"
        if pos_match: title = pos_match.group(1).strip()
        else: title = "Roster Member"

    # --- 6. BROADENED SPORT ASSASSIN ---
    if not is_player_card and name != "Dabo Swinney":
        header = clean_bio[:1000].lower()
        has_football = "football" in header or "football" in title.lower()
        
        for sport in FORBIDDEN_SPORTS:
            if sport.lower() in header:
                if not has_football: 
                    row['Name'] = "DELETE_ME"
                    return row

    # --- 7. SPECIAL CLEMSON/DABO FIX ---
    if "dabo" in name.lower() and "clemson" in school.lower():
        name = "Dabo Swinney"
        title = "Head Coach"
        role = "COACH/STAFF"

    # --- 8. SCHOOL CLEANUP 2 (Standard) ---
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
        # A. Single Name Expansion
        if is_single_word and not is_digit_name:
            single_pattern = rf"\b{re.escape(name)}\s+([A-Z][a-z]+(?:[-'][A-Z][a-z]+)?)"
            single_match = re.search(single_pattern, bio[:300])
            if single_match:
                pot_last = single_match.group(1)
                if pot_last.lower() not in ["bio", "profile", "football", "coach", "staff", "university"]:
                    rescued_name = f"{name} {pot_last}"

        # B. Title Rescue
        if not rescued_name:
            parts = title.split()
            if len(parts) >= 2 and parts[0].lower() not in ["head", "assistant", "associate", "football"]:
                 pot = f"{parts[0]} {parts[1]}"
                 if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS): rescued_name = pot

        # C. Bio Regex (Dash/Pipe)
        if not rescued_name:
            bio_match_dash = re.search(r"([A-Z][a-z\.]+(?:\s+[A-Z][a-z\.]+)+)\s+-\s+", clean_bio[:3000])
            if bio_match_dash: 
                pot = bio_match_dash.group(1).strip()
                if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS):
                    rescued_name = pot
            
        if not rescued_name:
            bio_match_pipe = re.search(r"([A-Z][a-z\.]+(?:\s+[A-Z][a-z\.]+)+)\s+\|\s+", clean_bio[:3000])
            if bio_match_pipe: 
                pot = bio_match_pipe.group(1).strip()
                if not any(ind.lower() in pot.lower() for ind in BAD_NAME_INDICATORS):
                    rescued_name = pot
        
        # D. Sentence Scanner
        if not rescued_name:
            sent_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+) (?:is|joined|starts|begins|enters|was named|returned)", clean_bio[:1000])
            if sent_match:
                potential_name = sent_match.group(1).strip()
                if "The " not in potential_name and "He " not in potential_name:
                    rescued_name = potential_name

        if rescued_name:
            name = rescued_name
        elif is_digit_name or "Skip To" in title:
            row['Name'] = "DELETE_ME"
            return row

    # --- 10. SUFFIX SAVER ---
    suffix_match = re.match(r"^([A-Z][a-z]+\s+)?(Sr\.|Jr\.|II|III|IV|V)$", title, re.IGNORECASE)
    if suffix_match:
        name = f"{name} {title}"
        title = ""

    # --- 11. TITLE PURGE & PLAYER EXTRACTION (Fallback) ---
    if re.fullmatch(r"20\d\d", title) or "Roster" in title:
        role = "PLAYER"
        pos_match = re.search(r"(?:Position|Pos)[:\s]+([A-Za-z0-9/]+)", bio[:5000], re.IGNORECASE)
        if pos_match:
            title = pos_match.group(1).strip()
        else:
            title = "Roster Member"
    
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
        clean_parts = [p for p in parts if normalize_text(p) != normalize_text(school) and "University" not in p and "Athletics" not in p]
        if clean_parts: title = clean_parts[0]
    
    words = title.split()
    new_words = []
    for w in words:
        clean_w = w.upper().replace(".", "").replace(",", "")
        if clean_w in TITLE_MAP: new_words.append(TITLE_MAP[clean_w])
        else: new_words.append(w)
    title = " ".join(new_words)
    title = re.sub(r"^[^a-zA-Z0-9]+", "", title).strip()

    # --- 12. ROLE HUNTER ---
    GENERIC_TITLES = ["Football Coach", "Coach", "Staff", "Assistant Coach", "Football Staff", "Bio", "Profile", "Football", "", "Unknown"]
    
    if role != "PLAYER":
        if not title or any(g.lower() == title.lower() for g in GENERIC_TITLES):
            found_role = False
            bio_search_zone = bio[:3000] 
            for pattern, replacement in ROLE_PATTERNS:
                if re.search(pattern, bio_search_zone, re.IGNORECASE):
                    title = replacement
                    found_role = True
                    break
            if not found_role:
                title = "Football Staff"

    # --- 13. ROLE SYNCHRONIZER ---
    t_low = title.lower()
    if role == "UNCERTAIN" or role == "NAN" or not role:
        if "coach" in t_low or "coordinator" in t_low or "director" in t_low or "assistant" in t_low or "staff" in t_low or "analyst" in t_low or "manager" in t_low:
            role = "COACH/STAFF"
        elif "roster" in t_low or "player" in t_low:
            role = "PLAYER"
        elif t_low == "unknown":
            role = "UNCERTAIN"
        else:
            role = "COACH/STAFF"

    row['Role'] = role
    row['Name'], row['Title'], row['School'] = name.title(), title, school
    return row

def process_search(df, master_lookup, name_lookup, keyword):
    print(f"   ⚡ Searching: '{keyword}'...", end="\r")
    mask = df['Full_Bio'].str.contains(keyword, case=False, na=False)
    results = df[mask].copy()
    if results.empty: return pd.DataFrame(), pd.DataFrame()

    results = results.apply(clean_row_logic, axis=1)
    results = results[results['Name'] != "DELETE_ME"]
    results['Context_Snippet'] = results['Full_Bio'].apply(lambda x: get_snippet(x, keyword))

    def enrich(row):
        s_key, n_key = normalize_text(row['School']), normalize_text(row['Name'])
        match = master_lookup.get((s_key, n_key))
        
        # Secondary Lookup: Correct School Name
        if not match:
            potential_matches = name_lookup.get(n_key, [])
            for cand in potential_matches:
                c_school_norm = normalize_text(cand['school'])
                # Fuzzy Match: "boston" in "bostoncollege"
                if s_key in c_school_norm or c_school_norm in s_key:
                    match = cand
                    row['School'] = cand['school'] # Use correct school name from DB
                    break

        if match:
            if not row['Email'] or str(row['Email']).lower() in ['', 'nan', 'n/a']:
                row['Email'] = match['email']
            if not row['Twitter'] or str(row['Twitter']).lower() in ['', 'nan', 'n/a']:
                if len(match['twitter']) > 3: row['Twitter'] = match['twitter']
            if match['title'] and len(match['title']) > 2:
                row['Title'] = match['title']
        return row

    results = results.apply(enrich, axis=1)
    is_wrong = results['Title'].str.contains('|'.join(FORBIDDEN_SPORTS), case=False, na=False)
    clean_df, reject_df = results[~is_wrong].copy(), results[is_wrong].copy()

    if not clean_df.empty:
        # Aggressive Deduplication: Drop if Name and School match (now that Name is cleaned)
        clean_df.drop_duplicates(subset=['Name', 'School'], keep='first', inplace=True)
        role_map = {'COACH/STAFF': 1, 'PLAYER': 2, 'UNCERTAIN': 3}
        clean_df['Role_Rank'] = clean_df['Role'].map(role_map).fillna(3)
        clean_df.sort_values(by=['Role_Rank', 'School', 'Name'], inplace=True)

    return clean_df[COLUMN_ORDER] if not clean_df.empty else pd.DataFrame(), \
           reject_df[COLUMN_ORDER] if not reject_df.empty else pd.DataFrame()

def format_excel(writer, df, sheet_name):
    workbook, worksheet = writer.book, writer.sheets[sheet_name]
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1})
    clip_fmt = workbook.add_format({'text_wrap': False, 'valign': 'top'})
    widths = [12, 22, 28, 30, 10, 28, 15, 60, 40]
    for i, w in enumerate(widths):
        worksheet.set_column(i, i, w, clip_fmt)
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_fmt)
    worksheet.freeze_panes(1, 0)

def search_loop():
    os.system('clear') 
    print(f"{HEADER_BG}{BOLD}  🏈  RECRUITING SEARCH PRO (v13.4 School Master)  📋  {RESET}")
    if not os.path.exists(RESULTS_FOLDER): os.makedirs(RESULTS_FOLDER)
    if not os.path.exists(REJECTED_FOLDER): os.makedirs(REJECTED_FOLDER)
    master_lookup, name_lookup = load_master_db()
    if not os.path.exists(DB_FILE): return
    print(f"{MAGENTA}⏳ Loading 57,000+ Profiles...{RESET}")
    try:
        df = pd.read_csv(DB_FILE, encoding='utf-8').fillna("")
    except UnicodeDecodeError:
        df = pd.read_csv(DB_FILE, encoding='latin1').fillna("")
        
    print(f"{GREEN}✅ Database Ready.{RESET}")

    while True:
        raw_input = input(f"\n{BOLD}🔎 ENTER KEYWORDS:{RESET} ").strip()
        if raw_input.lower() in ['exit', 'quit']: break
        keywords = [k.strip() for k in raw_input.split(',') if k.strip()]
        if not keywords: continue
        ts = datetime.now().strftime("%Y-%m-%d")
        temp_dir = tempfile.gettempdir()
        l_c, l_r = os.path.join(temp_dir, f"c_{os.getpid()}.xlsx"), os.path.join(temp_dir, f"r_{os.getpid()}.xlsx")
        try:
            with pd.ExcelWriter(l_c, engine='xlsxwriter') as w_c, pd.ExcelWriter(l_r, engine='xlsxwriter') as w_r:
                for key in keywords:
                    c_data, r_data = process_search(df, master_lookup, name_lookup, key)
                    if not c_data.empty: 
                        c_data.to_excel(w_c, sheet_name=key[:31], index=False)
                        format_excel(w_c, c_data, key[:31])
                        print(f"   ✅ '{key}': {len(c_data)} matches.       ")
                    if not r_data.empty: 
                        r_data.to_excel(w_r, sheet_name=key[:31], index=False)
                        format_excel(w_r, r_data, key[:31])
            if os.path.exists(l_c):
                shutil.copy2(l_c, os.path.join(RESULTS_FOLDER, f"{keywords[0]}_{ts}.xlsx"))
                os.remove(l_c)
            if os.path.exists(l_r):
                shutil.copy2(l_r, os.path.join(REJECTED_FOLDER, f"REJECTED_{keywords[0]}_{ts}.xlsx"))
                os.remove(l_r)
            print(f"{GREEN}💾 Saved successfully.{RESET}")
        except Exception as e: print(f"{RED}❌ Error: {e}{RESET}")

if __name__ == "__main__":
    search_loop()