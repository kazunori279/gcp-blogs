# ADK Bidi-Streaming: A Visual Guide to Real-Time Multimodal AI Agent Development

Building real-time voice AI is hard. You need WebSocket connections that stay alive, audio streaming that doesn't lag, interruption handling that feels natural, and session state that persists across reconnections. The complexity adds up fast—what should take weeks often stretches into months of infrastructure work.

What if you could skip all that plumbing and focus on what actually matters: your agent's behavior and your users' experience?

That's exactly what Google's [Agent Development Kit (ADK)](https://google.github.io/adk-docs/) delivers. The newly published [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) is a comprehensive 5-part series that takes you from architecture fundamentals to production deployment:

| Part | Focus | What You'll Learn |
|------|-------|-------------------|
| [Part 1](https://google.github.io/adk-docs/streaming/dev-guide/part1/) | Foundation | Architecture, Live API platforms, 4-phase lifecycle |
| [Part 2](https://google.github.io/adk-docs/streaming/dev-guide/part2/) | Upstream | Sending text, audio, video via LiveRequestQueue |
| [Part 3](https://google.github.io/adk-docs/streaming/dev-guide/part3/) | Downstream | Event handling, tool execution, multi-agent workflows |
| [Part 4](https://google.github.io/adk-docs/streaming/dev-guide/part4/) | Configuration | Session management, quotas, production controls |
| [Part 5](https://google.github.io/adk-docs/streaming/dev-guide/part5/) | Multimodal | Audio specs, model architectures, advanced features |

The guide also includes a complete working demo—a FastAPI WebSocket server with a web UI that you can run locally and experiment with:

![ADK Bidi-streaming Demo](assets/bidi-demo-screen.png)

**[Try the bidi-demo →](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo)**

This post distills the guide into a visual cheatsheet. Each infographic captures a core concept, with enough context to understand the "why" behind the architecture decisions.

---

## Understanding the Architecture

Before diving into code, you need a mental model of how the pieces connect. ADK Bidi-streaming follows a clean [separation of concerns](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview) across three layers, each with distinct responsibilities.

![ADK Bidi-streaming High-Level Architecture](assets/Bidi_arch.jpeg)

**You own the application layer.** This includes the client applications your users interact with (web, mobile, kiosk) and the transport server that manages connections. Most teams use [FastAPI](https://fastapi.tiangolo.com/) with WebSockets, but any framework supporting real-time communication works. You also define your [Agent](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent)—the instructions, tools, and behaviors that make your AI unique.

**ADK handles the orchestration.** The framework provides three key components that eliminate infrastructure work. [LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/) buffers and sequences incoming messages so you don't worry about race conditions. [Runner](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner) manages session lifecycles and conversation state. And the internal LLM Flow handles the complex protocol translation you never want to write yourself.

**Google provides the AI backbone.** The [Live API](https://google.github.io/adk-docs/streaming/dev-guide/part1/#12-gemini-live-api-and-vertex-ai-live-api)—available through [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) for rapid prototyping or [Vertex AI Live API](https://cloud.google.com/vertex-ai/generative-ai/docs/live-api) for enterprise production—delivers real-time, low-latency AI processing with built-in support for audio, video, and [natural interruptions](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag).

> **Why this matters:** The bidirectional arrows in the diagram aren't just decoration—they represent true concurrent communication. Users can interrupt the AI mid-sentence, just like in human conversation. This is fundamentally different from request-response APIs, and it's what makes voice AI feel natural rather than robotic.

---

## Why ADK Over Raw Live API?

Now that you understand where the pieces fit, the natural question is: why use ADK instead of building directly on the Live API? After all, the underlying Gemini API is well-documented.

The answer becomes viscerally clear when you compare the two approaches side-by-side.

![Raw Live API vs. ADK Bidi-streaming](assets/live_vs_adk.png)

With the raw Live API, you're responsible for everything. Tool execution? You detect function calls, invoke your code, format responses, and send them back—manually coordinating with ongoing audio streams. Connection drops? You implement reconnection logic, cache session handles, and restore state. Session persistence? You design the schema, handle serialization, and manage the storage layer.

**ADK transforms all of this into declarative configuration.** Tools execute automatically in parallel. Connections resume transparently when WebSocket timeouts occur. Sessions persist to your choice of database with zero custom code. Events arrive as typed Pydantic models you can serialize with a single method call.

The [feature comparison](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications) spans six critical areas:

| Capability | Raw Live API | ADK Bidi-streaming |
|------------|--------------|-------------------|
| Agent Framework | Build from scratch | Single/multi-agent with tools, evaluation, security |
| [Tool Execution](https://google.github.io/adk-docs/streaming/dev-guide/part3/#automatic-tool-execution-in-run_live) | Manual handling | Automatic parallel execution |
| [Connection Management](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption) | Manual reconnection | Transparent session resumption |
| [Event Model](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class) | Custom structures | Unified, typed Event objects |
| Async Framework | Manual coordination | LiveRequestQueue + run_live() generator |
| [Session Persistence](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice) | Manual implementation | Built-in SQL, Vertex AI, or in-memory |

> **The bottom line:** ADK reduces months of infrastructure development to days of application development. You focus on what your agent does, not how streaming works.

---

## The Four-Phase Application Lifecycle

Every ADK Bidi-streaming application follows a predictable [four-phase lifecycle](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle). Understanding these phases isn't just organizational—it's the key to resource efficiency and clean code architecture.

![ADK Bidi-streaming Application Lifecycle](assets/app_lifecycle.png)

### Phase 1: Application Initialization

When your server starts, you create three foundational components that live for the lifetime of the process. First, you [define your Agent](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent) with its model, tools, and personality. Then you [create a SessionService](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice)—in-memory for development, database-backed for production. Finally, you [initialize the Runner](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner) that will orchestrate all sessions.

These components are stateless and thread-safe. A single Runner can handle thousands of concurrent users because the per-user state lives elsewhere.

### Phase 2: Session Initialization

Each time a user connects via WebSocket, you set up their streaming session. You [get or create their Session](https://google.github.io/adk-docs/streaming/dev-guide/part1/#get-or-create-session) to restore conversation history. You [configure RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-runconfig) to specify modalities (audio or text), transcription settings, and features. You [create a fresh LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-liverequestqueue) for message buffering. Then you start the [run_live() event loop](https://google.github.io/adk-docs/streaming/dev-guide/part3/#how-run_live-works).

### Phase 3: Bidirectional Streaming

This is where the magic happens. Two concurrent async tasks run simultaneously: the upstream task [sends messages](https://google.github.io/adk-docs/streaming/dev-guide/part1/#send-messages-to-the-agent) from your WebSocket through the queue to the agent, while the downstream task [receives events](https://google.github.io/adk-docs/streaming/dev-guide/part1/#receive-and-process-events) from the agent and forwards them to your client.

The user can speak while the AI is responding. The AI can be [interrupted](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag) mid-sentence. It's true two-way communication, not alternating monologues.

### Phase 4: Session Termination

When the connection ends—whether the user disconnects, a timeout occurs, or an error happens—you [close the LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals). This sends a graceful termination signal, stops the run_live() loop, and ensures session state is persisted for future resumption.

> **Why this matters:** The arrow from Phase 4 back to Phase 2 represents session continuity. When a user reconnects—even days later—their conversation history is restored from the SessionService. The Live API session is ephemeral, but the ADK Session is permanent (as long as you use persistent session stores like SQL or Vertex AI rather than in-memory).

---

## Upstream Flow: LiveRequestQueue

The path from your application to the AI flows through a single interface: [LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/#liverequestqueue-and-liverequest). Instead of juggling different APIs for text, audio, and control signals, you use one elegant queue that handles everything.

![ADK Bidi-Streaming: Upstream Flow with LiveRequestQueue](assets/live_req_queue.png)

**Sending text** is straightforward. When a user types a message, you wrap it in a Content object and call [`send_content()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_content-sends-text-with-turn-by-turn). This signals a complete turn to the model, triggering immediate response generation.

**Streaming audio** works differently. You call [`send_realtime()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_realtime-sends-audio-image-and-video-in-real-time) with small chunks (50-100ms recommended) continuously as the user speaks. The model processes audio in real-time, using Voice Activity Detection to determine when the user has finished.

**Manual turn control** is available when you need it. If you're building a push-to-talk interface or using client-side VAD, [`send_activity_start()` and `send_activity_end()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#activity-signals) explicitly signal speech boundaries.

**Graceful shutdown** happens through [`close()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals). This tells the Live API to terminate cleanly rather than waiting for a timeout.

The queue is built on Python's asyncio.Queue, which means it's [non-blocking and thread-safe within the event loop](https://google.github.io/adk-docs/streaming/dev-guide/part2/#concurrency-and-thread-safety). Messages are processed in [FIFO order](https://google.github.io/adk-docs/streaming/dev-guide/part2/#message-ordering-guarantees)—what you send first arrives first.

> **💡 Pro tip:** Don't wait for model responses before sending the next audio chunk. The queue handles buffering, and the model expects continuous streaming. Waiting creates awkward pauses in conversation.

---

## Downstream Flow: The run_live() Method

The return path—from the AI back to your application—centers on [`run_live()`](https://google.github.io/adk-docs/streaming/dev-guide/part3/). This async generator is the heart of ADK streaming, yielding events in real-time without buffering.

![Comprehensive Summary of ADK Live Event Handling: The run_live() Method](assets/run_live.png)

### How run_live() Works

You call it with three inputs: **identity** (user_id and session_id to identify the conversation), **channel** (the LiveRequestQueue for upstream messages), and **configuration** (RunConfig for streaming behavior). The method returns an async generator that yields [Event objects](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class) as they arrive.

```python
async for event in runner.run_live(
    user_id=user_id,
    session_id=session_id,
    live_request_queue=queue,
    run_config=config
):
    # Process each event as it arrives
    await websocket.send_text(event.model_dump_json())
```

### The Seven Event Types

Not all events are created equal. Understanding the types helps you build responsive UIs.

**[Text events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#text-events)** contain the model's written response in `event.content.parts[0].text`. They arrive incrementally (with `partial=True`) as the model generates, then as a complete merged message (with `partial=False`).

**[Audio events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#audio-events)** come in two forms. Inline audio (`inline_data`) streams in real-time for immediate playback but is never saved. File audio (`file_data`) references stored artifacts when you enable persistence.

**[Transcription events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#transcription-events)** provide speech-to-text for both user input and model output. They're invaluable for accessibility, logging, and debugging voice interactions.

**[Metadata events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#metadata-events)** report token usage—essential for cost monitoring and quota management.

**[Tool call and response events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#tool-call-events)** let you observe function execution. ADK handles the execution automatically; you just watch the events flow.

**[Error events](https://google.github.io/adk-docs/streaming/dev-guide/part3/#error-events)** surface problems with `error_code` and `error_message` fields. Some errors are recoverable (rate limits), others are terminal (safety violations).

### The Flow Control Flags

Three boolean flags control conversation dynamics:

[**`partial`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-partial) tells you whether you're seeing an incremental chunk or complete text. Display partial events for real-time typing effects; use non-partial for final storage.

[**`interrupted`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag) signals that the user started speaking while the model was still responding. Stop audio playback immediately and clear any partial text—the model is pivoting to handle the interruption.

[**`turn_complete`**](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-turn_complete-flag) indicates the model has finished its entire response. Re-enable the microphone, hide typing indicators, and mark the turn boundary in your logs.

> **Why `interrupted` matters:** This flag is what makes voice AI feel natural. Without it, users must wait silently for the AI to finish speaking before they can respond. With it, conversation flows like it does between humans.

---

## A Real-World Example: Voice Search

Let's trace a complete interaction to see how these pieces work together. A user asks: *"What's the weather in Tokyo?"*

**1. Audio Capture → Queue**
The browser captures microphone input at 16kHz, converts to PCM chunks, and sends via WebSocket. Your server receives the binary frames and calls `live_request_queue.send_realtime(audio_blob)`.

**2. VAD Detection**
The Live API's Voice Activity Detection notices the user stopped speaking. It triggers processing of the accumulated audio.

**3. Transcription Event**
You receive an event with `input_transcription.text = "What's the weather in Tokyo?"`. Display this in the chat UI so users see their words recognized.

**4. Tool Execution**
The model decides to call the `google_search` tool. You receive a tool call event, ADK executes the search automatically, and a tool response event follows with the weather data.

**5. Audio Response**
The model generates a spoken response. Audio chunks arrive as events with `inline_data`. Your client feeds them to an AudioWorklet for real-time playback: *"The weather in Tokyo is currently 22 degrees and sunny."*

**6. Turn Complete**
Finally, an event arrives with `turn_complete=True`. The UI can remove the "..." indicator to show the agent finished talking.

This entire flow takes under two seconds. The user experiences it as natural conversation, unaware of the LiveRequestQueue, Event types, and session management happening beneath the surface.

---

## Configuring Sessions with RunConfig

[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/) is your control center for streaming behavior. Every aspect of a session—from audio format to cost limits—is configured here.

![Comprehensive Summary of Live API RunConfig](assets/runconfig.png)

### Essential Parameters

[**`response_modalities`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#response-modalities) determines whether the model responds with text or audio. You must choose one per session—`["TEXT"]` for chat applications, `["AUDIO"]` for voice. Native audio models require audio output; half-cascade models support both.

[**`streaming_mode`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#streamingmode-bidi-or-sse) selects the transport protocol. BIDI uses WebSockets to the Live API with full bidirectional streaming, interruptions, and VAD. SSE uses HTTP streaming to the standard Gemini API—simpler but text-only.

[**`session_resumption`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption) enables automatic reconnection. WebSocket connections timeout after ~10 minutes. With session resumption enabled, ADK handles reconnection transparently—your code never sees the interruption.

[**`context_window_compression`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-context-window-compression) solves two problems at once. It removes session duration limits (normally 15 minutes for audio, 2 minutes for video) and manages token limits by summarizing older conversation history. Enable this for any session that might run long.

### Production Controls

[**`max_llm_calls`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#max_llm_calls) caps invocations per session—useful for cost control, though it only applies to SSE mode. For BIDI streaming, implement your own turn counting.

[**`save_live_blob`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#save_live_blob) persists audio and video to your artifact storage. Enable for debugging, compliance, or training data collection—but watch storage costs.

[**`custom_metadata`**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#custom_metadata) attaches arbitrary key-value data to every event. Use it for user segmentation, A/B testing, or debugging context.

### [Understanding Session Types](https://google.github.io/adk-docs/streaming/dev-guide/part4/#understanding-live-api-connections-and-sessions)

One concept trips up many developers: the difference between ADK Sessions and Live API sessions.

[**ADK Session**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#adk-session-vs-live-api-session) is persistent. It lives in your SessionService (database, Vertex AI, or memory) and survives server restarts. When a user returns days later, their conversation history is still there.

[**Live API session**](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-connections-and-sessions) is ephemeral. It exists only during an active `run_live()` call. When the loop ends, the Live API session is destroyed—but ADK has already persisted the important events to your ADK Session.

> **Quota planning:** Gemini Live API allows 50-1,000 concurrent sessions depending on tier. Vertex AI supports up to 1,000 per project. For applications that might exceed these limits, implement [session pooling with a user queue](https://google.github.io/adk-docs/streaming/dev-guide/part4/#architectural-patterns-for-managing-quotas).

---

## Multimodal Capabilities

ADK Bidi-streaming isn't limited to text—it's a full [multimodal platform](https://google.github.io/adk-docs/streaming/dev-guide/part5/) supporting audio, images, and video. Understanding the specifications helps you build robust applications.

![Comprehensive Summary of ADK Live API Multimodal Capabilities](assets/multimodal.png)

### Audio: The Core Modality

[**Input audio**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#sending-audio-input) must be 16-bit PCM, mono, at 16kHz. Send chunks of 50-100ms (1,600-3,200 bytes) for optimal latency. The browser's AudioWorklet captures microphone input, converts Float32 samples to Int16, and streams via WebSocket.

[**Output audio**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#receiving-audio-output) arrives as 16-bit PCM, mono, at 24kHz. Use a ring buffer in your AudioWorklet player to absorb network jitter and ensure smooth playback.

### Image and Video: Frame-by-Frame

Both images and video use the same mechanism—[JPEG frames sent via `send_realtime()`](https://google.github.io/adk-docs/streaming/dev-guide/part5/#how-to-use-image-and-video). The recommended resolution is 768×768, with a maximum frame rate of 1 FPS.

This approach works well for visual context (showing a product, sharing a document) but isn't suitable for real-time action recognition. The 1 FPS limit means fast motion won't be captured meaningfully.

### Model Architectures

Two fundamentally different architectures power voice AI:

[**Native Audio models**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#native-audio-models) process audio end-to-end without text intermediates. They produce more natural prosody, support an extended voice library, and enable advanced features like [affective dialog](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog) (emotional adaptation) and [proactivity](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog) (unsolicited suggestions). The current model is `gemini-2.5-flash-native-audio-preview`.

[**Half-Cascade models**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#half-cascade-models) convert audio to text, process it, then synthesize speech. They support both TEXT and AUDIO response modalities, offering faster text responses and more predictable tool execution. The current model is `gemini-2.0-flash-live-001` (deprecated December 2025).

### Advanced Features

[**Audio transcription**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#audio-transcription) is enabled by default. Both user speech and model speech are transcribed, arriving as separate event fields. Essential for accessibility and conversation logging.

[**Voice Activity Detection**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-activity-detection-vad) automatically detects when users start and stop speaking. No manual signaling needed—just stream audio continuously and let the API handle turn-taking.

[**Voice configuration**](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-configuration-speech-config) lets you select from available voices. Set it per-agent for multi-agent scenarios where different agents should have distinct voices, or globally in RunConfig for consistency.

> **Choosing the right model:** For natural conversation with emotional awareness, use native audio. For applications prioritizing tool execution reliability or needing text output, use half-cascade until you've tested thoroughly with native audio.

---

## Putting It All Together

We've covered a lot of ground. Here's how the pieces connect into a coherent system:

**[Architecture](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview)** separates concerns cleanly. You own the application and agent definition. ADK handles orchestration. Google provides the AI infrastructure.

**[ADK vs Raw API](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications)** isn't a close comparison. ADK eliminates months of infrastructure work through automatic tool execution, transparent reconnection, typed events, and built-in persistence.

**[The four-phase lifecycle](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle)** structures your code correctly. Initialize once at startup, configure per-session, stream bidirectionally, and terminate cleanly.

**[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)** unifies upstream communication. Four methods handle all input types: text, audio, activity signals, and termination.

**[run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/)** streams events downstream. Seven event types cover text, audio, transcription, metadata, tools, and errors. Three flags control conversation flow.

**[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/)** makes behavior declarative. Modalities, resumption, compression, and controls—all set through configuration rather than code.

**[Multimodal capabilities](https://google.github.io/adk-docs/streaming/dev-guide/part5/)** extend beyond text. Audio at specific sample rates, images and video as JPEG frames, and advanced features like VAD and transcription.

The result? You can build production-ready real-time AI applications in days instead of months.

---

## Getting Started

Ready to build? Here's your path forward:

**Run the demo first.** The [bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo) is a complete FastAPI implementation you can run locally. It demonstrates the WebSocket handler, concurrent tasks, audio processing, and UI—everything discussed in this post.

**Read the full guide.** The [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) provides implementation details, code samples, and edge cases that go beyond this cheatsheet.

**Explore the broader ADK ecosystem.** The [official ADK documentation](https://google.github.io/adk-docs/) covers agent design, tool development, session management, and deployment patterns.

The future of AI interaction is real-time, multimodal, and conversational. ADK Bidi-streaming makes it accessible today.
