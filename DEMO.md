# ShopSphere Voice Support Demo Script (5-Minute Live Walkthrough)

This guide provides a step-by-step walkthrough to present the live Voice Customer Support Agent demo smoothly.

---

## Preparation
1. Ensure the local stack is running:
   - Backend: `http://localhost:8000` (FastAPI)
   - Frontend: `http://localhost:3000` (Next.js)
2. Open `http://localhost:3000` in Google Chrome or Microsoft Edge.
3. Keep your microphone unmuted and volume at a comfortable level.

---

## Scenario A: The Happy Path — Return & Refund (2 Minutes)

1. **Select Order:**
   - On the homepage dashboard, find order **`ORD-1001`** (Sony WH-1000XM5 Headphones - Delivered 2 days ago).
   - Click **View Details**.
2. **Start Voice Call:**
   - Click the prominent purple **"Speak to Support"** button.
   - The pre-call modal will appear. Review the consent notice and click **"Start Voice Call"**.
   - When the browser prompts for microphone permission, click **"Allow"**.
3. **Conversation with Maya:**
   - **Maya Greets:** *"Hello Aarav, I see you are calling about your Sony WH-1000XM5 headphones. How can I help you today?"*
   - **You Say:** *"Hi Maya, the left ear cup arrived cracked and broken. I want to return it."*
   - **Maya Confirms Reason & Address:** Maya expresses empathy, confirms your Indiranagar address, and checks the return window.
   - **You Say:** *"Yes, please pick it up from my Indiranagar address tomorrow afternoon."*
   - **Maya Reads Back Confirmation:** Maya reads back the item, pickup slot (Thursday afternoon), and refund amount (₹24,990 to original UPI). Notice the on-screen **Confirmation Card** appears.
   - **You Say:** *"Yes, please go ahead."* (Or tap the on-screen **Confirm (Yes)** button).
4. **Receipt & Closing:**
   - Maya arranges the pickup and processes the refund.
   - She slowly reads out the Pickup ID (`PKP-...`) and Refund ID (`REF-...`).
   - The **Call Summary Card** displays on screen with reference numbers and copy buttons.
   - Rate the call 5 stars and click **"Back to Order Details"**.

---

## Scenario B: Barge-In Interruption (1 Minute)

1. On order **`ORD-1002`** (Espresso Coffee Maker - In Transit, Delayed 6 Days), click **"Speak to Support"**.
2. **You Ask:** *"Where is my order?"*
3. Maya will begin explaining the tracking details and the weather delay at the Pune logistics hub.
4. **Interrupt Maya Mid-Sentence:**
   - Speak naturally over her: *"Wait, can I just cancel it?"*
   - Or click the amber **"Interrupt Maya"** button.
5. **Expected Behavior:**
   - Audio playback halts immediately (under 300 ms).
   - The previous agent speech bubble in the transcript is marked with an amber **"Interrupted"** tag.
   - Maya cleanly pivots and responds to your new question: gently explaining that in-transit shipments cannot be cancelled mid-route, and offering refusal at delivery or a delay compensation voucher.

---

## Scenario C: Human Escalation (1 Minute)

1. On any order, click **"Speak to Support"**.
2. **You Say:** *"This is completely unacceptable! I've been waiting for weeks and I want to speak to a manager right now!"*
3. **Expected Behavior:**
   - Maya stays calm and empathetic. She does not argue or mirror hostility.
   - She calls `escalate_to_human`, creates an escalation ticket (`TKT-...`), and tells you a senior specialist will call you back within 30 minutes during business hours.
   - The summary card marks the call as **ESCALATED** with ticket details.

---

## Scenario D: Failure Fallback & Resilient Degraded Mode (1 Minute)

1. Open the hidden **"Demo Controls"** panel in the bottom-right corner.
2. Toggle **"Simulate TTS Crash"** and click **"Apply Failure Hooks"**.
3. Now speak or type to Maya: *"What is the status of my order?"*
4. **Expected Behavior:**
   - Maya detects that TTS channels have failed.
   - A yellow banner appears: *"Voice is currently unavailable; continuing in typed text."*
   - The call **does not crash or disconnect**. Maya continues answering via rolling typed chat without losing any order context.

