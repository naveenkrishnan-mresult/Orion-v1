import streamlit as st

st.set_page_config(page_title="ORION Landing", page_icon="🚀", layout="wide")

# Initialize session state
if "show_popup" not in st.session_state:
    st.session_state.show_popup = False

# CSS for bot icon
st.markdown("""
<style>
.bot-icon {
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 60px;
    height: 60px;
    background: #5d23b6;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    z-index: 1000;
    font-size: 24px;
    color: white;
}
</style>
""", unsafe_allow_html=True)

# Floating bot button
if not st.session_state.show_popup:
    st.markdown("""
    <style>
    .floating-bot {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 1000;
    }
    </style>
    <div class="floating-bot">
    """, unsafe_allow_html=True)
    
    if st.button("🤖", key="floating_bot", help="Open ORION Assistant"):
        st.session_state.show_popup = True
        st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)

# Show popup if triggered
if st.session_state.show_popup:
    with st.container():
        st.markdown("### 🤖 ORION Assistant")
        st.markdown("Choose your workflow:")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🤖 Chatbot Interface", use_container_width=True):
                st.switch_page("pages/chatbot.py")
        with col2:
            if st.button("⚙️ Main Workflow", use_container_width=True):
                st.switch_page("main_interface.py")
        
        if st.button("❌ Close"):
            st.session_state.show_popup = False
            st.rerun()
else:
    # Main landing content
    st.title("🚀 ORION - JIRA Workflow System")
    st.markdown("### AI-Powered Project Management Assistant")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **🤖 Chatbot Interface**
        - Conversational JIRA task creation
        - Guided step-by-step process
        - Beginner-friendly
        """)
    
    with col2:
        st.markdown("""
        **⚙️ Main Workflow Interface**
        - Full JIRA project integration
        - Advanced requirement analysis
        - Comprehensive validation
        """)
    
    st.markdown("---")
    st.markdown("Click the bot icon in the bottom right to get started! 👉")