# db_writer.py
import asyncio
from services.db_sqlalchemy import save_engagement_sqlalchemy, save_transcript_sqlalchemy
from datetime import datetime

async def save_engagement(data):
    """
    data: dict with keys:
      - meeting_id (str)
      - participant_id (str)
      - attention_instant (str or float)
      - fatigue_instant (str or float)
      - hand_instant (str or float)
      - events_logged (list)
    """
    # Extract metrics you want to save as float values or convert accordingly
    metrics = {
        "attention_instant": data.get("attention_instant", "0"),
        "fatigue_instant": data.get("fatigue_instant", "0"),
        "hand_instant": data.get("hand_instant", "0"),
    }

    # Convert non-float values if possible (like strings "Focused" or "Distracted") to floats
    # Or just store string metric_type with float metric_value when meaningful
    # Here, we'll store 1.0 for positive states, 0.0 otherwise as example

    def convert_metric(value):
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            # example mapping
            if value.lower() in ("focused", "normal", "hand detected", "hand raised"):
                return 1.0
            elif value.lower() in ("distracted", "potential fatigue", "fatigue detected", "no hand detected"):
                return 0.0
        return 0.0

    metrics = {k: convert_metric(v) for k, v in metrics.items()}

    # Save engagement metrics in thread (blocking SQLAlchemy call)
    await asyncio.to_thread(
        save_engagement_sqlalchemy,
        data["meeting_id"],
        data["participant_id"],
        metrics,
    )

async def save_transcript(data):
    """
    data: dict with keys:
      - meeting_id (str)
      - participant_id (str)
      - transcript_text (str)
      - start_time (float, optional)
      - end_time (float, optional)
    """
    await asyncio.to_thread(
        save_transcript_sqlalchemy,
        meeting_id=data["meeting_id"],
        participant_id=data["participant_id"],
        transcript_text=data.get("transcript_text", ""),
        start_time=data.get("start_time"),
        end_time=data.get("end_time"),
    )
