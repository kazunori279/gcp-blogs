# ADK Bidi-Streaming Cheatsheet: A Visual Guide to Real-Time Multimodal AI Agent Development

Google recently published a comprehensive 5-part developer guide for building real-time voice and video AI applications with the [Agent Development Kit (ADK)](https://google.github.io/adk-docs/). The [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) covers everything from architecture fundamentals to production deployment:

- **[Part 1: Introduction to ADK Bidi-streaming](https://google.github.io/adk-docs/streaming/dev-guide/part1/)** — Architecture overview, Live API platforms, and the 4-phase application lifecycle
- **[Part 2: Sending Messages with LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)** — Upstream flow for text, audio, video, and activity signals
- **[Part 3: Event Handling with run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/)** — Downstream events, tool execution, and multi-agent workflows
- **[Part 4: Understanding RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/)** — Session management, quotas, and production controls
- **[Part 5: How to Use Audio, Image and Video](https://google.github.io/adk-docs/streaming/dev-guide/part5/)** — Multimodal capabilities, model architectures, and advanced features

The guide also includes a working demo application—a FastAPI-based WebSocket server with a web UI that showcases the complete streaming lifecycle:

![ADK Bidi-streaming Demo](assets/bidi-demo-screen.png)

**[bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo)**: Real-time bidirectional streaming with text, audio, and image input, automatic transcription, and Google Search integration.

In this post, we provide a visual summary of the key concepts as a cheatsheet for ADK Bidi-streaming development, so that you can quickly grasp the breadth and depth of ADK Bidi-streaming functionalities.

## Understanding the Architecture

The first step to mastering ADK Bidi-streaming is understanding how the pieces connect. The architecture follows a clear [separation of concerns](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview) across three domains.

![ADK Bidi-streaming High-Level Architecture](assets/Bidi_arch.jpeg)

This architecture diagram reveals the elegant layering that makes ADK powerful:

**Developer Provided (Application Layer)**: You build and own the client applications (web, mobile) and the transport layer (WebSocket/SSE server using frameworks like FastAPI). You also define your [Agent](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent) with custom instructions, tools, and behaviors.

**ADK Provided (Framework Layer)**: ADK handles the complex orchestration through four key components:
- **[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)**: Buffers and sequences incoming user messages
- **[Runner](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner)**: Orchestrates agent sessions and manages conversation state
- **LLM Flow**: Manages the processing pipeline (internal, not directly used)

**Google Provided (AI Services)**: The [Live API](https://google.github.io/adk-docs/streaming/dev-guide/part1/#12-gemini-live-api-and-vertex-ai-live-api) (either [Gemini Live API](https://ai.google.dev/gemini-api/docs/live) via AI Studio or [Vertex AI Live API](https://cloud.google.com/vertex-ai/generative-ai/docs/live-api) via Google Cloud) provides real-time, low-latency AI processing.

The arrows in the diagram show the bidirectional flow—messages travel from client through ADK to the Live API, while responses stream back in real-time. This concurrent two-way communication is what enables natural, [interruption-capable conversations](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag).

## Why ADK Over Raw Live API?

If you've worked with the raw Gemini Live API directly, you know the implementation burden. This comparison makes the [value proposition](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications) crystal clear.

![Raw Live API vs. ADK Bidi-streaming](assets/live_vs_adk.png)

ADK transforms complexity into simplicity across six critical areas:

- **Agent Framework** — Build from scratch vs. ready-made single/multi-agent with tools, evaluation, and security
- **[Tool Execution](https://google.github.io/adk-docs/streaming/dev-guide/part3/#automatic-tool-execution-in-run_live)** — Manual handling vs. automatic execution and orchestration
- **[Connection Management](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption)** — Manual reconnection vs. automatic session resumption
- **[Event Model](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class)** — Custom structures vs. unified, typed Event model with metadata
- **Async Framework** — Manual coordination vs. [LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/) and [run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/) async generator
- **[Session Persistence](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice)** — Manual implementation vs. built-in (SQL, Vertex AI, In-memory)

The bottom line: **ADK reduces months of infrastructure development to declarative configuration.** You focus on agent behavior and user experience, not streaming plumbing.

## The Four-Phase Application Lifecycle

Every ADK Bidi-streaming application follows a predictable [four-phase lifecycle](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle). Understanding these phases helps you structure your code correctly.

![ADK Bidi-streaming Application Lifecycle](assets/app_lifecycle.png)

**[Phase 1: Application Initialization](https://google.github.io/adk-docs/streaming/dev-guide/part1/#phase-1-application-initialization) (Once at Startup)**

When your application starts, you create the foundational components that will be reused across all sessions:
- **[Create Agent](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-agent)**: Define your AI's model, tools, and instructions
- **[Create SessionService](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-sessionservice)**: Set up state storage (in-memory for dev, database for production)
- **[Create Runner](https://google.github.io/adk-docs/streaming/dev-guide/part1/#define-your-runner)**: Initialize the orchestrator that manages sessions

**[Phase 2: Session Initialization](https://google.github.io/adk-docs/streaming/dev-guide/part1/#phase-2-session-initialization) (Per User Connection)**

Each time a user connects, you establish their streaming session:
- **[Get/Create Session](https://google.github.io/adk-docs/streaming/dev-guide/part1/#get-or-create-session)**: Restore context or create fresh conversation
- **[Create RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-runconfig)**: Configure modalities (audio/text), transcription, and features
- **[Create LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part1/#create-liverequestqueue)**: Set up the message buffer
- **Start [run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/#how-run_live-works) Event Loop**: Begin bidirectional streaming

**[Phase 3: Bidi-streaming Loop](https://google.github.io/adk-docs/streaming/dev-guide/part1/#phase-3-bidi-streaming-with-run_live-event-loop) (Active Communication)**

This is where the magic happens—concurrent two-way flow:
- **Upstream**: Client [sends messages](https://google.github.io/adk-docs/streaming/dev-guide/part1/#send-messages-to-the-agent) through Queue to Agent
- **Downstream**: Agent [responds through Events](https://google.github.io/adk-docs/streaming/dev-guide/part1/#receive-and-process-events) to Client
- **[Interruption](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag)**: Users can interrupt mid-response, just like natural conversation

**[Phase 4: Terminate Session](https://google.github.io/adk-docs/streaming/dev-guide/part1/#phase-4-terminate-live-api-session) (Connection End)**

Clean shutdown when the session ends:
- [Close LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals) (sends graceful termination signal)
- Stop run_live() loop
- Persist session state for future resumption

The arrow from Phase 4 back to Phase 2 shows how users can reconnect and resume conversations—session state persists across connections.

## Upstream Flow: LiveRequestQueue

The upstream path—from your application to the AI—flows through the [LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/#liverequestqueue-and-liverequest). This single interface handles all message types elegantly.

![ADK Bidi-Streaming: Upstream Flow with LiveRequestQueue](assets/live_req_queue.png)

The diagram shows four input types, each with its corresponding method:

- **[`send_content(Content)`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_content-sends-text-with-turn-by-turn)** — Turn-by-turn text messages
- **[`send_realtime(Blob)`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#send_realtime-sends-audio-image-and-video-in-real-time)** — Real-time audio/video chunks
- **[`send_activity_start/end()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#activity-signals)** — Manual turn control (push-to-talk)
- **[`close()`](https://google.github.io/adk-docs/streaming/dev-guide/part2/#control-signals)** — Graceful session termination

**Key Design Principles** (shown at the bottom of the infographic):
- **Asyncio-based**: Built on Python's asyncio.Queue for non-blocking operations
- **[Thread-safe within event loop](https://google.github.io/adk-docs/streaming/dev-guide/part2/#concurrency-and-thread-safety)**: Safe for concurrent access from the same thread
- **[FIFO ordering](https://google.github.io/adk-docs/streaming/dev-guide/part2/#message-ordering-guarantees)**: Messages processed in the order sent
- **Graceful termination**: close() signals clean shutdown

The flow is beautifully simple: your application calls the appropriate method, it's wrapped in a LiveRequest container, and serialized to the Gemini Live API over WebSocket.

## Downstream Flow: The run_live() Method

The downstream path—from the AI back to your application—centers on the [`run_live()`](https://google.github.io/adk-docs/streaming/dev-guide/part3/) async generator. This comprehensive diagram captures everything you need to know.

![Comprehensive Summary of ADK Live Event Handling: The run_live() Method](assets/run_live.png)

**The [run_live() Mechanism](https://google.github.io/adk-docs/streaming/dev-guide/part3/#how-run_live-works)** (left side):

The method takes three inputs:
- **Identity**: `user_id` and `session_id` to identify the conversation
- **Channel**: `live_request_queue` for upstream messages
- **Configuration**: `run_config` for streaming behavior

It functions as an async generator, yielding [Event objects](https://google.github.io/adk-docs/streaming/dev-guide/part3/#the-event-class) without buffering—you get responses in real-time as they're generated.

**[Event Types and Handling](https://google.github.io/adk-docs/streaming/dev-guide/part3/#event-types-and-handling)** (right side):

Seven event types you'll encounter:

- **[Text Event](https://google.github.io/adk-docs/streaming/dev-guide/part3/#text-events)** — `event.content.parts[0].text`, partial not saved
- **[Audio Event (Inline)](https://google.github.io/adk-docs/streaming/dev-guide/part3/#audio-events)** — `event.content.parts[0].inline_data`, ephemeral (never saved)
- **[Audio Event (File)](https://google.github.io/adk-docs/streaming/dev-guide/part3/#audio-events-with-file-data)** — `event.content.parts[0].file_data`, saved if `save_live_blob=True`
- **[Transcription](https://google.github.io/adk-docs/streaming/dev-guide/part3/#transcription-events)** — `event.input/output_transcription`, final saved
- **[Metadata](https://google.github.io/adk-docs/streaming/dev-guide/part3/#metadata-events)** — `usage_metadata.total_token_count`, always saved
- **[Tool Call/Response](https://google.github.io/adk-docs/streaming/dev-guide/part3/#tool-call-events)** — `function_call`, `function_response`, always saved
- **[Error](https://google.github.io/adk-docs/streaming/dev-guide/part3/#error-events)** — `event.error_code`, `event.error_message`, saved (logged)

**[Conversation Flow Control Flags](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-text-events)**:
- [`partial`](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-partial): True for incremental chunks, False for complete merged text
- [`interrupted`](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-interrupted-flag): True when user interrupted mid-response
- [`turn_complete`](https://google.github.io/adk-docs/streaming/dev-guide/part3/#handling-turn_complete-flag): True when model finished its response

**[Automatic Tool Execution](https://google.github.io/adk-docs/streaming/dev-guide/part3/#automatic-tool-execution-in-run_live)**:

ADK handles tool calls automatically—you define tools on your Agent, and ADK:
1. Detects function calls from the model
2. Executes tools in parallel
3. Formats and sends responses back
4. Yields both call and response events

**[Multi-Agent Workflows](https://google.github.io/adk-docs/streaming/dev-guide/part3/#best-practices-for-multi-agent-workflows)**:

For [SequentialAgent](https://google.github.io/adk-docs/streaming/dev-guide/part3/#sequentialagent-with-bidi-streaming) patterns, the diagram shows transparent transitions within a single `run_live()` loop. Events flow seamlessly across agent boundaries.

## Configuring Sessions with RunConfig

[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/) is your control center for streaming behavior. This infographic maps all the parameters and their purposes.

![Comprehensive Summary of Live API RunConfig](assets/runconfig.png)

**[Key RunConfig Parameters](https://google.github.io/adk-docs/streaming/dev-guide/part4/#runconfig-parameter-quick-reference)**:

- **[`response_modalities`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#response-modalities)** — Output format: `["TEXT"]` or `["AUDIO"]` (one per session)
- **[`streaming_mode`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#streamingmode-bidi-or-sse)** — BIDI (WebSocket) or SSE (HTTP streaming)
- **[`session_resumption`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption)** — Enables automatic reconnection across ~10min timeouts
- **[`context_window_compression`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-context-window-compression)** — Removes duration limits, manages token limits
- **[`max_llm_calls`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#max_llm_calls)** — Limits calls per invocation (SSE only)
- **[`save_live_blob`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#save_live_blob)** — Persists audio/video for debugging/compliance
- **[`custom_metadata`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#custom_metadata)** — Attaches tracking data to events
- **[`support_cfc`](https://google.github.io/adk-docs/streaming/dev-guide/part4/#support_cfc-experimental)** — Enables compositional function calling (Gemini 2.x)

**[Streaming Modes: BIDI vs. SSE](https://google.github.io/adk-docs/streaming/dev-guide/part4/#streamingmode-bidi-or-sse)**:

- **BIDI**: WebSocket to Live API, real-time audio/video, interruptions, [VAD](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-activity-detection-vad)
- **SSE**: HTTP streaming to standard Gemini API, text-only, simpler deployment

**[Session Management](https://google.github.io/adk-docs/streaming/dev-guide/part4/#understanding-live-api-connections-and-sessions)**:

The diagram illustrates two critical concepts:
- **[ADK Session](https://google.github.io/adk-docs/streaming/dev-guide/part4/#adk-session-vs-live-api-session)** (persistent): Survives restarts, stored in SessionService
- **[Live API Session](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-connections-and-sessions)** (ephemeral): Created/destroyed per `run_live()` call

**Session Duration Controls**:
1. **[Session Resumption](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-session-resumption)**: Automatically reconnects when ~10min WebSocket timeout hits
2. **[Context Window Compression](https://google.github.io/adk-docs/streaming/dev-guide/part4/#live-api-context-window-compression)**: Summarizes older history, enables unlimited duration

**[Concurrent Session Quotas](https://google.github.io/adk-docs/streaming/dev-guide/part4/#concurrent-live-api-sessions-and-quota-management)**:

- **Gemini Live API** — 50 (Tier 1) to 1,000 (Tier 2+) concurrent sessions
- **Vertex AI Live API** — Up to 1,000 per project

**[Architectural Patterns](https://google.github.io/adk-docs/streaming/dev-guide/part4/#architectural-patterns-for-managing-quotas)**:
- **Direct Mapping**: Simple 1:1 user-to-session for small apps
- **Session Pooling**: Queue users when quota exceeded for production scale

## Multimodal Capabilities

ADK Bidi-streaming isn't just about text—it's a full [multimodal platform](https://google.github.io/adk-docs/streaming/dev-guide/part5/). This final infographic covers audio, image, video, and advanced features.

![Comprehensive Summary of ADK Live API Multimodal Capabilities](assets/multimodal.png)

**[Audio Capabilities](https://google.github.io/adk-docs/streaming/dev-guide/part5/#how-to-use-audio)**:

- **[Input](https://google.github.io/adk-docs/streaming/dev-guide/part5/#sending-audio-input)** — 16-bit PCM, Mono, 16kHz, chunked streaming (50-100ms recommended)
- **[Output](https://google.github.io/adk-docs/streaming/dev-guide/part5/#receiving-audio-output)** — 16-bit PCM, Mono, 24kHz, ring buffer playback via AudioWorklet

The waveform visualization shows natural voice conversations with sub-second latency.

**[Image and Video](https://google.github.io/adk-docs/streaming/dev-guide/part5/#how-to-use-image-and-video)**:

Both images and video are processed as JPEG frames:
- **Format**: JPEG (`image/jpeg`)
- **Frame Rate**: 1 FPS maximum (not suitable for action recognition)
- **Resolution**: 768x768 recommended

The canvas capture flow shows: Video → Canvas → JPEG → ADK Live API.

**[Audio Model Architectures](https://google.github.io/adk-docs/streaming/dev-guide/part5/#understanding-audio-model-architectures)**:

- **[Native Audio](https://google.github.io/adk-docs/streaming/dev-guide/part5/#native-audio-models)** — End-to-end, natural prosody, extended voices, affective dialog (`gemini-2.5-flash-native-audio-preview`)
- **[Half-Cascade](https://google.github.io/adk-docs/streaming/dev-guide/part5/#half-cascade-models)** — Text intermediate, robust tool execution, TEXT/AUDIO support (`gemini-2.0-flash-live-001`, deprecated Dec 2025)

**Advanced Audio Features**:

1. **[Audio Transcription](https://google.github.io/adk-docs/streaming/dev-guide/part5/#audio-transcription)**: Enabled by default, delivers `types.Transcription` objects
2. **[Voice Activity Detection (VAD)](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-activity-detection-vad)**: Enabled by default for natural turn-taking
3. **[Voice Configuration (Speech Config)](https://google.github.io/adk-docs/streaming/dev-guide/part5/#voice-configuration-speech-config)**: Agent-level or RunConfig-level voice selection
4. **[Proactivity & Affective Dialog](https://google.github.io/adk-docs/streaming/dev-guide/part5/#proactivity-and-affective-dialog)**: Native audio only—model offers suggestions, adapts to emotions

## Putting It All Together

These infographics tell a cohesive story about ADK Bidi-streaming:

1. **[Architecture](https://google.github.io/adk-docs/streaming/dev-guide/part1/#14-adk-bidi-streaming-architecture-overview)** separates concerns cleanly—you own the application, ADK handles orchestration, Google provides AI
2. **[ADK vs Raw API](https://google.github.io/adk-docs/streaming/dev-guide/part1/#13-adk-bidi-streaming-for-building-realtime-agent-applications)** comparison shows the dramatic reduction in implementation complexity
3. **[Lifecycle](https://google.github.io/adk-docs/streaming/dev-guide/part1/#15-adk-bidi-streaming-application-lifecycle)** gives you the mental model for structuring your code
4. **[LiveRequestQueue](https://google.github.io/adk-docs/streaming/dev-guide/part2/)** simplifies all upstream communication to four methods
5. **[run_live()](https://google.github.io/adk-docs/streaming/dev-guide/part3/)** handles all downstream events through a single async generator
6. **[RunConfig](https://google.github.io/adk-docs/streaming/dev-guide/part4/)** provides declarative control over every aspect of streaming behavior
7. **[Multimodal](https://google.github.io/adk-docs/streaming/dev-guide/part5/)** capabilities enable voice, video, and advanced conversational AI features

The result? You can build production-ready real-time AI applications in days instead of months. The [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) provides the complete implementation details—from [FastAPI WebSocket servers](https://google.github.io/adk-docs/streaming/dev-guide/part1/#fastapi-application-example) to [client-side AudioWorklet processors](https://google.github.io/adk-docs/streaming/dev-guide/part5/#handling-audio-input-at-the-client)—to turn these concepts into working code.

## Getting Started

Ready to build? Here's your path forward:

1. **Read the full guide**: The [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) covers Parts 1-5 in detail
2. **Run the demo**: The [bidi-demo](https://github.com/google/adk-samples/tree/main/python/agents/bidi-demo) provides a working FastAPI implementation
3. **Explore ADK docs**: The [official ADK documentation](https://google.github.io/adk-docs/) covers agents, tools, sessions, and more

The future of AI interaction is real-time, multimodal, and conversational. ADK Bidi-streaming makes it accessible today.

---

*This article is part of the [ADK Bidi-streaming Developer Guide](https://google.github.io/adk-docs/streaming/dev-guide/part1/) series. For the complete technical documentation with code samples, see [Part 1](https://google.github.io/adk-docs/streaming/dev-guide/part1/), [Part 2](https://google.github.io/adk-docs/streaming/dev-guide/part2/), [Part 3](https://google.github.io/adk-docs/streaming/dev-guide/part3/), [Part 4](https://google.github.io/adk-docs/streaming/dev-guide/part4/), and [Part 5](https://google.github.io/adk-docs/streaming/dev-guide/part5/) of the guide.*
