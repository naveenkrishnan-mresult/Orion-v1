import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class HistoryManager:
    """Agentic history management for workflow sessions"""
    
    def __init__(self, db_path: str = "workflow_history.db"):
        self.db_path = db_path
        self.openai_client = None
        self._init_openai()
        self._init_database()
        logger.info("History Manager initialized")
    
    def _init_openai(self):
        """Initialize OpenAI client for agentic decisions"""
        api_key = os.getenv('OPENAI_API_KEY', '')
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
    
    def _init_database(self):
        """Initialize SQLite database with sessions table"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    workflow_type TEXT,
                    hlr TEXT,
                    additional_inputs TEXT,
                    selected_project TEXT,
                    persona TEXT,
                    slicing_type TEXT,
                    generation_type TEXT,
                    current_phase TEXT,
                    current_step TEXT,
                    state_snapshot TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    is_completed INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"Database initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise
    
    def save_checkpoint(self, state: Dict[str, Any]):
        """Save workflow state checkpoint"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Serialize state
            state_json = json.dumps(state, default=str)
            
            cursor.execute("""
                INSERT OR REPLACE INTO sessions 
                (session_id, workflow_type, hlr, additional_inputs, selected_project,
                 persona, slicing_type, generation_type, current_phase, current_step,
                 state_snapshot, created_at, updated_at, is_completed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 
                        COALESCE((SELECT created_at FROM sessions WHERE session_id = ?), ?),
                        ?, ?)
            """, (
                state.get('session_id', ''),
                state.get('workflow_type', ''),
                state.get('hlr', ''),
                state.get('additional_inputs', ''),
                state.get('selected_project', ''),
                state.get('persona', ''),
                state.get('slicing_type', ''),
                state.get('generation_type', {}).value if hasattr(state.get('generation_type', {}), 'value') else str(state.get('generation_type', '')),
                state.get('phase', {}).value if hasattr(state.get('phase', {}), 'value') else str(state.get('phase', '')),
                state.get('current_step', ''),
                state_json,
                state.get('session_id', ''),
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                1 if state.get('current_step') == 'final_validation' else 0
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"Checkpoint saved for session {state.get('session_id')}")
            
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
    
    def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all sessions from history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT session_id, workflow_type, hlr, selected_project, persona,
                       current_phase, current_step, created_at, updated_at, is_completed
                FROM sessions
                ORDER BY updated_at DESC
            """)
            
            sessions = []
            for row in cursor.fetchall():
                sessions.append({
                    'session_id': row[0],
                    'workflow_type': row[1],
                    'hlr': row[2],
                    'selected_project': row[3],
                    'persona': row[4],
                    'current_phase': row[5],
                    'current_step': row[6],
                    'created_at': row[7],
                    'updated_at': row[8],
                    'is_completed': bool(row[9])
                })
            
            conn.close()
            logger.info(f"Retrieved {len(sessions)} sessions from history")
            return sessions
            
        except Exception as e:
            logger.error(f"Error retrieving sessions: {e}")
            return []
    
    def get_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full state for a specific session"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT state_snapshot FROM sessions WHERE session_id = ?
            """, (session_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                state = json.loads(row[0])
                logger.info(f"Retrieved state for session {session_id}")
                return state
            
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving session state: {e}")
            return None
    
    def get_agent_summary(self, session: Dict[str, Any]) -> str:
        """Use agent to generate human-readable session summary"""
        if not self.openai_client:
            return self._fallback_summary(session)
        
        try:
            prompt = f"""
Summarize this workflow session in 2-3 concise lines for user selection:

Session ID: {session['session_id']}
Type: {session['workflow_type']}
HLR: {session['hlr'][:100]}...
Project: {session.get('selected_project', 'N/A')}
Phase: {session['current_phase']}
Status: {'Completed' if session['is_completed'] else 'In Progress'}
Last Updated: {session['updated_at']}

Provide a brief, actionable summary that helps user decide if they want to resume this session.
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a concise summarizer. Provide brief, actionable summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Agent summary error: {e}")
            return self._fallback_summary(session)
    
    def _fallback_summary(self, session: Dict[str, Any]) -> str:
        """Fallback summary when agent is unavailable"""
        status = "✓ Completed" if session['is_completed'] else "⏸ In Progress"
        hlr_preview = session['hlr'][:60] + "..." if len(session['hlr']) > 60 else session['hlr']
        
        return (f"{status} | {session['workflow_type'].upper()} | "
                f"'{hlr_preview}' | Phase: {session['current_phase']}")
    
    def get_resume_suggestion(self, state: Dict[str, Any]) -> str:
        """Agent suggests how to resume the workflow"""
        if not self.openai_client:
            return self._fallback_resume_suggestion(state)
        
        try:
            current_step = state.get('current_step', '')
            phase = state.get('phase', '')
            has_epics = bool(state.get('epics', []))
            has_stories = bool(state.get('user_stories', []))
            
            prompt = f"""
Analyze this workflow state and suggest how to resume:

Current Step: {current_step}
Phase: {phase}
Has Epics: {has_epics}
Has User Stories: {has_stories}
Questions Answered: {len(state.get('responses', {}))}
Feedback Count: {state.get('feedback_count', 0)}

Provide a brief recommendation on:
1. What was completed
2. What's the next logical step
3. Any options user should consider

Keep it concise and actionable (3-4 lines max).
"""
            
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a workflow assistant. Provide clear resume guidance."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"Resume suggestion error: {e}")
            return self._fallback_resume_suggestion(state)
    
    def _fallback_resume_suggestion(self, state: Dict[str, Any]) -> str:
        """Fallback resume suggestion"""
        step = state.get('current_step', 'unknown')
        
        suggestions = {
            'analyze_requirements': "Resume from requirement analysis. You'll continue with Q&A session.",
            'setup_generation': "Resume from generation setup. Choose what to generate next.",
            'generation': "Resume from content generation. Review and provide feedback.",
            'feedback': "Resume from feedback phase. Refine generated content.",
            'final_validation': "Session is complete. You can review results or start fresh."
        }
        
        return suggestions.get(step, f"Resume from {step} phase. Continue where you left off.")
    
    def delete_session(self, session_id: str):
        """Delete a session from history"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            
            conn.commit()
            conn.close()
            logger.info(f"Deleted session {session_id}")
            
        except Exception as e:
            logger.error(f"Error deleting session: {e}")


def display_history_menu(history_manager: HistoryManager) -> Optional[Dict[str, Any]]:
    """Display history and let user select a session to resume"""
    sessions = history_manager.get_all_sessions()
    
    if not sessions:
        print("\n No previous sessions found.")
        print("Starting fresh workflow...\n")
        return None
    
    print("\n" + "="*80)
    print(" WORKFLOW HISTORY")
    print("="*80)
    
    for i, session in enumerate(sessions, 1):
        summary = history_manager.get_agent_summary(session)
        print(f"\n{i}. {summary}")
        print(f"   Session ID: {session['session_id']}")
        print(f"   Updated: {session['updated_at']}")
    
    print("\n" + "-"*80)
    print("Options:")
    print("  • Enter session number to resume")
    print("  • Type 'delete <number>' to remove a session")
    print("  • Press Enter to start new workflow")
    print("-"*80)
    
    choice = input("\nYour choice: ").strip()
    
    # Handle delete
    if choice.lower().startswith('delete '):
        try:
            del_num = int(choice.split()[1])
            if 1 <= del_num <= len(sessions):
                session_to_delete = sessions[del_num - 1]
                confirm = input(f"Delete session {session_to_delete['session_id']}? (y/n): ").strip().lower()
                if confirm == 'y':
                    history_manager.delete_session(session_to_delete['session_id'])
                    print("✓ Session deleted")
                    return display_history_menu(history_manager)  # Show menu again
        except (ValueError, IndexError):
            print("Invalid delete command")
            return display_history_menu(history_manager)
    
    # Handle resume
    if choice.isdigit():
        session_num = int(choice)
        if 1 <= session_num <= len(sessions):
            selected_session = sessions[session_num - 1]
            state = history_manager.get_session_state(selected_session['session_id'])
            
            if state:
                print(f"\n✓ Loading session: {selected_session['session_id']}")
                print("\n" + "="*80)
                print("SESSION DETAILS")
                print("="*80)
                print(f"HLR: {state.get('hlr', 'N/A')}")
                print(f"Workflow Type: {state.get('workflow_type', 'N/A')}")
                print(f"Phase: {state.get('phase', 'N/A')}")
                
                # Get resume suggestion
                print("\n" + "-"*80)
                print("RESUME GUIDANCE:")
                print("-"*80)
                suggestion = history_manager.get_resume_suggestion(state)
                print(suggestion)
                print("-"*80)
                
                confirm = input("\nResume this session? (y/n): ").strip().lower()
                if confirm == 'y':
                    return state
                else:
                    return display_history_menu(history_manager)
    
    # Start new workflow
    return None


def get_workflow_start_choice() -> str:
    """Main menu: Projects or History"""
    print("\n" + "="*80)
    print(" JIRA WORKFLOW ASSISTANT")
    print("="*80)
    print("\n1.  Start New Project Workflow")
    print("2.  View History & Resume Session")
    print("\n" + "-"*80)
    
    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice in ['1', '2']:
            return 'new' if choice == '1' else 'history'
        print("Invalid choice. Please enter 1 or 2.")