import streamlit as st
import asyncio
from PIL import Image
from agents import JIRAAgentSystem, GenerationType
import time

st.set_page_config(page_title="JIRA Chatbot", page_icon="🤖", layout="centered")

# --- Custom CSS for chat container and border ---
st.markdown("""
    <style>
    .chat-header {
        background: #5d23b6;
        color: #fff;
        border-radius: 24px 24px 0 0;
        padding: 1rem 2rem 1rem 2rem;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    
    .chat-header .title {
        font-size: 1.5rem;
        font-weight: 500;
        letter-spacing: 1px;
    }
        
    .msg {
        margin: 0.5rem 0;
        padding: 0.5rem 1rem;
        background: white;
        border-radius: 10px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
    .chat-container {
     
        margin: auto;
        display: flex;
        flex-direction: column;
          /* space for input */
    }

    .msg-bubble {
        padding: 12px 18px;
        border-radius: 50px;
        max-width: 100%;
        word-wrap: break-word;
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
    
    .scroll-box {
        max-height: 400px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ccc;
        border-radius: 10px;
    }
       
        </style>
""", unsafe_allow_html=True)

st.markdown('<div class="chat-main-panel">', unsafe_allow_html=True)
st.markdown(
    """
    <div class="chat-header">
        <h2 class="title">ORION Chatbot</h2>
    </div>
    """,
    unsafe_allow_html=True
)
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    

# --- Chatbot Workflow ---
import streamlit as st

# --- Session State Initialization ---
if "system" not in st.session_state:
    st.session_state.system = JIRAAgentSystem()
if "step" not in st.session_state:
    st.session_state.step = "hlr"
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "bot", "content": "Hello! I'm Orion, your AI-powered JIRA assistant."},
        {"role": "bot", "content": "I can help you create and update tasks, generate epics and user stories, "
                                   "answer questions about your projects, and guide you through project management workflows."}
    ]
if "state" not in st.session_state:
    st.session_state.state = None
if "qa_responses" not in st.session_state:
    st.session_state.qa_responses = {}
if "skipped_questions" not in st.session_state:
    st.session_state.skipped_questions = []
if "feedback_count" not in st.session_state:
    st.session_state.feedback_count = 0

# --- Helper Functions ---
def bot_message(text):
    st.session_state.messages.append({"role": "bot", "content": text})

def user_message(text):
    st.session_state.messages.append({"role": "user", "content": text})

# --- Display Chat History ---
with st.container():
    st.markdown("""
    <style>
    .chat-box {
        max-height: 400px;
        overflow-y: auto;
        padding: 10px;
        border: 1px solid #ccc;
        border-radius: 10px;
        background-color: #f9f9f9;
    }
    .msg-bubble {
        padding: 10px;
        margin: 5px;
        border-radius: 10px;
        max-width: 80%;
    }
    .msg-bubble.user {
        background-color: #e0f7fa;
        text-align: right;
        margin-left: auto;
    }
    .msg-bubble.bot {
        background-color: #00796b;
        color: white;
        text-align: left;
        margin-right: auto;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Display chat history with bubbles (inside chat container) ---

chat_area = st.container()

chat_history = ""
for msg in st.session_state.messages:
    role_class = "user" if msg["role"] == "user" else "bot"
    chat_history = f'<div class="msg-bubble {role_class}">{msg["content"]}</div>'

    # st.markdown("""
    # <style>
    # .chat-box {
    #     max-height: 400px;
    #     overflow-y: auto;
    #     padding: 10px;
    #     border: 1px solid #ccc;
    #     border-radius: 10px;
    #     background-color: #f9f9f9;
    # }
    # .msg-bubble {
    #     padding: 10px;
    #     margin: 5px;
    #     border-radius: 10px;
    #     max-width: 80%;
    # }
    # .msg-bubble.user {
    #     background-color: #e0f7fa;
    #     text-align: right;
    #     margin-left: auto;
    # }
    # .msg-bubble.bot {
    #     background-color: #00796b;
    #     color: white;
    #     text-align: left;
    #     margin-right: auto;
    # }
    # </style>
    # """, unsafe_allow_html=True)

    st.markdown(
        f"""
        
            {chat_history}
            
       
        """,
        unsafe_allow_html=True
    )

# --- Chat input and workflow --- (INSIDE chat-container)
st.markdown('<div class="chat-footer">', unsafe_allow_html=True)

# Use chat_input instead of form
user_input = st.chat_input("Type your response...")


# Step 2: Action selection
if st.session_state.step == "hlr":
    if user_input:
        st.session_state.hlr = user_input
        user_message(user_input)
        keyword = ["create", "task", "help","issue", "i want to create", "apply", "generate","make"]
        if any([i in user_input.lower() for i in keyword]):# or "task" in user_input.lower() or "issue" in user_input.lower() or "i want to create" in user_input.lower():
            bot_message("Please input your requirement.")
            st.session_state.step = "requirement"
            st.rerun()
        else:
            bot_message("I can help with task creation. Please type 'create a task' to proceed.")
            st.rerun()

# Step 3: Requirement input
elif st.session_state.step == "requirement":
    if user_input:
        user_message(user_input)
        st.session_state.hlr = user_input
        bot_message("I can generate following issue types, Select one which you like to proceed with?")
        st.session_state.step = "generation_type"
    st.rerun()


elif st.session_state.step == "generation_type":
    st.session_state.gen_type = None
    # with st.form(key="gen_type_form", clear_on_submit=True):
    gen_type = st.radio(
            "Select issue type:",
            ["Epics Only", "User Stories Only", "Both"],
            index=None,# Default to "Both",
            label_visibility="collapsed"
        )
    st.session_state.gen_type = gen_type
        # submitted = st.form_submit_button("Send", use_container_width=True)

    if st.session_state.gen_type is not None :
        user_message(st.session_state.gen_type)
        options = {
            "Epics Only": GenerationType.EPICS_ONLY,
            "User Stories Only": GenerationType.STORIES_ONLY,
            "Both": GenerationType.BOTH
        }
        st.session_state.generation_type = options.get(gen_type.strip(), GenerationType.BOTH)
        st.session_state.state = st.session_state.system.create_session(
            st.session_state.hlr, st.session_state.generation_type
        )
        bot_message("Analyzing requirement and generating questions...")
        st.session_state.step = "analyze"
        st.rerun()


elif st.session_state.step == "analyze":
    async def analyze_and_generate():
        state = await st.session_state.system.requirement_agent.analyze_requirement(st.session_state.state)
        state = await st.session_state.system.requirement_agent.generate_questions(state)
        return state
    state = asyncio.run(analyze_and_generate())
    st.session_state.state = state
    st.session_state.question_idx = 0
    bot_message("Let's start with the questions to clarify your requirement.")
    st.session_state.step = "qa"
    
    st.rerun()

elif st.session_state.step == "qa":
    questions = st.session_state.state.questions
    idx = st.session_state.question_idx
    if idx < len(questions):
        q = questions[idx]
        if not st.session_state.get(f"asked_{idx}", False):
            bot_message(
                f"<b>Q{idx+1}:</b> {q.question}<br><span style='color:#7c3aed'>Context: {q.context}</span><br>"
                f"<span style='#B22222'>Priority: {q.priority}/6</span> | Required: <b>{'Yes' if q.required else 'No'}</b>"
                f"\n <span style='color:#888'>(Type 'skip' to skip the question)</span>",  
                
            )
            st.session_state[f"asked_{idx}"] = True
            st.rerun()
        
        # Handle user input immediately without requiring second enter
        if user_input:
            if user_input.lower() == "skip":
                user_message("skip")
                st.session_state.skipped_questions.append(q.id)
                st.session_state.question_idx += 1
                # Display next question immediately
                if st.session_state.question_idx < len(questions):
                    next_q = questions[st.session_state.question_idx]
                    bot_message(
                        f"<b>Q{st.session_state.question_idx+1}:</b> {next_q.question}<br><span style='color:#7c3aed'>Context: {next_q.context}</span><br>"
                        f"<span style='#B22222'>Priority: {next_q.priority}/6</span> | Required: <b>{'Yes' if next_q.required else 'No'}</b>"
                        f"\n <span style='color:#888'>(Type 'skip' to skip the question)</span>", 
                    )
                    st.session_state[f"asked_{st.session_state.question_idx}"] = True
                st.rerun()
            else:
                user_message(user_input)
                st.session_state.qa_responses[q.id] = user_input
                st.session_state.question_idx += 1
                # Display next question immediately
                if st.session_state.question_idx < len(questions):
                    next_q = questions[st.session_state.question_idx]
                    bot_message(
                        f"<b>Q{st.session_state.question_idx+1}:</b> {next_q.question}<br><span style='color:#888'>Context: {next_q.context}</span><br>"
                        f"<span style='color:#B22222'>Priority: {next_q.priority}/6</span> | Required: <b>{'Yes' if next_q.required else 'No'}</b><br>"
                        f"\n <span style='color:#888'>(Type 'skip' to skip the question)</span>",               )
                    st.session_state[f"asked_{st.session_state.question_idx}"] = True
                st.rerun()
    else:
        bot_message("Processing your answers and generating content...")
        st.session_state.step = "generate" 
        st.rerun()

elif st.session_state.step == "generate":
    async def process_and_generate():
        state = await st.session_state.system.process_qa_session(
            st.session_state.state,
            st.session_state.qa_responses,
            st.session_state.skipped_questions
        )
        state = await st.session_state.system.generate_content(state)
        return state
    state = asyncio.run(process_and_generate())
    st.session_state.state = state
    msg = ""
    if state.epics:
        msg += f"<b>Generated {len(state.epics)} epics:</b><br>" + "<br>".join([f"- {e.title}" for e in state.epics])
    if state.user_stories:
        msg += f"<br><b>Generated {len(state.user_stories)} user stories:</b><br>" + "<br>".join([f"- {s.title}" for s in state.user_stories])
    bot_message(msg)
    bot_message("Are you satisfied with the generated content? (yes/no)")
    st.session_state.step = "feedback"
    st.rerun()

elif user_input and st.session_state.step == "feedback":
    user_message(user_input)
    if user_input.lower() in ["yes", "y"]:
        bot_message("Thank you! Exporting and saving your output...")
        st.session_state.step = "export"
        st.rerun()
    else:
        async def apply_feedback():
            state, feedback_applied = await st.session_state.system.process_feedback(
                st.session_state.state, user_input
            )
            return state, feedback_applied
        state, applied = asyncio.run(apply_feedback())
        st.session_state.state = state
        if applied:
            bot_message("Feedback applied successfully. Updated content generated.")
        else:
            bot_message("Feedback was not valid or could not be applied.")
        st.session_state.feedback_count += 1
        if st.session_state.feedback_count < 3:
            bot_message("Are you satisfied with the updated content? (yes/no)")
        else:
            bot_message("Maximum feedback attempts reached. Exporting output.")
            st.session_state.step = "export"
        st.rerun()
elif st.session_state.step == "export":
    final_output = st.session_state.system.export_final_output(st.session_state.state)
    filename = st.session_state.system.save_output_to_file(final_output)
    bot_message(f"Process completed successfully! Output saved to: {filename}")
    st.session_state.step = "done"
    st.rerun()

# elif st.session_state.step == "done":
#     with st.form(key="done_form", clear_on_submit=True):
#         st.text_input("", key="done_input", placeholder="Chatbot session complete. Refresh to start over.", label_visibility="collapsed")
#         st.form_submit_button("Send", use_container_width=True)

st.markdown('</div>', unsafe_allow_html=True)  # End chat-footer
st.markdown('</div>', unsafe_allow_html=True)  # End chat-container
st.markdown('</div>', unsafe_allow_html=True)  # End chat-main-panel
