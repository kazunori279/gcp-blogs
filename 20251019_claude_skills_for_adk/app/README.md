# ADK Streaming Chat - Minimal FastAPI WebSocket App

A minimal FastAPI WebSocket application using Google's Agent Development Kit (ADK) for real-time bidirectional streaming chat with Google Search capabilities.

## Features

- Real-time bidirectional streaming using ADK's LiveRequestQueue
- WebSocket-based communication for low-latency chat
- Google Search integration via ADK's built-in `google_search` tool
- Clean, modern web UI for testing
- Minimal dependencies and simple architecture

## Prerequisites

- Python 3.10 or higher
- Google API Key from [Google AI Studio](https://aistudio.google.com/apikey)

## Project Structure

```
app/
├── agent/
│   ├── __init__.py          # Agent package initialization
│   └── agent.py             # Agent definition with google_search tool
├── static/
│   └── index.html           # Web client UI
├── .env                     # Environment variables (API key)
├── main.py                  # FastAPI application with WebSocket endpoint
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Installation

1. **Install dependencies:**

```bash
pip install -r requirements.txt
```

2. **Set up SSL certificates (required for ADK):**

```bash
export SSL_CERT_FILE=$(python -m certifi)
```

## Configuration

The `.env` file is already configured with your API key:

```env
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=your_api_key_here
```

## Running the Application

Start the FastAPI server:

```bash
uvicorn main:app --reload
```

Or run directly:

```bash
python main.py
```

The server will start on `http://localhost:8000`

## Usage

1. Open your browser and navigate to `http://localhost:8000`
2. You'll see a chat interface with the agent
3. Type your questions and press Send or hit Enter
4. The agent will use Google Search when needed to answer your questions
5. Responses stream in real-time as they're generated

### Example Questions

Try asking:
- "What's the weather in Tokyo right now?"
- "What are the latest news about AI?"
- "Who won the latest Super Bowl?"
- "What is the capital of France?"

## API Endpoints

### `GET /`
Serves the web UI (index.html)

### `WebSocket /ws/{user_id}`
WebSocket endpoint for real-time chat

**Parameters:**
- `user_id`: Unique identifier for the user session (string)

**Message Format (Client to Server):**
```json
{
  "data": "Your message text here"
}
```

**Message Format (Server to Client):**
```json
{
  "type": "message",
  "data": "Partial response text"
}
```

or

```json
{
  "type": "status",
  "turn_complete": true,
  "interrupted": false
}
```

## How It Works

### Agent Definition (`agent/agent.py`)

The agent is configured with:
- **Model**: `gemini-2.0-flash-exp` (Gemini 2.0 Flash with experimental features)
- **Tool**: `google_search` (built-in ADK tool for Google Search grounding)
- **Instructions**: Answer questions using Google Search when needed

### WebSocket Flow

1. **Client connects** to `/ws/{user_id}`
2. **Server initializes** ADK agent session with `InMemoryRunner`
3. **Two async tasks** are created:
   - `agent_to_client_messaging`: Streams agent responses to client
   - `client_to_agent_messaging`: Relays client messages to agent
4. **Bidirectional streaming** continues until disconnect or error
5. **Session cleanup** occurs when client disconnects

### Key Components

- **InMemoryRunner**: Manages the ADK agent execution
- **LiveRequestQueue**: Queue for sending user inputs to the agent
- **RunConfig**: Configures response modality (TEXT in this case)
- **live_events**: Async iterator for agent response events

## Testing with curl (Optional)

You can also test the WebSocket connection using tools like `wscat`:

```bash
npm install -g wscat
wscat -c ws://localhost:8000/ws/test-user
```

Then send JSON messages:
```json
{"data": "What is ADK?"}
```

## Customization

### Change the Model

Edit `agent/agent.py`:
```python
model="gemini-2.0-flash-exp"  # Change to another model
```

### Add More Tools

Import and add tools to the agent:
```python
from google.adk.tools import google_search, other_tool

root_agent = Agent(
    ...
    tools=[google_search, other_tool],
)
```

### Modify Agent Instructions

Edit `agent/agent.py`:
```python
instruction="Your custom instructions here"
```

## Troubleshooting

### Model Not Available Error

If you get an error about model availability, try changing the model in `agent/agent.py`:
```python
model="gemini-2.0-flash-live-001"
```

### WebSocket Connection Refused

Make sure:
- The server is running (`uvicorn main:app --reload`)
- You're accessing the correct URL (`http://localhost:8000`)
- No firewall is blocking port 8000

### SSL Certificate Errors

Run before starting the server:
```bash
export SSL_CERT_FILE=$(python -m certifi)
```

## Production Considerations

For production deployment:

1. **Use external session storage** instead of `InMemorySessionService`
2. **Implement load balancing** with sticky sessions for WebSocket support
3. **Add authentication** to the WebSocket endpoint
4. **Use environment variables** for sensitive configuration
5. **Set up proper logging** and monitoring
6. **Deploy to Cloud Run** or other container platforms

## Learn More

- [ADK Documentation](https://google.github.io/adk-docs/)
- [ADK Python Repository](https://github.com/google/adk-python)
- [ADK Streaming Guide](https://google.github.io/adk-docs/streaming/custom-streaming-ws/)
- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)

## License

This is a minimal example application. Use it as a starting point for your own projects.
