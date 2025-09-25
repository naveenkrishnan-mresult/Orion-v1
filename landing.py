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


/* Centered container */
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
    color: #222; /* dark text for readability */
    max-width: 700px;
    background: rgba(255,255,255,0.7); /* light semi-transparent background */
    padding: 20px;
    border-radius: 16px;
    box-shadow: 0 8px 16px rgba(0,0,0,0.2);
}

/* Floating chat icon */
.chat-icon {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 70px;
    height: 70px;
    cursor: pointer;
    border-radius: 50%;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    box-shadow: 0 4px 12px rgba(67, 206, 162,0.4);
}
.chat-icon:hover {
    transform: scale(1.1);
    box-shadow: 0 8px 24px rgba(67, 206, 162,0.6);
}
</style>
""", unsafe_allow_html=True)

# --- Logo in the center ---
col1, col2, col3 = st.columns([3,1,3])
with col2:
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

# --- Floating Chat Icon ---
chat_icon_base64 = get_base64_image("bot designs\images (1).jpg")
st.markdown(f"""
<a href="/chatbot" target="_blank">
    <img src="data:image/png;base64,{chat_icon_base64}" class="chat-icon">
</a>
""", unsafe_allow_html=True)
