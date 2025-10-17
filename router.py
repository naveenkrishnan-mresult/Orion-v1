import streamlit as st
import os 
from bot_frame_design.style import markdown_frame,user_message,show_typing_with_response,bot_message
from intents.intent_for_bot import intents_for_flow_detections
from config.config_setup import read_json
# Add debug logs to trace initialization
import logging
import json
logger = logging.getLogger(__name__)

from agents_framework.jira_interactions import JiraAgenticIntegration
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

if "workflow_state" not in st.session_state:
    logger.info("Initializing workflow state")
    st.session_state.workflow_state = {
        "selected_project": None,
        "parent_issue":None,
        "child_task":None,
    }

# Display chat history
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state.messages:
    role_class = "user" if msg["role"] == "user" else "bot"
    st.markdown(f'<div class="msg-bubble {role_class}">{msg["content"]}</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# Workflow steps following main.py node structure
if st.session_state.step == "hlr":
    user_input = st.chat_input("Type your response...",key="intializer")
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
    file_path=os.path.join("config", "project_access.json")
    projects=read_json(file_path)
    st.session_state.projects_loaded = True
    st.session_state.projects = projects
        
    if not st.session_state.projects:
        bot_message("No accessible JIRA projects found.")
        st.session_state.step = "hlr"
        st.rerun()
    else:
        st.markdown("<b>Select a JIRA project:</b>",unsafe_allow_html=True)
        project_options = [f"{p['key']}: {p['name']}" for p in projects]

        selected = st.selectbox("Projects", project_options, index=None, label_visibility="collapsed")
        
        if selected:
            project_key = selected.split(":")[0]
            st.session_state.workflow_state["selected_project"] = project_key
            user_message(f"Selected project: {selected}")
            bot_message("Choose your workflow:")
            st.session_state.step = "workflow_choice"
            del st.session_state.projects_loaded
            st.rerun()

elif st.session_state.step == "workflow_choice":
    st.markdown("<b>Choose workflow:</b>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Work with existing JIRA issues", use_container_width=True):
            user_message("Work with existing JIRA issues")
            st.session_state.step = "jira_issues"
            st.rerun()
    with col2:
        if st.button("Create new requirement", use_container_width=True):
            user_message("Create new requirement")
            bot_message("Please enter your High-Level Requirement:")
            st.session_state.step = "hlr_input"
            st.rerun()

elif st.session_state.step == "jira_issues":
    project_key = st.session_state.workflow_state["selected_project"]
    with st.spinner("Retrieving project tasks..."):
        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@developing comment this code@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
        # ##########################commenting this part out as we have epics in config file to reduce token usage code to call jira agent 
        
        # issues = JiraAgenticIntegration().get_issues_agentic(project_key)
        # issues_detail = []
        # selected_issues_list= [issue.key for issue in issues],
        # for ind, issue in enumerate(issues):
        #     issue_text = (
        #         f"{ind}. Issue: {issue.key} - {issue.summary} <br> "
        #         f"Type: {issue.issue_type} <br> "
        #         f"Status: {issue.status} <br> "
        #         f"{f'Description: {issue.description} <br>' if issue.description else ''}<br>"
        #     )
        #     issues_detail.append(issue_text)
        
        # #####################################end of jira agent ######################################
        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
   
        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@production comment this code @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
        # ############################code while developing to skip agent ###########################
        base_dir = os.path.dirname(__file__)        
        config_path = os.path.join(base_dir, "config", "data_epic.json")
        config_path_key = os.path.join(base_dir, "config", "data_epic_key.json")
        ## --- do this only once in a while Write list to file so that we can skip call to agent everytime ---
        
        # # #for the epics content
        # with open(config_path, "w", encoding="utf-8") as f:
        #     json.dump(issues_detail, f, indent=2, ensure_ascii=False)
        # # @for epics key
        # with open(config_path_key, "w", encoding="utf-8") as f:
        #     json.dump(selected_issues_list, f, indent=2, ensure_ascii=False)
        ## --- end of write to json ---

        ## ---comment this when write is present code to read from json ---
        with open(config_path, "r", encoding="utf-8") as f:
            issues_detail = json.load(f)
        with open(config_path_key, "r", encoding="utf-8") as f:
            selected_issues_list = json.load(f)

        # @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
            
        issues_detail_str = " <br> ".join(issues_detail)
        st.session_state.workflow_state.update({
            "issues_detail": issues_detail_str,
            "selected_issues": selected_issues_list,
            "issues_list": issues_detail
        })
        st.session_state.issues_loaded = True
    
    selected_issue = st.selectbox(
        f"Found {len(st.session_state.workflow_state['issues_list'])} issues in project {project_key}",
        options=st.session_state.workflow_state["issues_list"],
        key="issue_dropdown",
        format_func=lambda x: x.replace('<br>', ' | ').replace('<b>', '').replace('</b>', ''),
        index=None
    )
    
    if selected_issue:
        st.session_state.workflow_state["parent_issue"] = selected_issue
        user_message(f"Selected issue: {selected_issue.replace('<br>', ' | ').replace('<b>', '').replace('</b>', '')}")
        bot_message("Please enter your Requirement:")
        st.session_state.step = "get_child_task"
        st.rerun()

elif st.session_state.step == "get_child_task":
    child_task_input = st.chat_input("Type your response...",key="get_child_task")
    if child_task_input:
        st.session_state.workflow_state["get_child_task"] = child_task_input
        print(child_task_input)
        st.session_state.step = "end_task"
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
