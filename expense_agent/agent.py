# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import re
from zoneinfo import ZoneInfo
from typing import Any
import google.auth
import dotenv

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.workflow import Workflow, node
from google.genai import types
from pydantic import BaseModel, Field

from . import config

# Load local .env file
dotenv.load_dotenv()

# Setup Local Authentication config dynamically
if os.environ.get("GEMINI_API_KEY"):
    os.environ.pop("GOOGLE_GENAI_USE_VERTEXAI", None)
    os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
else:
    try:
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    except Exception:
        pass
    os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"


# Regex definitions for PII scrubbing
SSN_REGEX = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
# Credit Card Regex matching 13 to 16 digit numbers with optional spaces/hyphens
CC_REGEX = re.compile(r'\b(?:\d[ -]*?){13,16}\b')

# Keywords for detecting prompt injection attempts
INJECTION_KEYWORDS = [
    "ignore previous instructions",
    "ignore all instructions",
    "system prompt",
    "system instruction",
    "override rules",
    "auto-approve",
    "force auto-approval",
    "bypass verification",
    "bypass safety",
    "you must approve"
]


def scrub_pii(text: str) -> tuple[str, list[str]]:
    """Scrubs SSNs and Credit Card numbers from text, returning clean text and redacted categories."""
    redacted = []
    
    # Scrub SSNs
    scrubbed, ssn_count = SSN_REGEX.subn("[REDACTED SSN]", text)
    if ssn_count > 0:
        redacted.append("SSN")
        
    # Scrub Credit Cards
    scrubbed, cc_count = CC_REGEX.subn("[REDACTED CREDIT CARD]", scrubbed)
    if cc_count > 0:
        redacted.append("Credit Card")
        
    return scrubbed, redacted


def detect_prompt_injection(text: str) -> bool:
    """Checks if the text contains potential prompt injection phrases."""
    normalized = text.lower()
    for kw in INJECTION_KEYWORDS:
        if kw in normalized:
            return True
    return False


# 1. Define Typed Data Schemas
class ExpenseReport(BaseModel):
    amount: float = Field(description="The total monetary amount of the expense")
    submitter: str = Field(description="The email or name of the person submitting the expense")
    category: str = Field(description="The category of the expense (e.g. Travel, Meals, Office)")
    description: str = Field(description="Detailed description of the expense item or service")
    date: str = Field(description="The date of the expense transaction (YYYY-MM-DD)")


class RiskReview(BaseModel):
    risk_score: int = Field(description="Risk score rating from 1 (low risk) to 10 (high risk)")
    risk_factors: list[str] = Field(description="Specific risk factors or policy violations identified")
    alert_raised: bool = Field(description="Whether a security/compliance alert was triggered")
    reasoning: str = Field(description="Detailed reasoning for the assigned risk score")


class ApprovalOutcome(BaseModel):
    approved: bool = Field(description="True if the expense is approved, False otherwise")
    reason: str = Field(description="Reasoning or description of how the outcome was determined")


# 2. Define Workflow Graph Nodes
@node
def parse_input_event(ctx: Context, node_input: Any) -> Event:
    """Parses Pub/Sub (base64) or plain JSON event into an ExpenseReport,
    or handles plain text approval responses ('yes'/'no') if a session is paused.
    """
    raw_str = ""
    if hasattr(node_input, "parts") and node_input.parts:
        raw_str = node_input.parts[0].text or ""
    elif isinstance(node_input, str):
        raw_str = node_input
    elif isinstance(node_input, dict):
        raw_str = json.dumps(node_input)

    raw_str_clean = raw_str.strip().lower()

    # Check if this is a plain text resume attempt (e.g. typing "yes" or "no" in chat)
    if raw_str_clean in ("yes", "no"):
        expense_data = ctx.state.get("expense")
        if expense_data:
            expense_report = ExpenseReport(
                amount=float(expense_data.get("amount", 0.0)),
                submitter=str(expense_data.get("submitter", "")),
                category=str(expense_data.get("category", "")),
                description=str(expense_data.get("description", "")),
                date=str(expense_data.get("date", ""))
            )
            # Pass the decision down via session state
            return Event(output=expense_report, state={"chat_decision": raw_str_clean})

    try:
        data_dict = json.loads(raw_str)
    except Exception:
        if isinstance(node_input, dict):
            data_dict = node_input
        else:
            raise ValueError(f"Failed to parse input as JSON: {raw_str}")

    # Handle Pub/Sub message wrapping ("message": {"data": "..."})
    msg = data_dict.get("message", data_dict)
    data = msg.get("data")

    if not data:
        data = data_dict

    # Decode base64 if it is encoded
    if isinstance(data, str):
        try:
            decoded_bytes = base64.b64decode(data, validate=True)
            data_str = decoded_bytes.decode("utf-8")
            data_payload = json.loads(data_str)
        except Exception:
            try:
                data_payload = json.loads(data)
            except Exception:
                raise ValueError(f"Could not parse data string: {data}")
    elif isinstance(data, dict):
        data_payload = data
    else:
        raise ValueError(f"Unexpected data type under data key: {type(data)}")

    expense_report = ExpenseReport(
        amount=float(data_payload.get("amount", 0.0)),
        submitter=str(data_payload.get("submitter", "")),
        category=str(data_payload.get("category", "")),
        description=str(data_payload.get("description", "")),
        date=str(data_payload.get("date", ""))
    )
    return Event(output=expense_report)


@node
def route_by_amount(node_input: ExpenseReport) -> Event:
    """Routes the workflow based on the expense amount threshold."""
    # Store initial expense details in state
    state_delta = {"expense": node_input.model_dump()}
    
    if node_input.amount < config.THRESHOLD:
        return Event(output=node_input, route="auto_approve", state=state_delta)
    else:
        return Event(output=node_input, route="llm_review", state=state_delta)


@node
def auto_approve_handler(node_input: ExpenseReport) -> Event:
    """Auto-approves expenses that are below the dollar threshold."""
    outcome = ApprovalOutcome(
        approved=True,
        reason=f"Auto-approved: Expense amount ${node_input.amount:.2f} is under threshold of ${config.THRESHOLD:.2f}"
    )
    return Event(output=outcome, state={"outcome": "approved", "reason": "auto_approved"})


@node
def security_checkpoint(ctx: Context, node_input: ExpenseReport) -> Event:
    """Scrubs PII and checks for potential prompt injections in the description."""
    description = node_input.description
    
    # 1. Scrub SSNs and Credit Cards
    scrubbed_desc, redacted_categories = scrub_pii(description)
    
    # Update the expense details in the context state with the clean description
    clean_expense = node_input.model_copy(update={"description": scrubbed_desc})
    
    state_delta = {
        "expense": clean_expense.model_dump(),
        "pii_redacted": redacted_categories
    }
    
    # 2. Defend against prompt injection attempts
    if detect_prompt_injection(description):
        # Flag the security event
        state_delta["security_event"] = True
        state_delta["security_reason"] = "Potential prompt injection attempt detected in expense description."
        
        # Bypass LLM: create mock RiskReview to pass directly to human approval
        security_risk_review = RiskReview(
            risk_score=10,
            risk_factors=["Suspected Prompt Injection", "Security Violation"],
            alert_raised=True,
            reasoning="Bypassed automated LLM risk audit due to suspected prompt injection attempt in description."
        )
        return Event(output=security_risk_review, route="security_bypass", state=state_delta)
        
    return Event(output=clean_expense, route="clean", state=state_delta)


# 3. Define the LLM Risk Auditor Agent Node
llm_risk_review = LlmAgent(
    name="llm_risk_review",
    model=Gemini(
        model=config.MODEL_NAME,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are an automated risk auditor. Your task is to analyze the expense report details for any compliance or business risk.
Look for:
- Mismatches between category and description
- Unusually high prices for standard items
- Suspicious activity or policy violations (e.g. personal items, gifts, duplicate claims)

Assign a risk score (1-10) and raise an alert (alert_raised = True) if the risk score is >= 7 or if anything seems suspicious.""",
    output_schema=RiskReview,
)


@node(rerun_on_resume=True)
async def human_approval(ctx: Context, node_input: RiskReview):
    """Pauses the workflow for human approval if the amount requires review."""
    # Retrieve the parsed expense details stored in workflow state (will be scrubbed if PII was found)
    expense_data = ctx.state.get("expense")
    if not expense_data:
        raise ValueError("Expense data not found in workflow state.")
    
    expense = ExpenseReport(**expense_data)
    
    # Retrieve security metadata from state
    security_event = ctx.state.get("security_event", False)
    security_reason = ctx.state.get("security_reason", "")
    pii_redacted = ctx.state.get("pii_redacted", [])

    # Check if a chat decision was passed via state
    chat_decision = ctx.state.get("chat_decision")

    # Check if a human decision has been submitted yet
    if not chat_decision and (not ctx.resume_inputs or "decision" not in ctx.resume_inputs):
        msg_parts = [
            f"ALERT: Expense of ${expense.amount:.2f} submitted by {expense.submitter} requires approval.",
            f"Risk Score: {node_input.risk_score}/10",
            f"Alert Raised: {node_input.alert_raised}",
            f"Risk Factors: {', '.join(node_input.risk_factors) if node_input.risk_factors else 'None'}",
            f"Reasoning: {node_input.reasoning}"
        ]
        
        # Display security warning if prompt injection was detected
        if security_event:
            msg_parts.insert(1, f"⚠️ SECURITY ALERT: {security_reason}")
            
        # Display PII warning if scrubbing occurred
        if pii_redacted:
            msg_parts.insert(2, f"ℹ️ PII REDACTED: Redacted sensitive categories: {', '.join(pii_redacted)}")
            
        msg = "\n".join(msg_parts) + "\n\nPlease approve or reject this request (yes/no):"
        yield RequestInput(interrupt_id="decision", message=msg)
        return

    # Process the human decision response
    if chat_decision:
        decision = chat_decision
    else:
        raw_val = ctx.resume_inputs["decision"]
        if isinstance(raw_val, dict):
            decision = str(raw_val.get("decision") or raw_val.get("response") or next(iter(raw_val.values()), "")).strip().lower()
        else:
            decision = str(raw_val).strip().lower()
    approved = decision == "yes"
    
    outcome = ApprovalOutcome(
        approved=approved,
        reason=f"Human reviewer decided: {'Approved' if approved else 'Rejected'}"
    )
    yield Event(
        output=outcome,
        state={
            "outcome": "approved" if approved else "rejected",
            "reason": f"human_review_{decision}",
            "chat_decision": None  # Clean up state
        }
    )


# 4. Wire the Workflow Graph
root_agent = Workflow(
    name="expense_approval_workflow",
    edges=[
        ("START", parse_input_event),
        (parse_input_event, route_by_amount),
        (route_by_amount, {
            "auto_approve": auto_approve_handler,
            "llm_review": security_checkpoint,
        }),
        (security_checkpoint, {
            "clean": llm_risk_review,
            "security_bypass": human_approval,
        }),
        (llm_risk_review, human_approval),
    ]
)


app = App(
    root_agent=root_agent,
    name="expense_agent",
)
