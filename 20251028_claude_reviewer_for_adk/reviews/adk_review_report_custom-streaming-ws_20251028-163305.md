# ADK Review Report: custom-streaming-ws.md

**Target File:** `/Users/kazsato/Documents/GitHub/gcp-blogs/20251028_claude_reviewer_for_adk/article_after_review/custom-streaming-ws.md`

**Review Date:** 2025-10-28 16:33:05

**Reviewer:** Claude Code (ADK Review Agent)

---

## Review Summary

This document provides a comprehensive review of the ADK WebSocket streaming article and code examples. The review identified **1 critical issue**, **2 warnings**, and **3 suggestions** for improvement. Overall, the article demonstrates a good understanding of ADK streaming concepts, but there are important API signature issues and missing explanations that should be addressed.

The main concerns are:
1. Incorrect `run_live()` API signature usage (deprecated `session` parameter)
2. Missing explanation of when session creation is required
3. Incomplete error handling for streaming audio events

---

## Issues

### Critical Issues (Must Fix)

#### **C1: Incorrect `run_live()` API Signature - Using Deprecated `session` Parameter**

**Problem Statement:**

The code example in the article uses the deprecated `session` parameter when calling `runner.run_live()`. According to the ADK source code (`/Users/kazsato/Documents/GitHub/adk-python/src/google/adk/runners.py`, lines 726-779), the `session` parameter is deprecated and should be replaced with `user_id` and `session_id` parameters.

**Target Code:**

- **File:** Article line 230-264 (code example) and `/Users/kazsato/Documents/GitHub/gcp-blogs/20251028_claude_reviewer_for_adk/article_after_review/adk-streaming-ws/app/main.py` lines 79-83

```python
# Start agent session
live_events = runner.run_live(
    session=session,
    live_request_queue=live_request_queue,
    run_config=run_config,
)
```

**Reason:**

From ADK source code `runners.py` lines 726-779:

```python
async def run_live(
    self,
    *,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    live_request_queue: LiveRequestQueue,
    run_config: Optional[RunConfig] = None,
    session: Optional[Session] = None,  # DEPRECATED
) -> AsyncGenerator[Event, None]:
```

Lines 767-773 explicitly show the deprecation warning:

```python
if session is not None:
    warnings.warn(
        'The `session` parameter is deprecated. Please use `user_id` and'
        ' `session_id` instead.',
        DeprecationWarning,
        stacklevel=2,
    )
```

**Recommended Options:**

**O1: Update to use `user_id` and `session_id` parameters**

Replace the `run_live()` call with the current API signature:

```python
async def start_agent_session(user_id, is_audio=False):
    """Starts an agent session"""

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

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"
    run_config = RunConfig(
        response_modalities=[modality],
        session_resumption=types.SessionResumptionConfig()
    )

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session - USE user_id and session_id instead of session
    live_events = runner.run_live(
        user_id=user_id,
        session_id=session.id,  # Use session.id instead of passing session object
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue
```

Update the article documentation (lines 230-264) accordingly.

---

### Warnings (Should Fix)

#### **W1: Missing Explanation of Session Creation Requirement**

**Problem Statement:**

The article shows creating a session before calling `run_live()`, but doesn't explain when this is necessary or optional. According to the ADK source code, `run_live()` will fetch the session if `user_id` and `session_id` are provided (lines 774-779 in `runners.py`), making explicit session creation potentially redundant.

**Target Code:**

- **File:** Article lines 230-264

```python
# Create a Session
session = await runner.session_service.create_session(
    app_name=APP_NAME,
    user_id=user_id,  # Replace with actual user ID
)
```

**Reason:**

From `runners.py` lines 774-779:

```python
if not session:
    session = await self.session_service.get_session(
        app_name=self.app_name, user_id=user_id, session_id=session_id
    )
    if not session:
        raise ValueError(f'Session not found: {session_id}')
```

This shows that `run_live()` will fetch the session internally if needed. The article should clarify:
1. When to create a new session (first-time connection)
2. When to reuse an existing session (reconnection)
3. How to handle session lifecycle in WebSocket reconnection scenarios

**Recommended Options:**

**O1: Add session lifecycle explanation**

Add a new subsection explaining session management:

```markdown
### Session Management

In the `start_agent_session()` function, we create a new session for each WebSocket connection. In a production scenario, you may want to:

1. **Check if a session exists** before creating a new one:
```python
# Try to get existing session first
session = await runner.session_service.get_session(
    app_name=APP_NAME,
    user_id=user_id,
    session_id=session_id  # You'd need to pass this from the client
)

# Create new session only if it doesn't exist
if not session:
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )
```

2. **For this example**, we create a new session for each WebSocket connection to keep it simple. The session will persist conversation history for the duration of the connection.
```

**O2: Simplify by removing explicit session creation**

Since `run_live()` requires `user_id` and `session_id`, you could document the pattern where sessions are created once and reused:

```python
async def start_agent_session(user_id, session_id, is_audio=False):
    """Starts an agent session"""
    
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )
    
    # Ensure session exists (create if needed)
    session = await runner.session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    if not session:
        session = await runner.session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
        )
    
    # ... rest of the code
```

---

#### **W2: Incomplete Event Handling for Audio Streaming**

**Problem Statement:**

The `agent_to_client_messaging()` function only handles `turn_complete`, `interrupted`, audio, and partial text events. However, it doesn't handle the case where text is complete (non-partial). This could lead to missing final text responses in text mode.

**Target Code:**

- **File:** Article lines 330-375 and `main.py` lines 87-128

```python
# If it's text and a partial text, send it
if part.text and event.partial:
    message = {
        "mime_type": "text/plain",
        "data": part.text
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: text/plain: {message}")
```

**Reason:**

The code only sends text when `event.partial` is `True`, but complete text messages (where `event.partial` is `False`) are not sent. This means the final text of a response might not be transmitted to the client.

**Recommended Options:**

**O1: Handle both partial and complete text events**

```python
# If it's text, send it (both partial and complete)
if part.text:
    message = {
        "mime_type": "text/plain",
        "data": part.text
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: text/plain: {message} (partial={event.partial})")
```

**O2: Add explicit handling for complete text**

```python
# If it's text and a partial text, send it
if part.text and event.partial:
    message = {
        "mime_type": "text/plain",
        "data": part.text
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: text/plain (partial): {message}")

# If it's text and complete, send it
elif part.text and not event.partial:
    message = {
        "mime_type": "text/plain",
        "data": part.text
    }
    await websocket.send_text(json.dumps(message))
    print(f"[AGENT TO CLIENT]: text/plain (complete): {message}")
```

---

### Suggestions (Consider Improving)

#### **S1: Add Error Handling for WebSocket Disconnections**

**Problem Statement:**

The current implementation doesn't handle WebSocket disconnections gracefully within the messaging functions. If a client disconnects unexpectedly, the tasks might raise exceptions that aren't properly handled.

**Target Code:**

- **File:** Article lines 388-413 and `main.py` lines 131-151

```python
async def client_to_agent_messaging(websocket, live_request_queue):
    """Client to agent communication"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        # ... rest of code
```

**Reason:**

WebSocket operations can raise `WebSocketDisconnect` exceptions that should be caught to enable graceful cleanup.

**Recommended Options:**

**O1: Add try-except block for WebSocket errors**

```python
from fastapi import WebSocketDisconnect

async def client_to_agent_messaging(websocket, live_request_queue):
    """Client to agent communication"""
    try:
        while True:
            # Decode JSON message
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]

            # Send the message to the agent
            if mime_type == "text/plain":
                content = Content(role="user", parts=[Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
                print(f"[CLIENT TO AGENT]: {data}")
            elif mime_type == "audio/pcm":
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            else:
                raise ValueError(f"Mime type not supported: {mime_type}")
    except WebSocketDisconnect:
        print("Client disconnected from client_to_agent_messaging")
    except Exception as e:
        print(f"Error in client_to_agent_messaging: {e}")
```

Apply similar error handling to `agent_to_client_messaging()`.

---

#### **S2: Document Session Resumption Configuration More Clearly**

**Problem Statement:**

The article mentions session resumption (lines 286-327) but doesn't clearly explain that this is an optional feature and when it should be used.

**Target Code:**

- **File:** Article lines 286-327

**Reason:**

Session resumption is a powerful feature but adds complexity. Developers should understand:
1. When to use it (production scenarios with unreliable networks)
2. When not to use it (simple applications, development)
3. The performance/resource implications

**Recommended Options:**

**O1: Add a clear "When to Use" section**

```markdown
#### When to Use Session Resumption

Session resumption is beneficial for:
- **Production applications** with users on unreliable networks (mobile, rural areas)
- **Long-running conversations** where connection drops would be disruptive
- **Voice/video streaming** where continuity is critical

You may **skip** session resumption for:
- **Development and testing** environments
- **Simple chatbot** applications where users can easily restart
- **Scenarios with stable networks** (office environments, data centers)

To disable session resumption, simply remove the parameter:
```python
run_config = RunConfig(
    response_modalities=[modality]
    # No session_resumption parameter
)
```
```

---

#### **S3: Add Information About Runner Lifecycle Management**

**Problem Statement:**

The current code creates a new `InMemoryRunner` for each WebSocket connection, which is inefficient. The article should mention runner reuse patterns.

**Target Code:**

- **File:** Article lines 230-264 and `main.py` lines 53-84

```python
async def start_agent_session(user_id, is_audio=False):
    # Create a Runner
    runner = InMemoryRunner(
        app_name=APP_NAME,
        agent=root_agent,
    )
```

**Reason:**

Creating a runner per connection is wasteful. According to ADK patterns, runners should be created once and reused.

**Recommended Options:**

**O1: Create runner once at application startup**

```python
# Create runner once at module level
runner = InMemoryRunner(
    app_name=APP_NAME,
    agent=root_agent,
)

async def start_agent_session(user_id, is_audio=False):
    """Starts an agent session"""
    
    # Create a Session (reusing the global runner)
    session = await runner.session_service.create_session(
        app_name=APP_NAME,
        user_id=user_id,
    )
    
    # ... rest of the code uses the global runner
```

**O2: Add documentation note**

Add a note in the article:

```markdown
**Note for Production:** In this example, we create a new `InMemoryRunner` for each connection for simplicity. In production, you should create the runner once at application startup and reuse it for all connections to improve performance and resource utilization.
```

---

## Additional Observations

### Positive Aspects

1. **Clear code structure** - The separation between agent-to-client and client-to-agent messaging is well organized
2. **Good documentation** - The article provides helpful explanations of each component
3. **Practical examples** - The WebSocket implementation demonstrates real-world usage
4. **Comprehensive coverage** - Both text and audio modes are well documented

### Minor Improvements

1. Consider adding type hints to function parameters for better IDE support
2. The article could benefit from a sequence diagram showing the message flow
3. Consider adding logging best practices for production deployments

---

## Conclusion

The article provides a solid foundation for understanding ADK streaming with WebSockets. The critical issue (C1) must be addressed to ensure compatibility with current ADK versions. The warnings (W1, W2) should be fixed to improve clarity and robustness. The suggestions (S1, S2, S3) would enhance the article's production readiness and educational value.

**Priority Actions:**
1. Fix C1: Update `run_live()` API signature
2. Fix W1: Clarify session lifecycle management  
3. Fix W2: Handle complete text events
4. Consider S1-S3 for production-ready code

---

**End of Review Report**
