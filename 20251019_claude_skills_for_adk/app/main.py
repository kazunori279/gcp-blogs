import os
import json
import asyncio
from pathlib import Path
from dotenv import load_dotenv

from google.genai.types import Part, Content
from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from agent.agent import root_agent

# Load environment variables
load_dotenv()

APP_NAME = "ADK Streaming Chat"


async def start_agent_session(user_id: str):
    """Start an ADK agent session for text-based chat"""

    # Create a Runner
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )

    # Create a Session
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )

    # Set response modality to TEXT
    run_config = RunConfig(response_modalities=["TEXT"])

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )

    return live_events, live_request_queue


async def agent_to_client_messaging(websocket: WebSocket, live_events):
    """Stream agent responses to the client"""
    try:
        async for event in live_events:
            # Handle turn completion
            if event.turn_complete or event.interrupted:
                message = {
                    "type": "status",
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {message}")
                continue

            # Extract content from event
            part: Part = (
                event.content and event.content.parts and event.content.parts[0]
            )
            if not part:
                continue

            # Send partial text responses
            if part.text and event.partial:
                message = {
                    "type": "message",
                    "data": part.text
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {part.text}")
    except Exception as e:
        print(f"Error in agent_to_client_messaging: {e}")


async def client_to_agent_messaging(websocket: WebSocket, live_request_queue: LiveRequestQueue):
    """Relay client messages to the agent"""
    try:
        while True:
            # Receive message from client
            message_json = await websocket.receive_text()
            message = json.loads(message_json)

            # Extract text data
            text_data = message.get("data", "")

            # Send to agent
            content = Content(role="user", parts=[Part.from_text(text=text_data)])
            live_request_queue.send_content(content=content)
            print(f"[CLIENT TO AGENT]: {text_data}")
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in client_to_agent_messaging: {e}")


# FastAPI application
app = FastAPI(title="ADK Streaming Chat")

# Serve static files
STATIC_DIR = Path("static")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the index.html"""
    static_index = STATIC_DIR / "index.html"
    if static_index.exists():
        return FileResponse(static_index)
    return {"message": "ADK Streaming Chat API. Connect to /ws/{user_id} for WebSocket chat."}


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for real-time chat with the agent"""

    # Accept connection
    await websocket.accept()
    print(f"Client #{user_id} connected")

    try:
        # Start agent session
        live_events, live_request_queue = await start_agent_session(user_id)

        # Create bidirectional messaging tasks
        agent_to_client_task = asyncio.create_task(
            agent_to_client_messaging(websocket, live_events)
        )
        client_to_agent_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue)
        )

        # Wait for either task to complete (or error)
        tasks = [agent_to_client_task, client_to_agent_task]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

    except WebSocketDisconnect:
        print(f"Client #{user_id} disconnected")
    except Exception as e:
        print(f"Error in websocket_endpoint: {e}")
    finally:
        # Close LiveRequestQueue
        try:
            live_request_queue.close()
        except:
            pass
        print(f"Session ended for client #{user_id}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
