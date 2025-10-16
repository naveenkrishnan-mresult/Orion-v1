import streamlit as st

st.set_page_config(page_title="Chatbot", layout="wide")

# Button to open the dialog
if st.button("Open Chatbot"):
    @st.dialog(title="ORION Chat", width="medium")
    def chat_popup():
        st.markdown(
            """
            <div style="
                height:400px; 
                width:350px; 
                border:1px solid #ddd; 
                border-radius:10px; 
                padding:10px; 
                overflow-y:auto;
                display:flex;
                flex-direction:column;
            ">
            """,
            unsafe_allow_html=True
        )
        # Chat input
        user_input = st.text_input("Type your message...", key="chat_input")
        if user_input:
            st.markdown(
                f"<div style='margin-bottom:10px;padding:8px 12px;border-radius:8px;background-color:#DCF8C6;align-self:flex-end;'>{user_input}</div>",
                unsafe_allow_html=True
            )

    chat_popup()  # Call the decorated function to open the popup
