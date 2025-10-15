import streamlit as st

def markdown_frame(element):
    """
    add in the styles for the streamlit
    """
    if element=="base":

        markdown_styles="""
        <style>
        .main .block-container {
            padding-top: 0rem;
            padding-bottom: 0rem;
            margin-top: 0rem;
        }
        .stApp > header {
            background-color: transparent;
        }
        .stApp {
            margin-top: -50px;
        }
        .chat-container {
            display: flex;
            flex-direction: column;
            margin-top: 0rem;
            width: 100%;
        }
        .msg-bubble {
            padding: 12px 18px;
            border-radius: 50px;
            max-width: 70%;
            word-wrap: break-word;
            margin: 0.2rem 0;
        }
        .bot {
            background-color: #2c5f7e;
            color: white;
            align-self: flex-start;
            border-top-left-radius: 0;
            margin-right: auto;
        
        }
        .user {
            background-color: #E0E0E0;
            color: #333;
            align-self: flex-end;
            border-top-right-radius: 0;
            margin-left: auto;
    
        }
        .typing {
            background-color: #2c5f7e;
            color: white;
            align-self: flex-start;
            border-top-left-radius: 0;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 0.7; }
            50% { opacity: 1; }
        }
        .typing-dots {
            display: inline-block;
        }
        .typing-dots::after {
            content: '.';
            animation: dots 1.5s steps(4, end) infinite;
        }
        @keyframes dots {
            0%, 20% { content: '.'; }
            40% { content: '..'; }
            60% { content: '...'; }
            80%, 100% { content: ''; }
        }
        .stButton > button {
            margin-top: -0.5rem;
        }
        </style>
        """
    if element=="typing":
        markdown_styles="""
        <div class="msg-bubble typing">Typing<span class="typing-dots"></span></div>
        """
    return markdown_styles

def user_message(text):
    """
    appending of the user message
    """
    st.session_state.messages.append({"role": "user", "content": text})

def bot_message(text):
    """
    appending bot message
    """
    st.session_state.messages.append({"role": "bot", "content": text})

def show_typing_with_response(response_text, next_step=None):
    st.session_state.typing = True
    st.session_state.pending_response = {"text": response_text, "step": next_step}