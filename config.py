from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Anthropic (Claude) ────────────────────────────────────────────────
    anthropic_api_key: str

    # ── Twilio ────────────────────────────────────────────────────────────
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str          # e.g. +14155551234

    # ── ElevenLabs ────────────────────────────────────────────────────────
    elevenlabs_api_key: str
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # Rachel — change to any voice

    # ── OpenAI (Whisper STT) ──────────────────────────────────────────────
    openai_api_key: str

    # ── Google Calendar ───────────────────────────────────────────────────
    google_credentials_path: str = "google_credentials.json"
    google_token_path: str = "google_token.json"
    google_calendar_id: str = "primary"
    team_email: str = "team@yourstartup.com"

    # ── Slack ─────────────────────────────────────────────────────────────
    slack_webhook_url: str

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = "postgresql://user:password@localhost/ai_receptionist"

    # ── App ───────────────────────────────────────────────────────────────
    base_url: str                     # your ngrok or production URL (no trailing slash)
    company_name: str = "Acme Startup"
    receptionist_name: str = "Alex"
    business_hours: str = "Monday to Friday, 9 AM to 6 PM Pacific Time"

    class Config:
        env_file = ".env"


settings = Settings()
