import streamlit as st
import os
import glob
import re
import gc
# NOTE: We do NOT import pandas yet to save memory on startup

# 1. LIGHTWEIGHT STARTUP
st.set_page_config(page_title="Recruiting Search", layout="wide")
st.title("🏈 Recruiting Tool - Safe Mode")
st.write("### ✅ System Status: ONLINE")

# 2. VERIFY FILES
chunk_files = glob.glob("chunk_*.csv")
if not chunk_files:
    st.error("❌ No chunk files found.")
    st.stop()
else:
    st.info(f"📂 Detected {len(chunk_files)} database chunks ready for scanning.")

# 3. THE SAFETY SWITCH
# We only load the heavy logic when you physically press this button.
if "engine_loaded" not in st.session_state:
    st.session_state["engine_loaded"] = False

if not st.session_state["engine_loaded"]:
    if st.button("🚀 CLICK TO ACTIVATE SEARCH ENGINE"):
        st.session_state["engine_loaded"] = True
        st.rerun()

# 4. HEAVY LOGIC (Only runs after activation)
if st.session_state["engine_loaded"]:
    import pandas as pd  # Import here to save startup memory
    
    st.success("✅ Search Engine Active")
    
    # INPUT
    keywords_str = st.text_input("Enter Keywords (comma separated):", placeholder="e.g. tallahassee, atlanta")
    
    if st.button("Run Search"):
        if not keywords_str:
            st.warning("Please enter a keyword.")
        else:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
            results = []
            
            # Progress Bar
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Sort files numerically (chunk_0, chunk_1...)
            try: chunk_files.sort(key=lambda x: int(re.search(r'\d+', x).group()))
            except: pass

            # SCANNING LOOP
            for i, file in enumerate(chunk_files):
                status_text.text(f"Scanning file {i+1} of {len(chunk_files)}...")
                progress_bar.progress((i + 1) / len(chunk_files))
                
                try:
                    # Low-Memory Read: Only read headers first to find the Bio column
                    # This prevents loading useless columns into RAM
                    df_iter = pd.read_csv(file, chunksize=500) 
                    
                    for chunk in df_iter:
                        # Fix Columns
                        chunk.columns = [c.strip() for c in chunk.columns]
                        
                        # Find Bio Column
                        bio_col = None
                        for c in chunk.columns:
                            if c.lower() in ['bio', 'full_bio', 'description', 'full bio']:
                                bio_col = c
                                break
                        
                        if bio_col:
                            # Search
                            mask = chunk[bio_col].str.contains('|'.join(keywords), case=False, na=False)
                            if mask.any():
                                found_rows = chunk[mask].copy()
                                found_rows['Source_Chunk'] = file
                                results.append(found_rows)
                        
                        # cleanup
                        del chunk
                    
                    # Force Memory Release
                    gc.collect()

                except Exception as e:
                    print(f"Skipped {file}: {e}")
                    continue

            # CLEANUP UI
            status_text.empty()
            progress_bar.empty()

            # DISPLAY RESULTS
            if results:
                final_df = pd.concat(results)
                st.subheader(f"🎉 Found {len(final_df)} Matches!")
                st.dataframe(final_df)
            else:
                st.warning("No matches found in the database.")
