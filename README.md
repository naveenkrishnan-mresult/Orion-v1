# ORION - JIRA Workflow System

## Setup & Installation

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Environment Configuration
Create a `.env` file with your credentials:
```
OPENAI_API_KEY=your_openai_api_key
JIRA_SERVER=your_jira_server_url
JIRA_EMAIL=your_jira_email
JIRA_API_TOKEN=your_jira_api_token
```

## Running the Application

### Method 1: Landing Page with Popup (Recommended)

**Step 1:** Start the main workflow interface on port 8502
```bash
streamlit run main_interface.py --server.port 8502
```

**Step 2:** Start the landing page on default port 8501
```bash
streamlit run landing.py
```

**Access:** http://localhost:8501 (landing page with chat popup)

### Method 2: Direct Access
```bash
streamlit run main_interface.py
```
**Access:** http://localhost:8501 (direct workflow interface)

### Changing Popup Source
To change the iframe source in the popup, edit `landing.py` line 265:
```html
<iframe src="http://localhost:8502/?embed=true" ...>
```
Change `8502` to match your main_interface.py port.


## Requirements
- Python 3.8+
- OpenAI API key
- JIRA credentials (optional for full features)
- Dependencies: `pip install -r requirements.txt`

## Troubleshooting

### Common Issues
- **Port already in use**: Use `--server.port XXXX` to specify different port
- **Module not found**: Ensure virtual environment is activated and dependencies installed
- **JIRA connection**: Verify credentials in `.env` file
- **Popup not working**: Ensure main_interface.py is running on port 8502
- **Iframe blank**: Check if both Streamlit instances are running on correct ports

### Browser Access
- Default URL: http://localhost:8501
- The application will automatically open in your default browser
- Use Ctrl+C to stop the server
