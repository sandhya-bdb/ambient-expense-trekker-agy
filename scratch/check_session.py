import asyncio
import os
import json
import dotenv
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

dotenv.load_dotenv()

async def main():
    project = os.environ.get("GCP_PROJECT", "my-project-agy-499705")
    location = "us-east1"
    engine_id = "5460508995070459904"
    
    service = VertexAiSessionService(
        project=project,
        location=location,
        agent_engine_id=engine_id
    )
    
    session = await service.get_session(
        app_name="expense_agent",
        user_id="vais-query-reasoning-engine",
        session_id="6879086252843335680"
    )
    
    print("SESSION STATE:")
    print(json.dumps(session.state, indent=2))
    print("\nSESSION EVENTS:")
    for i, event in enumerate(session.events):
        print(f"\n--- Event {i} (author: {event.author}, node_info: {event.node_info}) ---")
        if event.content:
            print("Content parts:")
            for part in event.content.parts:
                print(f"  - text: {part.text}")
                print(f"  - function_call: {part.function_call}")
                print(f"  - function_response: {part.function_response}")
        if event.output:
            print(f"Output: {event.output}")

if __name__ == "__main__":
    asyncio.run(main())
