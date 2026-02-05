import streamlit as st
import os
import glob
import pandas as pd

st.set_page_config(page_title="Debug Mode")

st.title("✅ The App is Running!")
st.write("If you can see this, the server is working perfectly.")

st.header("📂 File System Check")
# List every single file in the folder so we know where the chunks are
files = os.listdir()
st.write(f"Files found in current directory: {len(files)}")
st.write(files)

st.header("🔍 Chunk Detective")
chunk_files = glob.glob("chunk_*.csv")
if chunk_files:
    st.success(f"SUCCESS: Found {len(chunk_files)} chunk files!")
    st.write(f"First 5 chunks: {chunk_files[:5]}")
    
    # Try to read the first one to verify pandas works
    try:
        df_test = pd.read_csv(chunk_files[0])
        st.success(f"✅ Pandas successfully read '{chunk_files[0]}' ({len(df_test)} rows).")
    except Exception as e:
        st.error(f"❌ Pandas crashed reading the file: {e}")
else:
    st.error("❌ FAILURE: No 'chunk_*.csv' files found. They might be in a subfolder?")
