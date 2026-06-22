# Ambient Expense Agent & Manager Dashboard

An intelligent, event-driven expense approval agent and compliance auditor built using the **Google Agent Development Kit (ADK)** and deployed on **Vertex AI Agent Engine (Reasoning Engine)**. The project includes a sleek, modern **Manager Approval Dashboard** hosted on **Cloud Run** for human-in-the-loop workflows.

## 🚀 Key Features

*   **Automated Routing & Approvals:** Automatically approves expenses under a specified threshold ($100.00) and routes larger amounts to a multi-stage review pipeline.
*   **AI-Powered Compliance Audit:** Leverages Gemini (via the ADK LlmAgent) to evaluate transaction risk, assign a risk score, list potential policy violations, and provide audit reasoning.
*   **Security & Guardrails:**
    *   **PII Scrubbing:** Automatically redacts sensitive information (like Credit Cards and SSNs) from transaction descriptions using regex-based pre-processing.
    *   **Prompt Injection Protection:** Intercepts malicious instructions designed to force approval or bypass safety constraints, automatically flagging a security alert and bypassing the LLM step entirely.
*   **Human-in-the-Loop (HITL) Workflow:** Pauses the agent execution graph via ADK's `adk_request_input` tool, awaiting manager approval or rejection.
*   **Premium Web Dashboard:** A responsive, dark-themed, glassmorphic manager dashboard to monitor pending claims, view risk analysis details, and approve/reject claims in real time.

---

## 📁 Project Directory Structure

```
ambient-expense-agent/
├── expense_agent/             # Core agent codebase
│   ├── agent.py               # Workflow graph (auto-approvals, PII scrubbing, injection check, human-approval interrupt)
│   ├── agent_runtime_app.py   # Agent Runtime (Reasoning Engine) application definition
│   ├── fast_api_app.py        # FastAPI wrapper for local runtime serving
│   └── app_utils/             # Telemetry, logging, and typing models
├── submission_frontend/       # Manager Approval Dashboard
│   ├── main.py                # FastAPI server rendering dashboard UI and handling resume actions
│   ├── Dockerfile             # Production container definition for Cloud Run
│   └── ...                    
├── tests/                     # Verification suite
│   ├── unit/                  # Local isolated unit tests
│   └── integration/           # Integration tests targeting active runtimes
├── pyproject.toml             # Python dependencies managed by `uv`
├── agents-cli-manifest.yaml   # Manifest for agents-cli deployment configuration
└── Makefile                   # Quick-access commands
```

---

## 🛠️ Prerequisites

Ensure you have the following installed:
*   **uv**: A Rust-based Python package installer and manager - [Installation Guide](https://docs.astral.sh/uv/getting-started/installation/)
*   **google-agents-cli**: Google Agent Platform CLI. Install using:
    ```bash
    uv tool install google-agents-cli
    ```
*   **Google Cloud SDK**: Active CLI configuration for deployment - [Installation Guide](https://cloud.google.com/sdk/docs/install)

---

## ⚙️ Setup and Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/sandhya-bdb/ambient-expense-trekker-agy.git
    cd ambient-expense-trekker-agy
    ```

2.  **Install Dependencies:**
    Initialize the local virtual environment and install all packages:
    ```bash
    agents-cli install
    ```

3.  **Configure Environment Variables:**
    Create a local `.env` file in the root directory:
    ```env
    GCP_PROJECT=your-project-id
    GOOGLE_CLOUD_LOCATION=us-east1
    LOGS_BUCKET_NAME=your-gcs-logs-bucket
    ```

---

## 💻 Local Development

### 1. Run the Playground
Use the interactive CLI playground to inspect, run, and debug the agent's workflow locally:
```bash
agents-cli playground
```

### 2. Run the Verification Tests
To execute unit and integration tests:
```bash
uv run pytest tests/unit tests/integration
```

---

## ☁️ Deployment

### 1. Deploy the Agent Runtime
Deploy the ADK agent to Vertex AI Reasoning Engine:
```bash
gcloud config set project <your-project-id>
gcloud config set run/region us-east1
agents-cli deploy
```
This command generates the remote runtime ID and writes it to `deployment_metadata.json`.

### 2. Deploy the Manager Dashboard
To deploy the dashboard service to Cloud Run:
```bash
gcloud run deploy expense-manager-dashboard \
  --source=./submission_frontend \
  --region=us-east1 \
  --allow-unauthenticated
```
Update the `AGENT_RUNTIME_ID` environment variable on the Cloud Run service to match the deployed Reasoning Engine resource name.

---

## 🛡️ License

This project is open-source and licensed under the **Apache License 2.0**. See the files for original copyright notices.
