import streamlit as st
from io import StringIO
import asyncio
import json
from main import (
    JiraIntegrationAgent, RequirementAnalysisAgent, EpicGeneratorAgent, 
    GenerationType, AnalysisPhase, UserStoryGeneratorAgent,create_clean_output
)    
from openai import OpenAI
import os
from dotenv import load_dotenv
from jira import JIRA
JIRA_SERVER =os.getenv("JIRA_SERVER")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Create Jira connection
jira = JIRA(
    server=JIRA_SERVER,
    basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)  # email + API token
)

load_dotenv()

st.set_page_config(page_title="JIRA Workflow", page_icon="🔄", layout="centered")

# Custom CSS
st.markdown("""
    <style>
    .chat-header {
        background: #5d23b6;
        color: #fff;
        border-radius: 24px 24px 0 0;
        padding: 1rem 2rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .chat-header .title {
        font-size: 1.5rem;
        font-weight: 500;
        letter-spacing: 1px;
    }
    .msg-bubble {
        padding: 12px 18px;
        border-radius: 50px;
        max-width: 100%;
        word-wrap: break-word;
        margin: 0.5rem 0;
    }
    .bot {
        background-color: #5d23b6;
        color: white;
        align-self: flex-start;
        border-top-left-radius: 0;
    }
    .user {
        background-color: #f1f0f0;
        color: #333;
        align-self: flex-end;
        border-top-right-radius: 0;
    }
    </style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
    <div class="chat-header">
        <h2 class="title">ORION JIRA Workflow</h2>
    </div>
""", unsafe_allow_html=True)

# Initialize session state
if "step" not in st.session_state:
    st.session_state.step = "hlr"
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "bot", "content": "Hello! I'm Orion, your AI-powered JIRA assistant."},
        {"role": "bot", "content": "I can help you create and update tasks, generate epics and user stories, answer questions about your projects, and guide you through project management workflows. Please let me know what you want to do!"}
    ]
if "workflow_state" not in st.session_state:
    st.session_state.workflow_state = {
        "session_id": "",
        "workflow_type": "",
        "hlr": "",
        "selected_project": None,
        "selected_issues": [],
        "issues_detail": "",
        "persona": "",
        "slicing_type": "",
        "generation_type": GenerationType.BOTH,
        "phase": AnalysisPhase.INPUT,
        "questions": [],
        "responses": {},
        "validation_results": {},
        "requirement_analysis": {},
        "epics": [],
        "user_stories": [],
        "feedback_history": [],
        "feedback_count": 0,
        "overall_confidence": 0.0,
        "errors": [],
        "current_step": ""
    }
if "agents" not in st.session_state:
    st.session_state.agents = {
        "jira": JiraIntegrationAgent(),
        "req": RequirementAnalysisAgent()
    }
if "question_idx" not in st.session_state:
    st.session_state.question_idx = 0

def bot_message(text):
    st.session_state.messages.append({"role": "bot", "content": text})

def user_message(text):
    st.session_state.messages.append({"role": "user", "content": text})

# Display chat history
for msg in st.session_state.messages:
    role_class = "user" if msg["role"] == "user" else "bot"
    st.markdown(f'<div class="msg-bubble {role_class}">{msg["content"]}</div>', unsafe_allow_html=True)

# Chat input
user_input = st.chat_input("Type your response...")

# Workflow steps
if st.session_state.step == "hlr":
    if user_input:
        st.session_state.hlr = user_input
        user_message(user_input)
        keyword = ["create", "task", "help","issue", "i want to create", "apply", "generate","make"]
        if any([i in user_input.lower() for i in keyword]):# or "task" in user_input.lower() or "issue" in user_input.lower() or "i want to create" in user_input.lower():
            bot_message("I can either work with the existing workflow or create a new one for you — which would you prefer?")
            st.session_state.step = "start"
            st.rerun()
        else:
            bot_message("I can help with task creation. Please type 'create a task' to proceed.")
            st.rerun()
elif st.session_state.step == "start":
    if user_input:
        user_message(user_input)
        bot_message("Choose your workflow:")
        st.session_state.step = "workflow_choice"
        st.rerun()
    else:
        st.markdown("<b>Choose workflow:</b>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Work with existing JIRA project", use_container_width=True):
                st.session_state.workflow_state["workflow_type"] = "existing"
                user_message("Work with existing JIRA project")
                bot_message("Let me fetch your JIRA projects...")
                st.session_state.step = "jira_projects"
                st.rerun()
        with col2:
            if st.button("Create new requirement", use_container_width=True):
                st.session_state.workflow_state["workflow_type"] = "new"
                user_message("Create new requirement")
                bot_message("Please enter your High-Level Requirement:")
                st.session_state.step = "hlr_input"
                st.rerun()

elif st.session_state.step == "jira_projects":
    projects = st.session_state.agents["jira"].get_projects()
    if not projects:
        bot_message("No JIRA projects found or JIRA not configured.")
        st.session_state.step = "start"
        st.rerun()
    else:
        st.markdown("<b>Select a JIRA project:</b>",unsafe_allow_html=True)
        project_options = [f"{p.key}: {p.name}" for p in projects]
        selected = st.selectbox("Projects", project_options, index=None, label_visibility="collapsed")
        
        if selected:
            project_key = selected.split(":")[0]
            st.session_state.workflow_state["selected_project"] = project_key
            user_message(f"Selected project: {selected}")
            
            # Display issues
            with st.spinner("Retrieving project tasks..."):
                issues = st.session_state.agents["jira"].get_issues_enhanced(project_key)
                issues_detail = []
                for ind, issue in enumerate(issues):
                    issue_text = (
                        f"{ind}. Issue: {issue.key} - {issue.summary} <br> "
                        f"Type: {issue.issue_type} <br> "
                        f"Status: {issue.status} <br> "
                        f"{f'Description: {issue.description} <br>' if issue.description else ''}<br>"
                    )
                    issues_detail.append(issue_text)
                    
                issues_detail_str = " <br> ".join(issues_detail)
                st.session_state.workflow_state.update({
                    "issues_detail": issues_detail_str,
                    "selected_issues": [issue.key for issue in issues],
                    "issues_list": issues_detail
                })
            
            st.selectbox(
                f"Found {len(issues)} issues in project {project_key}",
                options=st.session_state.workflow_state["issues_list"],
                key="issue_dropdown",
                format_func=lambda x: x.replace('<br>', ' | ').replace('<b>', '').replace('</b>', '')
            )
            
            
            bot_message("Now please enter your High-Level Requirement:")
            st.session_state.step = "hlr_input"


elif st.session_state.step == "hlr_input":
    if user_input:
        st.session_state.workflow_state["hlr"] = user_input
        user_message(user_input)
        bot_message("Analyzing your requirement...")
        st.session_state.step = "analyze"
        st.rerun()

elif st.session_state.step == "analyze":
    async def analyze_requirement():
        jira_guidance = ""
        if st.session_state.workflow_state["workflow_type"] == "existing":
            selected_project = st.session_state.workflow_state.get("selected_project")
            if selected_project:
                issues = st.session_state.agents["jira"].get_issues_enhanced(selected_project)
                jira_guidance = st.session_state.agents["jira"].generate_context_guidance(
                    issues, st.session_state.workflow_state["hlr"]
                )
        
        analysis = await st.session_state.agents["req"].analyze_requirement(
            st.session_state.workflow_state["hlr"], jira_guidance
        )
        st.session_state.workflow_state["requirement_analysis"] = analysis
        st.session_state.workflow_state["slicing_type"] = analysis.get("slicing_type", "functional")
        
        recommended_persona = analysis.get("recommended_persona", "Business Analyst")
        st.session_state.workflow_state["persona"] = recommended_persona
        
        questions = await st.session_state.agents["req"].generate_questions(
            st.session_state.workflow_state["hlr"],
            st.session_state.workflow_state["slicing_type"],
            recommended_persona,
            jira_guidance
        )
        st.session_state.workflow_state["questions"] = questions
        return analysis, questions
    
    with st.spinner("Analyzing requirement ..."):
        analysis, questions = asyncio.run(analyze_requirement())
    msg_1 = StringIO()

    msg_1.write("<b>Requirement Analysis Summary:</b><br>")
    msg_1.write(f"Recommended persona: <b>{analysis.get('recommended_persona')}</b> <br> Domain: {analysis.get('domain')}, Complexity: {analysis.get('complexity')}")
    bot_message(msg_1.getvalue())
    # bot_message(f"Generated {len(questions)} questions to clarify your requirement.")
    
    st.session_state.step = "persona_confirm"
    st.rerun()

elif st.session_state.step == "persona_confirm":
    recommended = st.session_state.workflow_state["requirement_analysis"].get("recommended_persona")
    st.markdown(f"<b>Suggested persona:</b> {recommended}",unsafe_allow_html=True)
    
    if st.button("Use suggested persona", use_container_width=True):
        user_message(f"Using suggested persona: {recommended}")
        bot_message("Great! Let's proceed with the questions.You can answer or skip any question by typing 'skip'")
        st.session_state.step = "qa"
        st.rerun()

    custom_persona = st.text_input("Or enter custom persona:", placeholder="e.g., Technical Lead")
    if custom_persona and st.button("Use custom persona", use_container_width=True):
        st.session_state.workflow_state["persona"] = custom_persona
        user_message(f"Using custom persona: {custom_persona}")
        bot_message("Perfect! Let's proceed with the questions.")
        st.session_state.step = "qa"
        st.rerun()
elif st.session_state.step == "qa":
    questions = st.session_state.workflow_state["questions"]
    idx = st.session_state.question_idx
    
    if idx < len(questions):
        q = questions[idx]
        if not st.session_state.get(f"asked_{idx}", False):
            bot_message(
    f"<b>Q{idx+1}:</b> {q.question}<br>"
    f"<i>Context:</i> {q.context}<br>"
    f"<i>Priority:</i> {q.priority}/7 | "
    f"<i>Required:</i> {'Yes' if q.required else 'No'} | "
    f"<b>Type skip to skip</b>"
)
            st.session_state[f"asked_{idx}"] = True
            st.rerun()
        
        if user_input:
            if user_input.lower() == "skip":
                user_message("skip")
                st.session_state.workflow_state["responses"][q.id] = "[SKIPPED]"
                st.session_state.question_idx += 1
                # if st.session_state.question_idx < len(questions):
                #     next_q = questions[st.session_state.question_idx]
                #     bot_message(f"**Q{st.session_state.question_idx+1}:** {next_q.question} <br> *Context:* {next_q.context}<br><br> *Priority:* {q.priority}/7 | *Required:* {'Yes' if q.required else 'No'} |**Type skip to skip**")
                st.rerun()
            elif user_input:
                user_message(user_input)

                st.session_state.workflow_state["responses"][q.id] = user_input
                st.session_state.question_idx += 1
                st.rerun()

    else:
        bot_message("All questions completed! Now select what to generate:")
        st.session_state.step = "generation_type"
        st.rerun()

elif st.session_state.step == "generation_type":
    st.markdown("**Select generation type:**")
    gen_type = st.radio(
        "Options:",
        ["Epics Only", "User Stories Only", "Both Epics and User Stories"],
        index=None,
        label_visibility="collapsed"
    )
    
    if gen_type:
        user_message(gen_type)
        options = {
            "Epics Only": GenerationType.EPICS_ONLY,
            "User Stories Only": GenerationType.STORIES_ONLY,
            "Both Epics and User Stories": GenerationType.BOTH
        }
        st.session_state.workflow_state["generation_type"] = options[gen_type]
        bot_message("Generating content...")
        st.session_state.step = "generate"
        st.rerun()

elif st.session_state.step == "generate":
    async def generate_content():
        # Prepare context
        context = f"Persona: {st.session_state.workflow_state.get('persona', 'Business Analyst')}\n"
        context += f"Slicing Type: {st.session_state.workflow_state.get('slicing_type', 'functional')}\n"
        context += f"Domain: {st.session_state.workflow_state.get('requirement_analysis', {}).get('domain', 'general')}\n"
        
        if st.session_state.workflow_state.get("issues_detail"):
            context += f"\nJIRA Issues Context:\n{st.session_state.workflow_state['issues_detail']}"

        if st.session_state.workflow_state.get("feedback_history"):
            context += f"Feedback: {st.session_state.workflow_state['feedback_history']}\n"
            context += f"Previous iterations: {st.session_state.workflow_state['feedback_count']}\n"
                 # Initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        openai_client = OpenAI(api_key=api_key)
        
        epic_agent = EpicGeneratorAgent(openai_client)
        story_agent = UserStoryGeneratorAgent(openai_client)
        
        # Generate content
        gen_type = st.session_state.workflow_state["generation_type"]
        hlr = st.session_state.workflow_state["hlr"]
        responses = st.session_state.workflow_state["responses"]
        
        if gen_type in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
            epics = await epic_agent.generate_epics(hlr, context, responses)
            st.session_state.workflow_state["epics"] = epics
        
        if gen_type in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
            stories = await story_agent.generate_user_stories(
                hlr, context, responses, st.session_state.workflow_state.get("epics", [])
            )
            st.session_state.workflow_state["user_stories"] = stories
    
    with st.spinner("Generating content..."):
        asyncio.run(generate_content())
    
    # Display results
    epics = st.session_state.workflow_state.get("epics", [])
    stories = st.session_state.workflow_state.get("user_stories", [])
    
    if epics:
        bot_message(f"Generated {len(epics)} epics:")
        for i, epic in enumerate(epics, 1):
            msg = f"{i}. <b>{epic.get('title', 'Untitled Epic')}</b><br>"
            msg += f"Priority: {epic.get('priority', 'Not set')}<br>"
            msg += f"Story Points: {epic.get('estimated_story_points', 'Not estimated')}<br>"
            msg += f"Business Value: {epic.get('business_value', 'Not specified')[:100]}...<br>"
            if epic.get('acceptance_criteria'):
                msg += f"Acceptance Criteria: {len(epic['acceptance_criteria'])} items<br>"
            if epic.get('dependencies'):
                msg += f"Dependencies: {', '.join(epic['dependencies'])}"
            bot_message(msg)    
    stroy_msg_str = StringIO()
    if stories:
        bot_message(f"Generated {len(stories)} user stories:\n")
        for i, story in enumerate(stories, 1):
            stroy_msg_str.write(f"{i}. <b>{story.get('title', 'Untitled Story')}</b><br>")
            stroy_msg_str.write(f"Description: {story.get('description', 'No description')}...<br>")
            stroy_msg_str.write(f"Priority: {story.get('priority', 'Not set')}<br>")
            stroy_msg_str.write(f"Story Points: {story.get('story_points', 'Not estimated')}<br>")
            stroy_msg_str.write(f"Persona: {story.get('user_persona', 'Not specified')}<br>")
            
            if story.get('epic_reference'):
                stroy_msg_str.write(f"Related Epic: {story['epic_reference']}<br>")
                
            if story.get('acceptance_criteria'):
                stroy_msg_str.write(f"Acceptance Criteria: {len(story['acceptance_criteria'])} items<br>")
                
            if story.get('labels'):
                stroy_msg_str.write(f"Labels: {', '.join(story['labels'])}<br>")
                
            stroy_msg_str.write("<br>")
        
        bot_message(stroy_msg_str.getvalue())
        
    bot_message("Are you satisfied with the generated content?")
    st.session_state.step = "feedback"
    st.rerun()

elif st.session_state.step == "feedback":
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Yes, I'm satisfied", use_container_width=True):
            user_message("Yes, I'm satisfied")
            bot_message("Great! Preparing final output...")
            st.session_state.step = "export"
            st.rerun()
    with col2:
        if st.button("No, I want changes", use_container_width=True):
            user_message("No, I want changes")
            bot_message("Please describe what changes you'd like:")
            st.session_state.step = "feedback_input"
            st.rerun()

elif st.session_state.step == "feedback_input":
    if user_input and st.session_state.workflow_state["feedback_count"] < 3:
        user_message(user_input)
        st.session_state.workflow_state["feedback_history"].append(user_input)
        st.session_state.workflow_state["feedback_count"] += 1
        
        bot_message("Applying your feedback and regenerating...")
        
        # Regenerate with feedback
        # async def regenerate_with_feedback():
        #     context = f"Persona: {st.session_state.workflow_state.get('persona', 'Business Analyst')}\n"
        #     context += f"Feedback: {user_input}\n"
        #     context += f"Previous iterations: {st.session_state.workflow_state['feedback_count']}\n"
            
        #     api_key = os.getenv('OPENAI_API_KEY')
        #     if api_key.startswith('"') and api_key.endswith('"'):
        #         api_key = api_key[1:-1]
        #     openai_client = OpenAI(api_key=api_key)
            
        #     epic_agent = EpicGeneratorAgent(openai_client)
        #     story_agent = UserStoryGeneratorAgent(openai_client)
            
        #     gen_type = st.session_state.workflow_state["generation_type"]
        #     hlr = st.session_state.workflow_state["hlr"]
        #     responses = st.session_state.workflow_state["responses"]
            
        #     if gen_type in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
        #         epics = await epic_agent.generate_epics(hlr, context, responses)
        #         st.session_state.workflow_state["epics"] = epics
            
        #     if gen_type in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
        #         stories = await story_agent.generate_user_stories(
        #             hlr, context, responses, st.session_state.workflow_state.get("epics", [])
        #         )
        #         st.session_state.workflow_state["user_stories"] = stories
        
        # with st.spinner("Regenerating content..."):
        #     asyncio.run(regenerate_with_feedback())
        
        bot_message("Content updated based on your feedback!")
        st.session_state.step = "generate"
        st.rerun()

elif st.session_state.step == "export":
    # Create final output
    clean_output = create_clean_output(st.session_state.workflow_state)
    
    # Display summary
    bot_message("<b>Final Summary:</b>")
    if st.session_state.workflow_state.get("epics"):
        bot_message(f"✅ {len(st.session_state.workflow_state['epics'])} Epics generated")
    if st.session_state.workflow_state.get("user_stories"):
        bot_message(f"✅ {len(st.session_state.workflow_state['user_stories'])} User Stories generated")
    
    # Show detailed output
    with st.expander("📋 Detailed Output", expanded=True):
        if st.session_state.workflow_state.get("epics"):
            st.subheader("Epics")
            for i, epic in enumerate(st.session_state.workflow_state["epics"], 1):
                st.write(f"<b>{i}. {epic.get('title', 'Untitled')}</b>",unsafe_allow_html=True)
                st.write(f"Priority: {epic.get('priority', 'Not set')}")
                st.write(f"Story Points: {epic.get('estimated_story_points', 'Not estimated')}")
                st.write(f"Description: {epic.get('description', 'No description')}")
                if epic.get('acceptance_criteria'):
                    st.write("Acceptance Criteria:")
                    for criteria in epic['acceptance_criteria']:
                        st.write(f"- {criteria}")
                st.write("---")
        
        if st.session_state.workflow_state.get("user_stories"):
            st.subheader("User Stories")
            for i, story in enumerate(st.session_state.workflow_state["user_stories"], 1):
                st.write(f"<b>{i}. {story.get('title', 'Untitled')}</b>",unsafe_allow_html=True)
                st.write(f"Description: {story.get('description', 'No description')}")
                st.write(f"Priority: {story.get('priority', 'Not set')} | Points: {story.get('story_points', 0)}")
                if story.get('acceptance_criteria'):
                    st.write("Acceptance Criteria:")
                    for criteria in story['acceptance_criteria']:
                        st.write(f"- {criteria}")
                st.write("---")
    
    # Download option
    json_output = json.dumps(clean_output, indent=2)
    st.download_button(
        label="📥 Download Results (JSON)",
        data=json_output,
        file_name=f"jira_results_{st.session_state.workflow_state.get('session_id', 'export')}.json",
        mime="application/json"
    )
    
    if st.button("🔄 Start New Workflow"):
        # Reset session state
        for key in list(st.session_state.keys()):
            if key not in ['step', 'messages', 'workflow_state', 'agents']:
                del st.session_state[key]
        st.session_state.step = "start"
        st.session_state.messages = [
            {"role": "bot", "content": "Welcome back! Ready to start a new workflow?"}
        ]
        st.rerun()
    # if st.button("push to jira"):
    #     data=json.loads(json_output)
    #     print(data)
    #  # Extract only title and description
    #     # stories = data["generated_content"]["user_stories"]
    #     # filtered_stories = [
    #     #     {k: story[k] for k in ("title", "description") if k in story}
    #     #     for story in stories
    #     # ]

    #     # print(json.dumps(filtered_stories, indent=2))
    #     # api_key = os.getenv('OPENAI_API_KEY')
    #     # if api_key.startswith('"') and api_key.endswith('"'):
    #     #     api_key = api_key[1:-1]
    #     # openai_client = OpenAI(api_key=api_key)
    #     # task_generator = TaskGenerator(openai_client,filtered_stories)
    #     # task_generated =task_generator.task_generation()
    #     # python_exec_code=(task_generated)

    #     # # loading and exec of the code 
    #     # # Define the execution context (allowed variables)
    #     # context = {"jira_instance": jira}

    #     # Execute multiple lines of code safely inside the context
    #     exec(python_exec_code, {}, context)
    #     final_response=context.get("final_response")
    #     print(final_response)
        
