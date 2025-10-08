import os
import json
import uuid
import asyncio
import re
import logging
from typing import Dict, List, Optional, Any, TypedDict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from jira import JIRA

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler('jira_agent.log'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class GenerationType(Enum):
    EPICS_ONLY = "epics_only"
    STORIES_ONLY = "stories_only"
    BOTH = "both"

class AnalysisPhase(Enum):
    INPUT = "input"
    ANALYZING = "analyzing"
    QUESTIONING = "questioning"
    VALIDATING = "validating"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"

@dataclass
class Question:
    id: str
    question: str
    context: str
    reasoning: str
    priority: int
    required: bool
    answered: bool = False
    answer: str = ""
    skipped: bool = False

@dataclass
class ValidationResult:
    is_valid: bool
    overall_score: float
    issues: List[str]
    suggestions: List[str]
    confidence: float

class WorkflowState(TypedDict):
    session_id: str
    workflow_type: str
    hlr: str
    selected_project: Optional[str]
    selected_issues: List[str]
    issues_detail: str
    persona: str
    slicing_type: str
    generation_type: GenerationType
    phase: AnalysisPhase
    questions: List[Question]
    responses: Dict[str, str]
    validation_results: Dict[str, ValidationResult]
    requirement_analysis: Dict[str, Any]
    epics: List[Dict]
    user_stories: List[Dict]
    feedback_history: List[str]
    feedback_count: int
    overall_confidence: float
    errors: List[str]
    current_step: str
    has_jira_access: bool

@dataclass
class JIRAProject:
    key: str
    name: str
    description: str

@dataclass
class JIRAIssue:
    key: str
    summary: str
    description: str
    issue_type: str
    status: str
    project_key: str

def strip_code_fences(text: str) -> str:
    return re.sub(r"^```[a-zA-Z]*\n|\n```$", "", text.strip())

class ProjectAccessManager:
    """Agentic manager for project access control"""
    
    def __init__(self, config_file: str = "project_access.json"):
        self.config_file = config_file
        self.allowed_projects = self._load_config()
        logger.info(f"Project Access Manager initialized with {len(self.allowed_projects)} allowed projects")
    
    def _load_config(self) -> List[str]:
        """Load allowed projects from config file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    projects = config.get('allowed_projects', [])
                    logger.info(f"Loaded {len(projects)} allowed projects from {self.config_file}")
                    return projects
            else:
                # Create default config
                default_config = {
                    "allowed_projects": ["BU25MVP", "ORI"],
                    "description": "List of JIRA project keys that users can access"
                }
                with open(self.config_file, 'w') as f:
                    json.dump(default_config, f, indent=2)
                logger.info(f"Created default config file: {self.config_file}")
                return default_config['allowed_projects']
        except Exception as e:
            logger.error(f"Error loading project config: {e}")
            return ["BU25MVP", "ORI"]  # Fallback
    
    def is_project_allowed(self, project_key: str) -> bool:
        """Check if project is in allowed list"""
        return project_key in self.allowed_projects
    
    def get_allowed_projects(self) -> List[str]:
        """Get list of allowed projects"""
        return self.allowed_projects.copy()
    
    def add_project(self, project_key: str):
        """Add project to allowed list"""
        if project_key not in self.allowed_projects:
            self.allowed_projects.append(project_key)
            self._save_config()
            logger.info(f"Added project {project_key} to allowed list")
    
    def remove_project(self, project_key: str):
        """Remove project from allowed list"""
        if project_key in self.allowed_projects:
            self.allowed_projects.remove(project_key)
            self._save_config()
            logger.info(f"Removed project {project_key} from allowed list")
    
    def _save_config(self):
        """Save current config to file"""
        try:
            config = {
                "allowed_projects": self.allowed_projects,
                "description": "List of JIRA project keys that users can access",
                "last_updated": datetime.now().isoformat()
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Saved config to {self.config_file}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

class JiraAgenticIntegration:
    """Fully agentic JIRA integration using OpenAI and jira-python"""
    
    def __init__(self):
        self.server = os.getenv('JIRA_SERVER', '').rstrip('/')
        email = os.getenv('JIRA_EMAIL', '')
        api_token = os.getenv('JIRA_API_TOKEN', '')
        
        # Initialize project access manager
        self.access_manager = ProjectAccessManager()
        
        # Initialize JIRA client
        if self.server and email and api_token:
            try:
                self.jira_client = JIRA(
                    server=self.server,
                    basic_auth=(email, api_token)
                )
                logger.info("Agentic JIRA integration configured successfully")
            except Exception as e:
                logger.error(f"JIRA client failed to initialize: {e}")
                self.jira_client = None
        else:
            self.jira_client = None
            logger.warning("JIRA credentials not configured")
        
        # Initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY', '')
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        self.openai_client = OpenAI(api_key=api_key)
    
    def _execute_jira_agent_task(self, task: str) -> str:
        """Execute JIRA task using agent-generated code"""
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "developer", "content": """You are a very good python developer who has very good knowledge in jira-python library. Your task is to write executable python code to interact with jira to achieve the task given by the user. The authentication is done and connection is established to jira and instance of jira is created in jira_instance. Return only executable python code with the final result stored in variable 'final_response' which will be used to access the result. Do not add any explanation and return only the executable code as I am directly feeding your response to exec method."""},
                    {"role": "user", "content": task}
                ],
                temperature=0.3
            )
            
            python_code = strip_code_fences(response.choices[0].message.content)
            
            # Execute agent-generated code
            context = {"jira_instance": self.jira_client, "final_response": "No result"}
            exec(python_code, {}, context)
            
            return context.get("final_response", "No result")
            
        except Exception as e:
            logger.error(f"Error executing JIRA agent task: {e}")
            return f"Error: {str(e)}"
    
    def get_projects_agentic(self) -> List[JIRAProject]:
        """Agentically retrieve and filter projects"""
        if not self.jira_client:
            logger.error("JIRA client not available")
            return []
        
        try:
            allowed_keys = self.access_manager.get_allowed_projects()
            
            if not allowed_keys:
                logger.warning("No allowed projects configured")
                return []
            
            # Use agent to fetch projects
            allowed_keys_str = ", ".join(allowed_keys)
            task = f"Retrieve project details for these project keys: {allowed_keys_str}. Return a list of dicts with 'key', 'name', and 'description' for each project."
            
            result = self._execute_jira_agent_task(task)
            
            # Parse result and convert to JIRAProject objects
            if isinstance(result, str):
                result = json.loads(result) if result.startswith('[') or result.startswith('{') else []
            
            projects = []
            for proj_data in result:
                if isinstance(proj_data, dict):
                    projects.append(JIRAProject(
                        key=proj_data.get('key', ''),
                        name=proj_data.get('name', ''),
                        description=proj_data.get('description', '')
                    ))
            
            logger.info(f"Successfully retrieved {len(projects)} accessible projects")
            return projects
            
        except Exception as e:
            logger.error(f"Error in agentic project retrieval: {e}")
            return []
    
    def get_issues_agentic(self, project_key: str) -> List[JIRAIssue]:
        """Agentically retrieve issues"""
        if not self.jira_client:
            return []
        
        if not self.access_manager.is_project_allowed(project_key):
            logger.warning(f"Access denied to project {project_key}")
            return []
        
        try:
            task = f"For project '{project_key}', retrieve all issues (max 100) with fields: key, summary, description, issue type, status. Return as list of dicts."
            
            result = self._execute_jira_agent_task(task)
            
            # Parse result
            if isinstance(result, str):
                result = json.loads(result) if result.startswith('[') else []
            
            jira_issues = []
            for issue_data in result:
                if isinstance(issue_data, dict):
                    jira_issues.append(JIRAIssue(
                        key=issue_data.get('key', ''),
                        summary=issue_data.get('summary', ''),
                        description=issue_data.get('description', ''),
                        issue_type=issue_data.get('issue_type', ''),
                        status=issue_data.get('status', ''),
                        project_key=project_key
                    ))
            
            logger.info(f"Retrieved {len(jira_issues)} issues from {project_key}")
            return jira_issues
            
        except Exception as e:
            logger.error(f"Error getting issues: {e}")
            return []
    
    def get_all_tasks_agentic(self, project_key: str) -> str:
        """Get comprehensive task list using agent"""
        if not self.jira_client:
            return "JIRA client not available"
        
        if not self.access_manager.is_project_allowed(project_key):
            return f"Access denied to project {project_key}"
        
        try:
            task = f"""For project '{project_key}', retrieve all issues and format them comprehensively:
- Issue count by type
- Each issue with: Key, Title, Type, Status, Description (first 150 chars)
- Grouped by issue type (Epic, Story, Task, Bug, etc.)
Return formatted string output."""
            
            result = self._execute_jira_agent_task(task)
            return result
                
        except Exception as e:
            logger.error(f"Error in agentic task retrieval: {e}")
            return f"Error: {str(e)}"
    
    def generate_context_guidance(self, issues: List[JIRAIssue], hlr: str) -> str:
        """Generate agentic guidance based on JIRA context"""
        if not issues:
            return ""
        
        issue_types = {}
        statuses = {}
        
        for issue in issues:
            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1
            statuses[issue.status] = statuses.get(issue.status, 0) + 1
        
        guidance = f"""
JIRA Project Context Analysis:
- Total Issues: {len(issues)}
- Issue Types: {dict(sorted(issue_types.items(), key=lambda x: x[1], reverse=True))}
- Status Distribution: {dict(sorted(statuses.items(), key=lambda x: x[1], reverse=True))}

Contextual Recommendations for HLR "{hlr}":
1. Consider existing issue patterns
2. Align with current project workflow
3. Leverage project structure and naming conventions
4. Account for team capacity based on status distribution
"""
        return guidance

class RequirementAnalysisAgent:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")
        
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4"
        self.temperature = 0.3
        
        self.slicing_config = {
            "functional": {
                "name": "Functional Decomposition",
                "description": "Break down by core business functions and user workflows",
                "personas": ["Business Analyst", "Product Owner", "Domain Expert"],
                "focus_areas": ["user_workflows", "business_processes", "functional_requirements"]
            },
            "technical": {
                "name": "Technical Layer Decomposition", 
                "description": "Break down by technical components and system layers",
                "personas": ["Technical Lead", "System Architect", "DevOps Engineer"],
                "focus_areas": ["system_architecture", "technical_components", "integration_points"]
            },
            "user_journey": {
                "name": "User Journey Decomposition",
                "description": "Break down by user personas and their interaction journeys",
                "personas": ["UX Designer", "Product Manager", "User Researcher"],
                "focus_areas": ["user_personas", "interaction_flows", "user_experience"]
            }
        }
        
        logger.info("Requirement Analysis Agent initialized")
    
    async def analyze_requirement(self, hlr: str, jira_guidance: str = "") -> Dict[str, Any]:
        analysis_prompt = f"""
You are an expert Business Analyst specializing in requirement analysis.

Analyze the following High-Level Requirement:

HLR: "{hlr}"

{jira_guidance}

Available slicing approaches:
- functional: Break down by business functions and workflows
- technical: Break down by technical components and system layers  
- user_journey: Break down by user personas and interaction journeys

Provide analysis as JSON:
{{
    "slicing_type": "functional|technical|user_journey",
    "recommended_persona": "most suitable persona",
    "domain": "identified business domain",
    "complexity": "Low|Medium|High",
    "user_types": ["list of user personas"],
    "main_features": ["key functional areas"],
    "confidence": 0.0-1.0
}}

JSON only:
"""
        
        try:
            response = await self._call_openai(analysis_prompt)
            result = self._parse_json_response(response)
            logger.info(f"Analysis completed: {result.get('slicing_type')}")
            return result
        except Exception as e:
            logger.error(f"Error analyzing requirement: {e}")
            return {
                "slicing_type": "functional",
                "recommended_persona": "Business Analyst", 
                "domain": "general",
                "complexity": "Medium",
                "user_types": ["user"],
                "main_features": [],
                "confidence": 0.5
            }
    
    async def generate_questions(self, hlr: str, slicing_type: str, persona: str, jira_guidance: str = "") -> List[Question]:
        slicing_info = self.slicing_config.get(slicing_type, self.slicing_config["functional"])
        
        question_prompt = f"""
You are an expert {persona} analyzing requirements for JIRA story creation.

Context:
- HLR: "{hlr}"
- Slicing Approach: {slicing_info['name']}
- Focus Areas: {slicing_info['focus_areas']}

{jira_guidance}

Generate 3 specific, actionable questions to decompose this HLR.

Response format (JSON only):
{{
    "questions": [
        {{
            "question": "What specific user roles will interact with this system?",
            "context": "Understanding user types helps define personas",
            "reasoning": "User roles impact story structure",
            "priority": 1,
            "required": true
        }}
    ]
}}

JSON only:
"""
        
        try:
            response = await self._call_openai(question_prompt)
            question_data = self._parse_json_response(response)
            
            questions = []
            for q_data in question_data.get('questions', []):
                question = Question(
                    id=f"q_{uuid.uuid4().hex[:8]}",
                    question=q_data['question'],
                    context=q_data.get('context', ''),
                    reasoning=q_data.get('reasoning', ''),
                    priority=q_data.get('priority', 3),
                    required=q_data.get('required', True)
                )
                questions.append(question)
            
            logger.info(f"Generated {len(questions)} questions")
            return questions
            
        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            return []
    
    async def validate_response(self, hlr: str, question: Question, user_response: str) -> ValidationResult:
        validation_prompt = f"""
Validate the response:

HLR: "{hlr}"
Question: "{question.question}"
Response: "{user_response}"

Validate for: relevance, completeness, clarity, actionability

JSON format:
{{
    "is_valid": true|false,
    "overall_score": 0.0-1.0,
    "issues": ["list of issues"],
    "suggestions": ["improvement suggestions"],
    "confidence": 0.0-1.0
}}

JSON only:
"""
        
        try:
            response = await self._call_openai(validation_prompt)
            validation_data = self._parse_json_response(response)
            
            result = ValidationResult(
                is_valid=validation_data['is_valid'],
                overall_score=validation_data['overall_score'],
                issues=validation_data['issues'],
                suggestions=validation_data['suggestions'],
                confidence=validation_data['confidence']
            )
            
            logger.info(f"Validation completed: {'valid' if result.is_valid else 'invalid'}")
            return result
            
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return ValidationResult(
                is_valid=True,
                overall_score=0.7,
                issues=[],
                suggestions=[],
                confidence=0.5
            )
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert requirements analyst. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=2000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Failed to parse JSON: {e}")
 
# class TaskGenerator:
#     """
#     this class the writes task for the jira agent which communicates with jira
#     """
#     def __init__(self, openai_client: OpenAI,data: List):
#         self.client = openai_client
#         self.model = "gpt-4"
#         self.temperature = 0.3
#         self.json_data=data
#         logger.info("task generator Agent initialized")
   
#     def _call_openai(self, prompt: str) -> str:
#         try:
#             response = self.client.chat.completions.create(
#                 model=self.model,
#                 messages=[
#                     {"role": "system", "content": "you are an expert task generator"},
#                     {"role": "user", "content": prompt}
#                 ],
#                 temperature=self.temperature,
#                 max_tokens=3000
#             )
#             return response.choices[0].message.content.strip()
#         except Exception as e:
#             logger.error(f"OpenAI API error: {e}")
#             raise
   
#     def _parse_json_response(self, response: str) -> Dict[str, Any]:
#         try:
#             cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
#             return json.loads(cleaned_response)
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse JSON response: {e}")
#             raise ValueError(f"Failed to parse JSON response: {e}")
       
#     def task_generation(self,):
#         Task_generated=f"your task is to convert the human requirment to jira task which will be then used by the jira interaction bot \
#         your task is to convert the human requirmrnt into step instruction that jira bot has to perform  \
#         humam reqirment :i want to create new story for the project with id ORI and my data are \
#                     {self.json_data}"
#         response = self._call_openai(Task_generated)
#         print("response 1================")
#         print(response)
 
#         task_code_generator=f"you are a very good python developer who uses has very good knowledge in jira-pypi library ypur task is to just write executable python code to interact with jira to achive the task given by the user provided authentication is done and connection is established to jira and instance of jira is created in jira_instance , return only the executable code python format with Format of your ouput always and must have final result in variable 'final_response' which will later be used to access the result of executable code do not add in any explanation and return only the executable code as i am directly feeding your response to exec method\
#         the list of tasks :{response}\
#         "
#         response = self._call_openai(task_code_generator)
#         print("code==================================")
#         print(response)
#         return response

class EpicGeneratorAgent:
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        self.model = "gpt-4"
        self.temperature = 0.3
        logger.info("Epic Generator Agent initialized")
    
    async def generate_epics(self, hlr: str, context: str, qa_responses: Dict[str, str]) -> List[Dict]:
        qa_context = self._build_qa_context(qa_responses)
        
        epic_prompt = f"""
You are an expert Epic writer for JIRA.

Context:
- HLR: "{hlr}"
- Additional Context: {context}
- Q&A Insights: {qa_context}

Generate 2-4 comprehensive epics.

JSON format:
{{
    "epics": [
        {{
            "title": "User Authentication and Authorization",
            "description": "Comprehensive description",
            "business_value": "Clear business value",
            "acceptance_criteria": ["Criteria 1", "Criteria 2"],
            "priority": "High|Medium|Low",
            "estimated_story_points": 21,
            "dependencies": ["External dependencies"],
            "assumptions": ["Key assumptions"],
            "risks": ["Identified risks"]
        }}
    ]
}}

JSON only:
"""
        
        try:
            response = await self._call_openai(epic_prompt)
            epic_data = self._parse_json_response(response)
            epics = epic_data.get('epics', [])
            logger.info(f"Generated {len(epics)} epics")
            return epics
        except Exception as e:
            logger.error(f"Error generating epics: {e}")
            return []
    
    def _build_qa_context(self, qa_responses: Dict[str, str]) -> str:
        if not qa_responses:
            return "No Q&A responses provided"
        
        context_parts = []
        for question_id, response in qa_responses.items():
            if response and response != "[SKIPPED]":
                context_parts.append(f"- {response}")
        
        return "\n".join(context_parts) if context_parts else "No valid responses"
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert Epic writer. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=3000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Failed to parse JSON: {e}")

class UserStoryGeneratorAgent:
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        self.model = "gpt-4"
        self.temperature = 0.3
        logger.info("User Story Generator Agent initialized")
    
    async def generate_user_stories(self, hlr: str, context: str, qa_responses: Dict[str, str], epics: List[Dict]) -> List[Dict]:
        qa_context = self._build_qa_context(qa_responses)
        epic_context = self._build_epic_context(epics)
        
        story_prompt = f"""
You are an expert User Story writer for JIRA.

Context:
- HLR: "{hlr}"
- Additional Context: {context}
- Q&A Insights: {qa_context}
- Related Epics: {epic_context}

Generate 5-12 detailed user stories following INVEST principles.

JSON format:
{{
    "user_stories": [
        {{
            "title": "User can log in with email and password",
            "description": "As a registered user, I want to log in using email and password so that I can access my dashboard",
            "user_persona": "Registered User",
            "acceptance_criteria": [
                "Given valid credentials, when I login, then I access dashboard",
                "Given invalid credentials, when I login, then I see error"
            ],
            "definition_of_done": [
                "Code implemented and tested",
                "Unit tests passing",
                "Code reviewed"
            ],
            "story_points": 3,
            "priority": "High|Medium|Low",
            "labels": ["authentication", "frontend"],
            "dependencies": ["Database setup"],
            "epic_reference": "Related Epic Title or null"
        }}
    ]
}}

JSON only:
"""
        
        try:
            response = await self._call_openai(story_prompt)
            story_data = self._parse_json_response(response)
            stories = story_data.get('user_stories', [])
            logger.info(f"Generated {len(stories)} user stories")
            return stories
        except Exception as e:
            logger.error(f"Error generating user stories: {e}")
            return []
    
    def _build_qa_context(self, qa_responses: Dict[str, str]) -> str:
        if not qa_responses:
            return "No Q&A responses provided"
        
        context_parts = []
        for question_id, response in qa_responses.items():
            if response and response != "[SKIPPED]":
                context_parts.append(f"- {response}")
        
        return "\n".join(context_parts) if context_parts else "No valid responses"
    
    def _build_epic_context(self, epics: List[Dict]) -> str:
        if not epics:
            return "No epics available"
        
        context_parts = []
        for epic in epics:
            context_parts.append(f"- {epic.get('title', 'Untitled')}: {epic.get('description', 'No description')}")
        
        return "\n".join(context_parts)
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert User Story writer. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=4000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Failed to parse JSON: {e}")

# Interactive functions
def select_project(projects: List[JIRAProject]) -> Optional[str]:
    if not projects:
        return None
    
    for i, project in enumerate(projects, 1):
        desc = f" - {project.description}" if project.description else ""
        print(f"{i}. {project.key}: {project.name}{desc}")
    
    while True:
        try:
            choice = int(input(f"\nSelect project (1-{len(projects)}): "))
            if 1 <= choice <= len(projects):
                return projects[choice - 1].key
        except ValueError:
            continue

def get_workflow_choice() -> str:
    while True:
        choice = input("\nChoose workflow:\n1. Work with existing JIRA issues\n2. Create new requirement\nEnter choice (1/2): ").strip()
        if choice in ["1", "2"]:
            return "existing" if choice == "1" else "new"

def display_all_issues_agentic(jira_agent: JiraAgenticIntegration, project_key: str) -> str:
    """Agentic display of all issues"""
    print(f"\nRetrieving tasks from project {project_key}...")
    
    tasks_display = jira_agent.get_all_tasks_agentic(project_key)
    print(tasks_display)
    
    issues = jira_agent.get_issues_agentic(project_key)
    
    issues_detail = []
    for issue in issues:
        issues_detail.append(f"Issue: {issue.key} - {issue.summary}\nType: {issue.issue_type}\nStatus: {issue.status}\nDescription: {issue.description}")
    
    return "\n\n".join(issues_detail)

def get_persona_with_suggestion(recommended_persona: str) -> str:
    """Get persona with AI suggestion and user confirmation"""
    print(f"\nPersona Selection:")
    print("-" * 30)
    print(f"Suggested persona: {recommended_persona}")
    
    choice = input(f"Press 'ok' to use suggested persona or enter your preferred persona: ").strip()
    
    if choice.lower() in ['ok', 'okay', '']:
        print(f"Using suggested persona: {recommended_persona}")
        return recommended_persona
    else:
        custom_persona = choice if choice else recommended_persona
        print(f"Using custom persona: {custom_persona}")
        return custom_persona

def get_hlr_input() -> str:
    """Get HLR input"""
    print("\nEnter your High-Level Requirement:")
    print("-" * 40)
    hlr = input().strip()
    
    if not hlr:
        print("Please enter your requirement:")
        hlr = input().strip()
    
    return hlr

def get_generation_type() -> GenerationType:
    options = {
        "1": GenerationType.EPICS_ONLY,
        "2": GenerationType.STORIES_ONLY,
        "3": GenerationType.BOTH
    }
    
    print("\n1. Epics Only")
    print("2. User Stories Only")
    print("3. Both Epics and User Stories")
    
    while True:
        choice = input("\nSelect generation type (1-3): ").strip()
        if choice in options:
            return options[choice]

# Initialize agents
jira_agent = JiraAgenticIntegration()
req_agent = RequirementAnalysisAgent()

# Node functions
async def start_node(state: WorkflowState) -> WorkflowState:
    state["session_id"] = f"session_{uuid.uuid4().hex[:8]}"
    state["current_step"] = "start"
    state["phase"] = AnalysisPhase.INPUT
    state["has_jira_access"] = True
    
    # Select project first
    print("\nAvailable Projects:")
    print("-" * 40)
    projects = jira_agent.get_projects_agentic()
    
    if not projects:
        print("No accessible JIRA projects found")
        state["errors"].append("No accessible JIRA projects found")
        state["has_jira_access"] = False
        state["workflow_type"] = "new"
        return state
    
    selected_project_key = select_project(projects)
    if not selected_project_key:
        print("No project selected")
        state["errors"].append("No project selected")
        state["has_jira_access"] = False
        state["workflow_type"] = "new"
        return state
    
    state["selected_project"] = selected_project_key
    
    # Now ask workflow choice
    state["workflow_type"] = get_workflow_choice()
    
    return state

async def jira_integration_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "jira_integration"
    
    # Display all issues
    issues_detail = display_all_issues_agentic(jira_agent, state["selected_project"])
    state["issues_detail"] = issues_detail
    
    issues = jira_agent.get_issues_agentic(state["selected_project"])
    state["selected_issues"] = [issue.key for issue in issues]
    
    # Get HLR after displaying issues
    state["hlr"] = get_hlr_input()
    
    return state

async def new_requirement_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "new_requirement"
    state["hlr"] = get_hlr_input()
    state["has_jira_access"] = False
    return state

async def requirement_analysis_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "requirement_analysis"
    state["phase"] = AnalysisPhase.ANALYZING
    
    if not state.get("hlr"):
        state["errors"].append("No HLR provided")
        return state
    
    # Generate JIRA guidance if working with existing project
    jira_guidance = ""
    if state.get("workflow_type") == "existing" and state.get("has_jira_access") and state.get("selected_issues"):
        selected_project = state.get("selected_project")
        if selected_project:
            issues = jira_agent.get_issues_agentic(selected_project)
            jira_guidance = jira_agent.generate_context_guidance(issues, state["hlr"])
    
    # Analyze requirement with JIRA context
    analysis = await req_agent.analyze_requirement(state["hlr"], jira_guidance)
    state["requirement_analysis"] = analysis
    state["slicing_type"] = analysis.get("slicing_type", "functional")
    
    # Get persona with AI suggestion
    recommended_persona = analysis.get("recommended_persona", "Business Analyst")
    state["persona"] = get_persona_with_suggestion(recommended_persona)
    
    # Generate questions with JIRA context
    state["phase"] = AnalysisPhase.QUESTIONING
    questions = await req_agent.generate_questions(state["hlr"], state["slicing_type"], state["persona"], jira_guidance)
    state["questions"] = questions
    
    # Interactive Q&A session
    qa_responses = {}
    
    for question in questions:
        print(f"\nQuestion: {question.question}")
        print(f"Context: {question.context}")
        print(f"Priority: {question.priority}/5 | Required: {'Yes' if question.required else 'No'}")
        
        response = input("Your answer (or 'skip' to skip): ").strip()
        
        if response.lower() == 'skip':
            question.skipped = True
            question.answered = True
            question.answer = "[SKIPPED]"
        elif response:
            # Validate response
            state["phase"] = AnalysisPhase.VALIDATING
            validation_result = await req_agent.validate_response(state["hlr"], question, response)
            
            question.answered = True
            question.answer = response
            qa_responses[question.id] = response
            state["validation_results"][question.id] = validation_result
            
            if not validation_result.is_valid and validation_result.issues:
                print("Issues found:")
                for issue in validation_result.issues:
                    print(f"- {issue}")
                
                if validation_result.suggestions:
                    print("Suggestions:")
                    for suggestion in validation_result.suggestions:
                        print(f"- {suggestion}")
                
                retry = input("Provide better answer? (y/n): ").strip().lower()
                if retry == 'y':
                    new_response = input("Your improved answer: ").strip()
                    if new_response:
                        question.answer = new_response
                        qa_responses[question.id] = new_response
    
    state["responses"] = qa_responses
    
    # Calculate overall confidence
    valid_scores = [vr.overall_score for vr in state["validation_results"].values() if vr.is_valid]
    state["overall_confidence"] = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0
    
    return state

async def setup_generation_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "setup_generation"
    state["generation_type"] = get_generation_type()
    return state

async def generation_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "generation"
    state["phase"] = AnalysisPhase.GENERATING
    
    # Prepare context
    context = f"Persona: {state.get('persona', 'Business Analyst')}\n"
    context += f"Slicing Type: {state.get('slicing_type', 'functional')}\n"
    context += f"Domain: {state.get('requirement_analysis', {}).get('domain', 'general')}\n"
    
    if state.get("issues_detail"):
        context += f"\nJIRA Issues Context:\n{state['issues_detail']}"
    
    # Initialize OpenAI client
    api_key = os.getenv('OPENAI_API_KEY')
    if api_key.startswith('"') and api_key.endswith('"'):
        api_key = api_key[1:-1]
    openai_client = OpenAI(api_key=api_key)
    
    epic_agent = EpicGeneratorAgent(openai_client)
    story_agent = UserStoryGeneratorAgent(openai_client)
    
    # Generate content based on type
    if state["generation_type"] in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
        epics = await epic_agent.generate_epics(state["hlr"], context, state["responses"])
        state["epics"] = epics
    
    if state["generation_type"] in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
        stories = await story_agent.generate_user_stories(
            state["hlr"], 
            context, 
            state["responses"], 
            state.get("epics", [])
        )
        state["user_stories"] = stories
    
    return state

async def feedback_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "feedback"
    
    # Display generated content
    print("\n" + "="*80)
    print("GENERATED CONTENT")
    print("="*80)
    
    if state.get("epics"):
        print(f"\nGENERATED EPICS ({len(state['epics'])}):")
        print("-" * 50)
        for i, epic in enumerate(state["epics"], 1):
            print(f"\n{i}. {epic.get('title', 'Untitled Epic')}")
            print(f"   Priority: {epic.get('priority', 'Not set')}")
            print(f"   Story Points: {epic.get('estimated_story_points', 'Not estimated')}")
            print(f"   Business Value: {epic.get('business_value', 'Not specified')[:100]}...")
    
    if state.get("user_stories"):
        print(f"\nGENERATED USER STORIES ({len(state['user_stories'])}):")
        print("-" * 50)
        for i, story in enumerate(state["user_stories"], 1):
            print(f"\n{i}. {story.get('title', 'Untitled Story')}")
            print(f"   Description: {story.get('description', 'No description')[:100]}...")
            print(f"   Priority: {story.get('priority', 'Not set')}")
            print(f"   Story Points: {story.get('story_points', 'Not estimated')}")
    
    # Feedback loop (max 3 iterations)
    while state["feedback_count"] < 3:
        satisfied = input("\nSatisfied with content? (yes/no): ").strip().lower()
        
        if satisfied in ['yes', 'y']:
            break
        
        feedback = input("Provide feedback for improvements: ").strip()
        if not feedback:
            break
        
        if feedback:
            state["feedback_history"].append(feedback)
            state["feedback_count"] += 1
            
            # Regenerate with feedback
            base_context = f"Persona: {state.get('persona', 'Business Analyst')}\n"
            base_context += f"Slicing Type: {state.get('slicing_type', 'functional')}\n"
            
            if state.get("issues_detail"):
                base_context += f"\nJIRA Context:\n{state['issues_detail']}"
            
            feedback_context = f"{base_context}\n\nUser Feedback: {feedback}\nIteration: {state['feedback_count']}"
            
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key.startswith('"') and api_key.endswith('"'):
                api_key = api_key[1:-1]
            openai_client = OpenAI(api_key=api_key)
            
            epic_agent = EpicGeneratorAgent(openai_client)
            story_agent = UserStoryGeneratorAgent(openai_client)
            
            if state["generation_type"] in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
                epics = await epic_agent.generate_epics(state["hlr"], feedback_context, state["responses"])
                state["epics"] = epics
            
            if state["generation_type"] in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
                stories = await story_agent.generate_user_stories(
                    state["hlr"], 
                    feedback_context, 
                    state["responses"], 
                    state.get("epics", [])
                )
                state["user_stories"] = stories
            
            # Show updated content
            print("\n" + "="*80)
            print("UPDATED CONTENT")
            print("="*80)
            
            if state.get("epics"):
                print(f"\nUPDATED EPICS ({len(state['epics'])}):")
                for i, epic in enumerate(state["epics"], 1):
                    print(f"{i}. {epic.get('title', 'Untitled')}")
            
            if state.get("user_stories"):
                print(f"\nUPDATED STORIES ({len(state['user_stories'])}):")
                for i, story in enumerate(state["user_stories"], 1):
                    print(f"{i}. {story.get('title', 'Untitled')}")
        else:
            break
    
    return state

async def final_validation_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "final_validation"
    state["phase"] = AnalysisPhase.COMPLETE
    
    if not state.get("epics") and not state.get("user_stories"):
        state["errors"].append("No content generated")
    
    return state

# Routing functions
def should_use_jira(state: WorkflowState) -> str:
    """Conditional edge based on workflow type"""
    return "jira_integration" if state.get("workflow_type") == "existing" else "new_requirement"

# Create workflow
workflow = StateGraph(WorkflowState)

# Add nodes
workflow.add_node("start", start_node)
workflow.add_node("jira_integration", jira_integration_node)
workflow.add_node("new_requirement", new_requirement_node)
workflow.add_node("requirement_analysis", requirement_analysis_node)
workflow.add_node("setup_generation", setup_generation_node)
workflow.add_node("generation", generation_node)
workflow.add_node("feedback", feedback_node)
workflow.add_node("final_validation", final_validation_node)

# Add edges with conditional routing
workflow.set_entry_point("start")
workflow.add_conditional_edges("start", should_use_jira)
workflow.add_edge("jira_integration", "requirement_analysis")
workflow.add_edge("new_requirement", "requirement_analysis")
workflow.add_edge("requirement_analysis", "setup_generation")
workflow.add_edge("setup_generation", "generation")
workflow.add_edge("generation", "feedback")
workflow.add_edge("feedback", "final_validation")
workflow.add_edge("final_validation", END)

# Compile workflow
app = workflow.compile()

def display_results(state: WorkflowState):
    print("\n" + "="*60)
    print("WORKFLOW RESULTS")
    print("="*60)
    
    session_info = f"""
Session ID: {state['session_id']}
Workflow Type: {state['workflow_type']}
Persona: {state.get('persona', 'Not set')}
Slicing Type: {state.get('slicing_type', 'Not set')}
Generation Type: {state.get('generation_type', {}).value if state.get('generation_type') else 'Not set'}
Overall Confidence: {state.get('overall_confidence', 0.0):.2f}
Feedback Iterations: {state.get('feedback_count', 0)}
"""
    print(session_info)
    
    if state.get('selected_project'):
        print(f"JIRA Project: {state['selected_project']}")
        print(f"Issues Analyzed: {len(state.get('selected_issues', []))}")
    
    print(f"\nHigh Level Requirement:")
    print("-" * 30)
    print(state.get('hlr', 'Not provided'))
    
    if state.get('epics'):
        print(f"\nGenerated Epics ({len(state['epics'])}):")
        print("-" * 30)
        for i, epic in enumerate(state['epics'], 1):
            print(f"\n{i}. {epic.get('title', 'Untitled')}")
            print(f"   Priority: {epic.get('priority', 'Not set')}")
            print(f"   Story Points: {epic.get('estimated_story_points', 'Not estimated')}")
    
    if state.get('user_stories'):
        print(f"\nGenerated User Stories ({len(state['user_stories'])}):")
        print("-" * 30)
        for i, story in enumerate(state['user_stories'], 1):
            print(f"\n{i}. {story.get('title', 'Untitled')}")
            print(f"   Priority: {story.get('priority', 'Not set')}")
            print(f"   Story Points: {story.get('story_points', 'Not estimated')}")
    
    if state.get('errors'):
        print("\nErrors:")
        print("-" * 30)
        for error in state['errors']:
            print(f"- {error}")

def create_clean_output(state: WorkflowState) -> Dict[str, Any]:
    """Create clean output without validation scores"""
    
    output = {
        "session_metadata": {
            "session_id": state['session_id'],
            "workflow_type": state['workflow_type'],
            "generation_type": state.get('generation_type', {}).value if state.get('generation_type') else None,
            "persona": state.get('persona', ''),
            "slicing_type": state.get('slicing_type', ''),
            "overall_confidence": state.get('overall_confidence', 0.0),
            "feedback_iterations": state.get('feedback_count', 0),
            "created_at": datetime.now().isoformat()
        },
        "requirement": {
            "hlr": state.get('hlr', ''),
            "analysis": {
                "domain": state.get('requirement_analysis', {}).get('domain', ''),
                "complexity": state.get('requirement_analysis', {}).get('complexity', ''),
                "user_types": state.get('requirement_analysis', {}).get('user_types', []),
                "main_features": state.get('requirement_analysis', {}).get('main_features', [])
            }
        }
    }
    
    if state.get('selected_project'):
        output["jira_context"] = {
            "project": state['selected_project'],
            "analyzed_issues": len(state.get('selected_issues', []))
        }
    
    if state.get('questions'):
        qa_summary = []
        for question in state['questions']:
            if question.answered and not question.skipped:
                qa_summary.append({
                    "question": question.question,
                    "answer": question.answer,
                    "priority": question.priority
                })
        
        output["qa_session"] = {
            "total_questions": len(state['questions']),
            "answered_questions": len([q for q in state['questions'] if q.answered and not q.skipped]),
            "responses": qa_summary
        }
    
    generated_content = {}
    
    if state.get('epics'):
        generated_content["epics"] = []
        for epic in state['epics']:
            clean_epic = {
                "title": epic.get('title', ''),
                "description": epic.get('description', ''),
                "business_value": epic.get('business_value', ''),
                "acceptance_criteria": epic.get('acceptance_criteria', []),
                "priority": epic.get('priority', ''),
                "estimated_story_points": epic.get('estimated_story_points', 0),
                "dependencies": epic.get('dependencies', []),
                "assumptions": epic.get('assumptions', []),
                "risks": epic.get('risks', [])
            }
            generated_content["epics"].append(clean_epic)
    
    if state.get('user_stories'):
        generated_content["user_stories"] = []
        for story in state['user_stories']:
            clean_story = {
                "title": story.get('title', ''),
                "description": story.get('description', ''),
                "user_persona": story.get('user_persona', ''),
                "acceptance_criteria": story.get('acceptance_criteria', []),
                "definition_of_done": story.get('definition_of_done', []),
                "story_points": story.get('story_points', 0),
                "priority": story.get('priority', ''),
                "labels": story.get('labels', []),
                "dependencies": story.get('dependencies', []),
                "epic_reference": story.get('epic_reference', None)
            }
            generated_content["user_stories"].append(clean_story)
    
    output["generated_content"] = generated_content
    
    output["statistics"] = {
        "total_epics": len(state.get('epics', [])),
        "total_user_stories": len(state.get('user_stories', [])),
        "total_story_points": sum(epic.get('estimated_story_points', 0) for epic in state.get('epics', [])) + 
                            sum(story.get('story_points', 0) for story in state.get('user_stories', [])),
        "errors_count": len(state.get('errors', []))
    }
    
    if state.get('feedback_history'):
        output["feedback_history"] = state['feedback_history']
    
    if state.get('errors'):
        output["errors"] = state['errors']
    
    return output

async def run_workflow():
    initial_state = {
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
        "current_step": "",
        "has_jira_access": False
    }
    
    try:
        final_state = await app.ainvoke(initial_state)
        display_results(final_state)
        
        clean_output = create_clean_output(final_state)
        
        save_option = input("\nSave results to file? (y/n): ").strip().lower()
        if save_option == 'y':
            filename = f"jira_results_{final_state['session_id']}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(clean_output, f, indent=2, ensure_ascii=False)
            print(f"Results saved to {filename}")
        
        return final_state
        
    except Exception as e:
        logger.error(f"Workflow error: {e}")
        print(f"Workflow error: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(run_workflow())