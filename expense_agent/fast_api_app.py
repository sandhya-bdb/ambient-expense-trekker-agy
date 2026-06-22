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
import json
import logging
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
import uvicorn

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.cli.api_server import _setup_telemetry
from google.genai import types

from .agent import root_agent

# Configure standard Python logging for console logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ambient_expense_service")

# Initialize telemetry with otel_to_cloud=False
_setup_telemetry(otel_to_cloud=False)

app = FastAPI(title="Ambient Expense Approval Service")

# Initialize ADK runner
session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    session_service=session_service,
    app_name="expense_agent",
    auto_create_session=True,
)


# Define Pub/Sub Request Payload Schemas
class PubSubMessage(BaseModel):
    data: Any = Field(description="The actual payload data, possibly base64 encoded")
    messageId: str = Field(description="Unique message identifier")
    publishTime: str = Field(description="Time when the message was published")
    attributes: Optional[Dict[str, str]] = None


class PubSubEnvelope(BaseModel):
    message: PubSubMessage = Field(description="The Pub/Sub message details")
    subscription: str = Field(description="The fully-qualified subscription path")


# Helper to normalize subscription name
def normalize_subscription(subscription: str) -> str:
    """Normalizes 'projects/PROJECT_ID/subscriptions/SUB_NAME' down to 'SUB_NAME'."""
    if "/" in subscription:
        return subscription.split("/")[-1]
    return subscription


# Endpoint 1: Pub/Sub push subscription target
@app.post("/")
async def handle_pubsub(envelope: PubSubEnvelope):
    logger.info(f"Received Pub/Sub message from subscription: {envelope.subscription}")
    
    # Normalize subscription path to keep session ID clean and readable
    session_id = normalize_subscription(envelope.subscription)
    logger.info(f"Normalized session ID (subscription name): {session_id}")
    
    # Convert Pub/Sub envelope to JSON string to feed to workflow parser
    envelope_json = envelope.model_dump_json()
    new_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=envelope_json)]
    )
    
    try:
        events = []
        is_paused = False
        approval_prompt = ""
        
        # Run the workflow using run_async to propagate exceptions correctly
        async for event in runner.run_async(
            user_id="pubsub_trigger",
            session_id=session_id,
            new_message=new_message,
        ):
            events.append(event)
            
            # Check if workflow requires human-in-the-loop input (RequestInput)
            if event.content and event.content.parts:
                part = event.content.parts[0]
                # In ADK 2.0, RequestInput is emitted as a function call event named "adk_request_input"
                if part.function_call and part.function_call.name == "adk_request_input":
                    is_paused = True
                    args = part.function_call.args or {}
                    approval_prompt = args.get("message") or "Human approval required."
                    logger.info(f"Workflow paused. Human approval required: {approval_prompt}")
            
            if event.output is not None:
                logger.info(f"Workflow event output: {event.output}")
        
        if is_paused:
            return {
                "status": "paused",
                "session_id": session_id,
                "message": "Workflow is paused waiting for human approval.",
                "details": approval_prompt
            }
            
        return {
            "status": "completed",
            "session_id": session_id,
            "message": "Workflow completed successfully."
        }
        
    except Exception as e:
        logger.exception("Error processing Pub/Sub expense event in workflow")
        raise HTTPException(status_code=500, detail=str(e))


# Endpoint 2: Human approval endpoint to resume workflow
class HumanDecision(BaseModel):
    decision: str = Field(description="Must be 'yes' or 'no'")


@app.post("/approve/{session_id}")
async def approve_expense(session_id: str, payload: HumanDecision):
    decision = payload.decision.strip().lower()
    if decision not in ("yes", "no"):
        raise HTTPException(status_code=400, detail="Decision must be 'yes' or 'no'")
        
    logger.info(f"Received human decision '{decision}' for session ID: {session_id}")
    
    # Resume the workflow by sending a FunctionResponse part matching the interrupt ID "decision"
    reply_message = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name="adk_request_input",
                    id="decision",
                    response={"decision": decision}
                )
            )
        ]
    )
    
    try:
        outcomes = []
        async for event in runner.run_async(
            user_id="pubsub_trigger",
            session_id=session_id,
            new_message=reply_message,
        ):
            if event.output is not None:
                outcomes.append(event.output)
                logger.info(f"Resumed workflow completed with output: {event.output}")
                
        if not outcomes:
            raise HTTPException(status_code=404, detail=f"No active paused session found for ID {session_id} or session already completed.")
            
        return {
            "status": "success",
            "session_id": session_id,
            "outcome": outcomes[-1]
        }
        
    except Exception as e:
        logger.exception("Error resuming workflow")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
async def list_active_sessions():
    """Lists all active session IDs and basic metadata."""
    response = await session_service.list_sessions(app_name="expense_agent")
    sessions_list = []
    for session in response.sessions:
        sessions_list.append({
            "session_id": session.id,
            "user_id": session.user_id,
            "last_update_time": session.last_update_time,
            "state": session.state
        })
    return {"sessions": sessions_list}


@app.get("/sessions/{session_id}")
async def get_session_details(session_id: str):
    """Retrieves full state details and event logs for a specific session."""
    from fastapi.encoders import jsonable_encoder
    session = await session_service.get_session(
        app_name="expense_agent",
        user_id="pubsub_trigger",
        session_id=session_id
    )
    if not session:
        raise HTTPException(status_code=404, detail=f"Session with ID {session_id} not found.")
        
    serialized_events = []
    for event in session.events:
        node_name = getattr(event, "node_name", None)
        if not node_name and event.node_info:
            node_name = getattr(event.node_info, "node_name", None) or (
                event.node_info.path.split("/")[-1].split("@")[0] if event.node_info.path else None
            )
            
        serialized_events.append({
            "id": event.id,
            "author": event.author,
            "timestamp": event.timestamp,
            "content": jsonable_encoder(event.content) if event.content else None,
            "output": jsonable_encoder(event.output) if event.output is not None else None,
            "actions": jsonable_encoder(event.actions) if event.actions else None,
            "node_name": node_name
        })
        
    return {
        "session_id": session.id,
        "user_id": session.user_id,
        "last_update_time": session.last_update_time,
        "state": session.state,
        "events": serialized_events
    }


def start():
    """Starts the FastAPI service via Uvicorn."""
    uvicorn.run("expense_agent.fast_api_app:app", host="127.0.0.1", port=8080, reload=True)


if __name__ == "__main__":
    start()
