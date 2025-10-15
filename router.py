import streamlit as st
from bot_frame_design.style import markdown_frame,user_message,show_typing_with_response,bot_message
from intents.intent_for_bot import intents_for_flow_detections
from agents_framework import JiraAgenticIntegration
st.markdown(markdown_frame("base"), unsafe_allow_html=True)

################# Initialize of session items################
if "step" not in st.session_state:
    st.session_state.step = "hlr"
if "typing" not in st.session_state:
    st.session_state.typing = False
if "pending_response" not in st.session_state:
    st.session_state.pending_response = None

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "bot", "content": "Hello! I'm Orion, your AI-powered JIRA assistant."},
        {"role": "bot", "content": "I can help you create and update tasks, generate epics and user stories, answer questions about your projects, and guide you through project management workflows."}
    ]


# Display chat history
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state.messages:
    role_class = "user" if msg["role"] == "user" else "bot"
    st.markdown(f'<div class="msg-bubble {role_class}">{msg["content"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Chat input
user_input = st.chat_input("Type your response...")

# Workflow steps following main.py node structure
if st.session_state.step == "hlr":
    if user_input:
        st.session_state.hlr = user_input
        user_message(user_input)
        keyword =intents_for_flow_detections()
        if any([i in user_input.lower() for i in keyword]):
            show_typing_with_response("Let me fetch your JIRA projects...", "jira_projects")
            st.rerun()
        else:
            show_typing_with_response("I can help with task creation. Please type 'create a task' to proceed.")
        st.rerun()

elif st.session_state.step == "jira_projects":   
    agents = JiraAgenticIntegration()
    projects = agents.get_projects_agentic()
    st.session_state.projects_loaded = True
    st.session_state.projects = projects
        
    if not st.session_state.projects:
        bot_message("No accessible JIRA projects found.")
        st.session_state.step = "hlr"
        st.rerun()
    else:
        st.markdown("<b>Select a JIRA project:</b>",unsafe_allow_html=True)
        project_options = [f"{p.key}: {p.name}" for p in st.session_state.projects]

        selected = st.selectbox("Projects", project_options, index=None, label_visibility="collapsed")
        
        if selected:
            project_key = selected.split(":")[0]
            st.session_state.workflow_state["selected_project"] = project_key
            user_message(f"Selected project: {selected}")
            bot_message("Choose your workflow:")
            st.session_state.step = "workflow_choice"
            
            del st.session_state.projects_loaded
            st.rerun()

# Show typing indicator and handle pending response
if st.session_state.typing:
    st.markdown(markdown_frame("typing"), unsafe_allow_html=True)
    # Process pending response after a brief delay
    if st.session_state.pending_response:
        response_data = st.session_state.pending_response
        st.session_state.typing = False
        st.session_state.pending_response = None
        bot_message(response_data["text"])
        if response_data["step"]:
            st.session_state.step = response_data["step"]
        st.rerun()
