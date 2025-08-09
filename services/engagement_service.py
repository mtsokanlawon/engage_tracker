import datetime

async def save_engagement_metrics(db_writer, meeting_id, participant_id, result):
    """
    db_writer: callable that will handle saving to DB
    result: dict from VideoProcessor.process_frame_bytes
    """
    data = {
        "meeting_id": meeting_id,
        "participant_id": participant_id,
        "timestamp": datetime.utcnow(),
        "attention_instant": result["attention_instant"],
        "fatigue_instant": result["fatigue_instant"],
        "hand_instant": result["hand_instant"],
        "events_logged": result["events_logged"]
    }
    await db_writer(data)
