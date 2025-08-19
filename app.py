# app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, File, Depends, UploadFile, HTTPException, APIRouter
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

import asyncio, time

from fpdf import FPDF
from sqlalchemy.orm import Session

from detection.video_processor import VideoProcessor
from detection.audio_processor import AudioProcessor
from services.db_sqlalchemy import EngagementMetric, AudioTranscript, get_db  # <
from services.engagement_service import save_engagement_metrics

from typing import Dict

# =========================
# App Setup
# =========================
app = FastAPI(title="EngageTrack API (per-participant WS)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allowing all for testing
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()

video_processors: Dict[str, VideoProcessor] = {}
last_active: Dict[str, float] = {}
processors_lock = asyncio.Lock()
PROCESSOR_IDLE_TIMEOUT = 60
cleanup_task = None

try:
    audio_proc = AudioProcessor()
except Exception as e:
    audio_proc = None
    print(f"Warning: Audio processor not initialized: {e}")

# =========================
# Startup / Shutdown
# =========================
@app.on_event("startup")
async def start_cleanup_task():
    global cleanup_task
    cleanup_task = asyncio.create_task(_cleanup_inactive_processors_loop())
    print("Cleanup task started.")

@app.on_event("shutdown")
async def shutdown_cleanup_task():
    global cleanup_task
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
    async with processors_lock:
        for pid, proc in list(video_processors.items()):
            try:
                proc.close()
            except Exception:
                pass
            video_processors.pop(pid, None)
            last_active.pop(pid, None)
    print("Shutdown complete: processors closed.")

async def _cleanup_inactive_processors_loop():
    try:
        while True:
            now = time.time()
            evict = []
            async with processors_lock:
                for pid, ts in list(last_active.items()):
                    if now - ts > PROCESSOR_IDLE_TIMEOUT:
                        evict.append(pid)
                for pid in evict:
                    proc = video_processors.pop(pid, None)
                    last_active.pop(pid, None)
                    if proc:
                        try:
                            proc.close()
                        except Exception:
                            pass
                        print(f"Evicted processor for participant {pid} due to inactivity.")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        return

# =========================
# Endpoints
# =========================
@app.get("/health")
async def health():
    return {"status": "running"}

@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...), db=Depends(get_db)):
    contents = await file.read()
    proc = VideoProcessor()
    try:
        result = await asyncio.to_thread(proc.process_frame_bytes, contents)
        metric = EngagementMetric(
            meeting_id="single_frame_test",
            participant_id="single_participant",
            attention_instant=result["attention_instant"],
            fatigue_instant=result["fatigue_instant"],
            hand_instant=result["hand_instant"],
            events_logged=result["events_logged"]
        )
        db.add(metric)
        db.commit()
    finally:
        try:
            proc.close()
        except Exception:
            pass
    return JSONResponse(result)

@app.post("/analyze_audio")
async def analyze_audio(file: UploadFile = File(...), 
                        meeting_id: str = Query(...),
                        participant_id: str = Query(...),
                        db=Depends(get_db)):
    if audio_proc is None:
        raise HTTPException(status_code=503, detail="Audio processor not available")
    contents = await file.read()
    try:
        result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)
        transcript = AudioTranscript(
            meeting_id=meeting_id,
            participant_id=participant_id,
            transcript=" ".join([r["text"] for r in result]),
            raw_events=result
            )

        db.add(transcript)
        db.commit()
        return JSONResponse({"transcriptions": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# @app.websocket("/ws/frames")
# async def websocket_frames(websocket: WebSocket, 
#                            meeting_id: str = Query(...),
#                            participant_id: str = Query(...),
#                            db=Depends(get_db)):
#     await websocket.accept()
#     proc = None
#     try:
#         async with processors_lock:
#             proc = video_processors.get(participant_id)
#             if proc is None:
#                 proc = VideoProcessor()
#                 video_processors[participant_id] = proc
#             last_active[participant_id] = time.time()

#         while True:
#             frame_bytes = await websocket.receive_bytes()
#             async with processors_lock:
#                 last_active[participant_id] = time.time()
#             try:
#                 result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)
#                 metric = EngagementMetric(
#                     meeting_id=meeting_id,
#                     participant_id=participant_id,
#                     attention_instant=result["attention_instant"],
#                     fatigue_instant=result["fatigue_instant"],
#                     hand_instant=result["hand_instant"],
#                     events_logged=result["events_logged"]
#                 )
#                 db.add(metric)
#                 db.commit()
#             except Exception as e:
#                 await websocket.send_json({"error": str(e)})
#                 continue

#             result_with_meta = {"participant_id": participant_id, "analysis": result}
#             await websocket.send_json(result_with_meta)

#     except WebSocketDisconnect:
#         async with processors_lock:
#             last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
#         print(f"WS disconnected: {participant_id}")
#     except Exception as e:
#         print("WS error for participant", participant_id, ":", e)
#         try:
#             await websocket.close()
#         except Exception:
#             pass
#         async with processors_lock:
#             last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1

@router.post("/webhook/frames")
async def receive_frame(
    payload: dict,
    meeting_id: str = Query(...),
    participant_id: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    Expects JSON body like:
    { "frame": "data:image/jpeg;base64,......" }
    """

    # Validate incoming payload
    if "frame" not in payload:
        raise HTTPException(status_code=400, detail="Missing 'frame' in body")

    dataurl = payload["frame"]
    try:
        # Remove the prefix 'data:image/jpeg;base64,'
        base64_string = dataurl.split(",", 1)[1]
        frame_bytes = base64.b64decode(base64_string)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid base64 string")

    # Obtain or create processor
    try:
        proc = video_processors.get(participant_id)
        if proc is None:
            proc = VideoProcessor()
            video_processors[participant_id] = proc

        # Process frame
        result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)

        # Save metric
        metric = EngagementMetric(
            meeting_id=meeting_id,
            participant_id=participant_id,
            attention_instant=result["attention_instant"],
            fatigue_instant=result["fatigue_instant"],
            hand_instant=result["hand_instant"],
            events_logged=result["events_logged"]
        )
        db.add(metric)
        db.commit()

    except Exception as e:
        # Rollback to keep DB clean if commit fails
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

    return {"status": "received", "analysis": result}

# @app.get("/meetings/{meeting_id}/summary/pdf")
# def get_meeting_summary_pdf(meeting_id: str, db: Session = Depends(get_db)):
#     # Query engagement metrics
#     metrics = db.query(EngagementMetric).filter_by(meeting_id=meeting_id).all()
#     transcripts = db.query(AudioTranscript).filter_by(meeting_id=meeting_id).all()

#     # Aggregate engagement data
#     total_events = len(metrics)
#     focused_count = sum(1 for m in metrics if m.attention_instant == "Focused")
#     distracted_count = total_events - focused_count
#     fatigue_count = sum(1 for m in metrics if "Fatigue" in m.fatigue_instant)
#     hand_raises = sum(1 for m in metrics if m.hand_instant == "Hand Raised")

#     # Build PDF
#     pdf = FPDF()
#     pdf.add_page()
#     pdf.set_font("Arial", "B", 16)
#     pdf.cell(0, 10, f"Meeting Summary - {meeting_id}", ln=True)

#     pdf.set_font("Arial", "", 12)
#     pdf.cell(0, 8, f"Total frames: {total_events}", ln=True)
#     pdf.cell(0, 8, f"Focused: {focused_count} ({focused_count/total_events:.1%})", ln=True)
#     pdf.cell(0, 8, f"Distracted: {distracted_count} ({distracted_count/total_events:.1%})", ln=True)
#     pdf.cell(0, 8, f"Fatigue events: {fatigue_count}", ln=True)
#     pdf.cell(0, 8, f"Hand raises: {hand_raises}", ln=True)
#     pdf.ln(5)

#     pdf.set_font("Arial", "B", 14)
#     pdf.cell(0, 10, "Transcript:", ln=True)
#     pdf.set_font("Arial", "", 11)

#     for t in transcripts:
#         pdf.multi_cell(0, 8, f"[{t.participant_id}] {t.transcript}")

#     # Save PDF
#     filename = f"/tmp/{meeting_id}_summary.pdf"
#     pdf.output(filename)

#     return FileResponse(filename, media_type="application/pdf", filename=f"{meeting_id}_summary.pdf")

@app.get("/meetings/{meeting_id}/summary/pdf")
def get_meeting_summary_pdf(meeting_id: str, db: Session = Depends(get_db)):
    metrics = db.query(EngagementMetric).filter_by(meeting_id=meeting_id).all()
    transcripts = db.query(AudioTranscript).filter_by(meeting_id=meeting_id).all()

    # Aggregate engagement data
    total_events = len(metrics)
    focused_count = sum(1 for m in metrics if m.attention_instant == "Focused")
    distracted_count = total_events - focused_count
    fatigue_count = sum(1 for m in metrics if "Fatigue" in m.fatigue_instant)
    hand_raises = sum(1 for m in metrics if m.hand_instant == "Hand Raised")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Meeting Summary - {meeting_id}", ln=True)

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 8, f"Total frames: {total_events}", ln=True)

    # Avoid division by zero
    if total_events > 0:
        pdf.cell(0, 8, f"Focused: {focused_count} ({focused_count/total_events:.1%})", ln=True)
        pdf.cell(0, 8, f"Distracted: {distracted_count} ({distracted_count/total_events:.1%})", ln=True)
    else:
        pdf.cell(0, 8, f"Focused: {focused_count} (0%)", ln=True)
        pdf.cell(0, 8, f"Distracted: {distracted_count} (0%)", ln=True)

    pdf.cell(0, 8, f"Fatigue events: {fatigue_count}", ln=True)
    pdf.cell(0, 8, f"Hand raises: {hand_raises}", ln=True)
    pdf.ln(5)

    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, "Transcript:", ln=True)
    pdf.set_font("Arial", "", 11)

    for t in transcripts:
        pdf.multi_cell(0, 8, f"[{t.participant_id}] {t.transcript}")

    filename = f"/tmp/{meeting_id}_summary.pdf"
    pdf.output(filename)

    return FileResponse(filename, media_type="application/pdf", filename=f"{meeting_id}_summary.pdf")


