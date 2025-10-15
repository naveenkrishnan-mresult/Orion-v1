from io import StringIO
import asyncio
import json
import uuid
from main import (
    JiraAgenticIntegration, RequirementAnalysisAgent, EpicGeneratorAgent, 
    UserStoryGeneratorAgent, GenerationType, AnalysisPhase, WorkflowState,
    ProjectAccessManager, JIRAProject, JIRAIssue, Question, ValidationResult
)
from history import HistoryManager, display_history_menu, get_workflow_start_choice
from openai import OpenAI
import os
from dotenv import load_dotenv
from jira import JIRA

load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER")
JIRA_EMAIL = os.getenv("JIRA_EMAIL")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN")

# Create Jira connection
if JIRA_SERVER and JIRA_EMAIL and JIRA_API_TOKEN:
    jira = JIRA(
        server=JIRA_SERVER,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
    )
else:
    jira = None


# Add debug logs to trace initialization
import logging
logger = logging.getLogger(__name__)



# Prevent duplicate execution
if "app_initialized" not in st.session_state:
    logger.info("Initializing app session state")
    st.session_state.app_initialized = True



if "workflow_state" not in st.session_state:
    logger.info("Initializing workflow state")
    st.session_state.workflow_state = {
        "session_id": "",
        "workflow_type": "",
        "hlr": "",
        "additional_inputs": "",
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
        "current_step": "",
        "has_jira_access": True,
        "is_resumed": False
    }
if "agents" not in st.session_state:
    st.session_state.agents = None
if "question_idx" not in st.session_state:
    st.session_state.question_idx = 0


@st.cache_resource
def initialize_agents():
    """Initialize agents once and cache them"""
    from main import JiraAgenticIntegration, RequirementAnalysisAgent
    return {
        "jira": JiraAgenticIntegration(),
        "req": RequirementAnalysisAgent()
    }

# Use cached agents
if "agents" not in st.session_state or st.session_state.agents is None:
    st.session_state.agents = initialize_agents()


    






# Workflow steps following main.py node structure
if st.session_state.step == "hlr":
    if user_input:
        st.session_state.hlr = user_input
        user_message(user_input)
        keyword = ["create", "task", "help","issue", "i want to create", "apply", "generate","make","issue","epic","story","stories","user story"]
        if any([i in user_input.lower() for i in keyword]):
            show_typing_with_response("Let me fetch your JIRA projects...", "jira_projects")
            st.rerun()
        else:
            show_typing_with_response("I can help with task creation. Please type 'create a task' to proceed.")
        st.rerun()




elif st.session_state.step == "workflow_choice":
    st.markdown("<b>Choose workflow:</b>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Work with existing JIRA issues", use_container_width=True):
            st.session_state.workflow_state["workflow_type"] = "existing"
            user_message("Work with existing JIRA issues")
            st.session_state.step = "jira_issues"
            st.rerun()
    with col2:
        if st.button("Create new requirement", use_container_width=True):
            st.session_state.workflow_state["workflow_type"] = "new"
            user_message("Create new requirement")
            bot_message("Please enter your High-Level Requirement:")
            
            st.session_state.step = "hlr_input"
            st.rerun()

elif st.session_state.step == "jira_issues":
    # Display issues
    project_key = st.session_state.workflow_state["selected_project"]
    
    if "issues_loaded" not in st.session_state:
        with st.spinner("Retrieving project tasks..."):
            issues = st.session_state.agents["jira"].get_issues_agentic(project_key)
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
            st.session_state.issues_loaded = True
    
    selected_issue = st.selectbox(
        f"Found {len(st.session_state.workflow_state['issues_list'])} issues in project {project_key}",
        options=st.session_state.workflow_state["issues_list"],
        key="issue_dropdown",
        format_func=lambda x: x.replace('<br>', ' | ').replace('<b>', '').replace('</b>', ''),
        index=None
    )
    
    if selected_issue:
        st.session_state.workflow_state["hlr"] = selected_issue
        user_message(f"Selected issue: {selected_issue.replace('<br>', ' | ').replace('<b>', '').replace('</b>', '')}")
        show_typing_with_response("Analyzing selected issue...", "analyze")
        del st.session_state.issues_loaded
        st.rerun()

elif st.session_state.step == "hlr_input":
    if user_input:
        st.session_state.workflow_state["hlr"] = user_input
        user_message(user_input)
        bot_message("Do you have any additional inputs or context to provide? (Press Enter to skip)")
        st.session_state.step = "additional_inputs"
        st.rerun()

elif st.session_state.step == "additional_inputs":
    if user_input:
        st.session_state.workflow_state["additional_inputs"] = user_input
        user_message(user_input)
        show_typing_with_response("Analyzing your requirement with additional context...", "analyze")
    else:
        # Skip additional inputs
        bot_message("Skipping additional inputs.")
        show_typing_with_response("Analyzing your requirement...", "analyze")
    st.rerun()

elif st.session_state.step == "analyze":
    async def analyze_requirement():
        jira_guidance = ""
        if st.session_state.workflow_state["workflow_type"] == "existing":
            selected_project = st.session_state.workflow_state.get("selected_project")
            if selected_project and "cached_issues" not in st.session_state:
                # Use cached issues from previous step or fetch if not available
                if st.session_state.workflow_state.get("selected_issues"):
                    # Reconstruct issues from cached data
                    from main import JIRAIssue
                    issues = []
                    # Use the issues_detail that was already fetched
                    jira_guidance = f"JIRA Project Context: {selected_project}\nIssues analyzed: {len(st.session_state.workflow_state.get('selected_issues', []))}\nIssues detail: {st.session_state.workflow_state.get('issues_detail', '')}"
                else:
                    # Fallback: fetch issues if not cached
                    issues = st.session_state.agents["jira"].get_issues_agentic(selected_project)
                    jira_guidance = st.session_state.agents["jira"].generate_context_guidance(
                        issues, st.session_state.workflow_state["hlr"]
                    )
                st.session_state.cached_issues = True
            elif st.session_state.workflow_state.get("issues_detail"):
                # Use already cached guidance
                jira_guidance = f"JIRA Project Context: {selected_project}\nIssues analyzed: {len(st.session_state.workflow_state.get('selected_issues', []))}\nIssues detail: {st.session_state.workflow_state.get('issues_detail', '')}"
        
        # Include additional inputs in analysis
        additional_inputs = st.session_state.workflow_state.get("additional_inputs", "")
        
        analysis = await st.session_state.agents["req"].analyze_requirement(
            st.session_state.workflow_state["hlr"], additional_inputs, jira_guidance
        )
        st.session_state.workflow_state["requirement_analysis"] = analysis
        st.session_state.workflow_state["slicing_type"] = analysis.get("slicing_type", "functional")
        
        recommended_persona = analysis.get("recommended_persona", "Business Analyst")
        st.session_state.workflow_state["persona"] = recommended_persona
        
        questions = await st.session_state.agents["req"].generate_questions(
            st.session_state.workflow_state["hlr"],
            additional_inputs,
            st.session_state.workflow_state["slicing_type"],
            recommended_persona,
            jira_guidance
        )
        st.session_state.workflow_state["questions"] = questions
        
        return analysis, questions
    
    # Skip analysis if already done (for resumed sessions)
    if not st.session_state.workflow_state.get("requirement_analysis") or not st.session_state.workflow_state.get("questions"):
        with st.spinner("Analyzing requirement ..."):
            analysis, questions = asyncio.run(analyze_requirement())
    else:
        analysis = st.session_state.workflow_state["requirement_analysis"]
        questions = st.session_state.workflow_state["questions"]
    
    msg_1 = StringIO()
    msg_1.write("<b>Requirement Analysis Summary:</b><br>")
    msg_1.write(f"Recommended persona: <b>{analysis.get('recommended_persona')}</b> <br> Domain: {analysis.get('domain')}, Complexity: {analysis.get('complexity')}")
    bot_message(msg_1.getvalue())
    
    st.session_state.step = "persona_confirm"
    st.rerun()

elif st.session_state.step == "persona_confirm":
    recommended = st.session_state.workflow_state["requirement_analysis"].get("recommended_persona")
    st.markdown(f"<b>Suggested persona:</b> {recommended}",unsafe_allow_html=True)
    
    if st.button("Use suggested persona", use_container_width=True):
        user_message(f"Using suggested persona: {recommended}")
        bot_message("Great! Let's proceed with the questions.You can answer or skip any question")
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
                f"<i>Priority:</i> {q.priority}/3 | "
                f"<i>Required:</i> {'Yes' if q.required else 'No'}"
            )
            st.session_state[f"asked_{idx}"] = True
            st.rerun()

        # Add skip button
        if st.button("Skip Question", key=f"skip_{idx}"):
            user_message("Skipped question")
            st.session_state.workflow_state["responses"][q.id] = "[SKIPPED]"
            st.session_state.question_idx += 1
            st.rerun()
        
        if user_input:
            user_message(user_input)
            st.session_state.workflow_state["responses"][q.id] = user_input
            st.session_state.question_idx += 1
            st.rerun()

    else:
        bot_message("All questions completed! Now select what to generate:")
        st.session_state.step = "generation_type"
        st.rerun()
elif st.session_state.step == "generation_type":
    from main import GenerationType
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
    if "generation_done" not in st.session_state:
        async def generate_content():
            from main import EpicGeneratorAgent, UserStoryGeneratorAgent, GenerationType
            from openai import OpenAI
            
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
        
        st.session_state.generation_done = True
    
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
        
        # Clear generation flag to allow regeneration
        if "generation_done" in st.session_state:
            del st.session_state.generation_done
        
        bot_message("Applying your feedback and regenerating...")
        st.session_state.step = "generate"
        st.rerun()

elif st.session_state.step == "export":
    # Create final output
    clean_output = {
        "session_id": st.session_state.workflow_state.get("session_id", ""),
        "hlr": st.session_state.workflow_state.get("hlr", ""),
        "generated_content": {
            "epics": st.session_state.workflow_state.get("epics", []),
            "user_stories": st.session_state.workflow_state.get("user_stories", [])
        }
    }
    
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
        
        # Reset workflow state
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
        st.session_state.question_idx = 0
        st.session_state.step = "hlr"
        st.session_state.messages = [
            {"role": "bot", "content": "Welcome back! How can I help you?"}
        ]
        st.rerun()