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

# --- Enhanced Custom CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

.stApp {
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: #fff;
    text-align: center;
    padding: 2rem;
    margin-top: -50px;
}

/* Animated background particles */
.particles {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: -1;
}

.particle {
    position: absolute;
    width: 4px;
    height: 4px;
    background: rgba(255,255,255,0.3);
    border-radius: 50%;
    animation: float 6s ease-in-out infinite;
}

@keyframes float {
    0%, 100% { transform: translateY(0px) rotate(0deg); }
    50% { transform: translateY(-20px) rotate(180deg); }
}



/* Enhanced logo style */
.logo-container {
    position: relative;
    margin-bottom: 1rem;
    animation: fadeInUp 1s ease-out;
}

.company-logo {
    width: 150px;
    height: 130px;
    border-radius: 50%;
    box-shadow: 0 20px 40px rgba(0,0,0,0.3), 0 0 0 10px rgba(255,255,255,0.1);
    transition: all 0.4s ease;
    object-fit: cover;
    border: 4px solid rgba(255,255,255,0.2);
}

.company-logo:hover {
    transform: scale(1.1) rotate(5deg);
    box-shadow: 0 30px 60px rgba(0,0,0,0.4), 0 0 0 15px rgba(255,255,255,0.2);
}

/* Title */
.stMarkdown .title {
    font-size: 3rem;
    font-weight: 600;
    margin-bottom: rem;
    background: -webkit-linear-gradient(#fff, #ddd);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

/* Description */
.stMarkdown .description {
    font-size: 1.2rem;
    max-width: 900px;
    margin: 0 auto 2rem auto;
    background: rgba(255,255,255,0.15);
    padding: 1rem;
    border-radius: 12px;
    line-height: 1.6;
    color: #fff;
}

/* Features grid */
.stMarkdown .features {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1rem;
    margin-top: 1rem;
}

/* Feature card */
.stMarkdown .feature-card {
    background: rgba(255,255,255,0.15);
    padding: 1rem;
    border-radius: 16px;
    box-shadow: 0 6px 18px rgba(0,0,0,0.1);
    transition: all 0.3s ease;
    width: 90%;
}
.stMarkdown .feature-card:hover {
    transform: translateY(-6px);
}

/* Feature content */
.stMarkdown .feature-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
    display: block;
}
.stMarkdown .feature-title {
    font-size: 1.2rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}
.stMarkdown .feature-text {
    font-size: 1rem;
    opacity: 0.9;
}

/* Enhanced floating chat icon */
.chat-fab {
    position: fixed;
    bottom: 30px;
    right: 30px;
    width: 80px;
    height: 80px;
    border-radius: 50%;
    cursor: pointer;
    box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4);
    transition: all 0.3s ease;
    z-index: 10000;
    border: 3px solid rgba(255,255,255,0.3);
    background-size: cover;
    background-position: center;
    animation: pulse 2s infinite;
}

.chat-fab:hover {
    transform: scale(1.15);
    box-shadow: 0 15px 35px rgba(102, 126, 234, 0.6);
}

@keyframes pulse {
    0% { box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4), 0 0 0 0 rgba(102, 126, 234, 0.7); }
    70% { box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4), 0 0 0 10px rgba(102, 126, 234, 0); }
    100% { box-shadow: 0 8px 25px rgba(102, 126, 234, 0.4), 0 0 0 0 rgba(102, 126, 234, 0); }
}

/* Animations */
@keyframes fadeInUp {
    from {
        opacity: 0;
        transform: translateY(30px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

/* Footer */
.stMarkdown .footer {
    background: rgba(0,0,0,0.3);
    padding: 2rem 1rem;
    margin-top: 3rem;
    text-align: center;
    border-top: 1px solid rgba(255,255,255,0.1);
}

.stMarkdown .footer-logo {
    width: 60px;
    height: 60px;
    border-radius: 50%;
    object-fit: cover;
    margin-bottom: 1rem;
}

.stMarkdown .footer-text {
    color: rgba(255,255,255,0.8);
    font-size: 0.9rem;
}

/* Responsive design */
@media (max-width: 768px) {
    .title {
        font-size: 2.5rem;
    }
    .description {
        font-size: 1.2rem;
        padding: 2rem;
    }
    .company-logo {
        width: 150px;
        height: 150px;
    }
    .features {
        grid-template-columns: 1fr;
    }
}
</style>
""", unsafe_allow_html=True)

# --- Animated background particles ---
st.markdown("""
<div class="particles">
    <div class="particle" style="left: 10%; animation-delay: 0s;"></div>
    <div class="particle" style="left: 20%; animation-delay: 1s;"></div>
    <div class="particle" style="left: 30%; animation-delay: 2s;"></div>
    <div class="particle" style="left: 40%; animation-delay: 3s;"></div>
    <div class="particle" style="left: 50%; animation-delay: 4s;"></div>
    <div class="particle" style="left: 60%; animation-delay: 5s;"></div>
    <div class="particle" style="left: 70%; animation-delay: 0.5s;"></div>
    <div class="particle" style="left: 80%; animation-delay: 1.5s;"></div>
    <div class="particle" style="left: 90%; animation-delay: 2.5s;"></div>
</div>
""", unsafe_allow_html=True)

# --- Main Content ---
logo_base64 = get_base64_image("bot designs/logo.png")
logo_base64_1 = get_base64_image("bot designs/images.jpg")

st.markdown(f"""

    <div class="logo-container">
        <img src="data:image/jpeg;base64,{logo_base64}" class="company-logo" alt="ORION Logo",caption="ORION">
    </div>
    <div class="title">Your Virtual JIRA Assistant Awaits</div>

    <div class="description">
        🚀 ORION is an AI-powered JIRA assistant that revolutionizes your project management experience. 
        Create, update, and track tasks effortlessly while generating epics and user stories automatically. 
        Get instant guidance and streamline your entire project workflow with intelligent automation.
    </div>

    <div class="features">
        <div class="feature-card">
            <span class="feature-icon">📚</span>
            <div class="feature-title">AI Epic Creation</div>
            <div class="feature-text">Intelligent AI agents automatically generate comprehensive epics with detailed requirements and acceptance criteria</div>
        </div>
        <div class="feature-card">
            <span class="feature-icon">📝</span>
            <div class="feature-title">Smart User Stories</div>
            <div class="feature-text">AI-powered user story generation with proper formatting, acceptance criteria, and story point estimation</div>
        </div>
        <div class="feature-card">
            <span class="feature-icon">🎫</span>
            <div class="feature-title">Automated Issue Tickets</div>
            <div class="feature-text">Automated issue ticket creation with intelligent assignment to user groups based on skills and workload</div>
        </div>
    </div>

    <div class="footer">
        <img src="data:image/jpeg;base64,{logo_base64_1}" class="footer-logo" alt="ORION Logo">
        <div class="footer-text">
            © 2024 ORION. All rights reserved.
        </div>
    </div>

""", unsafe_allow_html=True)

# Initialize popup state
if "show_popup" not in st.session_state:
    st.session_state.show_popup = False

# Load chat icon as base64
chat_icon_base64 = get_base64_image("bot designs/images (1).jpg")

# Only show one chat icon as clickable button
st.markdown(f"""
<form method="get">
    <button type="submit" name="chat_clicked" value="true" 
            style="position: fixed; bottom: 20px; right: 20px; z-index: 1000;
                width: 70px; height: 70px; border-radius: 50%; border: none;
                background-image: url(data:image/jpeg;base64,{chat_icon_base64});
                background-size: cover; background-position: center; cursor: pointer;
                box-shadow: 0 4px 12px rgba(67, 206, 162,0.4);
                transition: transform 0.3s ease;"
                class="chat-fab">
    </button>
</form>
""", unsafe_allow_html=True)

# Check if chat icon was clicked
if st.query_params.get("chat_clicked"):
    st.session_state.show_popup = True
    st.query_params.clear()

# Popup modal
if st.session_state.show_popup:
    st.markdown(f"""
    <div style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        z-index: 9999;
        display: flex;
        justify-content: flex-end;
        align-items: center;
    ">
        <div style="
            background: white;
            border-radius: 50px;
            width: 40%;
            height: 90%;
            position: relative;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            overflow: hidden;
            margin-right: 20px;
        ">
            <!-- Header -->
            <div style="
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 15px 20px;
                display: flex;
                align-items: center;
                justify-content: space-between;
                border-radius: 50px 50px 0 0;
            ">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <img src="data:image/jpeg;base64,{logo_base64}" 
                         style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;">
                    <div style="color: white; font-weight: 600; font-size: 18px;">ORION Chat</div>
                </div>
            </div>
            <iframe
                src="http://localhost:8502/?embed=true"
                height="95%"
                style="width:100%;border:none;"
            ></iframe>
            <!-- Close button inside modal -->
            <form method="get" style="position:absolute; top:10px; right:10px;">
                <button type="submit" value="true"
                    style="
                        border:none;
                        background:#f00;
                        color:white;
                        font-size:16px;
                        padding:5px 10px;
                        border-radius:20px;
                        cursor:pointer;
                    ">✕</button>
            </form>
        </div>
    </div>
    """, unsafe_allow_html=True)

# Handle close query param
if st.query_params.get("close_popup"):
    st.session_state.show_popup = False
    st.query_params # clear params


