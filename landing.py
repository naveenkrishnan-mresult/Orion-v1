import streamlit as st
from PIL import Image
import base64
st.set_page_config(
    page_title="ORION Chatbot",
    page_icon="🤖",
    layout="wide",
)

def get_base64_image(image_path):
    with open(image_path, "rb") as f:
        data = f.read()
        return base64.b64encode(data).decode()

# --- Custom CSS with new colors ---
st.markdown("""
<style>
body {
    background: linear-gradient(135deg, #ff512f, #dd2476);
    font-family: 'Arial', sans-serif;
}
.center-container {
display: flex;
flex-direction: column;
align-items: center;
justify-content: center;
text-align: center;

color: white;
}
/* Logo style */
.company-logo {
    width: 150px;
    height: auto;
    margin-bottom: 10px;
    border-radius: 50%;
    box-shadow: 0 8px 20px rgba(0,0,0,0.3);
    transition: transform 0.3s ease;
}
.company-logo:hover {
    transform: scale(1.05);
}
/* Title style */
.title {
    font-size: 3rem;
    font-weight: bold;
    margin-bottom: 15px;
    background: -webkit-linear-gradient(#43cea2, #185a9d);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Description style */
.description {
    font-size: 1.3rem;
    color: #222;
    max-width: 700px;
    background: rgba(255,255,255,0.7);
    padding: 20px;
    border-radius: 16px;
    box-shadow: 0 8px 16px rgba(0,0,0,0.2);
}

/* Floating chat icon */
.chat-fab {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 70px;
    height: 70px;
    border-radius: 50%;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(67, 206, 162,0.4);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    z-index: 10000;
    border: none;
    background-size: cover;
    background-position: center;
}
.chat-fab:hover {
    transform: scale(1.1);
    box-shadow: 0 8px 24px rgba(67, 206, 162,0.6);
}
</style>
""", unsafe_allow_html=True)

# --- Logo in the center ---
st.image("bot designs/images.jpg", width=150)

# --- Title and Description ---
st.markdown("""
<div class="center-container">
    <div class="title">Your Virtual JIRA Assistant Awaits</div>
    <div class="description">
        ORION is an AI-powered JIRA assistant that helps you create, update, and track tasks effortlessly. 
        Generate epics and user stories automatically, get instant guidance, and streamline your project workflow.
    </div>
</div>
""", unsafe_allow_html=True)

# Initialize popup state
if "show_popup" not in st.session_state:
    st.session_state.show_popup = False

# Load chat icon as base64
chat_icon_base64 = get_base64_image("bot designs/images (1).jpg")

# Chat button with styling
st.markdown(f"""
<style>
div[data-testid="stButton"] > button {{
    position: fixed !important;
    bottom: 20px !important;
    right: 20px !important;
    left: auto !important;
    margin-left: auto !important;
    width: 70px !important;
    height: 70px !important;
    border-radius: 50% !important;
    border: none !important;
    background-image: url(data:image/jpeg;base64,{chat_icon_base64}) !important;
    background-size: cover !important;
    background-position: center !important;
    cursor: pointer !important;
    transition: transform 0.3s ease, box-shadow 0.3s ease !important;
    box-shadow: 0 4px 12px rgba(67, 206, 162,0.4) !important;
    z-index: 1000 !important;
    color: transparent !important;
    font-size: 0 !important;
}}
div[data-testid="stButton"] > button:hover {{
    transform: scale(1.1) !important;
    box-shadow: 0 8px 24px rgba(67, 206, 162,0.6) !important;
}}
</style>
""", unsafe_allow_html=True)

# Chat button positioned absolutely
st.markdown(f"""
<div style="position: fixed; bottom: 20px; right: 20px; z-index: 1000;">
    <img src="data:image/jpeg;base64,{chat_icon_base64}" 
        style="width: 70px; height: 70px; border-radius: 50%; cursor: pointer; 
                box-shadow: 0 4px 12px rgba(67, 206, 162,0.4); 
                transition: transform 0.3s ease;" 
        onclick="document.getElementById('chat_trigger').click()">
</div>
""", unsafe_allow_html=True)

# Check if chat icon was clicked
if st.query_params.get("chat_clicked"):
    st.session_state.show_popup = True
    st.query_params.clear()

# Chat icon as clickable button
st.markdown(f"""
<form method="get">
    <button type="submit" name="chat_clicked" value="true" 
            style="position: fixed; bottom: 20px; right: 20px; z-index: 1000;
                width: 70px; height: 70px; border-radius: 50%; border: none;
                background-image: url(data:image/jpeg;base64,{chat_icon_base64});
                background-size: cover; background-position: center; cursor: pointer;
                box-shadow: 0 4px 12px rgba(67, 206, 162,0.4);
                transition: transform 0.3s ease;">
    </button>
</form>
""", unsafe_allow_html=True)

# Popup modal
if st.session_state.show_popup:
    st.markdown("""
    <div style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        z-index: 9999;
        display: flex;
        justify-content: center;
        align-items: center;
    ">
        <div style="
            background: white;
            border-radius: 10px;
            width: 50%;
            height: 80%;
            position: relative;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        ">
            <iframe
                src="http://localhost:8501/?embed=true"
                height="650"
                style="width:100%;border:none;"
            ></iframe>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Close button
    if st.button("✕ Close", key="close_popup"):
        st.session_state.show_popup = False


