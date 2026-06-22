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
import logging
import os
from typing import Any

import vertexai
from dotenv import load_dotenv
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.cloud import logging as google_cloud_logging
from vertexai.agent_engines.templates.adk import AdkApp

from expense_agent.agent import app as adk_app
from expense_agent.app_utils.telemetry import setup_telemetry
from expense_agent.app_utils.typing import Feedback

# Load environment variables from .env file at runtime
load_dotenv()


class AgentEngineApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the agent engine app with logging and telemetry."""
        vertexai.init()
        setup_telemetry()
        super().set_up()
        logging.basicConfig(level=logging.INFO)
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    def query(
        self,
        message: Any,
        user_id: str = "default-user",
        session_id: Any = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Queries the ADK application synchronously (handles Pub/Sub / REST query)."""
        import json
        from google.genai import types
        from vertexai.agent_engines import _utils

        if not self._tmpl_attrs.get("runner"):
            self.set_up()

        if isinstance(message, dict):
            if "role" in message or "parts" in message:
                content = types.Content.model_validate(message)
            else:
                content = types.Content(role="user", parts=[types.Part.from_text(text=json.dumps(message))])
        elif isinstance(message, str):
            content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
        else:
            raise TypeError("message must be a string or a dictionary.")

        if not session_id:
            session = self.create_session(user_id=user_id)
            session_id = session["id"]

        runner = self._tmpl_attrs.get("runner")
        events = []
        for event in runner.run(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
            **kwargs,
        ):
            events.append(_utils.dump_event_for_json(event))

        return {"events": events, "session_id": session_id}

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()
        operations[""] = [*operations.get("", []), "register_feedback", "query"]
        return operations

    def clone(self) -> "AgentEngineApp":
        """Returns a clone of the Agent Runtime application."""
        return self


gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
agent_runtime = AgentEngineApp(
    app=adk_app,
    artifact_service_builder=lambda: (
        GcsArtifactService(bucket_name=logs_bucket_name)
        if logs_bucket_name
        else InMemoryArtifactService()
    ),
)
