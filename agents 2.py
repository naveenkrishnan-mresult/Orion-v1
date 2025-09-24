import os
import json
import requests
import base64
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import re
import uuid
from enum import Enum
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AnalysisPhase(Enum):
    INPUT = "input"
    ANALYZING = "analyzing"
    QUESTIONING = "questioning"
    VALIDATING = "validating"
    GENERATING_EPICS = "generating_epics"
    GENERATING_STORIES = "generating_stories"
    FEEDBACK_PROCESSING = "feedback_processing"
    COMPLETE = "complete"
    ERROR = "error"

class GenerationType(Enum):
    EPICS_ONLY = "epics_only"
    STORIES_ONLY = "stories_only"
    BOTH = "both"

@dataclass
class Question:
    id: str
    question: str
    context: str
    reasoning: str
    priority: int
    required: bool
    validation_criteria: List[str]
    answered: bool = False
    answer: str = ""
    validation_status: str = "pending"
    validation_score: float = 0.0
    skipped: bool = False
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class ValidationResult:
    is_valid: bool
    overall_score: float
    criteria_scores: Dict[str, float]
    issues: List[str]
    suggestions: List[str]
    confidence: float
    validated_at: datetime = field(default_factory=datetime.now)

@dataclass
class Epic:
    id: str
    title: str
    description: str
    business_value: str
    acceptance_criteria: List[str]
    priority: str
    estimated_story_points: int
    dependencies: List[str]
    assumptions: List[str]
    risks: List[str]
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class UserStory:
    id: str
    epic_id: Optional[str]
    title: str
    description: str
    user_persona: str
    acceptance_criteria: List[str]
    definition_of_done: List[str]
    story_points: int
    priority: str
    labels: List[str]
    dependencies: List[str]
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class SystemState:
    session_id: str
    hlr: str
    phase: AnalysisPhase
    generation_type: Optional[GenerationType]
    slicing_type: Optional[str]
    persona: str
    questions: List[Question]
    responses: Dict[str, str]
    validation_results: Dict[str, ValidationResult]
    epics: List[Epic]
    user_stories: List[UserStory]
    feedback_history: List[str]
    feedback_count: int
    overall_confidence: float
    errors: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

@dataclass
class JIRAIssue:
    key: str
    id: str
    issue_type: str
    summary: str
    description: str
    status: str
    assignee: Optional[str]
    priority: str
    created: datetime
    updated: datetime
    story_points: Optional[int] = None
    epic_link: Optional[str] = None

@dataclass
class JIRAProject:
    key: str
    id: str
    name: str
    description: str

class JIRAIntegrationAgent:
    def __init__(self):
        # Initialize OpenAI
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found")
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        self.client = OpenAI(api_key=api_key)
        
        # JIRA setup
        self.server = None
        self.headers = None
        self.current_project = None
        self.model = "gpt-4"
        self.temperature = 0.3
        
    def setup_jira_connection(self) -> bool:
        self.server = os.getenv('JIRA_SERVER')
        email = os.getenv('JIRA_EMAIL')
        api_token = os.getenv('JIRA_API_TOKEN')
        
        if not all([self.server, email, api_token]):
            return False
            
        self.server = self.server.rstrip('/')
        auth_string = f"{email}:{api_token}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.get(f"{self.server}/rest/api/2/myself", headers=self.headers, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def get_projects(self) -> List[JIRAProject]:
        try:
            response = requests.get(f"{self.server}/rest/api/2/project", headers=self.headers)
            response.raise_for_status()
            
            projects = []
            for project_data in response.json():
                project = JIRAProject(
                    key=project_data['key'],
                    id=project_data['id'],
                    name=project_data['name'],
                    description=project_data.get('description', '')
                )
                projects.append(project)
            return projects
        except:
            return []
    
    def get_epics(self, project_key: str) -> List[JIRAIssue]:
        jql = f'project = {project_key} AND issuetype = Epic ORDER BY created DESC'
        return self._search_issues(jql)
    
    def get_user_stories(self, project_key: str, epic_key: str = None) -> List[JIRAIssue]:
        if epic_key:
            jql = f'project = {project_key} AND issuetype = Story AND "Epic Link" = {epic_key} ORDER BY created DESC'
        else:
            jql = f'project = {project_key} AND issuetype = Story ORDER BY created DESC'
        return self._search_issues(jql)
    
    def _search_issues(self, jql: str, max_results: int = 50) -> List[JIRAIssue]:
        try:
            params = {
                'jql': jql,
                'maxResults': max_results,
                'fields': 'summary,description,status,assignee,priority,created,updated,issuetype,customfield_10014,customfield_10016'
            }
            
            response = requests.get(f"{self.server}/rest/api/2/search", headers=self.headers, params=params)
            response.raise_for_status()
            
            issues = []
            for issue_data in response.json().get('issues', []):
                issue = self._parse_issue(issue_data)
                if issue:
                    issues.append(issue)
            return issues
        except:
            return []
    
    def _parse_issue(self, issue_data: Dict) -> Optional[JIRAIssue]:
        try:
            fields = issue_data['fields']
            story_points = fields.get('customfield_10014')
            if story_points and not isinstance(story_points, (int, float)):
                story_points = None
            
            epic_link = fields.get('customfield_10016')
            
            issue = JIRAIssue(
                key=issue_data['key'],
                id=issue_data['id'],
                issue_type=fields['issuetype']['name'],
                summary=fields.get('summary', ''),
                description=fields.get('description', ''),
                status=fields['status']['name'],
                assignee=fields['assignee']['displayName'] if fields.get('assignee') else None,
                priority=fields['priority']['name'] if fields.get('priority') else 'Medium',
                created=datetime.fromisoformat(fields['created'].replace('Z', '+00:00')),
                updated=datetime.fromisoformat(fields['updated'].replace('Z', '+00:00')),
                story_points=story_points,
                epic_link=epic_link
            )
            return issue
        except:
            return None
    
    def create_session(self, hlr: str, generation_type: GenerationType) -> SystemState:
        session_id = f"jira_{uuid.uuid4().hex[:8]}"
        return SystemState(
            session_id=session_id,
            hlr=hlr.strip(),
            phase=AnalysisPhase.INPUT,
            generation_type=generation_type,
            slicing_type=None,
            persona="",
            questions=[],
            responses={},
            validation_results={},
            epics=[],
            user_stories=[],
            feedback_history=[],
            feedback_count=0,
            overall_confidence=0.0,
            errors=[],
            metadata={},
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    
    async def analyze_requirement(self, state: SystemState) -> SystemState:
        state.phase = AnalysisPhase.ANALYZING
        
        prompt = f"""Analyze this requirement and respond with JSON only: "{state.hlr}"
        
        {{
          "slicing_type": "user_journey_slicing",
          "persona": "Product Manager",
          "confidence": 0.9
        }}"""
        
        try:
            response = await self._call_openai(prompt)
            data = self._parse_json_response(response)
            state.slicing_type = data.get('slicing_type')
            state.persona = data.get('persona')
            state.overall_confidence = data.get('confidence', 0.8)
            state.updated_at = datetime.now()
            return state
        except Exception as e:
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Analysis error: {str(e)}")
            raise
    
    async def generate_questions(self, state: SystemState) -> SystemState:
        state.phase = AnalysisPhase.QUESTIONING
        
        prompt = f"""Generate 3 focused questions for requirement: "{state.hlr}"
        
        {{
          "questions": [
            {{
              "question": "What are the main user actions needed?",
              "context": "Understanding user workflow",
              "reasoning": "Defines story breakdown",
              "priority": 1,
              "required": true,
              "validation_criteria": ["specific", "actionable"]
            }}
          ]
        }}"""
        
        try:
            response = await self._call_openai(prompt)
            data = self._parse_json_response(response)
            
            questions = []
            for i, q_data in enumerate(data.get('questions', [])):
                question = Question(
                    id=f"q_{state.session_id}_{i+1}",
                    question=q_data['question'],
                    context=q_data.get('context', ''),
                    reasoning=q_data.get('reasoning', ''),
                    priority=q_data.get('priority', 3),
                    required=q_data.get('required', True),
                    validation_criteria=q_data.get('validation_criteria', [])
                )
                questions.append(question)
            
            state.questions = questions
            state.updated_at = datetime.now()
            return state
        except Exception as e:
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Question generation error: {str(e)}")
            raise
    
    async def validate_response(self, state: SystemState, question_id: str, user_response: str) -> SystemState:
        question = next((q for q in state.questions if q.id == question_id), None)
        if not question:
            raise ValueError(f"Question {question_id} not found")
        
        state.phase = AnalysisPhase.VALIDATING
        
        prompt = f"""Validate this response: Q: "{question.question}" A: "{user_response}"
        
        {{
          "is_valid": true,
          "overall_score": 0.8,
          "criteria_scores": {{"relevance": 0.8, "completeness": 0.8}},
          "issues": [],
          "suggestions": [],
          "confidence": 0.8
        }}"""
        
        try:
            response = await self._call_openai(prompt)
            data = self._parse_json_response(response)
            
            validation_result = ValidationResult(
                is_valid=data['is_valid'],
                overall_score=data['overall_score'],
                criteria_scores=data['criteria_scores'],
                issues=data['issues'],
                suggestions=data['suggestions'],
                confidence=data['confidence']
            )
            
            question.answered = True
            question.answer = user_response
            question.validation_status = "valid" if validation_result.is_valid else "invalid"
            question.validation_score = validation_result.overall_score
            
            state.validation_results[question_id] = validation_result
            state.responses[question_id] = user_response
            state.updated_at = datetime.now()
            
            return state
        except Exception as e:
            state.errors.append(f"Validation error for {question_id}: {str(e)}")
            raise
    
    async def generate_epics(self, state: SystemState) -> SystemState:
        state.phase = AnalysisPhase.GENERATING_EPICS
        
        qa_context = "\n".join([f"Q: {q.question} A: {q.answer}" for q in state.questions if q.answered and not q.skipped])
        
        prompt = f"""Generate epics for: "{state.hlr}"
        Q&A: {qa_context}
        
        {{
          "epics": [
            {{
              "title": "User Management Epic",
              "description": "Handle user registration and authentication",
              "business_value": "Enable user access to system",
              "acceptance_criteria": ["Users can register", "Users can login"],
              "priority": "High",
              "estimated_story_points": 13,
              "dependencies": ["Database setup"],
              "assumptions": ["Email service available"],
              "risks": ["Security vulnerabilities"]
            }}
          ]
        }}"""
        
        try:
            response = await self._call_openai(prompt)
            data = self._parse_json_response(response)
            
            epics = []
            for i, epic_info in enumerate(data.get('epics', [])):
                epic = Epic(
                    id=f"epic_{state.session_id}_{i+1}",
                    title=epic_info['title'],
                    description=epic_info['description'],
                    business_value=epic_info['business_value'],
                    acceptance_criteria=epic_info['acceptance_criteria'],
                    priority=epic_info['priority'],
                    estimated_story_points=epic_info['estimated_story_points'],
                    dependencies=epic_info['dependencies'],
                    assumptions=epic_info['assumptions'],
                    risks=epic_info['risks']
                )
                epics.append(epic)
            
            state.epics = epics
            state.updated_at = datetime.now()
            return state
        except Exception as e:
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Epic generation error: {str(e)}")
            raise
    
    async def generate_user_stories(self, state: SystemState) -> SystemState:
        state.phase = AnalysisPhase.GENERATING_STORIES
        
        qa_context = "\n".join([f"Q: {q.question} A: {q.answer}" for q in state.questions if q.answered and not q.skipped])
        
        prompt = f"""Generate user stories for: "{state.hlr}"
        Q&A: {qa_context}
        
        {{
          "user_stories": [
            {{
              "epic_id": "epic_1",
              "title": "User can register account",
              "description": "As a new user, I want to register an account so that I can access the system",
              "user_persona": "New User",
              "acceptance_criteria": ["Valid email required", "Password validation"],
              "definition_of_done": ["Code tested", "UI implemented"],
              "story_points": 3,
              "priority": "High",
              "labels": ["frontend", "backend"],
              "dependencies": ["Database schema"]
            }}
          ]
        }}"""
        
        try:
            response = await self._call_openai(prompt)
            data = self._parse_json_response(response)
            
            user_stories = []
            for i, story_info in enumerate(data.get('user_stories', [])):
                user_story = UserStory(
                    id=f"story_{state.session_id}_{i+1}",
                    epic_id=story_info.get('epic_id'),
                    title=story_info['title'],
                    description=story_info['description'],
                    user_persona=story_info['user_persona'],
                    acceptance_criteria=story_info['acceptance_criteria'],
                    definition_of_done=story_info['definition_of_done'],
                    story_points=story_info['story_points'],
                    priority=story_info['priority'],
                    labels=story_info['labels'],
                    dependencies=story_info['dependencies']
                )
                user_stories.append(user_story)
            
            state.user_stories = user_stories
            state.updated_at = datetime.now()
            return state
        except Exception as e:
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"User story generation error: {str(e)}")
            raise
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a requirements analyst. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=2000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}")
    
    def create_epic_in_jira(self, project_key: str, epic: Epic) -> Optional[str]:
        if not self.headers:
            return None
        
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "summary": epic.title,
                "description": epic.description,
                "issuetype": {"name": "Epic"},
                "priority": {"name": epic.priority}
            }
        }
        
        try:
            response = requests.post(f"{self.server}/rest/api/2/issue", headers=self.headers, json=issue_data)
            response.raise_for_status()
            return response.json()['key']
        except:
            return None
    
    def create_story_in_jira(self, project_key: str, story: UserStory, epic_key: str = None) -> Optional[str]:
        if not self.headers:
            return None
        
        issue_data = {
            "fields": {
                "project": {"key": project_key},
                "summary": story.title,
                "description": story.description,
                "issuetype": {"name": "Story"},
                "priority": {"name": story.priority}
            }
        }
        
        if epic_key:
            issue_data["fields"]["customfield_10016"] = epic_key
        if story.story_points:
            issue_data["fields"]["customfield_10014"] = story.story_points
        
        try:
            response = requests.post(f"{self.server}/rest/api/2/issue", headers=self.headers, json=issue_data)
            response.raise_for_status()
            return response.json()['key']
        except:
            return None

async def main():
    agent = JIRAIntegrationAgent()
    
    # Choice: new or existing
    choice = input("1. New requirement 2. From JIRA: ")
    
    hlr = ""
    if choice == "2":
        if agent.setup_jira_connection():
            projects = agent.get_projects()
            if projects:
                for i, p in enumerate(projects[:5], 1):
                    print(f"{i}. {p.key} - {p.name}")
                
                proj_choice = input("Project number: ")
                try:
                    project = projects[int(proj_choice) - 1]
                    agent.current_project = project
                    
                    epics = agent.get_epics(project.key)
                    stories = agent.get_user_stories(project.key)
                    
                    all_issues = []
                    if epics:
                        print("Epics:")
                        for i, e in enumerate(epics[:5], 1):
                            print(f"{i}. {e.key} - {e.summary}")
                        all_issues.extend(epics)
                    
                    if stories:
                        print("Stories:")
                        for i, s in enumerate(stories[:5], len(epics) + 1):
                            print(f"{i}. {s.key} - {s.summary}")
                        all_issues.extend(stories)
                    
                    selected = input("Select numbers (1,2,3): ")
                    indices = [int(x.strip()) - 1 for x in selected.split(',')]
                    selected_issues = [all_issues[i] for i in indices if 0 <= i < len(all_issues)]
                    
                    hlr = " ".join([f"{issue.summary}: {issue.description}" for issue in selected_issues])
                except:
                    pass
        else:
            print("JIRA connection failed")
    
    if not hlr:
        hlr = input("Enter HLR: ")
    
    # Generation type
    gen_type = input("1. Epics 2. Stories 3. Both: ")
    generation_type = {
        "1": GenerationType.EPICS_ONLY,
        "2": GenerationType.STORIES_ONLY,
        "3": GenerationType.BOTH
    }.get(gen_type, GenerationType.BOTH)
    
    # Process
    state = agent.create_session(hlr, generation_type)
    state = await agent.analyze_requirement(state)
    state = await agent.generate_questions(state)
    
    # Quick Q&A
    for question in state.questions:
        answer = input(f"{question.question}: ")
        if answer:
            await agent.validate_response(state, question.id, answer)
    
    # Generate content
    if generation_type in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
        state = await agent.generate_epics(state)
    if generation_type in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
        state = await agent.generate_user_stories(state)
    
    # Results
    if state.epics:
        print(f"Generated {len(state.epics)} epics:")
        for epic in state.epics:
            print(f"- {epic.title}")
    
    if state.user_stories:
        print(f"Generated {len(state.user_stories)} user stories:")
        for story in state.user_stories:
            print(f"- {story.title}")
    
    # Publish to JIRA
    if agent.current_project and (state.epics or state.user_stories):
        publish = input("Publish to JIRA? (y/n): ")
        if publish.lower() == 'y':
            created_epics = []
            for epic in state.epics:
                epic_key = agent.create_epic_in_jira(agent.current_project.key, epic)
                if epic_key:
                    created_epics.append(epic_key)
                    print(f"Created epic: {epic_key}")
            
            for i, story in enumerate(state.user_stories):
                epic_key = created_epics[i % len(created_epics)] if created_epics else None
                story_key = agent.create_story_in_jira(agent.current_project.key, story, epic_key)
                if story_key:
                    print(f"Created story: {story_key}")
        else:
            print("JIRA connection failed. Check environment variables.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())