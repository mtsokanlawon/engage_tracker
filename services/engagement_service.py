# services/engagement_service.py
from sqlalchemy.orm import Session
from db_sqlalchemy import EngagementMetric, AudioTranscript
from datetime import datetime

def save_engagement_metrics(db: Session, meeting_id: str, participant_id: str, metrics: dict):
    record = EngagementMetric(
        meeting_id=meeting_id,
        participant_id=participant_id,
        timestamp=datetime.utcnow(),
        attention_instant=metrics.get("attention_instant"),
        fatigue_instant=metrics.get("fatigue_instant"),
        hand_instant=metrics.get("hand_instant"),
        events_logged=metrics.get("events_logged", [])
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

def save_audio_transcript(db: Session, meeting_id: str, participant_id: str, transcript_text: str, raw_events=None):
    record = AudioTranscript(
        meeting_id=meeting_id,
        participant_id=participant_id,
        timestamp=datetime.utcnow(),
        transcript=transcript_text,
        raw_events=raw_events or {}
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record
