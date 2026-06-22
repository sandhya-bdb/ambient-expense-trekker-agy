#!/usr/bin/env python3
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

import json
import os
import sys
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.events.event import Event
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Add project root to sys.path so we can import expense_agent
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from expense_agent.agent import RiskReview, root_agent


# 1. Mock LlmAgent.run_async to avoid external network calls in sandbox
async def mock_run_async(self, parent_context):
    session = parent_context.session
    expense_data = session.state.get("expense", {})
    amount = expense_data.get("amount", 0.0)
    category = expense_data.get("category", "")
    
    # Simple rule-based logic to mock risk review outcomes
    if category.lower() == "luxury" or amount >= 1000:
        review = RiskReview(
            risk_score=8,
            risk_factors=["Luxury expense", "High amount review"],
            alert_raised=True,
            reasoning="Expense contains luxury items or unusually high amount."
        )
    else:
        review = RiskReview(
            risk_score=2,
            risk_factors=[],
            alert_raised=False,
            reasoning="Mocked standard business expense, details match category."
        )
        
    yield Event(
        author="llm_risk_review",
        content=types.Content(
            role="model",
            parts=[types.Part.from_text(text=review.model_dump_json())]
        ),
        output=review
    )

# Apply the monkey patch
LlmAgent.run_async = mock_run_async


def serialize_part(part: Any) -> dict[str, Any]:
    part_dict = {}
    
    def get_val(obj, key):
        if hasattr(obj, key):
            return getattr(obj, key)
        if isinstance(obj, dict):
            return obj.get(key)
        return None

    text = get_val(part, "text")
    function_call = get_val(part, "function_call")
    function_response = get_val(part, "function_response")

    if text is not None:
        part_dict["text"] = text
    elif function_call is not None:
        part_dict["function_call"] = {
            "name": get_val(function_call, "name"),
            "args": get_val(function_call, "args")
        }
        fc_id = get_val(function_call, "id")
        if fc_id:
            part_dict["function_call"]["id"] = fc_id
    elif function_response is not None:
        part_dict["function_response"] = {
            "name": get_val(function_response, "name"),
            "response": get_val(function_response, "response")
        }
        fr_id = get_val(function_response, "id")
        if fr_id:
            part_dict["function_response"]["id"] = fr_id
            
    return part_dict


def serialize_content(content: Any) -> dict[str, Any]:
    if not content:
        return {}
        
    role = getattr(content, "role", None) or (
        content.get("role") if isinstance(content, dict) else "model"
    )
    parts = getattr(content, "parts", None) or (
        content.get("parts") if isinstance(content, dict) else []
    )
    
    return {
        "role": role,
        "parts": [serialize_part(p) for p in parts if p]
    }


def convert_session_to_trace(session: Any, case_id: str) -> dict[str, Any]:
    # Gather events with valid content, and synthesize for the final outcome event if empty
    events_with_content = []
    
    for idx, e in enumerate(session.events):
        if e.content:
            events_with_content.append(e)
        elif idx == len(session.events) - 1 and e.output:
            # Synthesize final outcome text for the evaluator
            output = e.output
            approved = getattr(output, "approved", False) if not isinstance(output, dict) else output.get("approved", False)
            reason = getattr(output, "reason", "") if not isinstance(output, dict) else output.get("reason", "")
            status_str = "Approved" if approved else "Rejected"
            synthesized_content = types.Content(
                role="model",
                parts=[types.Part.from_text(text=f"{status_str}. {reason}")]
            )
            e_copy = e.model_copy(update={"content": synthesized_content})
            events_with_content.append(e_copy)

    turns = []
    current_turn_events = []
    turn_index = 0
    
    for e in events_with_content:
        is_user_input = (e.author == "user" or (e.content and e.content.role == "user"))
        if is_user_input and current_turn_events:
            turns.append({
                "turn_index": turn_index,
                "events": current_turn_events
            })
            current_turn_events = []
            turn_index += 1
            
        event_dict = {
            "author": e.author,
            "content": serialize_content(e.content)
        }
        current_turn_events.append(event_dict)
        
    if current_turn_events:
        turns.append({
            "turn_index": turn_index,
            "events": current_turn_events
        })
        
    return {
        "eval_case_id": case_id,
        "agent_data": {
            "agents": {
                "expense_approval_workflow": {
                    "agent_id": "expense_approval_workflow",
                    "instruction": "Expense approval coordinator workflow"
                },
                "llm_risk_review": {
                    "agent_id": "llm_risk_review",
                    "instruction": "LLM risk auditor agent"
                }
            },
            "turns": turns
        }
    }


def main():
    dataset_path = "tests/eval/datasets/basic-dataset.json"
    if not os.path.exists(dataset_path):
        print(f"Error: dataset file not found at {dataset_path}")
        sys.exit(1)
        
    with open(dataset_path, "r") as f:
        dataset = json.load(f)
        
    eval_cases = dataset.get("eval_cases", [])
    output_traces = []
    
    session_service = InMemorySessionService()
    
    for case in eval_cases:
        case_id = case.get("eval_case_id")
        prompt_text = case["prompt"]["parts"][0]["text"]
        print(f"Running scenario: {case_id}...")
        
        session_id = f"session_{case_id}"
        session = session_service.create_session_sync(user_id="test_user", app_name="expense_agent", session_id=session_id)
        runner = Runner(agent=root_agent, session_service=session_service, app_name="expense_agent")
        
        # Run turn 1
        message = types.Content(role="user", parts=[types.Part.from_text(text=prompt_text)])
        events = list(runner.run(new_message=message, user_id="test_user", session_id=session.id))
        
        # Check if paused waiting for decision
        is_paused = False
        for e in events:
            if e.content and e.content.parts:
                part = e.content.parts[0]
                if hasattr(part, "function_call") and part.function_call and part.function_call.name == "adk_request_input":
                    is_paused = True
                    break
                    
        if is_paused:
            # Automate human approval decision
            if case_id in ("manual_approve_clean", "pii_leak"):
                decision = "yes"
            else:
                decision = "no"
                
            print(f"  Workflow paused for review. Automated decision: {decision}")
            
            # Resume turn 2
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
            list(runner.run(new_message=reply_message, user_id="test_user", session_id=session.id))
            
        # Get full session events and convert to trace
        full_session = session_service.get_session_sync(user_id="test_user", app_name="expense_agent", session_id=session.id)
        trace = convert_session_to_trace(full_session, case_id)
        output_traces.append(trace)
        print(f"  Completed scenario {case_id}.")
        
    # Write output file
    output_dir = "artifacts/traces"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "generated_traces.json")
    
    with open(output_path, "w") as f:
        json.dump({"eval_cases": output_traces}, f, indent=2)
        
    print(f"Successfully generated evaluation traces and saved to {output_path}")


if __name__ == "__main__":
    main()
