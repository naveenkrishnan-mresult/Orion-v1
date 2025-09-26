import streamlit as st

st.set_page_config(page_title="Chatbot Popup", layout="wide")

# --- Custom CSS for floating chatbox ---
st.markdown("""
    <style>
    .chat-popup {
        position: fixed;
        bottom: 20px;
        right: 20px;
        border: 1px solid #ccc;
        border-radius: 10px;
        width: 300px;
        background: white;
        box-shadow: 0px 4px 12px rgba(0,0,0,0.2);
        z-index: 9999;
        padding: 10px;
    }
    .chat-messages {
        max-height: 250px;
        overflow-y: auto;
        margin-bottom: 10px;
    }
    .user-msg {
        background: #0084ff;
        color: white;
        padding: 6px 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: right;
    }
    .bot-msg {
        background: #e5e5ea;
        color: black;
        padding: 6px 10px;
        border-radius: 10px;
        margin: 5px 0;
        text-align: left;
    }
    </style>
""", unsafe_allow_html=True)

# --- Chat UI ---
st.markdown('<div class="chat-popup">', unsafe_allow_html=True)
st.markdown('<div class="chat-messages">', unsafe_allow_html=True)

# Example messages
st.markdown('<div class="user-msg">Hey, how are you?</div>', unsafe_allow_html=True)
st.markdown('<div class="bot-msg">I am doing great, how about you?</div>', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# Input box
user_input = st.text_input("Ask me anything!", key="chat_input")
st.markdown('</div>', unsafe_allow_html=True)

if user_input:
    st.write(f"User typed: {user_input}")
