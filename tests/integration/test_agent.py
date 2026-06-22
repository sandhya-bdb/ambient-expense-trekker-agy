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

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from expense_agent.agent import root_agent


def test_agent_stream() -> None:
    """
    Integration test for the agent stream functionality.
    Tests that the agent returns valid streaming responses.
    """

    session_service = InMemorySessionService()

    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    # Pass a valid expense report JSON that is under $100 for auto-approval
    message = types.Content(
        role="user", parts=[types.Part.from_text(text='{"amount": 50.0, "submitter": "alice@example.com", "category": "Meals", "description": "Lunch client meeting", "date": "2026-06-19"}')]
    )

    events = list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )
    assert len(events) > 0, "Expected at least one message"

    # Verify that the workflow executed and yielded output events
    outcome_event = None
    for idx, event in enumerate(events):
        output = event.output
        if output is not None:
            if hasattr(output, "approved") or (isinstance(output, dict) and "approved" in output):
                outcome_event = output
                break
    assert outcome_event is not None, "Expected an outcome event with approval status"
    approved = getattr(outcome_event, "approved", None) if not isinstance(outcome_event, dict) else outcome_event.get("approved")
    reason = getattr(outcome_event, "reason", None) if not isinstance(outcome_event, dict) else outcome_event.get("reason")
    assert approved is True
    assert "Auto-approved" in reason


def test_agent_plain_text_approval() -> None:
    """
    Integration test for resuming the workflow via plain text "yes" message.
    """
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    # Pass an expense report over the threshold ($100) to trigger human approval
    message1 = types.Content(
        role="user",
        parts=[types.Part.from_text(text='{"amount": 150.0, "submitter": "alice@example.com", "category": "Meals", "description": "Lunch client meeting", "date": "2026-06-19"}')]
    )

    events1 = list(
        runner.run(
            new_message=message1,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )

    # Verify that the workflow paused on human approval (adk_request_input)
    is_paused = False
    for event in events1:
        if event.content and event.content.parts:
            part = event.content.parts[0]
            if part.function_call and part.function_call.name == "adk_request_input":
                is_paused = True
                break
    assert is_paused, "Expected workflow to be paused on human approval"

    # Send plain text "yes" as a new user message to resume
    message2 = types.Content(
        role="user",
        parts=[types.Part.from_text(text='yes')]
    )

    events2 = list(
        runner.run(
            new_message=message2,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )

    # Verify that the workflow resumed and completed with approval
    outcome_event = None
    for event in events2:
        output = event.output
        if output is not None:
            if hasattr(output, "approved") or (isinstance(output, dict) and "approved" in output):
                outcome_event = output
                break

    assert outcome_event is not None, "Expected an outcome event on resumption"
    approved = getattr(outcome_event, "approved", None) if not isinstance(outcome_event, dict) else outcome_event.get("approved")
    reason = getattr(outcome_event, "reason", None) if not isinstance(outcome_event, dict) else outcome_event.get("reason")
    assert approved is True
    assert "Human reviewer decided: Approved" in reason

