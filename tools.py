"""
tools.py — All tools available to the Claude receptionist agent.

Each tool has:
  1. A schema (for Claude's tool_use API)
  2. An implementation function
  3. Registration in TOOL_MAP for the dispatcher
"""

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

import httpx
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from twilio.rest import Client as TwilioClient

from config import settings
from database import SessionLocal, CallLog


# ═══════════════════════════════════════════════════════════════════════════
# TOOL SCHEMAS  (sent to Claude so it knows what tools exist)
# ═══════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "get_available_slots",
        "description": (
            "Check what meeting times are available in the calendar for a given date. "
            "Always call this BEFORE book_meeting so you can offer real options to the caller."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["date"]
        }
    },
    {
        "name": "book_meeting",
        "description": (
            "Book a meeting in Google Calendar. Use when the caller wants to schedule "
            "a demo, consultation, or appointment. Always confirm details with caller first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caller_name":      {"type": "string", "description": "Full name of the caller"},
                "caller_email":     {"type": "string", "description": "Caller's email address"},
                "preferred_date":   {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "preferred_time":   {"type": "string", "description": "Time in HH:MM 24-hour format"},
                "duration_minutes": {"type": "integer", "description": "Meeting duration (default 30)", "default": 30},
                "reason":           {"type": "string", "description": "Purpose of the meeting"}
            },
            "required": ["caller_name", "caller_email", "preferred_date", "preferred_time", "reason"]
        }
    },
    {
        "name": "notify_slack",
        "description": (
            "Send a call summary to the team Slack channel. "
            "Always call this at the end of every call, regardless of outcome."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "caller_name":   {"type": "string"},
                "caller_number": {"type": "string"},
                "summary":       {"type": "string", "description": "1-3 sentence summary of the call"},
                "intent":        {"type": "string", "description": "book_meeting | faq | complaint | support | other"},
                "outcome":       {"type": "string", "description": "meeting_booked | transferred | resolved | callback_requested"},
                "urgent":        {"type": "boolean", "description": "True if needs immediate human attention", "default": False}
            },
            "required": ["caller_name", "caller_number", "summary", "intent", "outcome"]
        }
    },
    {
        "name": "save_call_log",
        "description": (
            "Save the call record to the database. "
            "Always call this at the end of every call — it's required for billing and analytics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "call_sid":      {"type": "string"},
                "caller_number": {"type": "string"},
                "transcript":    {"type": "array",  "items": {"type": "object"},
                                  "description": "Full conversation as [{role, content}] list"},
                "summary":       {"type": "string"},
                "intent":        {"type": "string"},
                "outcome":       {"type": "string"},
                "meeting_id":    {"type": "string", "description": "Google Calendar event ID if meeting booked"}
            },
            "required": ["call_sid", "caller_number", "transcript", "summary", "intent", "outcome"]
        }
    },
    {
        "name": "transfer_to_human",
        "description": (
            "Transfer the call to a human agent. Use when: caller is upset, "
            "issue is too complex, caller explicitly requests a human, or you've tried twice and failed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason":   {"type": "string", "description": "Why the call needs a human"},
                "priority": {"type": "string", "enum": ["normal", "urgent"], "default": "normal"}
            },
            "required": ["reason"]
        }
    },
    {
        "name": "send_sms_followup",
        "description": (
            "Send an SMS to the caller with confirmation details, meeting info, or a callback link. "
            "Always send after successfully booking a meeting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to_number": {"type": "string", "description": "Caller's phone number in E.164 format"},
                "message":   {"type": "string", "description": "SMS content (keep under 160 chars)"}
            },
            "required": ["to_number", "message"]
        }
    }
]


# ═══════════════════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════

def get_available_slots(date: str) -> dict:
    """Return available 30-min meeting slots for a given date."""
    try:
        creds = _get_google_creds()
        service = build("calendar", "v3", credentials=creds)

        day_start = datetime.strptime(date, "%Y-%m-%d").replace(hour=9, minute=0, second=0)
        day_end   = day_start.replace(hour=17, minute=0)

        events_result = service.events().list(
            calendarId=settings.google_calendar_id,
            timeMin=day_start.isoformat() + "Z",
            timeMax=day_end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime"
        ).execute()

        busy_blocks = []
        for ev in events_result.get("items", []):
            start = ev.get("start", {}).get("dateTime")
            end   = ev.get("end",   {}).get("dateTime")
            if start and end:
                busy_blocks.append((
                    datetime.fromisoformat(start.replace("Z", "")),
                    datetime.fromisoformat(end.replace("Z", ""))
                ))

        # Build 30-min slots; exclude busy ones
        available = []
        slot = day_start
        while slot < day_end:
            slot_end = slot + timedelta(minutes=30)
            is_free = all(slot_end <= b[0] or slot >= b[1] for b in busy_blocks)
            if is_free:
                available.append(slot.strftime("%I:%M %p"))
            slot = slot_end

        return {"success": True, "date": date, "available_slots": available[:8]}

    except Exception as e:
        print(f"[get_available_slots] error: {e}")
        # Fallback slots so the conversation can continue
        return {
            "success": True,
            "date": date,
            "available_slots": ["10:00 AM", "11:00 AM", "2:00 PM", "3:00 PM", "4:00 PM"],
            "note": "Calendar unavailable — showing default slots"
        }


def book_meeting(
    caller_name: str,
    caller_email: str,
    preferred_date: str,
    preferred_time: str,
    reason: str,
    duration_minutes: int = 30
) -> dict:
    """Create a Google Calendar event and return the confirmation details."""
    try:
        creds = _get_google_creds()
        service = build("calendar", "v3", credentials=creds)

        start_dt = datetime.strptime(f"{preferred_date} {preferred_time}", "%Y-%m-%d %H:%M")
        end_dt   = start_dt + timedelta(minutes=duration_minutes)

        event = service.events().insert(
            calendarId=settings.google_calendar_id,
            conferenceDataVersion=1,
            body={
                "summary": f"Meeting with {caller_name} — {reason}",
                "description": (
                    f"Booked via AI Receptionist\n"
                    f"Caller: {caller_name}\n"
                    f"Email: {caller_email}\n"
                    f"Reason: {reason}"
                ),
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Los_Angeles"},
                "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "America/Los_Angeles"},
                "attendees": [
                    {"email": caller_email},
                    {"email": settings.team_email}
                ],
                "conferenceData": {
                    "createRequest": {"requestId": str(uuid.uuid4()), "conferenceSolutionKey": {"type": "hangoutsMeet"}}
                },
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "email",  "minutes": 60},
                        {"method": "popup",  "minutes": 15}
                    ]
                }
            }
        ).execute()

        meet_link = None
        conf_data = event.get("conferenceData", {})
        for ep in conf_data.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meet_link = ep.get("uri")
                break

        return {
            "success": True,
            "event_id":       event["id"],
            "event_link":     event.get("htmlLink"),
            "meet_link":      meet_link,
            "confirmed_time": start_dt.strftime("%A, %B %d at %I:%M %p"),
            "duration":       f"{duration_minutes} minutes"
        }

    except Exception as e:
        print(f"[book_meeting] error: {e}")
        return {"success": False, "error": str(e)}


async def notify_slack(
    caller_name: str,
    caller_number: str,
    summary: str,
    intent: str,
    outcome: str,
    urgent: bool = False
) -> dict:
    """Post a call summary card to the team Slack channel."""
    try:
        emoji   = "🚨" if urgent else "📞"
        color   = "#E74C3C" if urgent else "#36C5F0"
        outcome_emoji = {
            "meeting_booked":      "📅",
            "transferred":         "👤",
            "resolved":            "✅",
            "callback_requested":  "🔁"
        }.get(outcome, "📋")

        payload = {
            "attachments": [{
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"{emoji} *New call — {caller_name}* (`{caller_number}`)"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Intent:*\n{intent}"},
                            {"type": "mrkdwn", "text": f"*Outcome:*\n{outcome_emoji} {outcome}"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Summary:*\n{summary}"}
                    },
                    {
                        "type": "context",
                        "elements": [{
                            "type": "mrkdwn",
                            "text": f"AI Receptionist · {datetime.utcnow().strftime('%b %d %Y, %H:%M UTC')}"
                        }]
                    }
                ]
            }]
        }

        if urgent:
            payload["text"] = "🚨 Urgent call — needs immediate attention"

        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(settings.slack_webhook_url, json=payload)

        return {"success": r.status_code == 200}

    except Exception as e:
        print(f"[notify_slack] error: {e}")
        return {"success": False, "error": str(e)}


def save_call_log(
    call_sid: str,
    caller_number: str,
    transcript: list,
    summary: str,
    intent: str,
    outcome: str,
    meeting_id: Optional[str] = None,
    urgent: bool = False
) -> dict:
    """Persist the call record to PostgreSQL."""
    try:
        db = SessionLocal()
        log = CallLog(
            call_sid=call_sid,
            caller_number=caller_number,
            transcript=transcript,
            summary=summary,
            intent=intent,
            outcome=outcome,
            meeting_id=meeting_id,
            urgent=urgent,
            ended_at=datetime.utcnow()
        )
        db.add(log)
        db.commit()
        log_id = log.id
        db.close()
        return {"success": True, "log_id": log_id}

    except Exception as e:
        print(f"[save_call_log] error: {e}")
        return {"success": False, "error": str(e)}


def transfer_to_human(reason: str, priority: str = "normal") -> dict:
    """
    Initiate a call transfer to a human agent.
    In production: use Twilio's <Dial> TwiML verb to forward the call.
    """
    print(f"[transfer_to_human] reason='{reason}' priority={priority}")
    # TODO: signal main.py to inject <Dial> TwiML into the active call
    return {
        "success": True,
        "transfer_initiated": True,
        "reason": reason,
        "priority": priority,
        "message": "Transferring you to a team member now. Please hold."
    }


async def send_sms_followup(to_number: str, message: str) -> dict:
    """Send a follow-up SMS via Twilio."""
    try:
        client = TwilioClient(settings.twilio_account_sid, settings.twilio_auth_token)
        msg = client.messages.create(
            body=message,
            from_=settings.twilio_phone_number,
            to=to_number
        )
        return {"success": True, "message_sid": msg.sid}

    except Exception as e:
        print(f"[send_sms_followup] error: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
# TOOL DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════

TOOL_MAP = {
    "get_available_slots": get_available_slots,
    "book_meeting":        book_meeting,
    "notify_slack":        notify_slack,
    "save_call_log":       save_call_log,
    "transfer_to_human":   transfer_to_human,
    "send_sms_followup":   send_sms_followup,
}


async def execute_tool(name: str, inputs: dict) -> str:
    """
    Execute a tool by name and return a JSON string.
    Handles both sync and async tool functions transparently.
    """
    import asyncio

    fn = TOOL_MAP.get(name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {name}"})

    try:
        if asyncio.iscoroutinefunction(fn):
            result = await fn(**inputs)
        else:
            result = fn(**inputs)
    except Exception as e:
        result = {"error": str(e)}

    return json.dumps(result)


# ═══════════════════════════════════════════════════════════════════════════
# GOOGLE AUTH HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _get_google_creds() -> Credentials:
    """
    Load or refresh Google OAuth2 credentials.
    On first run this opens a browser for authorization and saves the token.
    """
    import os
    from google.oauth2.credentials import Credentials as GoogleCreds

    SCOPES = ["https://www.googleapis.com/auth/calendar"]
    creds = None

    if os.path.exists(settings.google_token_path):
        creds = GoogleCreds.from_authorized_user_file(settings.google_token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.google_credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(settings.google_token_path, "w") as f:
            f.write(creds.to_json())

    return creds
