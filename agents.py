import os
import json
import re
import uuid
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, asdict, field
from enum import Enum
from openai import OpenAI
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('jira_agent_system.log'),
        logging.StreamHandler()
    ]
)
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
class FeedbackResult:
    is_valid: bool
    processed_feedback: str
    reasoning: str
    confidence: float
    timestamp: datetime = field(default_factory=datetime.now)

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

class RequirementAnalysisAgent:
    def __init__(self, config_path: str = "slicing_config.json"):
        logger.info("Initializing Requirement Analysis Agent")
        
        # Load OpenAI API key
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        # Remove quotes if present
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        
        # Initialize OpenAI client
        self.client = OpenAI(api_key=api_key)
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Model configuration
        self.model = "gpt-4"
        self.temperature = 0.3
        
        logger.info("Requirement Analysis Agent initialized successfully")
        
    def _load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Configuration file {config_path} not found")
            raise FileNotFoundError(f"Configuration file {config_path} not found")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in configuration file: {e}")
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    async def analyze_requirement(self, state: SystemState) -> SystemState:
        logger.info(f"Analyzing requirement for session {state.session_id}")
        state.phase = AnalysisPhase.ANALYZING
        
        analysis_prompt = self._build_analysis_prompt(state.hlr)
        
        try:
            response = await self._call_openai(analysis_prompt)
            analysis_result = self._parse_json_response(response)
            
            state.slicing_type = analysis_result.get('slicing_type')
            state.persona = analysis_result.get('persona')
            state.metadata.update(analysis_result.get('metadata', {}))
            state.updated_at = datetime.now()
            
            logger.info(f"Analysis completed: slicing_type={state.slicing_type}, persona={state.persona}")
            return state
            
        except Exception as e:
            logger.error(f"Analysis error: {str(e)}")
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Analysis error: {str(e)}")
            raise
    
    async def generate_questions(self, state: SystemState) -> SystemState:
        logger.info(f"Generating questions for session {state.session_id}")
        state.phase = AnalysisPhase.QUESTIONING
        
        slicing_config = self.config['slicing_types'][state.slicing_type]
        question_prompt = self._build_question_generation_prompt(state.hlr, slicing_config, state.persona)
        
        try:
            response = await self._call_openai(question_prompt)
            questions_data = self._parse_json_response(response)
            
            questions = []
            for i, q_data in enumerate(questions_data.get('questions', [])):
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
            
            logger.info(f"Generated {len(questions)} questions")
            return state
            
        except Exception as e:
            logger.error(f"Question generation error: {str(e)}")
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Question generation error: {str(e)}")
            raise
    
    async def validate_response(self, state: SystemState, question_id: str, user_response: str) -> SystemState:
        question = next((q for q in state.questions if q.id == question_id), None)
        if not question:
            raise ValueError(f"Question {question_id} not found")
        
        state.phase = AnalysisPhase.VALIDATING
        
        validation_prompt = self._build_validation_prompt(state.hlr, question, user_response, state.persona)
        
        try:
            response = await self._call_openai(validation_prompt)
            validation_data = self._parse_json_response(response)
            
            validation_result = ValidationResult(
                is_valid=validation_data['is_valid'],
                overall_score=validation_data['overall_score'],
                criteria_scores=validation_data['criteria_scores'],
                issues=validation_data['issues'],
                suggestions=validation_data['suggestions'],
                confidence=validation_data['confidence']
            )
            
            # Update question status
            question.answered = True
            question.answer = user_response
            question.validation_status = "valid" if validation_result.is_valid else "invalid"
            question.validation_score = validation_result.overall_score
            
            # Store validation result
            state.validation_results[question_id] = validation_result
            state.responses[question_id] = user_response
            state.updated_at = datetime.now()
            
            logger.info(f"Validation completed for question {question_id}: {'valid' if validation_result.is_valid else 'invalid'}")
            return state
            
        except Exception as e:
            logger.error(f"Validation error for {question_id}: {str(e)}")
            state.errors.append(f"Validation error for {question_id}: {str(e)}")
            raise
    
    def _build_analysis_prompt(self, hlr: str) -> str:
        slicing_options = json.dumps(self.config['slicing_types'], indent=2)
        
        return f"""
You are an expert Business Analyst and Requirements Engineer specializing in JIRA story decomposition.

TASK: Analyze the following High-Level Requirement (HLR) and determine the optimal slicing approach.

HLR: "{hlr}"

AVAILABLE SLICING TYPES:
{slicing_options}

INSTRUCTIONS:
1. Analyze the HLR to understand its core functionality, data requirements, security implications, UI needs, and testing considerations
2. Determine which slicing type would be most effective for breaking down this requirement
3. Select the most appropriate persona from the chosen slicing type
4. Provide reasoning for your choices
5. Identify key complexity factors and potential challenges

RESPONSE FORMAT (JSON only):
{{
  "slicing_type": "selected_slicing_type_key",
  "persona": "selected_persona",
  "confidence": 0.95,
  "reasoning": {{
    "slicing_rationale": "Why this slicing type is optimal",
    "persona_rationale": "Why this persona is most suitable",
    "complexity_factors": ["factor1", "factor2"],
    "potential_challenges": ["challenge1", "challenge2"]
  }},
  "metadata": {{
    "primary_domain": "domain_name",
    "estimated_story_count": 5,
    "priority_areas": ["area1", "area2"]
  }}
}}

Respond only with valid JSON. No additional text or formatting.
"""
    
    def _build_question_generation_prompt(self, hlr: str, slicing_config: Dict, persona: str) -> str:
        return f"""
You are an expert {persona} analyzing requirements for JIRA story creation.

CONTEXT:
- HLR: "{hlr}"
- Slicing Type: {slicing_config['name']}
- Your Role: {persona}
- Focus Areas: {slicing_config['focus_areas']}

SLICING DESCRIPTION:
{slicing_config['description']}

SLICING CRITERIA:
{chr(10).join(slicing_config['criteria'])}

TASK: Generate 5-8 highly specific, insightful questions that will help decompose this HLR into actionable user stories from your persona's perspective.

REQUIREMENTS:
1. Questions must be directly relevant to the HLR and slicing approach
2. Each question should uncover critical details needed for story creation
3. Questions should be open-ended but focused
4. Include both functional and non-functional aspects
5. Consider edge cases and integration points
6. Prioritize questions by importance (1=highest, 5=lowest)

RESPONSE FORMAT (JSON only):
{{
  "questions": [
    {{
      "question": "What specific data entities need to be processed in this chatbot interaction?",
      "context": "Understanding data requirements for proper story decomposition",
      "reasoning": "Data entities directly impact storage, processing, and retrieval stories",
      "priority": 1,
      "required": true,
      "validation_criteria": ["must_be_specific", "must_relate_to_hlr", "must_be_actionable"]
    }}
  ],
  "total_questions": 6,
  "estimated_story_complexity": "medium"
}}

Generate questions that only an expert {persona} would ask. Be specific to the domain and slicing approach.
Respond only with valid JSON.
"""
    
    def _build_validation_prompt(self, hlr: str, question: Question, user_response: str, persona: str) -> str:
        validation_criteria = self.config.get('validation_criteria', {})
        
        return f"""
You are an expert validator analyzing user responses for JIRA requirement decomposition.

CONTEXT:
- Original HLR: "{hlr}"
- Question: "{question.question}"
- Question Context: "{question.context}"
- User Response: "{user_response}"
- Persona: {persona}

VALIDATION CRITERIA:
{json.dumps(validation_criteria, indent=2)}

TASK: Validate the user response against the question and overall HLR context.

VALIDATION CHECKS:
1. Relevance: Does the response directly address the question and relate to the HLR?
2. Completeness: Is the response sufficiently detailed and comprehensive?
3. Clarity: Is the response clear, understandable, and well-structured?
4. Consistency: Does it align with other responses and the overall requirement?
5. Feasibility: Are the described elements technically and practically feasible?
6. Specificity: Is the response specific enough to be actionable?

ADDITIONAL CHECKS:
- Detect gibberish or nonsensical content
- Check for vague or generic responses
- Verify technical accuracy where applicable
- Assess business value alignment

RESPONSE FORMAT (JSON only):
{{
  "is_valid": true,
  "overall_score": 0.85,
  "criteria_scores": {{
    "relevance": 0.9,
    "completeness": 0.8,
    "clarity": 0.85,
    "consistency": 0.85,
    "feasibility": 0.9,
    "specificity": 0.8
  }},
  "issues": ["Issue description if any"],
  "suggestions": ["Suggestion for improvement"],
  "confidence": 0.92,
  "analysis": {{
    "strengths": ["What was good about the response"],
    "weaknesses": ["Areas for improvement"],
    "gibberish_detected": false,
    "technical_accuracy": "high"
  }}
}}

Be strict in validation. A response should only be marked valid if it genuinely helps with story decomposition.
Respond only with valid JSON.
"""
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert requirements analyst. Always respond with valid JSON only."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=2000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            # Clean response (remove markdown if present)
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
    
    async def generate_epics(self, state: SystemState) -> SystemState:
        logger.info(f"Generating epics for session {state.session_id}")
        state.phase = AnalysisPhase.GENERATING_EPICS
        
        # Prepare context from Q&A
        qa_context = self._build_qa_context(state)
        
        epic_prompt = f"""
You are an expert Epic writer for JIRA. Generate comprehensive epics based on the analyzed requirement.

CONTEXT:
- HLR: "{state.hlr}"
- Slicing Type: {state.slicing_type}
- Persona: {state.persona}
- Analysis Confidence: {state.overall_confidence}

Q&A CONTEXT:
{qa_context}

TASK: Generate 2-4 well-structured epics that decompose the HLR effectively.

EPIC REQUIREMENTS:
1. Clear, actionable epic titles
2. Comprehensive descriptions with business context
3. Measurable business value statements
4. Detailed acceptance criteria
5. Priority assessment (Critical, High, Medium, Low)
6. Story point estimates
7. Dependencies identification
8. Risk assessment
9. Key assumptions

RESPONSE FORMAT (JSON only):
{{
  "epics": [
    {{
      "title": "User Authentication and Authorization Epic",
      "description": "Comprehensive description of the epic covering all aspects",
      "business_value": "Clear business value statement with metrics",
      "acceptance_criteria": [
        "Specific, measurable criteria 1",
        "Specific, measurable criteria 2"
      ],
      "priority": "High",
      "estimated_story_points": 21,
      "dependencies": ["External service integration", "Database schema"],
      "assumptions": ["API availability", "User base size"],
      "risks": ["Performance bottlenecks", "Security vulnerabilities"]
    }}
  ],
  "total_epics": 3,
  "epic_relationships": {{
    "sequential": ["epic1", "epic2"],
    "parallel": ["epic3", "epic4"]
  }}
}}

Ensure epics are comprehensive, actionable, and directly derived from the HLR and Q&A context.
Respond only with valid JSON.
"""
        
        try:
            response = await self._call_openai(epic_prompt)
            epic_data = self._parse_json_response(response)
            
            epics = []
            for i, epic_info in enumerate(epic_data.get('epics', [])):
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
            state.metadata['epic_relationships'] = epic_data.get('epic_relationships', {})
            state.updated_at = datetime.now()
            
            logger.info(f"Generated {len(epics)} epics successfully")
            return state
            
        except Exception as e:
            logger.error(f"Epic generation error: {str(e)}")
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"Epic generation error: {str(e)}")
            raise
    
    def _build_qa_context(self, state: SystemState) -> str:
        context_parts = []
        for question in state.questions:
            if question.answered and not question.skipped:
                context_parts.append(f"Q: {question.question}\nA: {question.answer}\nValidation Score: {question.validation_score}")
            elif question.skipped:
                context_parts.append(f"Q: {question.question}\nA: [SKIPPED]")
        return "\n\n".join(context_parts)
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert Epic writer for JIRA. Always respond with valid JSON only."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=3000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error in Epic Generator: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Epic JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

class UserStoryGeneratorAgent:
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        self.model = "gpt-4"
        self.temperature = 0.3
        logger.info("User Story Generator Agent initialized")
    
    async def generate_user_stories(self, state: SystemState) -> SystemState:
        logger.info(f"Generating user stories for session {state.session_id}")
        state.phase = AnalysisPhase.GENERATING_STORIES
        
        # Prepare context from Q&A and epics if available
        qa_context = self._build_qa_context(state)
        epic_context = self._build_epic_context(state)
        
        story_prompt = f"""
You are an expert User Story writer for JIRA. Generate comprehensive user stories based on the analyzed requirement.

CONTEXT:
- HLR: "{state.hlr}"
- Slicing Type: {state.slicing_type}
- Persona: {state.persona}
- Analysis Confidence: {state.overall_confidence}

Q&A CONTEXT:
{qa_context}

EPIC CONTEXT:
{epic_context}

TASK: Generate 5-12 well-structured user stories that implement the HLR effectively.

USER STORY REQUIREMENTS:
1. Follow standard format: "As a [user], I want [goal] so that [benefit]"
2. Clear, concise titles
3. Detailed descriptions with context
4. Specific acceptance criteria
5. Definition of done
6. Story point estimates (1, 2, 3, 5, 8, 13)
7. Priority assessment
8. Appropriate labels
9. Dependencies identification
10. Link to relevant epics if available

RESPONSE FORMAT (JSON only):
{{
  "user_stories": [
    {{
      "epic_id": "epic_session_id_1",
      "title": "User can log in with email and password",
      "description": "As a registered user, I want to log in using my email and password so that I can access my personalized dashboard",
      "user_persona": "Registered User",
      "acceptance_criteria": [
        "Given a valid email and password, when I click login, then I should be redirected to dashboard",
        "Given invalid credentials, when I click login, then I should see error message"
      ],
      "definition_of_done": [
        "Code implemented and tested",
        "Unit tests written and passing",
        "Integration tests completed",
        "Code reviewed and approved"
      ],
      "story_points": 3,
      "priority": "High",
      "labels": ["authentication", "frontend", "backend"],
      "dependencies": ["Database setup", "API endpoint creation"]
    }}
  ],
  "total_stories": 8,
  "story_mapping": {{
    "by_epic": {{
      "epic_1": ["story_1", "story_2"],
      "epic_2": ["story_3", "story_4"]
    }},
    "by_priority": {{
      "critical": 2,
      "high": 4,
      "medium": 2
    }}
  }}
}}

Ensure stories are independent, valuable, estimable, small, and testable (INVEST principles).
Respond only with valid JSON.
"""
        
        try:
            response = await self._call_openai(story_prompt)
            story_data = self._parse_json_response(response)
            
            user_stories = []
            for i, story_info in enumerate(story_data.get('user_stories', [])):
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
            state.metadata['story_mapping'] = story_data.get('story_mapping', {})
            state.updated_at = datetime.now()
            
            logger.info(f"Generated {len(user_stories)} user stories successfully")
            return state
            
        except Exception as e:
            logger.error(f"User story generation error: {str(e)}")
            state.phase = AnalysisPhase.ERROR
            state.errors.append(f"User story generation error: {str(e)}")
            raise
    
    def _build_qa_context(self, state: SystemState) -> str:
        context_parts = []
        for question in state.questions:
            if question.answered and not question.skipped:
                context_parts.append(f"Q: {question.question}\nA: {question.answer}")
            elif question.skipped:
                context_parts.append(f"Q: {question.question}\nA: [SKIPPED]")
        return "\n\n".join(context_parts)
    
    def _build_epic_context(self, state: SystemState) -> str:
        if not state.epics:
            return "No epics available"
        
        context_parts = []
        for epic in state.epics:
            context_parts.append(f"Epic: {epic.title}\nDescription: {epic.description}")
        return "\n\n".join(context_parts)
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert User Story writer for JIRA. Always respond with valid JSON only."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=4000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error in User Story Generator: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse User Story JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

class FeedbackAgent:
    def __init__(self, openai_client: OpenAI):
        self.client = openai_client
        self.model = "gpt-4"
        self.temperature = 0.3
        logger.info("Feedback Agent initialized")
    
    async def validate_feedback(self, state: SystemState, feedback: str) -> FeedbackResult:
        logger.info(f"Validating feedback for session {state.session_id}")
        
        validation_prompt = f"""
You are an expert feedback validator for JIRA story generation systems.

CONTEXT:
- HLR: "{state.hlr}"
- Current Epics Count: {len(state.epics)}
- Current Stories Count: {len(state.user_stories)}
- Feedback: "{feedback}"

TASK: Validate if the feedback is constructive and actionable for improving epics/user stories.

VALIDATION CRITERIA:
1. Specificity: Is the feedback specific about what needs to be changed?
2. Actionability: Can the feedback be implemented in the generated content?
3. Relevance: Is the feedback relevant to the HLR and generated content?
4. Constructiveness: Is the feedback constructive rather than purely critical?
5. Clarity: Is the feedback clear and understandable?

INVALID FEEDBACK EXAMPLES:
- Gibberish or nonsensical text
- Overly vague comments like "make it better"
- Feedback unrelated to the HLR or generated content
- Abusive or inappropriate language

RESPONSE FORMAT (JSON only):
{{
  "is_valid": true,
  "processed_feedback": "Clear, specific improvements needed in user authentication epic",
  "reasoning": "Feedback is specific, actionable, and directly relevant to the generated content",
  "confidence": 0.95,
  "suggested_improvements": [
    "Add specific details about authentication methods",
    "Include error handling scenarios"
  ]
}}

Respond only with valid JSON.
"""
        
        try:
            response = await self._call_openai(validation_prompt)
            feedback_data = self._parse_json_response(response)
            
            result = FeedbackResult(
                is_valid=feedback_data['is_valid'],
                processed_feedback=feedback_data['processed_feedback'],
                reasoning=feedback_data['reasoning'],
                confidence=feedback_data['confidence']
            )
            
            logger.info(f"Feedback validation completed: {'valid' if result.is_valid else 'invalid'}")
            return result
            
        except Exception as e:
            logger.error(f"Feedback validation error: {str(e)}")
            raise Exception(f"Feedback validation error: {str(e)}")
    
    async def apply_feedback(self, state: SystemState, feedback: str) -> SystemState:
        logger.info(f"Applying feedback for session {state.session_id}")
        state.phase = AnalysisPhase.FEEDBACK_PROCESSING
        
        # Determine what needs to be updated based on generation type
        current_content = self._prepare_current_content(state)
        
        feedback_prompt = f"""
You are an expert content editor for JIRA epics and user stories.

CONTEXT:
- HLR: "{state.hlr}"
- Generation Type: {state.generation_type.value if state.generation_type else "unknown"}
- Feedback: "{feedback}"

CURRENT CONTENT:
{current_content}

TASK: Apply the feedback to improve the generated content while maintaining structure and quality.

REQUIREMENTS:
1. Maintain the same JSON structure as the original content
2. Apply feedback improvements where relevant
3. Preserve good aspects of the original content
4. Ensure all generated content still aligns with the HLR
5. Keep acceptance criteria specific and testable
6. Maintain proper story point estimates and priorities

RESPONSE FORMAT: Return the improved content in the same JSON structure as provided.

Apply the feedback thoughtfully and respond only with valid JSON.
"""
        
        try:
            response = await self._call_openai(feedback_prompt)
            updated_data = self._parse_json_response(response)
            
            # Update state based on generation type
            if state.generation_type in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
                if 'epics' in updated_data:
                    state.epics = self._rebuild_epics(updated_data['epics'], state.session_id)
            
            if state.generation_type in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
                if 'user_stories' in updated_data:
                    state.user_stories = self._rebuild_user_stories(updated_data['user_stories'], state.session_id)
            
            state.feedback_history.append(feedback)
            state.feedback_count += 1
            state.updated_at = datetime.now()
            
            logger.info(f"Feedback applied successfully, feedback count: {state.feedback_count}")
            return state
            
        except Exception as e:
            logger.error(f"Feedback application error: {str(e)}")
            state.errors.append(f"Feedback application error: {str(e)}")
            raise
    
    def _prepare_current_content(self, state: SystemState) -> str:
        content_parts = []
        
        if state.epics:
            epics_data = {
                "epics": [
                    {
                        "title": epic.title,
                        "description": epic.description,
                        "business_value": epic.business_value,
                        "acceptance_criteria": epic.acceptance_criteria,
                        "priority": epic.priority,
                        "estimated_story_points": epic.estimated_story_points,
                        "dependencies": epic.dependencies,
                        "assumptions": epic.assumptions,
                        "risks": epic.risks
                    } for epic in state.epics
                ]
            }
            content_parts.append(f"EPICS:\n{json.dumps(epics_data, indent=2)}")
        
        if state.user_stories:
            stories_data = {
                "user_stories": [
                    {
                        "title": story.title,
                        "description": story.description,
                        "user_persona": story.user_persona,
                        "acceptance_criteria": story.acceptance_criteria,
                        "definition_of_done": story.definition_of_done,
                        "story_points": story.story_points,
                        "priority": story.priority,
                        "labels": story.labels,
                        "dependencies": story.dependencies
                    } for story in state.user_stories
                ]
            }
            content_parts.append(f"USER STORIES:\n{json.dumps(stories_data, indent=2)}")
        
        return "\n\n".join(content_parts)
    
    def _rebuild_epics(self, epics_data: List[Dict], session_id: str) -> List[Epic]:
        epics = []
        for i, epic_info in enumerate(epics_data):
            epic = Epic(
                id=f"epic_{session_id}_{i+1}",
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
        return epics
    
    def _rebuild_user_stories(self, stories_data: List[Dict], session_id: str) -> List[UserStory]:
        user_stories = []
        for i, story_info in enumerate(stories_data):
            user_story = UserStory(
                id=f"story_{session_id}_{i+1}",
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
        return user_stories
    
    async def _call_openai(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert content editor for JIRA epics and user stories. Always respond with valid JSON only."
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                max_tokens=4000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API error in Feedback Agent: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        try:
            cleaned_response = re.sub(r'```json\n?|\n?```', '', response.strip())
            return json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Feedback JSON response: {e}")
            raise ValueError(f"Failed to parse JSON response: {e}")

class JIRAAgentSystem:
    def __init__(self, config_path: str = "slicing_config.json"):
        logger.info("Initializing JIRA Agent System")
        
        # Initialize OpenAI client
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        if api_key.startswith('"') and api_key.endswith('"'):
            api_key = api_key[1:-1]
        
        self.openai_client = OpenAI(api_key=api_key)
        
        # Initialize agents
        self.requirement_agent = RequirementAnalysisAgent(config_path)
        self.epic_agent = EpicGeneratorAgent(self.openai_client)
        self.story_agent = UserStoryGeneratorAgent(self.openai_client)
        self.feedback_agent = FeedbackAgent(self.openai_client)
        
        # Initialize state graph
        self.workflow = self._build_workflow()
        
        logger.info("JIRA Agent System initialized successfully")
    
    def _build_workflow(self) -> CompiledStateGraph:
        workflow = StateGraph(SystemState)
        
        # Add nodes
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("question", self._question_node)
        workflow.add_node("generate", self._generate_node)
        workflow.add_node("feedback", self._feedback_node)
        workflow.add_node("complete", self._complete_node)
        
        # Add edges
        workflow.set_entry_point("analyze")
        workflow.add_edge("analyze", "question")
        workflow.add_edge("question", "generate")
        workflow.add_edge("generate", "feedback")
        workflow.add_edge("feedback", "complete")
        workflow.add_edge("complete", END)
        
        return workflow.compile()
    
    async def _analyze_node(self, state: SystemState) -> SystemState:
        return await self.requirement_agent.analyze_requirement(state)
    
    async def _question_node(self, state: SystemState) -> SystemState:
        return await self.requirement_agent.generate_questions(state)
    
    async def _generate_node(self, state: SystemState) -> SystemState:
        if state.generation_type in [GenerationType.EPICS_ONLY, GenerationType.BOTH]:
            state = await self.epic_agent.generate_epics(state)
        
        if state.generation_type in [GenerationType.STORIES_ONLY, GenerationType.BOTH]:
            state = await self.story_agent.generate_user_stories(state)
        
        return state
    
    async def _feedback_node(self, state: SystemState) -> SystemState:
        # This node is called when feedback processing is needed
        return state
    
    async def _complete_node(self, state: SystemState) -> SystemState:
        state.phase = AnalysisPhase.COMPLETE
        return state
    
    def create_session(self, hlr: str, generation_type: GenerationType) -> SystemState:
        session_id = f"jira_{uuid.uuid4().hex[:8]}"
        
        state = SystemState(
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
        
        logger.info(f"Session created: {session_id} with generation type: {generation_type.value}")
        return state
    
    async def process_qa_session(self, state: SystemState, qa_responses: Dict[str, str], skipped_questions: List[str] = None) -> SystemState:
        logger.info(f"Processing Q&A session for {state.session_id}")
        
        if skipped_questions is None:
            skipped_questions = []
        
        # Mark skipped questions
        for question in state.questions:
            if question.id in skipped_questions:
                question.skipped = True
                question.answered = True
                question.answer = "[SKIPPED]"
                logger.info(f"Question {question.id} marked as skipped")
        
        # Process answered questions
        for question_id, response in qa_responses.items():
            if question_id not in skipped_questions and response.strip():
                try:
                    state = await self.requirement_agent.validate_response(state, question_id, response)
                except Exception as e:
                    logger.error(f"Error validating question {question_id}: {str(e)}")
                    state.errors.append(f"Validation error for {question_id}: {str(e)}")
        
        # Calculate overall confidence
        valid_scores = [
            vr.overall_score for vr in state.validation_results.values() 
            if vr.is_valid
        ]
        if valid_scores:
            state.overall_confidence = sum(valid_scores) / len(valid_scores)
        else:
            state.overall_confidence = 0.0
        
        logger.info(f"Q&A processing completed with confidence: {state.overall_confidence}")
        return state
    
    async def generate_content(self, state: SystemState) -> SystemState:
        logger.info(f"Generating content for session {state.session_id}")
        return await self._generate_node(state)
    
    async def process_feedback(self, state: SystemState, feedback: str) -> Tuple[SystemState, bool]:
        logger.info(f"Processing feedback for session {state.session_id}")
        
        if state.feedback_count >= 3:
            logger.warning(f"Maximum feedback limit reached for session {state.session_id}")
            return state, False
        
        # Validate feedback
        feedback_result = await self.feedback_agent.validate_feedback(state, feedback)
        
        if not feedback_result.is_valid:
            logger.info(f"Feedback invalid: {feedback_result.reasoning}")
            return state, False
        
        # Apply feedback
        state = await self.feedback_agent.apply_feedback(state, feedback)
        return state, True
    
    def export_final_output(self, state: SystemState) -> Dict[str, Any]:
        logger.info(f"Exporting final output for session {state.session_id}")
        
        output = {
            "session_metadata": {
                "session_id": state.session_id,
                "created_at": state.created_at.isoformat(),
                "completed_at": datetime.now().isoformat(),
                "generation_type": state.generation_type.value if state.generation_type else None,
                "slicing_type": state.slicing_type,
                "persona": state.persona,
                "overall_confidence": state.overall_confidence,
                "feedback_iterations": state.feedback_count
            },
            "original_requirement": {
                "hlr": state.hlr,
                "analysis_metadata": state.metadata
            },
            "qa_session": {
                "questions": [
                    {
                        "id": q.id,
                        "question": q.question,
                        "context": q.context,
                        "priority": q.priority,
                        "required": q.required,
                        "answered": q.answered,
                        "skipped": q.skipped,
                        "answer": q.answer if not q.skipped else "[SKIPPED]",
                        "validation_score": q.validation_score,
                        "validation_status": q.validation_status
                    }
                    for q in state.questions
                ],
                "validation_summary": {
                    "total_questions": len(state.questions),
                    "answered_questions": len([q for q in state.questions if q.answered and not q.skipped]),
                    "skipped_questions": len([q for q in state.questions if q.skipped]),
                    "valid_responses": len([vr for vr in state.validation_results.values() if vr.is_valid]),
                    "average_validation_score": state.overall_confidence
                }
            },
            "generated_content": {},
            "feedback_history": state.feedback_history,
            "processing_errors": state.errors
        }
        
        # Add epics if generated
        if state.epics:
            output["generated_content"]["epics"] = [
                {
                    "id": epic.id,
                    "title": epic.title,
                    "description": epic.description,
                    "business_value": epic.business_value,
                    "acceptance_criteria": epic.acceptance_criteria,
                    "priority": epic.priority,
                    "estimated_story_points": epic.estimated_story_points,
                    "dependencies": epic.dependencies,
                    "assumptions": epic.assumptions,
                    "risks": epic.risks,
                    "created_at": epic.created_at.isoformat()
                }
                for epic in state.epics
            ]
        
        # Add user stories if generated
        if state.user_stories:
            output["generated_content"]["user_stories"] = [
                {
                    "id": story.id,
                    "epic_id": story.epic_id,
                    "title": story.title,
                    "description": story.description,
                    "user_persona": story.user_persona,
                    "acceptance_criteria": story.acceptance_criteria,
                    "definition_of_done": story.definition_of_done,
                    "story_points": story.story_points,
                    "priority": story.priority,
                    "labels": story.labels,
                    "dependencies": story.dependencies,
                    "created_at": story.created_at.isoformat()
                }
                for story in state.user_stories
            ]
        
        # Add content statistics
        output["content_statistics"] = {
            "total_epics": len(state.epics),
            "total_user_stories": len(state.user_stories),
            "total_story_points": sum(epic.estimated_story_points for epic in state.epics) + 
                               sum(story.story_points for story in state.user_stories),
            "priority_distribution": self._calculate_priority_distribution(state),
            "dependencies_count": len(set(
                dep for epic in state.epics for dep in epic.dependencies
            ).union(
                dep for story in state.user_stories for dep in story.dependencies
            ))
        }
        
        return output
    
    def _calculate_priority_distribution(self, state: SystemState) -> Dict[str, int]:
        priorities = {}
        
        for epic in state.epics:
            priorities[epic.priority] = priorities.get(epic.priority, 0) + 1
        
        for story in state.user_stories:
            priorities[story.priority] = priorities.get(story.priority, 0) + 1
        
        return priorities
    
    def save_output_to_file(self, output: Dict[str, Any], filename: Optional[str] = None) -> str:
        if not filename:
            session_id = output["session_metadata"]["session_id"]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"jira_output_{session_id}_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Output saved to file: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error saving output to file: {str(e)}")
            raise Exception(f"Failed to save output: {str(e)}")

# Main interaction function
async def main():
    """Main function to run the JIRA Agent System interactively"""
    
    # Initialize system
    try:
        system = JIRAAgentSystem()
        logger.info("System initialized successfully")
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        return
    
    # Get user input
    hlr = input("Enter your High-Level Requirement (HLR): ").strip()
    if not hlr:
        logger.error("Empty HLR provided")
        return
    
    # Get generation type preference
    generation_options = {
        "1": GenerationType.EPICS_ONLY,
        "2": GenerationType.STORIES_ONLY,
        "3": GenerationType.BOTH
    }
    
    print("\nSelect generation type:")
    print("1. Epics Only")
    print("2. User Stories Only") 
    print("3. Both Epics and User Stories")
    
    choice = input("Enter your choice (1-3): ").strip()
    generation_type = generation_options.get(choice, GenerationType.BOTH)
    
    try:
        # Create session
        state = system.create_session(hlr, generation_type)
        
        # Analyze and generate questions
        state = await system.requirement_agent.analyze_requirement(state)
        state = await system.requirement_agent.generate_questions(state)
        
        # Interactive Q&A
        qa_responses = {}
        skipped_questions = []
        
        for question in state.questions:
            print(f"\nQuestion: {question.question}")
            print(f"Context: {question.context}")
            print(f"Priority: {question.priority}/5 | Required: {'Yes' if question.required else 'No'}")
            
            response = input("Your answer (or 'skip' to skip): ").strip()
            
            if response.lower() == 'skip':
                skipped_questions.append(question.id)
            elif response:
                qa_responses[question.id] = response
        
        # Process Q&A
        state = await system.process_qa_session(state, qa_responses, skipped_questions)
        
        # Generate content
        state = await system.generate_content(state)
        
        # Display generated content
        if state.epics:
            print(f"\nGenerated {len(state.epics)} epics:")
            for epic in state.epics:
                print(f"- {epic.title}")
        
        if state.user_stories:
            print(f"\nGenerated {len(state.user_stories)} user stories:")
            for story in state.user_stories:
                print(f"- {story.title}")
        
        # Feedback loop
        while state.feedback_count < 3:
            satisfied = input("\nAre you satisfied with the generated content? (yes/no): ").strip().lower()
            
            if satisfied in ['yes', 'y']:
                break
            
            feedback = input("Please provide your feedback: ").strip()
            if feedback:
                state, feedback_applied = await system.process_feedback(state, feedback)
                
                if feedback_applied:
                    print("Feedback applied successfully. Updated content generated.")
                    if state.epics:
                        print(f"Updated epics: {len(state.epics)}")
                    if state.user_stories:
                        print(f"Updated user stories: {len(state.user_stories)}")
                else:
                    print("Feedback was not valid or could not be applied.")
            else:
                break
        
        # Export and save
        final_output = system.export_final_output(state)
        filename = system.save_output_to_file(final_output)
        
        print(f"\nProcess completed successfully!")
        print(f"Output saved to: {filename}")
        
    except Exception as e:
        logger.error(f"Process failed: {str(e)}")
        print(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())