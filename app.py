import streamlit as st
import pandas as pd
import io
import requests
import os
import re
from datetime import datetime

# --- CONFIGURATION ---
DB_FILE = 'football_master_db.csv'
MASTER_DB_FILE = 'REC_CONS_MASTER.csv' 
GOOGLE_SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/18kLsLZVPYehzEjlkZMTn0NP0PitRonCKXyjGCRjLmms/export?format=csv&gid=1572560106"

# --- CONSTANTS & LISTS ---
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

    # 2. Load Main Database (The 57k list)
    try:
        df = pd.read_csv(DB_FILE, encoding='utf-8').fillna("")
    except UnicodeDecodeError:
        df = pd.read_csv(DB_FILE, encoding='latin1').fillna("")
    except FileNotFoundError:
        return None, None, None

    return df, lookup, name_lookup

def get_snippet(text, keyword):
    if pd.isna(text) or text == "": return ""
    clean_text = str(text).replace('\n', ' ').replace('\r', ' ')
    for term in GOLD_
