# ShopSphere: Production-Grade Voice Customer Support Agent

A production-grade, multimodal voice customer support system for e-commerce. Customers can tap **"Speak to Support"** on any order page, conduct a natural, unbroken voice conversation with an AI agent (Maya), and receive written receipts and instant resolutions (refunds, pickup scheduling, delay vouchers, or specialist escalation).

Built with **Google Antigravity Agent SDK**, **Gemini Flash**, and **Gnani Vachana Voice AI** (Prisma STT + Timbre TTS).

---

## Architecture & Data Flow

```
   ┌─────────────────────────────────────────────────────────────┐
   │                    Next.js Frontend (3000)                  │
   │  Web Audio API (AudioWorklet)  │  Rolling Transcript & UI   │
   └──────────────▲───────────────────────────────┬──────────────┘
                  │ 16kHz PCM Frames (Binary)    │ JSON Events / Audio
                  │ WS: /ws/call/{session_id}     ▼
   ┌──────────────┴──────────────────────────────────────────────┐
   │                    FastAPI Backend (8000)                   │
   │                                                             │
   │  ┌────────────────────┐            ┌─────────────────────┐  │
   │  │ Gnani Vachana STT  │◄───────────┤  Call Session & WS  │  │
   │  │ (Prisma v2.5 WS)   │  Audio Up  │  Manager (State M.) │  │
   │  └─────────┬──────────┘            └──────────┬──────────┘  │
   │            │ Final Transcripts                │             │
   │            ▼                                  ▼             │
   │  ┌────────────────────┐            ┌─────────────────────┐  │
   │  │ Antigravity Agent  │───────────►│  Order Service &    │  │
   │  │ (Gemini Flash)     │ Tool Calls │  Idempotent Tools   │  │
   │  └─────────┬──────────┘            └─────────────────────┘  │
   │            │ Streaming Chunks (Sentence Chunker)            │
   │            ▼                                                │
   │  ┌────────────────────┐                                     │
   │  │  tts_normalize()   │                                     │
   │  └─────────┬──────────┘                                     │
   │            ▼                                                │
   │  ┌────────────────────┐                                     │
   │  │ Gnani Vachana TTS  │ (Cascade: WS -> SSE -> REST)        │
   │  │ (Timbre v2.5)      │─────────────────────────────────────┘
   │  └────────────────────┘
```

---

## Key Capabilities & Edge Cases Covered

1. **Sub-1.5s Voice Latency & Streaming:** Gemini tokens are pipelined into a sentence chunker that immediately streams audio to Gnani TTS sentence-by-sentence.
2. **Sub-300ms Barge-In:** Customers can interrupt at any point. Audio playback is instantly flushed, active LLM generation is cancelled, and the agent addresses the new query.
3. **Strict Order Security & Tool Truth:** All actions are scoped to the authenticated customer order. Actions are strictly idempotent. No action executes without explicit confirmation.
4. **Resilient Failure Cascades:** If WebSocket TTS encounters network issues, it cascades to SSE, then REST, and gracefully continues in typed chat without dropping the session.
5. **No Vendor Secrets in Client:** All Gnani and Gemini authentication is strictly server-side. The frontend bundle contains zero vendor credentials.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Next.js (App Router, TypeScript), TailwindCSS, Web Audio API AudioWorklet |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Asyncio, Pydantic v2 |
| **Agent** | `google-antigravity` SDK (LocalAgentConfig, Agent, Gemini Flash) |
| **Voice STT** | Gnani Vachana Prisma v2.5 (16kHz PCM stream with VAD) |
| **Voice TTS** | Gnani Vachana Timbre v2.5 (WebSocket, SSE, REST cascade) |
| **Transport** | Full-duplex WebSocket per call session (binary audio + JSON control events) |

---

## 10-Minute Local Quickstart

### Prerequisites
- Node.js 18+ and npm
- Python 3.11+
- Git

### 1. Clone & Set Up Backend Environment
```bash
# Verify backend/.env exists with valid credentials:
cp backend/.env.example backend/.env
# (Populate GEMINI_API_KEY, GNANI_API_KEY, JWT_SECRET in backend/.env)
```

### 2. Install Dependencies
```bash
# Python backend
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt # or install backend packages

# Frontend
cd frontend
npm install
cd ..
```

### 3. Run Locally

**Start Backend (Port 8000):**
```bash
# From workspace root:
.\.venv\Scripts\python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Start Frontend (Port 3000):**
```bash
# In a second terminal:
cd frontend
npm run dev
```

Open `http://localhost:3000` in Google Chrome.

---

## Docker Deployment

To spin up the entire stack with Docker Compose:
```bash
docker compose up --build -d
```
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Health check: `http://localhost:8000/healthz`

---

## Running the Automated Test Suite

### 1. Secret Scanning Test (Ensures zero vendor keys leaked)
```bash
python scripts/check_no_secrets.py
```

### 2. Unit Tests (Tool validation, idempotency, dates, normalizer, chunker)
```bash
pytest tests
```

### 3. Agent CLI Test Harness (10 complete automated customer scenarios)
```bash
python scripts/simulate_call.py
```

---

## Demo Script Walkthrough

For a 5-minute live demo covering the happy path return, barge-in interruption, escalation, and failure recovery, see [`DEMO.md`](./DEMO.md).

For architectural decisions and SDK integration notes, see [`DECISIONS.md`](./DECISIONS.md).

