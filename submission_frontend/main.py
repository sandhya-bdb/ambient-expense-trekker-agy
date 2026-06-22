import logging
import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
import dotenv

from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

# Load local environment variables
dotenv.load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("manager_dashboard")

app = FastAPI(title="Manager Approval Dashboard Service")

# HTML Content for Dashboard
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manager Approval Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0813;
            --card-bg: rgba(255, 255, 255, 0.03);
            --card-border: rgba(255, 255, 255, 0.07);
            --card-hover-border: rgba(139, 92, 246, 0.3);
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --primary-glow: radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.15) 0%, transparent 60%);
            --accent: #8b5cf6;
            --success: #10b981;
            --danger: #ef4444;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            background-image: radial-gradient(circle at 10% 20%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
                              radial-gradient(circle at 90% 80%, rgba(139, 92, 246, 0.08) 0%, transparent 40%);
            color: var(--text-primary);
            font-family: 'Outfit', 'Inter', sans-serif;
            min-height: 100vh;
            overflow-x: hidden;
            display: flex;
            flex-direction: column;
        }

        header {
            padding: 2rem 4rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            position: sticky;
            top: 0;
            z-index: 10;
        }

        h1 {
            font-size: 1.8rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            background: linear-gradient(135deg, #fff 30%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .dashboard-container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 3rem 4rem;
            width: 100%;
            flex-grow: 1;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 2rem;
        }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 2rem;
            backdrop-filter: blur(12px);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            overflow: hidden;
        }

        .card:hover {
            transform: translateY(-4px);
            border-color: var(--card-hover-border);
            box-shadow: 0 12px 30px rgba(139, 92, 246, 0.1);
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: radial-gradient(circle at 100% 0%, rgba(139, 92, 246, 0.05) 0%, transparent 50%);
            pointer-events: none;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1.5rem;
        }

        .submitter {
            font-weight: 600;
            font-size: 1.1rem;
            color: #fff;
        }

        .amount {
            font-size: 1.4rem;
            font-weight: 800;
            color: var(--accent);
        }

        .details-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
            margin-bottom: 1.5rem;
            font-size: 0.9rem;
        }

        .detail-label {
            color: var(--text-secondary);
            margin-bottom: 0.2rem;
        }

        .detail-val {
            font-weight: 500;
            color: var(--text-primary);
        }

        .risk-badge {
            padding: 0.3rem 0.8rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
        }

        .risk-low {
            background: rgba(16, 185, 129, 0.1);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .risk-medium {
            background: rgba(245, 158, 11, 0.1);
            color: #f59e0b;
            border: 1px solid rgba(245, 158, 11, 0.2);
        }

        .risk-high {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .actions {
            display: flex;
            gap: 1rem;
            margin-top: 1.5rem;
        }

        .btn {
            flex: 1;
            padding: 0.8rem;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: inherit;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .btn-approve {
            background: var(--success);
            color: #fff;
        }

        .btn-approve:hover {
            background: #059669;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        }

        .btn-reject {
            background: rgba(239, 68, 68, 0.1);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }

        .btn-reject:hover {
            background: var(--danger);
            color: #fff;
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.4);
        }

        .btn-review {
            width: 100%;
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
            border: 1px solid rgba(255, 255, 255, 0.1);
            margin-top: 1rem;
        }

        .btn-review:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }

        /* Slide-out Panel (Modal) */
        .drawer-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.6);
            backdrop-filter: blur(4px);
            z-index: 100;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
        }

        .drawer-overlay.active {
            opacity: 1;
            visibility: visible;
        }

        .drawer {
            position: fixed;
            top: 0;
            right: -450px;
            width: 450px;
            height: 100%;
            background: #0f0c1b;
            border-left: 1px solid rgba(255, 255, 255, 0.1);
            box-shadow: -10px 0 30px rgba(0, 0, 0, 0.5);
            z-index: 101;
            padding: 3rem 2.5rem;
            display: flex;
            flex-direction: column;
            transition: right 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .drawer.active {
            right: 0;
        }

        .drawer-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2.5rem;
        }

        .drawer-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 1.5rem;
            cursor: pointer;
        }

        .drawer-close:hover {
            color: #fff;
        }

        .drawer-content {
            flex-grow: 1;
            overflow-y: auto;
            font-size: 0.95rem;
            line-height: 1.6;
        }

        .drawer-section {
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }

        .drawer-section-title {
            font-weight: 700;
            font-size: 1.1rem;
            color: var(--accent);
            margin-bottom: 1rem;
        }

        /* Spinner */
        .spinner {
            width: 18px;
            height: 18px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 0.8s linear infinite;
            display: none;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .loading .spinner {
            display: inline-block;
        }

        .loading span {
            display: none;
        }

        .empty-state {
            grid-column: 1 / -1;
            text-align: center;
            padding: 4rem;
            color: var(--text-secondary);
            background: var(--card-bg);
            border: 1px dashed var(--card-border);
            border-radius: 16px;
        }
    </style>
</head>
<body>
    <header>
        <h1>Manager Approvals</h1>
        <div id="connection-status" style="font-size: 0.85rem; color: var(--text-secondary); display: flex; align-items: center; gap: 0.5rem;">
            <div style="width: 8px; height: 8px; border-radius: 50%; background: var(--success);"></div>
            Connected to Agent Runtime
        </div>
    </header>

    <div class="dashboard-container">
        <div id="approvals-grid" class="grid">
            <!-- Cards will be injected here -->
            <div class="empty-state">Loading pending approvals...</div>
        </div>
    </div>

    <!-- Drawer / Modal -->
    <div id="drawer-overlay" class="drawer-overlay"></div>
    <div id="drawer" class="drawer">
        <div class="drawer-header">
            <h2 id="drawer-title" style="font-weight: 800; font-size: 1.5rem;">Compliance Audit</h2>
            <button id="drawer-close" class="drawer-close">&times;</button>
        </div>
        <div class="drawer-content">
            <div class="drawer-section">
                <div class="drawer-section-title">Expense Summary</div>
                <p id="audit-desc" style="color: #fff; margin-bottom: 0.5rem;"></p>
                <div style="display: flex; gap: 1.5rem;">
                    <div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">Date</div>
                        <div id="audit-date" style="font-weight: 500;"></div>
                    </div>
                    <div>
                        <div style="font-size: 0.8rem; color: var(--text-secondary);">Category</div>
                        <div id="audit-category" style="font-weight: 500;"></div>
                    </div>
                </div>
            </div>
            <div class="drawer-section">
                <div class="drawer-section-title">LLM Risk Audit Details</div>
                <div style="margin-bottom: 1rem;">
                    <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.2rem;">Risk Score</div>
                    <span id="audit-risk-badge" class="risk-badge"></span>
                </div>
                <div style="margin-bottom: 1rem;">
                    <div style="font-size: 0.8rem; color: var(--text-secondary);">Risk Factors</div>
                    <ul id="audit-factors" style="list-style-type: none; margin-top: 0.2rem; color: #fff;"></ul>
                </div>
                <div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary);">AI Audit Reasoning</div>
                    <p id="audit-reasoning" style="color: var(--text-primary); margin-top: 0.2rem; font-size: 0.9rem;"></p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let pendingApprovals = [];

        async function fetchPending() {
            const grid = document.getElementById('approvals-grid');
            try {
                const res = await fetch('/api/pending');
                const data = await res.json();
                pendingApprovals = data.pending || [];
                
                if (pendingApprovals.length === 0) {
                    grid.innerHTML = '<div class="empty-state">No pending approvals found. All clean!</div>';
                    return;
                }

                grid.innerHTML = pendingApprovals.map((item, idx) => {
                    const expense = item.expense || {};
                    const risk = item.risk_review || {};
                    const riskScore = risk.risk_score || 0;
                    
                    let riskClass = 'risk-low';
                    if (riskScore >= 7) riskClass = 'risk-high';
                    else if (riskScore >= 4) riskClass = 'risk-medium';

                    return `
                        <div class="card" id="card-${item.session_id}">
                            <div class="card-header">
                                <div class="submitter">${expense.submitter || 'Unknown Submitter'}</div>
                                <div class="amount">$${(expense.amount || 0).toFixed(2)}</div>
                            </div>
                            
                            <div class="details-grid">
                                <div>
                                    <div class="detail-label">Date</div>
                                    <div class="detail-val">${expense.date || 'N/A'}</div>
                                </div>
                                <div>
                                    <div class="detail-label">Category</div>
                                    <div class="detail-val">${expense.category || 'N/A'}</div>
                                </div>
                                <div style="grid-column: span 2;">
                                    <div class="detail-label">Description</div>
                                    <div class="detail-val" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 320px;">
                                        ${expense.description || 'N/A'}
                                    </div>
                                </div>
                            </div>

                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span class="risk-badge ${riskClass}">
                                    Risk Score: ${riskScore}/10
                                </span>
                            </div>

                            <button class="btn btn-review" onclick="openAudit(${idx})">
                                View Compliance Review
                            </button>

                            <div class="actions">
                                <button class="btn btn-approve" id="btn-approve-${item.session_id}" onclick="takeAction('${item.session_id}', '${item.interrupt_id}', true)">
                                    <div class="spinner"></div>
                                    <span>Approve</span>
                                </button>
                                <button class="btn btn-reject" id="btn-reject-${item.session_id}" onclick="takeAction('${item.session_id}', '${item.interrupt_id}', false)">
                                    <div class="spinner"></div>
                                    <span>Reject</span>
                                </button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (err) {
                console.error(err);
                grid.innerHTML = '<div class="empty-state" style="color: var(--danger);">Failed to load pending approvals. Connection error.</div>';
            }
        }

        async function takeAction(sessionId, interruptId, approved) {
            const btnApprove = document.getElementById(`btn-approve-${sessionId}`);
            const btnReject = document.getElementById(`btn-reject-${sessionId}`);
            
            if (approved) {
                btnApprove.classList.add('loading');
                btnReject.disabled = true;
            } else {
                btnReject.classList.add('loading');
                btnApprove.disabled = true;
            }

            try {
                const res = await fetch(`/api/action/${sessionId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ approved, interrupt_id: interruptId })
                });

                if (res.ok) {
                    const card = document.getElementById(`card-${sessionId}`);
                    card.style.opacity = '0';
                    card.style.transform = 'scale(0.9)';
                    setTimeout(() => {
                        card.remove();
                        if (document.querySelectorAll('.card').length === 0) {
                            document.getElementById('approvals-grid').innerHTML = '<div class="empty-state">No pending approvals found. All clean!</div>';
                        }
                    }, 300);
                } else {
                    alert('Failed to submit approval action to Agent Runtime.');
                    btnApprove.classList.remove('loading');
                    btnReject.classList.remove('loading');
                    btnApprove.disabled = false;
                    btnReject.disabled = false;
                }
            } catch (err) {
                console.error(err);
                alert('Connection error occurred.');
                btnApprove.classList.remove('loading');
                btnReject.classList.remove('loading');
                btnApprove.disabled = false;
                btnReject.disabled = false;
            }
        }

        function openAudit(index) {
            const item = pendingApprovals[index];
            const expense = item.expense || {};
            const risk = item.risk_review || {};
            const riskScore = risk.risk_score || 0;

            document.getElementById('audit-desc').innerText = expense.description || 'N/A';
            document.getElementById('audit-date').innerText = expense.date || 'N/A';
            document.getElementById('audit-category').innerText = expense.category || 'N/A';

            const riskBadge = document.getElementById('audit-risk-badge');
            riskBadge.innerText = `Score: ${riskScore}/10`;
            riskBadge.className = 'risk-badge';
            if (riskScore >= 7) riskBadge.classList.add('risk-high');
            else if (riskScore >= 4) riskBadge.classList.add('risk-medium');
            else riskBadge.classList.add('risk-low');

            const factorsList = document.getElementById('audit-factors');
            factorsList.innerHTML = '';
            const factors = risk.risk_factors || [];
            if (factors.length === 0) {
                factorsList.innerHTML = '<li>None</li>';
            } else {
                factors.forEach(f => {
                    const li = document.createElement('li');
                    li.innerText = `• ${f}`;
                    factorsList.appendChild(li);
                });
            }

            document.getElementById('audit-reasoning').innerText = risk.reasoning || 'No details provided.';

            document.getElementById('drawer-overlay').classList.add('active');
            document.getElementById('drawer').classList.add('active');
        }

        function closeAudit() {
            document.getElementById('drawer-overlay').classList.remove('active');
            document.getElementById('drawer').classList.remove('active');
        }

        document.getElementById('drawer-close').onclick = closeAudit;
        document.getElementById('drawer-overlay').onclick = closeAudit;

        fetchPending();
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return DASHBOARD_HTML


@app.get("/api/pending")
async def get_pending():
    project = os.environ.get("GCP_PROJECT", "my-project-agy-499705")
    agent_runtime_id = os.environ.get("AGENT_RUNTIME_ID", "projects/253873765199/locations/us-east1/reasoningEngines/5460508995070459904")
    
    # Parse agent_runtime_id to extract engine_id and location
    location = "us-east1"
    engine_id = "5460508995070459904"
    if "/" in agent_runtime_id:
        parts = agent_runtime_id.split("/")
        if len(parts) >= 6:
            location = parts[3]
            engine_id = parts[5]
    else:
        engine_id = agent_runtime_id

    service = VertexAiSessionService(
        project=project,
        location=location,
        agent_engine_id=engine_id
    )
    
    try:
        # List all sessions (user_id=None lists all)
        res = await service.list_sessions(app_name="expense_agent", user_id=None)
        
        pending = []
        for s in res.sessions:
            # Get full session details (including events)
            session = await service.get_session(
                app_name="expense_agent",
                user_id=s.user_id,
                session_id=s.id
            )
            if not session:
                continue
            
            # Find unresolved adk_request_input events
            calls = {}
            responses = set()
            for event in session.events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call and part.function_call.name == "adk_request_input":
                            interrupt_id = part.function_call.id or "decision"
                            msg = part.function_call.args.get("message") if part.function_call.args else ""
                            calls[interrupt_id] = {
                                "session_id": session.id,
                                "user_id": session.user_id,
                                "interrupt_id": interrupt_id,
                                "message": msg,
                            }
                        if part.function_response and part.function_response.name == "adk_request_input":
                            interrupt_id = part.function_response.id or "decision"
                            responses.add(interrupt_id)
            
            for interrupt_id, call_info in calls.items():
                if interrupt_id not in responses:
                    expense = session.state.get("expense", {})
                    # Find LLM risk review output in events
                    risk_review = {}
                    for event in session.events:
                        is_risk_node = (event.author in ("llm_risk_review", "security_checkpoint")) or (event.node_info and event.node_info.path and ("llm_risk_review" in event.node_info.path or "security_checkpoint" in event.node_info.path))
                        if is_risk_node:
                            if event.output:
                                risk_review = event.output
                            elif event.content and event.content.parts:
                                for part in event.content.parts:
                                    if part.text:
                                        try:
                                            import json
                                            data = json.loads(part.text)
                                            if isinstance(data, dict):
                                                risk_review = data
                                        except Exception:
                                            pass

                    
                    call_info["expense"] = expense
                    call_info["risk_review"] = risk_review
                    pending.append(call_info)
        
        return {"pending": pending}
    except Exception as e:
        logger.exception("Error getting pending approvals")
        raise HTTPException(status_code=500, detail=str(e))


class ActionPayload(BaseModel):
    approved: bool
    interrupt_id: str


@app.post("/api/action/{session_id}")
async def take_action(session_id: str, payload: ActionPayload):
    project = os.environ.get("GCP_PROJECT", "my-project-agy-499705")
    agent_runtime_id = os.environ.get("AGENT_RUNTIME_ID", "projects/253873765199/locations/us-east1/reasoningEngines/5460508995070459904")
    
    # Initialize vertexai
    import vertexai
    from vertexai.preview.reasoning_engines import ReasoningEngine
    
    vertexai.init(project=project, location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-east1"))
    
    try:
        engine = ReasoningEngine(agent_runtime_id)
        
        # Build the message payload exactly as requested
        # To avoid duplicate parameter errors on the ADK runner, pass the resume payload directly as the dict value of the message argument.
        resume_message = {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "adk_request_input",
                        "id": payload.interrupt_id,
                        "response": {
                            "approved": payload.approved,
                            "decision": "yes" if payload.approved else "no"
                        }
                    }
                }
            ]
        }
        
        # Query the reasoning engine to resume
        response = engine.query(
            message=resume_message,
            user_id="default-user", # Strictly set user_id to "default-user"
            session_id=session_id
        )
        
        return {"status": "success", "response": response}
    except Exception as e:
        logger.exception("Error resuming session")
        raise HTTPException(status_code=500, detail=str(e))
