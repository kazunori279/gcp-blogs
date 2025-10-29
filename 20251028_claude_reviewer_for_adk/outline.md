# Supercharge Tech Writing with Claude Code Subagents and Agent Skills

- Challenge: improving my past article on ADK Bidi-streaming
  - https://google.github.io/adk-docs/streaming/custom-streaming-ws/
  - I wanted to update the content for the latest ADK version
  - I wanted to improve the writing and code snippet quality

- Challenges of high-quality tech writing
  - Needs a deep review by a professional editor for consistent writing and styling
  - Needs a deep review by a professional code reviewer for code snippets with consistent coding practice
  - Needs a deep review by a subject matter expert (supervisor). In this case, they need source code level knowledge on adk-python SDK, Gemini Live API and Vertex AI Live API and how these APIs interact

- Solution: use Claude Code Subagents and Agent Skills
  - What are they
    - Claude Code Subagents: https://docs.claude.com/en/docs/claude-code/sub-agents
    - Claude Code Agent Skills: https://docs.claude.com/en/docs/claude-code/skills
  - Strategy:
    - Define a Subagent [docs-reviewer agent](.claude/agents/docs-reviewer.md) who plays the role of the professional editor and code reviewer
    - Define a Subagent [adk-reviewer agent](.claude/agents/adk-reviewer.md) who plays the role of the ADK expert who has the following Agent Skills:
      - Agent Skill [google-adk](.claude/skills/google-adk/SKILL.md)
      - Agent Skill [gemini-live-api](.claude/skills/gemini-live-api/SKILL.md)
      - Agent Skill [vertexai-live-api](.claude/skills/vertexai-live-api/SKILL.md)
      - See also: https://medium.com/google-cloud/supercharge-adk-development-with-claude-code-skills-d192481cbe72
  - Claude on Vertex AI: https://docs.claude.com/en/api/claude-on-vertex-ai
      - To integrate the billing to Vertex AI

- Writing and coding review process with `docs-reviewer` agent
  - Use `docs-reviewer` agent for the article on Claude Code
  - An example of [Review report](reviews/docs_review_report_custom-streaming-ws_20251028-162615)
  - Review the issues one by one. Let Claude Code fix the issue based on the recommendation options

Review process example on C2:

```
Excellent! I've successfully fixed C2. Here's a summary of the changes made:

  C2 Fix Summary

  Issue: Incomplete Import in Session Resumption Section - The session resumption section showed importing from google.genai import types but this import was not shown in the main imports
  section.

  Changes Made:

  1. Added types import to main imports (custom-streaming-ws.md:204):
    - Added from google.genai import types to the main imports section so it's consistent throughout the document
  2. Removed duplicate import instruction (custom-streaming-ws.md:290-298):
    - Removed the separate "Import the required types" step from the Session Resumption section
    - Updated the text to directly mention configuring RunConfig without the separate import step
    - Added a blank line before the code block for proper markdown formatting

  Result: Now all code examples consistently reference types.SessionResumptionConfig() and the types import is properly shown in the main imports section at the beginning of the code
  walkthrough.
```

Review process example on W1:

```
W1 Fix Summary

  Issue: Inconsistent Heading Level Structure - Section headings used inconsistent levels with some subsections using ### while function descriptions also used ###, creating unclear hierarchy.

  Changes Made:

  1. Function/code example headings changed from ### to ####:
    - start_agent_session(session_id, is_audio=False) (line 228)
    - agent_to_client_messaging(websocket, live_events) (line 323)
    - client_to_agent_messaging(websocket, live_request_queue) (line 383)
  2. Session Resumption subsections changed from ###/#### to ####/#####:
    - Session Resumption Configuration changed to #### (line 286)
    - Enabling Session Resumption changed to ##### (line 290)
    - Session Resumption Features changed to ##### (line 301)
    - Implementation Notes changed to ##### (line 308)
    - Troubleshooting changed to ##### (line 315)

  Final Hierarchy:
  - # - Main title
  - ## - Major sections (Install, Platform Setup, Interact, Server Code, Client Code, Summary)
  - ### - Conceptual subsections (ADK Streaming Setup, FastAPI Web Application, Prerequisites, WebSocket Handling, Audio Handling)
  - #### - Function/code titles and major configuration sections
  - ##### - Sub-subsections within configuration sections

  Result: Consistent heading hierarchy throughout the document that clearly distinguishes between conceptual sections, function definitions, and detailed subsections.
```

```
W3 Fix Summary

  Issue: Missing Cross-References - References to related content didn't follow consistent format, with awkward wording and unclear cross-reference style.

  Changes Made:

  1. Improved SSE version cross-reference (line 14):
    - Before: There is also a [SSE](custom-streaming.md) version of the sample is available.
    - After: > **Learn More:** An [SSE (Server-Sent Events) version](custom-streaming.md) of this sample is also available.

  Improvements:
    - Fixed awkward grammar ("There is also a... is available")
    - Used blockquote format (>) for consistent "Learn More" callout style
    - Expanded "SSE" acronym to "Server-Sent Events" for clarity
    - Made the sentence more natural and readable
  2. Image paths review:
    - Reviewed image paths at ../assets/quickstart-streaming-tool.png and other locations
    - Left unchanged as they appear to be correct for the current deployment structure
    - Note added in commit message for future verification if deployment location changes

  Result: Cross-references now follow a consistent, professional format with clear callout styling that improves document navigation and readability.
```

- ADK related review process with `adk-reviewer` agent
  - Use `adk-reviewer` agent for the article on Claude Code
  - An example of [Review report](reviews/adk_review_report_custom-streaming-ws_20251028-163305.md)
  - Review the issues one by one. Let Claude Code fix the issue based on the recommendation options

Review process example with C1:

```
Perfect! I've successfully updated the article to address the critical issue C1 from the review report. The change replaces the deprecated session parameter with the current user_id and
  session_id parameters in the run_live() call.

  Summary of changes:

  - File: article_after_review/custom-streaming-ws.md:313-318
  - Fix: Updated runner.run_live() call to use:
    - user_id=user_id instead of session=session
    - session_id=session.id to pass the session ID extracted from the created session object

  This aligns the code with the current ADK API signature and removes the use of the deprecated parameter that triggers a DeprecationWarning in ADK version 1.10.0+.
```

```
For W2, is it possible that the partial=True text event could lose final text chunk? Check with the google-adk skill.
```

```
Perfect! The comment at lines 122-123 confirms: "The text should not partial and the returned LlmResponse is not be partial."

  So the flow for run_live() with TEXT mode is:

  1. Multiple events with partial=True - Each contains a text chunk
  2. ONE final event with partial=None/False - Contains the COMPLETE accumulated text (line 182-184)
  3. ONE turn_complete event - Signals the turn is done

  This means W2 is CORRECT - we need to handle both partial and complete text events. However, since the final complete text contains ALL the text already sent in partials, we should be careful
  about duplication.

  Let me write the corrected recommendation based on this understanding:

  Based on my thorough analysis of the ADK source code, W2 is correct but needs refinement. Here's what I found:

  Critical Finding

  The current code pattern in the article (and in the official ADK examples) DOES miss the final complete text event. However, this may or may not be a problem depending on the use case.

  How ADK Text Streaming Works (run_live() mode)

  From gemini_llm_connection.py:145-189:

  1. Partial events (partial=True): Individual text chunks as they arrive
  2. Complete event (partial=False/None): Final event with COMPLETE ACCUMULATED TEXT sent when turn_complete arrives
  3. Turn complete event: Signals the end of the turn

  The Issue

  The current pattern only sends partial=True events:
  if part.text and event.partial:
      # Sends incremental chunks

  This misses the final complete text event that contains the full accumulated response.

  However, There's a Nuance

  Since the complete event contains text that was already sent incrementally via partial events, sending it would cause duplication on the client side. The current pattern actually avoids 
  duplication by only showing the streaming chunks.

  Recommendation for the Article

  Option 1: Keep current behavior but document it (Recommended)

  The current code is actually intentional to avoid duplication. Add a comment explaining this:

  # If it's text and a partial text, send it for streaming display
  # Note: We only send partial=True events to show incremental streaming.
  # A final event with partial=False containing the complete text is also
  # sent by ADK, but we skip it here to avoid duplication since the client
  # has already received all chunks via partial events.
  if part.text and event.partial:
      message = {
          "mime_type": "text/plain",
          "data": part.text
      }
      await websocket.send_text(json.dumps(message))
      print(f"[AGENT TO CLIENT]: text/plain: {message}")

  Option 2: Handle both and mark them differently

  If you want to send both for client-side flexibility:

  # Handle both partial and complete text events
  if part.text:
      message = {
          "mime_type": "text/plain",
          "data": part.text,
          "partial": event.partial if event.partial is not None else False
      }
      await websocket.send_text(json.dumps(message))
      print(f"[AGENT TO CLIENT]: text/plain (partial={event.partial}): {message}")

  Then update the client to handle duplicates or use the partial flag to decide whether to append or replace.

  My recommendation: Use Option 1 - the current code avoids duplication and works correctly for streaming. Just add documentation to explain why only partial=True is handled.
```
