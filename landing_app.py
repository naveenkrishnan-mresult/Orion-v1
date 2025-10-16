import streamlit as st

# Simple landing app that links to the chat-based main_interface
# This file is a standalone Streamlit entrypoint. It does not modify
# `main_interface.py`. Run it with:
#   streamlit run landing_app.py

st.set_page_config(page_title="ORION Landing", layout="wide")

st.markdown("""
    <style>
    .landing-container { max-width:900px; margin: 40px auto; }
    .chat-icon { position: fixed; right: 24px; bottom: 24px; width: 64px; height: 64px; border-radius: 50%; background: linear-gradient(135deg, #2c5f7e, #4ea1d3); display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 18px rgba(0,0,0,0.2); cursor: pointer; z-index: 9999; }
    .chat-icon img { width: 36px; height: 36px; }
    </style>
""", unsafe_allow_html=True)

st.markdown("<div class='landing-container'>", unsafe_allow_html=True)
st.title("ORION — JIRA Workflow Assistant")
st.write("Welcome to ORION. Click the chat icon at the bottom-right to open the assistant.")
st.write("This landing page is separate from the chat entrypoint and will open the chat in the same browser tab.")

# The main chat UI is in main_interface.py; we use a query param to open it.
open_link = "main_interface.py?open_chat=true"

st.markdown(f"<a href='{open_link}' class='chat-icon' title='Open chat'><img src='https://img.icons8.com/ios-filled/50/ffffff/chat.png' alt='chat'></a>", unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)

# Small note with run instructions
st.info("Run with: `streamlit run landing_app.py` and then click the chat icon to open the assistant.")
