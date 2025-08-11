# app.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, File, Depends, UploadFile, HTTPException
from fastapi.responses import JSONResponse
import asyncio, time

from detection.video_processor import VideoProcessor
from detection.audio_processor import AudioProcessor
from services.db_sqlalchemy import EngagementMetric, AudioTranscript, get_db  # <
from services.engagement_service import save_engagement_metrics

from typing import Dict

# =========================
# App Setup
# =========================
app = FastAPI(title="EngageTrack API (per-participant WS)")

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

@app.websocket("/ws/frames")
async def websocket_frames(websocket: WebSocket, 
                           meeting_id: str = Query(...),
                           participant_id: str = Query(...),
                           db=Depends(get_db)):
    await websocket.accept()
    proc = None
    try:
        async with processors_lock:
            proc = video_processors.get(participant_id)
            if proc is None:
                proc = VideoProcessor()
                video_processors[participant_id] = proc
            last_active[participant_id] = time.time()

        while True:
            frame_bytes = await websocket.receive_bytes()
            async with processors_lock:
                last_active[participant_id] = time.time()
            try:
                result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)
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
                await websocket.send_json({"error": str(e)})
                continue

            result_with_meta = {"participant_id": participant_id, "analysis": result}
            await websocket.send_json(result_with_meta)

    except WebSocketDisconnect:
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
        print(f"WS disconnected: {participant_id}")
    except Exception as e:
        print("WS error for participant", participant_id, ":", e)
        try:
            await websocket.close()
        except Exception:
            pass
        async with processors_lock:
            last_active[participant_id] = time.time() - PROCESSOR_IDLE_TIMEOUT - 1
