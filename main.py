import os
import json
import requests
import base64
import uuid
import asyncio
import re
import logging
from typing import Dict, List, Optional, Any, TypedDict, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from typing import Annotated
from typing_extensions import TypedDict as LangGraphTypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
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

class JiraState(LangGraphTypedDict):
    jira_task: str
    jira_task_output: dict

class JiraIntegrationAgent:
    def __init__(self):
        # Original JIRA integration (REST API)
        self.server = os.getenv('JIRA_SERVER', '').rstrip('/')
        email = os.getenv('JIRA_EMAIL', '')
        api_token = os.getenv('JIRA_API_TOKEN', '')
        
        if self.server and email and api_token:
            auth_string = f"{email}:{api_token}"
            auth_b64 = base64.b64encode(auth_string.encode('ascii')).decode('ascii')
            self.headers = {
                'Authorization': f'Basic {auth_b64}',
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            
            # Enhanced JIRA integration using jira-python library
            try:
                self.jira_client = JIRA(
                    server=self.server,
                    basic_auth=(email, api_token)
                )
                logger.info("JIRA integration configured successfully with both REST API and jira-python")
            except Exception as e:
                logger.warning(f"jira-python client failed to initialize: {e}, falling back to REST API only")
                self.jira_client = None
        else:
            self.headers = None
            self.jira_client = None
            logger.warning("JIRA credentials not configured. JIRA integration will not be available.")
    
    def get_projects(self) -> List[JIRAProject]:
        if not self.headers:
            return []
        
        try:
            response = requests.get(f"{self.server}/rest/api/2/project", headers=self.headers, timeout=10)
            if response.status_code == 200:
                projects = [JIRAProject(p['key'], p['name'], p.get('description', '')) 
                           for p in response.json()]
                logger.info(f"Retrieved {len(projects)} JIRA projects")
                return projects
            else:
                logger.error(f"Failed to get projects. Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
        return []
    
    def get_issues_enhanced(self, project_key: str) -> List[JIRAIssue]:
        """Enhanced method to get issues using jira-python library with better task retrieval"""
        if not self.jira_client:
            return self.get_issues(project_key)  # Fallback to original method
        
        try:
            # Use JQL to get all issues from the project with more details
            jql_query = f'project = {project_key} ORDER BY created DESC'
            issues = self.jira_client.search_issues(
                jql_query,
                maxResults=100,
                fields='summary,description,issuetype,status,assignee,priority,created,updated,reporter'
            )
            
            jira_issues = []
            for issue in issues:
                # Extract description safely
                description = ""
                if hasattr(issue.fields, 'description') and issue.fields.description:
                    description = issue.fields.description
                
                jira_issue = JIRAIssue(
                    key=issue.key,
                    summary=issue.fields.summary,
                    description=description,
                    issue_type=issue.fields.issuetype.name,
                    status=issue.fields.status.name,
                    project_key=project_key
                )
                jira_issues.append(jira_issue)
            
            logger.info(f"Retrieved {len(jira_issues)} issues from project {project_key} using enhanced method")
            return jira_issues
            
        except Exception as e:
            logger.error(f"Error getting issues with enhanced method: {e}")
            return self.get_issues(project_key)  # Fallback to original method
    
    def get_issues(self, project_key: str) -> List[JIRAIssue]:
        """Original method as fallback"""
        if not self.headers:
            return []
        
        try:
            jql = f'project = {project_key} ORDER BY created DESC'
            params = {'jql': jql, 'maxResults': 100, 'fields': 'summary,description,issuetype,status'}
            
            response = requests.get(f"{self.server}/rest/api/2/search", headers=self.headers, params=params, timeout=10)
            if response.status_code == 200:
                issues = []
                for issue_data in response.json().get('issues', []):
                    fields = issue_data['fields']
                    issue = JIRAIssue(
                        key=issue_data['key'],
                        summary=fields.get('summary', ''),
                        description=fields.get('description', '') or '',
                        issue_type=fields['issuetype']['name'],
                        status=fields['status']['name'],
                        project_key=project_key
                    )
                    issues.append(issue)
                
                logger.info(f"Retrieved {len(issues)} issues from project {project_key}")
                return issues
            else:
                logger.error(f"Failed to get issues. Status: {response.status_code}")
        except Exception as e:
            logger.error(f"Error getting issues: {e}")
        return []
    
    def get_all_tasks_for_project(self, project_key: str) -> str:
        """Get comprehensive task list using OpenAI-powered JIRA interaction"""
        if not self.jira_client:
            logger.warning("Enhanced JIRA client not available, using basic method")
            issues = self.get_issues(project_key)
            return self.format_issues_display(issues)
        
        # Initialize OpenAI client
        client = OpenAI()
        
        def jira_interaction(state: JiraState) -> JiraState:
            state["jira_task"] = state["jira_task"]
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=[{
                    "role": "user",
                    "content": state["jira_task"],
                }],
            )
            state["jira_task_output"] = completion.choices[0].message.content
            return state
        
        try:
            # Create graph for JIRA interaction
            graph_builder = StateGraph(JiraState)
            graph_builder.add_node("jira_interaction", jira_interaction)
            graph_builder.add_edge(START, "jira_interaction")
            graph_builder.add_edge("jira_interaction", END)
            graph = graph_builder.compile()
            
            # Execute the graph to get JIRA tasks
            task_query = f"for project {project_key} get the list of all available issues with their titles, types, statuses, and descriptions. Format the output in a structured way showing: Issue Key, Title, Type, Status, Description (first 100 chars)"
            
            result = graph.invoke({"jira_task": task_query})
            python_code = strip_code_fences(result["jira_task_output"])
            
            # Execute the generated code with JIRA context
            context = {"jira_instance": self.jira_client, "final_response": "No tasks found"}
            try:
                exec(python_code, {}, context)
                tasks_response = context.get("final_response", "No tasks found")
                
                if tasks_response and tasks_response != "No tasks found":
                    return tasks_response
                else:
                    # Fallback to direct method
                    return self.get_tasks_direct(project_key)
                    
            except Exception as exec_error:
                logger.error(f"Error executing generated code: {exec_error}")
                return self.get_tasks_direct(project_key)
                
        except Exception as e:
            logger.error(f"Error in OpenAI-powered task retrieval: {e}")
            return self.get_tasks_direct(project_key)
    
    def get_tasks_direct(self, project_key: str) -> str:
        """Direct method to get and format tasks"""
        issues = self.get_issues_enhanced(project_key)
        return self.format_issues_display(issues)
    
    def format_issues_display(self, issues: List[JIRAIssue]) -> str:
        """Format issues for display"""
        if not issues:
            return "No issues found in this project."
        
        formatted_output = f"Found {len(issues)} issues in project:\n"
        formatted_output += "="*80 + "\n"
        
        # Group issues by type
        issue_types = {}
        for issue in issues:
            issue_type = issue.issue_type
            if issue_type not in issue_types:
                issue_types[issue_type] = []
            issue_types[issue_type].append(issue)
        
        # Display by type
        for issue_type, type_issues in issue_types.items():
            formatted_output += f"\n{issue_type.upper()} ({len(type_issues)}):\n"
            formatted_output += "-" * 40 + "\n"
            
            for i, issue in enumerate(type_issues, 1):
                formatted_output += f"{i}. [{issue.key}] {issue.summary}\n"
                formatted_output += f"   Status: {issue.status}\n"
                
                if issue.description:
                    desc = issue.description[:150] + "..." if len(issue.description) > 150 else issue.description
                    formatted_output += f"   Description: {desc}\n"
                formatted_output += "\n"
        
        return formatted_output
    
    def generate_context_guidance(self, issues: List[JIRAIssue], hlr: str) -> str:
        """Generate guidance prompt based on JIRA issues and HLR to improve requirement analysis"""
        
        if not issues:
            return ""
        
        # Analyze issue patterns
        issue_types = {}
        statuses = {}
        common_themes = []
        
        for issue in issues:
            # Count issue types
            issue_types[issue.issue_type] = issue_types.get(issue.issue_type, 0) + 1
            # Count statuses
            statuses[issue.status] = statuses.get(issue.status, 0) + 1
            # Extract themes from summaries
            if issue.summary:
                common_themes.append(issue.summary.lower())
        
        # Generate contextual guidance
        guidance = f"""
JIRA Project Context Analysis:
- Total Issues: {len(issues)}
- Issue Types Distribution: {dict(sorted(issue_types.items(), key=lambda x: x[1], reverse=True))}
- Status Distribution: {dict(sorted(statuses.items(), key=lambda x: x[1], reverse=True))}

Project Patterns Identified:
- Most common issue type: {max(issue_types.items(), key=lambda x: x[1])[0] if issue_types else 'N/A'}
- Primary workflow stage: {max(statuses.items(), key=lambda x: x[1])[0] if statuses else 'N/A'}

Contextual Recommendations for HLR "{hlr}":
1. Consider existing issue patterns when breaking down requirements
2. Align new stories with current project workflow and issue types
3. Leverage existing project structure and naming conventions
4. Account for current team capacity based on issue status distribution

Integration Points:
- Link generated epics/stories to related existing issues where applicable
- Maintain consistency with project's established patterns
- Consider dependencies on current in-progress items
"""
        
        return guidance

class RequirementAnalysisAgent:
    def __init__(self):
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4"
        self.temperature = 0.3
        
        # Load slicing configuration
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

Analyze the following High-Level Requirement and determine the optimal approach:

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

JSON only - no additional text:
"""
        
        try:
            response = await self._call_openai(analysis_prompt)
            result = self._parse_json_response(response)
            logger.info(f"Requirement analysis completed: {result.get('slicing_type')} approach selected")
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

Generate 5-7 specific, actionable questions that will help decompose this HLR into user stories.

Requirements:
1. Questions must be directly relevant to the HLR
2. Each question should uncover critical details for story creation
3. Questions should be specific and actionable
4. Include both functional and technical aspects
5. Consider integration points and edge cases
6. Account for JIRA project context if provided

Response format (JSON only):
{{
    "questions": [
        {{
            "question": "What specific user roles will interact with this system?",
            "context": "Understanding user types helps define personas and access patterns",
            "reasoning": "User roles directly impact story structure and acceptance criteria",
            "priority": 1,
            "required": true
        }}
    ]
}}

JSON only - no additional text:
"""
        
        try:
            response = await self._call_openai(question_prompt)
            question_data = self._parse_json_response(response)
            
            questions = []
            for i, q_data in enumerate(question_data.get('questions', [])):
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
You are a validation expert for JIRA requirement analysis.

Context:
- HLR: "{hlr}"
- Question: "{question.question}"
- User Response: "{user_response}"

Validate the response for:
1. Relevance to the question and HLR
2. Completeness and detail level
3. Clarity and specificity
4. Actionability for story creation

Response format (JSON only):
{{
    "is_valid": true|false,
    "overall_score": 0.0-1.0,
    "issues": ["list of issues found"],
    "suggestions": ["list of improvement suggestions"],
    "confidence": 0.0-1.0
}}

JSON only - no additional text:
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
            
            logger.info(f"Validation completed for question {question.id}: {'valid' if result.is_valid else 'invalid'}")
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
                    {"role": "system", "content": "You are an expert requirements analyst. Always respond with valid JSON only."},
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
            logger.error(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

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

Generate 2-4 comprehensive epics that decompose the HLR effectively.

Requirements:
1. Clear, actionable epic titles
2. Comprehensive descriptions
3. Measurable business value statements
4. Detailed acceptance criteria
5. Priority assessment
6. Story point estimates
7. Dependencies and assumptions

Response format (JSON only):
{{
    "epics": [
        {{
            "title": "User Authentication and Authorization",
            "description": "Comprehensive description covering all aspects",
            "business_value": "Clear business value with measurable impact",
            "acceptance_criteria": ["Specific criteria 1", "Specific criteria 2"],
            "priority": "High|Medium|Low",
            "estimated_story_points": 21,
            "dependencies": ["External dependencies"],
            "assumptions": ["Key assumptions"],
            "risks": ["Identified risks"]
        }}
    ]
}}

JSON only - no additional text:
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
        
        return "\n".join(context_parts) if context_parts else "No valid responses provided"
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert Epic writer. Always respond with valid JSON only."},
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
            logger.error(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

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

Requirements:
1. Standard format: "As a [user], I want [goal] so that [benefit]"
2. Clear, concise titles
3. Detailed descriptions
4. Specific acceptance criteria
5. Definition of done
6. Story point estimates (1, 2, 3, 5, 8, 13)
7. Priority assessment
8. Appropriate labels
9. Dependencies

Response format (JSON only):
{{
    "user_stories": [
        {{
            "title": "User can log in with email and password",
            "description": "As a registered user, I want to log in using email and password so that I can access my dashboard",
            "user_persona": "Registered User",
            "acceptance_criteria": [
                "Given valid credentials, when I login, then I should access dashboard",
                "Given invalid credentials, when I login, then I should see error message"
            ],
            "definition_of_done": [
                "Code implemented and tested",
                "Unit tests written and passing",
                "Code reviewed and approved"
            ],
            "story_points": 3,
            "priority": "High|Medium|Low",
            "labels": ["authentication", "frontend"],
            "dependencies": ["Database setup"],
            "epic_reference": "Related Epic Title or null"
        }}
    ]
}}

JSON only - no additional text:
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
        
        return "\n".join(context_parts) if context_parts else "No valid responses provided"
    
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
                    {"role": "system", "content": "You are an expert User Story writer. Always respond with valid JSON only."},
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
            logger.error(f"Failed to parse JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

# Interactive functions with enhanced features
def get_user_choice():
    while True:
        choice = input("\nChoose workflow:\n1. Work with existing JIRA project\n2. Create new requirement\nEnter choice (1/2): ").strip()
        if choice in ["1", "2"]:
            return "existing" if choice == "1" else "new"

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

def display_all_issues_enhanced(jira_agent: JiraIntegrationAgent, project_key: str) -> str:
    """Enhanced display of all issues using the new method"""
    print(f"\nRetrieving tasks from project {project_key}...")
    
    # Use the enhanced method to get comprehensive task information
    tasks_display = jira_agent.get_all_tasks_for_project(project_key)
    
    # Print the formatted display
    print(tasks_display)
    
    # Also get the issues for context building
    issues = jira_agent.get_issues_enhanced(project_key)
    
    # Create detailed context from all issues
    issues_detail = []
    for issue in issues:
        issues_detail.append(f"Issue: {issue.key} - {issue.summary}\nType: {issue.issue_type}\nStatus: {issue.status}\nDescription: {issue.description}")
    
    return "\n\n".join(issues_detail)

def get_persona_with_suggestion(recommended_persona: str) -> str:
    """Get persona with AI suggestion and user confirmation"""
    print(f"\nPersona Selection:")
    print("-" * 30)
    print(f"Suggested persona based on your requirement: {recommended_persona}")
    
    choice = input(f"Press 'ok' to use suggested persona '{recommended_persona}' or enter your preferred persona: ").strip()
    
    if choice.lower() in ['ok', 'okay', '']:
        print(f"Using suggested persona: {recommended_persona}")
        return recommended_persona
    else:
        custom_persona = choice if choice else recommended_persona
        print(f"Using custom persona: {custom_persona}")
        return custom_persona

def display_all_issues(issues: List[JIRAIssue]) -> str:
    """Original display method kept for backward compatibility"""
    if not issues:
        print("No issues found in this project.")
        return ""
    
    print(f"\nFound {len(issues)} issues in the project:")
    print("="*80)
    
    # Display epics first
    epics = [issue for issue in issues if issue.issue_type.lower() in ['epic']]
    if epics:
        print("\nEPICS:")
        print("-" * 40)
        for i, issue in enumerate(epics, 1):
            print(f"{i}. [{issue.key}] {issue.summary}")
            print(f"   Status: {issue.status}")
            if issue.description:
                desc = issue.description[:200] + "..." if len(issue.description) > 200 else issue.description
                print(f"   Description: {desc}")
            print()
    
    # Display user stories
    stories = [issue for issue in issues if issue.issue_type.lower() in ['story', 'user story']]
    if stories:
        print("\nUSER STORIES:")
        print("-" * 40)
        for i, issue in enumerate(stories, 1):
            print(f"{i}. [{issue.key}] {issue.summary}")
            print(f"   Status: {issue.status}")
            if issue.description:
                desc = issue.description[:200] + "..." if len(issue.description) > 200 else issue.description
                print(f"   Description: {desc}")
            print()
    
    # Display other issues
    other_issues = [issue for issue in issues if issue.issue_type.lower() not in ['epic', 'story', 'user story']]
    if other_issues:
        print("\nOTHER ISSUES:")
        print("-" * 40)
        for i, issue in enumerate(other_issues, 1):
            print(f"{i}. [{issue.key}] {issue.summary}")
            print(f"   Type: {issue.issue_type} | Status: {issue.status}")
            if issue.description:
                desc = issue.description[:150] + "..." if len(issue.description) > 150 else issue.description
                print(f"   Description: {desc}")
            print()
    
    # Create detailed context from all issues
    issues_detail = []
    for issue in issues:
        issues_detail.append(f"Issue: {issue.key} - {issue.summary}\nType: {issue.issue_type}\nStatus: {issue.status}\nDescription: {issue.description}")
    
    return "\n\n".join(issues_detail)

def get_hlr_input() -> str:
    """Get HLR input without the DONE requirement"""
    print("\nEnter your High-Level Requirement:")
    print("-" * 40)
    hlr = input().strip()
    
    # Allow multi-line input if needed
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
jira_agent = JiraIntegrationAgent()
req_agent = RequirementAnalysisAgent()

# Node functions
async def start_node(state: WorkflowState) -> WorkflowState:
    state["session_id"] = f"session_{uuid.uuid4().hex[:8]}"
    state["current_step"] = "start"
    state["workflow_type"] = get_user_choice()
    state["phase"] = AnalysisPhase.INPUT
    return state

async def jira_integration_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "jira_integration"
    
    projects = jira_agent.get_projects()
    if not projects:
        state["errors"].append("No JIRA projects found or JIRA not configured")
        return state
    
    selected_project_key = select_project(projects)
    if not selected_project_key:
        state["errors"].append("No project selected")
        return state
    
    state["selected_project"] = selected_project_key
    
    # Use enhanced method to display all issues and get detailed context
    issues_detail = display_all_issues_enhanced(jira_agent, selected_project_key)
    state["issues_detail"] = issues_detail
    
    # Get all issue keys for context
    issues = jira_agent.get_issues_enhanced(selected_project_key)
    state["selected_issues"] = [issue.key for issue in issues]
    
    # Now ask for HLR after showing all issues
    state["hlr"] = get_hlr_input()
    
    return state

async def new_requirement_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "new_requirement"
    state["hlr"] = get_hlr_input()
    return state

async def requirement_analysis_node(state: WorkflowState) -> WorkflowState:
    state["current_step"] = "requirement_analysis"
    state["phase"] = AnalysisPhase.ANALYZING
    
    if not state.get("hlr"):
        state["errors"].append("No HLR provided")
        return state
    
    # Generate JIRA guidance if working with existing project
    jira_guidance = ""
    if state.get("workflow_type") == "existing" and state.get("selected_issues"):
        # Get issues for guidance generation
        projects = jira_agent.get_projects()
        if projects:
            selected_project = state.get("selected_project")
            if selected_project:
                issues = jira_agent.get_issues_enhanced(selected_project)
                jira_guidance = jira_agent.generate_context_guidance(issues, state["hlr"])
    
    # Analyze the requirement with JIRA context
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
    skipped_questions = []
    
    for question in questions:
        print(f"\nQuestion: {question.question}")
        print(f"Context: {question.context}")
        print(f"Priority: {question.priority}/5 | Required: {'Yes' if question.required else 'No'}")
        
        response = input("Your answer (or 'skip' to skip): ").strip()
        
        if response.lower() == 'skip':
            skipped_questions.append(question.id)
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
                print("Issues found with your response:")
                for issue in validation_result.issues:
                    print(f"- {issue}")
                
                if validation_result.suggestions:
                    print("Suggestions:")
                    for suggestion in validation_result.suggestions:
                        print(f"- {suggestion}")
                
                retry = input("Would you like to provide a better answer? (y/n): ").strip().lower()
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
    
    # Initialize OpenAI client for generators
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
    
    # Display generated content with detailed view
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
            if epic.get('acceptance_criteria'):
                print(f"   Acceptance Criteria: {len(epic['acceptance_criteria'])} items")
            if epic.get('dependencies'):
                print(f"   Dependencies: {', '.join(epic['dependencies'])}")
    
    if state.get("user_stories"):
        print(f"\nGENERATED USER STORIES ({len(state['user_stories'])}):")
        print("-" * 50)
        for i, story in enumerate(state["user_stories"], 1):
            print(f"\n{i}. {story.get('title', 'Untitled Story')}")
            print(f"   Description: {story.get('description', 'No description')[:100]}...")
            print(f"   Priority: {story.get('priority', 'Not set')}")
            print(f"   Story Points: {story.get('story_points', 'Not estimated')}")
            print(f"   Persona: {story.get('user_persona', 'Not specified')}")
            
            if story.get('epic_reference'):
                print(f"   Related Epic: {story['epic_reference']}")
            
            if story.get('acceptance_criteria'):
                print(f"   Acceptance Criteria: {len(story['acceptance_criteria'])} items")
            
            if story.get('labels'):
                print(f"   Labels: {', '.join(story['labels'])}")
    
    # Feedback loop (max 3 iterations)
    while state["feedback_count"] < 3:
        satisfied = input("\nAre you satisfied with the generated content? (yes/no): ").strip().lower()
        
        if satisfied in ['yes', 'y']:
            break
        
        feedback = input("Please provide your feedback for improvements: ").strip()
        if not feedback:
            break
        
        # Simple feedback processing - regenerate with feedback context
        if feedback:
            state["feedback_history"].append(feedback)
            state["feedback_count"] += 1
            
            # Prepare context for feedback
            base_context = f"Persona: {state.get('persona', 'Business Analyst')}\n"
            base_context += f"Slicing Type: {state.get('slicing_type', 'functional')}\n"
            base_context += f"Domain: {state.get('requirement_analysis', {}).get('domain', 'general')}\n"
            
            if state.get("issues_detail"):
                base_context += f"\nJIRA Issues Context:\n{state['issues_detail']}"
            
            # Add feedback context and regenerate
            feedback_context = f"{base_context}\n\nUser Feedback: {feedback}\nPrevious Iterations: {state['feedback_count']}"
            
            # Initialize generators again
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key.startswith('"') and api_key.endswith('"'):
                api_key = api_key[1:-1]
            openai_client = OpenAI(api_key=api_key)
            
            epic_agent = EpicGeneratorAgent(openai_client)
            story_agent = UserStoryGeneratorAgent(openai_client)
            
            # Regenerate based on feedback
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
                print("-" * 50)
                for i, epic in enumerate(state["epics"], 1):
                    print(f"\n{i}. {epic.get('title', 'Untitled Epic')}")
                    print(f"   Priority: {epic.get('priority', 'Not set')}")
                    print(f"   Story Points: {epic.get('estimated_story_points', 'Not estimated')}")
                    print(f"   Business Value: {epic.get('business_value', 'Not specified')[:100]}...")
            
            if state.get("user_stories"):
                print(f"\nUPDATED USER STORIES ({len(state['user_stories'])}):")
                print("-" * 50)
                for i, story in enumerate(state["user_stories"], 1):
                    print(f"\n{i}. {story.get('title', 'Untitled Story')}")
                    print(f"   Description: {story.get('description', 'No description')[:100]}...")
                    print(f"   Priority: {story.get('priority', 'Not set')}")
                    print(f"   Story Points: {story.get('story_points', 'Not estimated')}")
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
    return "jira_integration" if state.get("workflow_type") == "existing" else "new_requirement"

def should_generate_epics(state: WorkflowState) -> str:
    return "generation"

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

# Add edges
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
    
    # Show Q&A summary
    if state.get('questions'):
        answered = len([q for q in state['questions'] if q.answered and not q.skipped])
        skipped = len([q for q in state['questions'] if q.skipped])
        total = len(state['questions'])
        print(f"\nQ&A Summary: {answered}/{total} answered, {skipped} skipped")
    
    # Show generated content
    if state.get('epics'):
        print(f"\nGenerated Epics ({len(state['epics'])}):")
        print("-" * 30)
        for i, epic in enumerate(state['epics'], 1):
            print(f"\n{i}. {epic.get('title', 'Untitled')}")
            print(f"   Priority: {epic.get('priority', 'Not set')}")
            print(f"   Story Points: {epic.get('estimated_story_points', 'Not estimated')}")
            print(f"   Business Value: {epic.get('business_value', 'Not specified')[:100]}...")
            
            if epic.get('acceptance_criteria'):
                print(f"   Acceptance Criteria: {len(epic['acceptance_criteria'])} items")
    
    if state.get('user_stories'):
        print(f"\nGenerated User Stories ({len(state['user_stories'])}):")
        print("-" * 30)
        for i, story in enumerate(state['user_stories'], 1):
            print(f"\n{i}. {story.get('title', 'Untitled')}")
            print(f"   Priority: {story.get('priority', 'Not set')}")
            print(f"   Story Points: {story.get('story_points', 'Not estimated')}")
            print(f"   Persona: {story.get('user_persona', 'Not specified')}")
            
            if story.get('epic_reference'):
                print(f"   Epic: {story['epic_reference']}")
            
            if story.get('acceptance_criteria'):
                print(f"   Acceptance Criteria: {len(story['acceptance_criteria'])} items")
    
    if state.get('errors'):
        print("\nErrors:")
        print("-" * 30)
        for error in state['errors']:
            print(f"- {error}")

def create_clean_output(state: WorkflowState) -> Dict[str, Any]:
    """Create clean output without validation scores and unnecessary metadata"""
    
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
    
    # Add JIRA context if used
    if state.get('selected_project'):
        output["jira_context"] = {
            "project": state['selected_project'],
            "analyzed_issues": len(state.get('selected_issues', [])),
            "issues_found": len(state.get('selected_issues', []))
        }
    
    # Add Q&A summary (clean format)
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
            "skipped_questions": len([q for q in state['questions'] if q.skipped]),
            "responses": qa_summary
        }
    
    # Add generated content
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
    
    # Add content statistics
    output["statistics"] = {
        "total_epics": len(state.get('epics', [])),
        "total_user_stories": len(state.get('user_stories', [])),
        "total_story_points": sum(epic.get('estimated_story_points', 0) for epic in state.get('epics', [])) + 
                            sum(story.get('story_points', 0) for story in state.get('user_stories', [])),
        "errors_count": len(state.get('errors', []))
    }
    
    # Add feedback history if any
    if state.get('feedback_history'):
        output["feedback_history"] = state['feedback_history']
    
    # Add errors if any
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
        "current_step": ""
    }
    
    try:
        final_state = await app.ainvoke(initial_state)
        display_results(final_state)
        
        # Create and save clean output
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