"""
main.py — FastAPI application.

Endpoints:
  POST /incoming-call         Twilio webhook — returns TwiML to open audio stream
  WS   /audio-stream          Live bidirectional audio WebSocket with Twilio
  GET  /calls                 Dashboard: list recent call logs
  GET  /calls/{call_sid}      Dashboard: full transcript for one call
  GET  /stats                 Dashboard: summary stats (counts, intents, outcomes)
  GET  /health                Health check
"""

import asyncio
import json
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from config import settings
from agent import ReceptionistAgent
from voice import transcribe_audio, synthesize_speech, encode_for_twilio, decode_from_twilio
from database import get_db, CallLog, create_tables

app = FastAPI(title="AI Receptionist API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# In-memory session store (swap for Redis in production)
_sessions: dict[str, ReceptionistAgent] = {}
_audio_buffers: dict[str, bytearray]    = defaultdict(bytearray)
_silence_counters: dict[str, int]       = defaultdict(int)

SILENCE_THRESHOLD_MARKS = 3   # ~1.5 seconds of Twilio "mark" events = end of speech
MIN_AUDIO_BYTES         = 1600 # ignore very short buffers (background noise)


# ═══════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    create_tables()
    print(f"✅ AI Receptionist started — {settings.company_name}")


# ═══════════════════════════════════════════════════════════════════════════
# HEALTH
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), "active_calls": len(_sessions)}


# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — TWILIO WEBHOOK: incoming call
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/incoming-call")
async def incoming_call(request: Request):
    """
    Twilio calls this when someone dials the Twilio number.
    We respond with TwiML that opens a WebSocket audio stream.
    """
    form         = await request.form()
    call_sid     = form.get("CallSid",    "unknown")
    caller_number= form.get("From",       "unknown")
    caller_city  = form.get("FromCity",   "")
    caller_state = form.get("FromState",  "")

    print(f"📞  Incoming call  |  {caller_number}  ({caller_city}, {caller_state})  |  SID: {call_sid}")

    # Create agent session for this call
    _sessions[call_sid] = ReceptionistAgent(
        call_sid=call_sid,
        caller_number=caller_number
    )

    ws_host = settings.base_url.replace("https://", "").replace("http://", "")
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{ws_host}/audio-stream">
            <Parameter name="call_sid"      value="{call_sid}"/>
            <Parameter name="caller_number" value="{caller_number}"/>
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


# ═══════════════════════════════════════════════════════════════════════════
# STEP 2-6 — WEBSOCKET: live audio stream
# ═══════════════════════════════════════════════════════════════════════════

@app.websocket("/audio-stream")
async def audio_stream(websocket: WebSocket):
    """
    Bidirectional WebSocket with Twilio Media Streams.

    Inbound:  caller's audio → STT → Claude → TTS → outbound audio
    Outbound: AI voice response bytes → back to caller via Twilio
    """
    await websocket.accept()

    call_sid : str | None = None
    stream_sid: str | None = None

    async def _speak(text: str):
        """Synthesize text and stream audio back to the caller."""
        audio = await synthesize_speech(text)
        if audio and stream_sid:
            await websocket.send_json({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": encode_for_twilio(audio)}
            })

    async def _process_buffered_audio(sid: str):
        """
        Called after silence is detected.
        Buffer → STT → Claude agentic loop → TTS → speak.
        """
        buf = bytes(_audio_buffers[sid])
        _audio_buffers[sid] = bytearray()
        _silence_counters[sid] = 0

        if len(buf) < MIN_AUDIO_BYTES:
            return

        # ── Step 3: Speech → Text ──────────────────────────────────────
        transcript = await transcribe_audio(buf)
        if not transcript:
            return
        print(f"  👤 Caller:  {transcript}")

        # ── Steps 4-5: Claude thinks + calls tools ─────────────────────
        agent = _sessions.get(sid)
        if not agent:
            return

        response_text = await agent.process_turn(transcript)
        print(f"  🤖 {settings.receptionist_name}: {response_text}")

        # ── Step 6: Text → Voice → Caller ─────────────────────────────
        await _speak(response_text)

    try:
        while True:
            raw = await websocket.receive_text()
            data  = json.loads(raw)
            event = data.get("event")

            # ── WebSocket handshake ────────────────────────────────────
            if event == "connected":
                print("  WebSocket connected to Twilio")

            # ── Stream started: call just picked up ───────────────────
            elif event == "start":
                stream_sid = data["start"]["streamSid"]
                params     = data["start"].get("customParameters", {})
                call_sid   = params.get("call_sid")
                print(f"  Stream started  |  streamSid: {stream_sid}")

                # Send opening greeting immediately
                async def _greet():
                    agent = _sessions.get(call_sid)
                    if agent:
                        greeting = await agent.process_turn("__greeting__")
                        print(f"  🤖 {settings.receptionist_name} (greeting): {greeting}")
                        await _speak(greeting)

                asyncio.create_task(_greet())

            # ── Incoming audio chunk ───────────────────────────────────
            elif event == "media":
                if not call_sid:
                    continue
                chunk = decode_from_twilio(data["media"]["payload"])
                _audio_buffers[call_sid].extend(chunk)
                _silence_counters[call_sid] = 0

            # ── Mark event: Twilio silence detection ───────────────────
            elif event == "mark":
                if not call_sid:
                    continue
                _silence_counters[call_sid] += 1

                if _silence_counters[call_sid] >= SILENCE_THRESHOLD_MARKS:
                    asyncio.create_task(_process_buffered_audio(call_sid))

            # ── Call ended ─────────────────────────────────────────────
            elif event == "stop":
                print(f"  Call ended  |  SID: {call_sid}")
                if call_sid:
                    _sessions.pop(call_sid, None)
                    _audio_buffers.pop(call_sid, None)
                    _silence_counters.pop(call_sid, None)
                break

    except WebSocketDisconnect:
        print(f"  WebSocket disconnected  |  SID: {call_sid}")
    except Exception as e:
        print(f"  WebSocket error: {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# STEPS 7-9 — handled inside tools.py (save_call_log, notify_slack, calendar)
# Those are triggered by Claude during the agentic loop above.
# ═══════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD API
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/calls")
async def list_calls(limit: int = 50, db: Session = Depends(get_db)):
    """Return recent call logs for the dashboard."""
    calls = (
        db.query(CallLog)
        .order_by(CallLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"calls": [
        {
            "id":             c.id,
            "call_sid":       c.call_sid,
            "caller_number":  c.caller_number,
            "duration":       c.duration_seconds,
            "intent":         c.intent,
            "outcome":        c.outcome,
            "summary":        c.summary,
            "urgent":         c.urgent,
            "meeting_id":     c.meeting_id,
            "created_at":     c.created_at.isoformat() if c.created_at else None
        }
        for c in calls
    ]}


@app.get("/calls/{call_sid}")
async def get_call(call_sid: str, db: Session = Depends(get_db)):
    """Return full transcript and details for a single call."""
    call = db.query(CallLog).filter(CallLog.call_sid == call_sid).first()
    if not call:
        return JSONResponse(status_code=404, content={"error": "Call not found"})
    return {
        "id":            call.id,
        "call_sid":      call.call_sid,
        "caller_number": call.caller_number,
        "duration":      call.duration_seconds,
        "transcript":    call.transcript,
        "summary":       call.summary,
        "intent":        call.intent,
        "outcome":       call.outcome,
        "urgent":        call.urgent,
        "meeting_id":    call.meeting_id,
        "created_at":    call.created_at.isoformat() if call.created_at else None,
        "ended_at":      call.ended_at.isoformat() if call.ended_at else None
    }


@app.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Aggregate stats for the dashboard overview cards."""
    from sqlalchemy import func

    total  = db.query(func.count(CallLog.id)).scalar()
    urgent = db.query(func.count(CallLog.id)).filter(CallLog.urgent == True).scalar()

    intents = (
        db.query(CallLog.intent, func.count(CallLog.id))
        .group_by(CallLog.intent)
        .all()
    )
    outcomes = (
        db.query(CallLog.outcome, func.count(CallLog.id))
        .group_by(CallLog.outcome)
        .all()
    )

    return {
        "total_calls":    total,
        "urgent_calls":   urgent,
        "intents":        {i[0]: i[1] for i in intents  if i[0]},
        "outcomes":       {o[0]: o[1] for o in outcomes if o[0]},
        "active_calls":   len(_sessions)
    }


# ═══════════════════════════════════════════════════════════════════════════
# ENTRYPOINT
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
