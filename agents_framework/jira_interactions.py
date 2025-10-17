import os 
from jira import JIRA
import logging
from openai import OpenAI
from typing import Dict, List, Optional, Any, TypedDict
from dotenv import load_dotenv
load_dotenv()
import json
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)

@dataclass
class JIRAIssue:
    key: str
    summary: str
    description: str
    issue_type: str
    status: str
    project_key: str



class JiraAgenticIntegration:
    print("this is getting called")
    """Fully agentic JIRA integration using OpenAI and jira-python"""
    _instance = None
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        self.server = os.getenv('JIRA_SERVER', '').rstrip('/')
        email = os.getenv('JIRA_EMAIL', '')
        api_token = os.getenv('JIRA_API_TOKEN', '')
        
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
        self._initialized = True
    
    def strip_code_fences(self,text: str) -> str:
        return re.sub(r"^```[a-zA-Z]*\n|\n```$", "", text.strip())
    
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
            
            python_code = self.strip_code_fences(response.choices[0].message.content)
            
            # Execute agent-generated code
            context = {"jira_instance": self.jira_client, "final_response": "No result"}
            exec(python_code, {}, context)
            
            return context.get("final_response", "No result")
            
        except Exception as e:
            logger.error(f"Error executing JIRA agent task: {e}")
            return f"Error: {str(e)}"
        
    def get_issues_agentic(self, project_key: str) -> List[JIRAIssue]:
        """Agentically retrieve issues"""
        if not self.jira_client:
            return []
        try:
            task = f"For project '{project_key}', retrieve all Epics (max 100) with fields: key, summary, description, issue type, status. Return as list of dicts."
            
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
    
 