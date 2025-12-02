# Building AI Shopping Assistants Like Shopper's Concierge: A Deep Dive into ADK Bidi-Streaming

The ADK team recently published a comprehensive [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/)—a five-part series that enables developers to build real-time, multimodal AI applications quickly. To showcase what's possible with this framework, let's look at the [Shopper's Concierge 2 demo](https://www.youtube.com/watch?v=LwHPYyw7u6U).

<div class="video-container">
  <iframe src="https://www.youtube-nocookie.com/embed/LwHPYyw7u6U" title="Shopper's Concierge Demo" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
</div>

Watch a user speak naturally to an AI assistant: *"Can you find cups with dancing people."* Within seconds, the agent responds with search results—while **real-time audio transcripts** appear on screen. The user pivots: *"Now I'd like to find a birthday present for my 10-year-old son."* The agent remembers the context. When the user requests "deep research," the agent **reports progress of the long running task** as it receives intermediate results. The user can **interrupt** at any moment, and the agent responds immediately. Then the user holds up an image, and the agent says: *"I see a desk, a chair, and a laptop on the desk"* with it's **multimodal understanding**—and offers to search for related products.

This is a working application—not a concept video—that demonstrates what's possible when you combine real-time voice interaction, visual understanding, and intelligent tool execution in a single conversational experience built with ADK Bidi-streaming.

**The question this article answers: How do you build something like this?**

We'll deconstruct the Shopper's Concierge experience and map each capability to the specific ADK Bidi-streaming features that make it possible. By the end, you'll understand exactly what infrastructure ADK provides—and how it reduces months of streaming development to declarative configuration.

## What the Demo Reveals: Essential Capabilities

Before diving into architecture, let's identify what the Shopper's Concierge actually demonstrates. Each interaction reveals a specific technical requirement:

| Demo Moment | User Action | What It Requires |
|-------------|-------------|------------------|
| **Instant voice search** | *"Find cups with dancing people"* | Low-latency voice processing with tool use |
| **Real-time transcripts** | User and agent speak, text appears live | Real-time audio transcription |
| **Progress updates** | User requests Deep Research with Google Search | Streaming Tools yields intermediate results during the long running task |
| **Interruption** | User interrupts mid-response | Immediate response with interruption handling |
| **Image understanding** | User uploads their room image | Multimodal context understanding |

These aren't isolated features—they must work together seamlessly. A user might interrupt mid-response, switch from voice to image, or ask follow-up questions that depend on earlier context. Building this from scratch would require:

- WebSocket connection management with reconnection logic
- Async coordination between input streams and response generation
- Tool execution orchestration with parallel processing
- Session state persistence across connections
- Platform abstraction for development vs. production environments

**ADK Bidi-streaming handles all of this.** Let's see how.

## Capability 1: Low-Latency Voice Interaction

**Demo moment**: The user speaks naturally, and the agent responds in real-time—no awkward pauses, no "processing" delays.

### The Challenge

Traditional AI interactions follow a rigid pattern: send complete request → wait → receive complete response. This "ask-and-wait" model feels robotic. Real conversations are fluid—both parties can speak, listen, and respond simultaneously.

### How ADK Solves It: Bidirectional Streaming

ADK's [Bidi-streaming architecture](https://google.github.io/adk-docs/streaming/dev-guide/part1/#11-what-is-bidi-streaming) establishes a persistent WebSocket connection that enables true two-way communication:

![ADK Bidi-streaming High-Level Architecture](assets/Bidi_arch.jpeg)

The key insight is **concurrent upstream and downstream flows**:

- **Upstream**: User audio streams continuously to the agent via [`LiveRequestQueue`](https://google.github.io/adk-docs/streaming/dev-guide/part2/)
- **Downstream**: Agent responses stream back via [`run_live()`](https://google.github.io/adk-docs/streaming/dev-guide/part3/) events
- **Interruption**: Users can interrupt mid-response—the agent stops immediately

This is fundamentally different from server-side streaming (one-way) or token-level streaming (no interruption). Bidi-streaming enables the phone-call-like interaction you see in the demo.

### The Implementation Pattern

```python
# Concurrent tasks enable true bidirectional flow
async def upstream_task():
    """User audio → LiveRequestQueue → Agent"""
    while True:
        audio_chunk = await websocket.receive_bytes()
        audio_blob = types.Blob(mime_type="audio/pcm;rate=16000", data=audio_chunk)
        live_request_queue.send_realtime(audio_blob)

async def downstream_task():
    """Agent → Events → User"""
    async for event in runner.run_live(...):
        await websocket.send_text(event.model_dump_json())

# Both run simultaneously
await asyncio.gather(upstream_task(), downstream_task())
```

The user never waits for processing—audio streams in while responses stream out.

## Capability 2: Stateful Context Management

**Demo moment**: After searching for cups, the user says *"Now I'd like to find a birthday present for my 10-year-old son."* The agent correctly interprets this as a new search while retaining context about the child's age.

### The Challenge

Conversations aren't stateless requests. Users expect agents to remember:
- What was discussed earlier in the session
- Preferences and context established over time
- The current state of multi-turn interactions

### How ADK Solves It: Session Architecture

ADK separates two types of state with different lifecycles:

![Comprehensive Summary of Live API RunConfig](assets/runconfig.png)

**[ADK Session](https://google.github.io/adk-docs/streaming/dev-guide/part4/#adk-session-vs-live-api-session)** (persistent):
- Stored in [`SessionService`](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice) (database, Vertex AI, or in-memory)
- Survives application restarts
- Contains full conversation history

**Live API Session** (ephemeral):
- Created per `run_live()` call
- Initialized with history from ADK Session
- Destroyed when streaming ends

This separation means the Shopper's Concierge can maintain conversation context across:
- Multiple voice interactions in a single session
- Network disconnections (via [session resumption](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption))
- Even application restarts (with persistent SessionService)

### The Implementation Pattern

```python
# Phase 1: Create once at startup
session_service = DatabaseSessionService(connection_string="postgresql://...")
runner = Runner(app_name="shoppers-concierge", agent=agent, session_service=session_service)

# Phase 2: Get or create per user connection
session = await session_service.get_session(app_name, user_id, session_id)
if not session:
    await session_service.create_session(app_name, user_id, session_id)

# Context automatically flows into run_live()
async for event in runner.run_live(user_id=user_id, session_id=session_id, ...):
    # Agent has full conversation history
```

## Capability 3: Asynchronous Tool Execution

**Demo moment**: The user requests *"deep research"*, and the agent performs complex analysis—categorizing results into "STEM building kits," "action figures," "outdoor adventure gear," etc.—without freezing the conversation.

### The Challenge

Real agents need tools: search APIs, databases, external services. With raw APIs, you must:
1. Detect when the model requests a tool
2. Execute the tool yourself
3. Format the response correctly
4. Send it back to the model
5. All while managing the active stream

This orchestration is error-prone and blocks conversation flow.

### How ADK Solves It: Automatic Tool Execution

ADK's [`run_live()`](https://google.github.io/adk-docs/streaming/dev-guide/part3/#automatic-tool-execution-in-run_live) handles the entire tool lifecycle automatically:

![Comprehensive Summary of ADK Live Event Handling](assets/run_live.png)

When you define tools on your Agent, ADK:
1. **Detects** function calls in streaming responses
2. **Executes** tools in parallel for maximum performance
3. **Formats** responses according to Live API requirements
4. **Sends** results back to the model seamlessly
5. **Yields** both call and response events to your application

The "deep research" feature runs as a background process while the conversation remains responsive.

### Streaming Tools: Real-Time Progress Reporting

But what about the progress updates you see in the demo—*"found 5 item categories"*, *"sending Concierge's Pick"*? These aren't just console logs; they're spoken by the agent in real-time while the tool is still running.

ADK supports **streaming tools** via Python's `AsyncGenerator` pattern. Unlike regular tools that return a single result, streaming tools can yield intermediate results continuously:

```python
from typing import AsyncGenerator

async def deep_research(query: str) -> AsyncGenerator[dict, None]:
    """Streaming tool that reports progress in real-time."""

    # First yield: Starting search
    yield {"status": "Searching for items matching your criteria..."}

    results = await search_products(query)

    # Second yield: Report what was found
    yield {"status": f"Found {len(results)} items, analyzing categories..."}

    categories = await analyze_categories(results)

    # Third yield: Categories identified
    yield {"status": f"Found {len(categories)} item categories"}

    for category in categories:
        picks = await select_top_picks(category)
        # Yield progress for each category
        yield {"status": f"Sending Concierge's Pick for {category['name']}"}
        yield {"pick": picks}

    # Final yield: Complete results
    yield {"status": "Research complete", "summary": categories}
```

Each `yield` becomes an event that ADK streams back to the model immediately. The model can then speak these status updates naturally—creating the real-time progress reporting you see in the Shopper's Concierge demo.

**Streaming Tool Lifecycle**:
1. **Start**: ADK invokes your async generator when the model calls the tool
2. **Stream**: Your function yields results continuously via `AsyncGenerator`
3. **Stop**: ADK cancels the generator when the session ends, an error occurs, or you provide a `stop_streaming()` function the model can call

For complete streaming tools documentation, see [Part 5: Custom Video Streaming Tools Support](https://google.github.io/adk-docs/streaming/dev-guide/part5/#custom-video-streaming-tools-support).

### The Implementation Pattern

```python
# Define agent with tools
agent = Agent(
    name="shoppers_concierge",
    model="gemini-2.5-flash-native-audio-preview",
    tools=[google_search, deep_research, virtual_tryon],  # Your custom tools
    instruction="You are a helpful shopping assistant..."
)

# ADK handles everything automatically
async for event in runner.run_live(...):
    # You see tool calls and responses as events
    if event.get_function_calls():
        print(f"Tool called: {event.get_function_calls()[0].name}")
    if event.get_function_responses():
        print(f"Tool result: {event.get_function_responses()[0].response}")
```

Compare this to the raw Live API approach:

| Aspect | Raw Live API | ADK Bidi-streaming |
|--------|--------------|-------------------|
| Tool declaration | Manual schema definition | Automatic from Python functions |
| Tool execution | Manual in app code | Automatic parallel execution |
| Response formatting | Manual JSON construction | Automatic |
| Stream coordination | Manual | Automatic event yielding |

![Raw Live API vs. ADK Bidi-streaming](assets/live_vs_adk.png)

## Capability 4: Concurrent Multimodal Input

**Demo moment**: The user holds up an image of a laptop on a desk. The agent says *"I see a desk, a chair, and a laptop"* and offers to search for related electronics.

### The Challenge

Multimodal applications must handle multiple input types simultaneously:
- Voice audio streaming continuously
- Images captured from camera
- Text typed in chat
- Activity signals for push-to-talk

Managing separate channels for each modality creates engineering complexity.

### How ADK Solves It: Unified LiveRequestQueue

ADK provides a single interface—[`LiveRequestQueue`](https://google.github.io/adk-docs/streaming/dev-guide/part2/)—that handles all input types:

![ADK Bidi-Streaming: Upstream Flow with LiveRequestQueue](assets/live_req_queue.png)

| Input Type | Method | Use Case |
|------------|--------|----------|
| Text | `send_content(Content)` | Chat messages, commands |
| Audio/Video/Image | `send_realtime(Blob)` | Voice, camera frames |
| Activity signals | `send_activity_start/end()` | Push-to-talk control |
| Session end | `close()` | Graceful termination |

All inputs flow through a single WebSocket connection to the Live API.

### The Implementation Pattern

```python
# Text input
content = types.Content(parts=[types.Part(text="Find electronics")])
live_request_queue.send_content(content)

# Audio input (streaming)
audio_blob = types.Blob(mime_type="audio/pcm;rate=16000", data=audio_chunk)
live_request_queue.send_realtime(audio_blob)

# Image input
image_blob = types.Blob(mime_type="image/jpeg", data=image_data)
live_request_queue.send_realtime(image_blob)

# All through the same queue, same connection
```

The Shopper's Concierge uses this exact pattern—voice and images flow through `send_realtime()`, enabling the seamless multimodal experience.

## Capability 5: Production-Ready Audio

**Demo moment**: Voice interactions feel natural—the agent knows when the user stops speaking and responds without explicit "I'm done" signals.

### How ADK Solves It: Native Audio Support

ADK provides comprehensive [audio capabilities](https://google.github.io/adk-docs/streaming/dev-guide/part5/):

![Comprehensive Summary of ADK Live API Multimodal Capabilities](assets/multimodal.png)

**Audio Specifications**:
- Input: 16-bit PCM, 16kHz, mono
- Output: 16-bit PCM, 24kHz, mono (native audio models)

**Key Features**:
- **[Voice Activity Detection (VAD)](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-activity-detection-vad)**: Automatically detects when users start/stop speaking
- **[Audio Transcription](https://google.github.io/adk-docs/streaming/dev-guide/part5/#audio-transcription)**: Real-time speech-to-text for both input and output
- **[Voice Configuration](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-configuration-speech-config)**: Choose from multiple voice personas
- **[Affective Dialog](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog)**: Model adapts to emotional cues (native audio models)

### Audio Model Architectures

ADK supports two model types:

| Architecture | Characteristics | Best For |
|--------------|-----------------|----------|
| **Native Audio** | End-to-end audio processing, natural prosody, affective dialog | Natural voice experiences like Shopper's Concierge |
| **Half-Cascade** | Text intermediate step, TEXT/AUDIO response modes | Reliable tool execution, text-first applications |

The Shopper's Concierge uses native audio models for the most natural conversational experience.

## The Complete Picture: Four-Phase Lifecycle

All these capabilities operate within ADK's [structured lifecycle](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle):

![ADK Bidi-streaming Application Lifecycle](assets/app_lifecycle.png)

**Phase 1: Application Initialization** (once at startup)
- Create Agent with model, tools, instructions
- Create SessionService for state persistence
- Create Runner to orchestrate everything

**Phase 2: Session Initialization** (per user connection)
- Get or create user session
- Configure RunConfig (modalities, transcription, features)
- Create LiveRequestQueue for this connection

**Phase 3: Bidi-streaming Loop** (active conversation)
- Upstream: User input → LiveRequestQueue → Agent
- Downstream: Agent → Events → User
- Tools execute automatically in the background

**Phase 4: Terminate** (connection end)
- Close LiveRequestQueue
- Session state persists for future resumption

This lifecycle ensures clean resource management, proper state isolation, and scalable multi-user support.

## Configuration: RunConfig

ADK provides declarative configuration through [`RunConfig`](https://google.github.io/adk-docs/streaming/dev-guide/part4/):

```python
run_config = RunConfig(
    streaming_mode=StreamingMode.BIDI,           # WebSocket to Live API
    response_modalities=["AUDIO"],               # Voice responses
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
    session_resumption=types.SessionResumptionConfig(),  # Auto-reconnect
    # Optional: context_window_compression for unlimited sessions
)
```

Key parameters for Shopper's Concierge-style apps:

| Parameter | Purpose |
|-----------|---------|
| `response_modalities` | `["AUDIO"]` for voice, `["TEXT"]` for chat |
| `session_resumption` | Automatic reconnection across ~10min timeouts |
| `context_window_compression` | Unlimited session duration |
| `input/output_audio_transcription` | Real-time speech-to-text |

## From Demo to Your Application

The Shopper's Concierge demonstrates what's possible. Here's how to build your own:

### 1. Start with the Demo

The [bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo) provides a working FastAPI implementation with:
- WebSocket communication
- Multimodal input (text, audio, image)
- Automatic model detection
- Event console for debugging

### 2. Define Your Agent

```python
from google.adk.agents import Agent
from google.adk.tools import google_search

agent = Agent(
    name="my_assistant",
    model="gemini-2.5-flash-native-audio-preview",
    tools=[google_search, your_custom_tools],
    instruction="Your agent's personality and capabilities..."
)
```

### 3. Implement the Lifecycle

Follow the four-phase pattern:
- Initialize once at startup
- Create session per connection
- Run concurrent upstream/downstream tasks
- Clean up on disconnect

### 4. Read the Full Guide

The [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) provides complete implementation details:
- [Part 1](https://google.github.io/adk-docs/streaming/dev-guide/part1/): Architecture and lifecycle
- [Part 2](https://google.github.io/adk-docs/streaming/dev-guide/part2/): LiveRequestQueue (upstream)
- [Part 3](https://google.github.io/adk-docs/streaming/dev-guide/part3/): run_live() events (downstream)
- [Part 4](https://google.github.io/adk-docs/streaming/dev-guide/part4/): RunConfig and session management
- [Part 5](https://google.github.io/adk-docs/streaming/dev-guide/part5/): Audio, image, and video

## Conclusion

The Shopper's Concierge isn't magic—it's ADK Bidi-streaming. Every capability you saw maps directly to framework features:

| Demo Capability | ADK Feature |
|-----------------|-------------|
| Instant voice response | Bidirectional streaming with concurrent tasks |
| Real-time transcripts | Audio transcription in RunConfig |
| Context memory | Session architecture with persistent storage |
| Deep research | Automatic tool execution in run_live() |
| Real-time progress updates | Streaming tools with AsyncGenerator |
| Interruption handling | Bidirectional flow with `interrupted` flag |
| Image understanding | Unified LiveRequestQueue for multimodal input |

What would take months to build from scratch—WebSocket management, async coordination, tool orchestration, session persistence, platform abstraction—ADK provides out of the box.

The future of AI interaction is real-time, multimodal, and conversational. ADK Bidi-streaming makes it accessible today.

---

*This article is based on the [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/). For complete technical documentation with code samples, see [Parts 1-5](https://google.github.io/adk-docs/streaming/dev-guide/part1/) of the guide.*
