from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import uuid
from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class CallLog(Base):
    __tablename__ = "calls"

    id           = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    call_sid     = Column(String, unique=True, index=True)
    caller_number= Column(String, index=True)
    duration_seconds = Column(Integer, default=0)
    transcript   = Column(JSON, default=list)      # list of {role, content} dicts
    summary      = Column(Text)
    intent       = Column(String)                  # book_meeting | faq | complaint | support
    outcome      = Column(String)                  # meeting_booked | transferred | resolved | callback
    meeting_id   = Column(String, nullable=True)   # Google Calendar event ID
    urgent       = Column(Boolean, default=False)
    created_at   = Column(DateTime, default=datetime.utcnow)
    ended_at     = Column(DateTime, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
