class JiraAgenticIntegration:
    """Fully agentic JIRA integration using OpenAI and jira-python"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
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
        self._initialized = True
    
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
        """Get only epics from project using agent"""
        if not self.jira_client:
            return "JIRA client not available"
        
        if not self.access_manager.is_project_allowed(project_key):
            return f"Access denied to project {project_key}"
        
        try:
            task = f"""For project '{project_key}', retrieve ONLY Epic type issues and format them:
    - Total epic count
    - Each epic with: Key, Title, Status, Description (first 150 chars)
    Return formatted string output showing only Epics."""
            
            result = self._execute_jira_agent_task(task)
            return result
                
        except Exception as e:
            logger.error(f"Error in agentic epic retrieval: {e}")
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
