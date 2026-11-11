# Architectural & Implementation Decisions

## 1. SDK Verifications & Surfaces

### 1.1 Google Antigravity SDK (`google-antigravity` 0.1.23)
- **Module Import:** The package installs under namespace `google.antigravity`.
- **Agent Initialization:** Verified `from google.antigravity import Agent, LocalAgentConfig`.
- **Context Management:** `Agent` is an asynchronous context manager (`async with Agent(config) as agent:`). Session lifecycle is bounded within this context manager.
- **Streaming & Interaction:** `agent.chat(prompt)` returns `ChatResponse`.
  - `ChatResponse` implements `__aiter__` which yields conversational text token deltas (`async for delta in response:`).
  - `response.chunks` yields semantic chunks (`Text`, `Thought`, `ToolCall`, `ToolResult`).
  - `await response.text()` returns full aggregated response text.
  - `await response.cancel()` cleanly aborts active in-flight stream (used for barge-in cancellation).
- **Authentication:** `api_key` mode with `LocalAgentConfig(api_key=..., model='gemini-3.5-flash-lite')` authenticated and generated tokens successfully without requiring Vertex AI express mode.

### 1.2 Gnani Vachana SDK (`gnani-vachana` 0.9.0)
- **Module Import:** The package installs under namespace `gnani`, with subpackages `gnani.stt` and `gnani.tts`.
- **Realtime STT:** Uses `gnani.stt.GnaniSTTStreamClient(api_key=..., language_code=..., model='prisma-v2.5', sample_rate=16000)`. It establishes an authenticated WebSocket to `wss://api.vachana.ai/stt/v3/stream` with headers `x-api-key-id`, `lang_code`, etc. VAD and final transcripts are received on this stream.
- **Realtime TTS:** Uses `gnani.tts.GnaniTTSRealtimeClient(api_key=...)`. Streams raw audio chunks via WebSocket (`wss://api.vachana.ai/api/v1/tts`).
- **TTS Voice Selection:** Configured with `Devika` (clear, articulate female voice in `timbre-v2.5` catalog for Indian English & Hindi).
- **TTS Fallback Cascade:**
  1. WebSocket (`GnaniTTSRealtimeClient.synthesize`)
  2. SSE (`GnaniTTSStreamClient.synthesize_stream`)
  3. REST (`GnaniTTSClient.synthesize`)
  4. Text-only mode if all voice services fail.

## 2. Audio Pipeline & Transport Architecture

- **Single WebSocket Connection:** Browser connects to backend via `/ws/call/{session_id}`. Audio PCM frames flow client-to-server as binary frames; TTS audio frames flow server-to-client as binary frames preceded by JSON header metadata.
- **AudioWorklet:** Web Audio API AudioWorklet captures 16 kHz 16-bit mono PCM and emits 1,024-byte frames at real-time cadence.
- **Barge-In:** When user speech is detected during agent speaking:
  - Agent output stream is cancelled via `await response.cancel()`.
  - In-flight TTS is flushed/closed.
  - Server sends `agent_interrupted` event to browser with spoken-up-to character offset.
  - Audio playback queue in browser is immediately stopped and cleared.
- **Sentence Chunking:** Agent streaming tokens are buffered into a sentence chunker (splitting on sentence terminators `.?!\n` while respecting abbreviations and numeric amounts). Each complete sentence is immediately normalized via `tts_normalize` and passed to TTS.

## 3. Tool Idempotency & Validation

- All 5 tools (`get_order_status`, `process_refund`, `schedule_pickup`, `escalate_to_human`, `issue_voucher`, `cancel_order`) enforce order scoping (validating against session `order_id`).
- Tools are strictly idempotent: repeat calls for the same order return existing refund, pickup, or voucher IDs.
- Order state transitions are persisted in-memory (seeded from `data/orders.json`) for the duration of the server runtime.

## 4. Audio Clarity, Turn-Taking, and Anti-Repetition Rules

- **Audio Clarity & Rate Matching:** Resolved muffled voice root cause: Gnani TTS was omitting `AudioConfig` and defaulting to 48 kHz while Web Audio was playing at 24 kHz (resulting in 2x pitch drop and sluggish delivery). We explicitly set `AudioConfig(sample_rate=24000)` on all synthesis channels and selected `Devika` (crystal-clear female voice), achieving crisp, natural speech articulation.
- **Turn-Taking Half-Duplex Auto-Muting:**
  1. The agent delivers an initial 1-sentence opening greeting while the customer's mic is automatically muted.
  2. As soon as the agent finishes speaking, the customer's mic is automatically unmuted (`state: listening`, badge: *"Listening to you… (Speak now)"*), giving the customer clear floor time.
  3. When customer input is received, the mic is immediately muted while the agent processes tools and formulates a crisp reply.
  4. Once agent playback ends, the mic is unmuted again. This to-and-fro rhythm prevents speaker-to-mic echo loops and eliminates audio clipping.
- **Brevity & Anti-Hallucination:** System prompt strictly caps turns at 1 to 2 sentences, forbids repetitive greetings or repeating customer names, and only allows repeating details when the customer explicitly asks *"Could you repeat that?"*.

## 5. Customer Speech-to-Text (STT) Transmission & Silence Pacing

- **Stale Closure in AudioWorklet onmessage (Root Cause & Fix):** In `VoiceSupportModal.tsx`, `workletNode.port.onmessage` captured `isMuted` by value in its closure during initial WebSocket connection when `isMuted` was `true`. Subsequent calls to `setIsMuted(false)` updated React state but left the worklet closure checking the stale `true`, causing every microphone frame to be dropped before WebSocket transmission. We introduced `isMutedRef`, `pushToTalkRef`, and `isPressingPTTRef` (`useRef`), synchronized them with React state, and updated the AudioWorklet message handler to read from refs.
- **Web Audio Context Autoplay Resilience:** Added `ensureAudioResumed()` to unlock suspended AudioContexts on any user interaction (modal click, mic toggle, PTT hold, spacebar).
- **AudioWorklet Chromium Graph Termination:** Routed worklet node through a 0-gain node into `audioCtx.destination` to ensure the audio processing graph remains continuously scheduled in Chromium without causing speaker echo/feedback.
- **Gnani STT Inactivity Reconnect:** Gnani STT server drops idle connections after 60 seconds (`Session closed: no speech segment received for 60 seconds`). We updated `STTPipeline.send_audio` to detect inactive or closed connections and transparently reconnect before forwarding new audio frames.
- **Pacing & Anti-Repetition Buffer:** Extended silence watchdog to a generous 35-second quiet buffer before any check-in, preventing unprompted repetitive reminders while the customer is thinking.
