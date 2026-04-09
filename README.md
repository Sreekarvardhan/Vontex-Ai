# AI Receptionist — Agentic Workflow

An autonomous AI receptionist that handles inbound business phone calls end-to-end.

## What it does
- Answers phone calls via Twilio
- Transcribes speech using OpenAI Whisper
- Reasons and responds using Anthropic Claude (agentic loop)
- Books Google Calendar meetings automatically
- Notifies team on Slack
- Logs calls to PostgreSQL
- Sends SMS confirmations via Twilio

## Tech Stack
Python · FastAPI · Anthropic Claude · Twilio · ElevenLabs · OpenAI Whisper · PostgreSQL · Google Calendar API · Slack

## Setup
1. Clone the repo
2. Copy `.env.example` to `.env` and fill in your API keys
3. Run `pip install -r requirements.txt`
4. Run `python3 main.py`

See full setup guide in the documentation.
EOF
