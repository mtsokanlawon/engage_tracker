# app.py
import asyncio
import time
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, File, Depends, UploadFile, HTTPException
from fastapi.responses import JSONResponse

from services.engagement_service import save_engagement_metrics

# from services.db_stub import db_writer_stub  # swap with real writer in production
# =======
from services.db_sqlalchemy import (
    save_engagement_sqlalchemy as db_writer_stub,
    save_transcript_sqlalchemy
)


app = FastAPI(title="EngageTrack API (per-participant WS)")

# Map participant_id -> VideoProcessor instance (lazy-created)
video_processors: Dict[str, object] = {}
# Map participant_id -> last active timestamp (epoch seconds)
last_active: Dict[str, float] = {}
# Lock to protect shared maps
processors_lock = asyncio.Lock()

# Idle timeout (seconds) after which a participant processor will be evicted
PROCESSOR_IDLE_TIMEOUT = 60  # adjust as needed

# Background cleanup task handle
cleanup_task = None

# Lazy audio processor handle (don't instantiate at startup)
audio_proc = None


@app.on_event("startup")
async def start_cleanup_task():
    global cleanup_task
    cleanup_task = asyncio.create_task(_cleanup_inactive_processors_loop())
    app.logger = app.logger if hasattr(app, "logger") else None
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

    # Close all remaining processors
    async with processors_lock:
        for pid, proc in list(video_processors.items()):
            try:
                await _close_processor(proc)
            except Exception:
                pass
            video_processors.pop(pid, None)
            last_active.pop(pid, None)
    print("Shutdown complete: processors closed.")


async def _cleanup_inactive_processors_loop():
    """
    Periodically evict idle participants to free resources.
    """
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
                            await _close_processor(proc)
                        except Exception:
                            pass
                        print(f"Evicted processor for participant {pid} due to inactivity.")
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        return


async def _close_processor(proc):
    """
    Close MediaPipe/OpenCV resources for a VideoProcessor instance.
    This is run in a thread because close() may be blocking native code.
    """
    if proc is None:
        return
    # if the proc exposes 'close', call it in a thread
    close_fn = getattr(proc, "close", None)
    if close_fn is None:
        return
    await asyncio.to_thread(close_fn)


@app.get("/health")
async def health():
    return {"status": "running"}


@app.post("/analyze_frame")
async def analyze_frame(file: UploadFile = File(...)):
    """
    HTTP endpoint for single-frame analysis.
    Lazy-imports VideoProcessor to avoid loading heavy libs on startup.
    """
    contents = await file.read()
    # lazy import & create one-off processor
    from detection.video_processor import VideoProcessor  # local import (lazy)
    proc = None
    try:
        proc = VideoProcessor()
        result = await asyncio.to_thread(proc.process_frame_bytes, contents)
    finally:
        # ensure release of resources
        if proc:
            try:
                await _close_processor(proc)
            except Exception:
                pass
    return JSONResponse(result)


# @app.post("/analyze_audio")

# async def analyze_audio(
#                         file: UploadFile = File(...),
#                         meeting_id: str = Query(...),
#                         participant_id: str = Query(...)
#                         ):
#     """
#     Lazy-initialize the AudioProcessor only when audio is requested.
#     """
#     global audio_proc
#     #=======
#     # async def analyze_audio(
#     #     file: UploadFile = File(...), 
#     #     meeting_id: str = Query(...),
#     #     participant_id: str = Query(...)
#     # ):
#     #     if audio_proc is None:
#     #         raise HTTPException(status_code=503, detail="Audio processor not available")

#     contents = await file.read()

#     if audio_proc is None:
#         # local import to avoid heavy model load at startup
#         from detection.audio_processor import AudioProcessor  # lazy import
#         try:
#             audio_proc = AudioProcessor()  # may load model (heavy)
#         except Exception as e:
#             raise HTTPException(status_code=503, detail=f"Audio processor init error: {e}")

#     try:
#         # run transcription in thread (CPU-bound/blocking)
#         result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)

#         trasncript_text = " ".join(
#             seg["text"] if isinstance(seg, dict) and "text" in seg else str(seg)
#             for seg in result
#         )

#         # Save transcript to DB
#         save_transcript_sqlalchemy(
#             meeting_id=meeting_id,
#             participant_id=participant_id,
#             transcript_text=trasncript_text
#         )

        
#         return JSONResponse({"transcriptions": result})
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# @app.post("/analyze_audio")
# async def analyze_audio(
#     file: UploadFile = File(...),
#     meeting_id: str = Query(...),
#     participant_id: str = Query(...)
# ):
#     global audio_proc
#     print("=== analyze_audio request started ===")

#     contents = await file.read()
#     print(f"Read {len(contents)} bytes from uploaded file")

#     if audio_proc is None:
#         print("Audio processor not loaded, attempting init...")
#         from detection.audio_processor import AudioProcessor
#         try:
#             audio_proc = AudioProcessor()
#             print("Audio processor loaded successfully")
#         except Exception as e:
#             print("Audio processor failed to load:", e)
#             raise HTTPException(status_code=503, detail=f"Audio processor init error: {e}")

#     print("Running transcription...")
#     try:
#         result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)
#         print("Transcription finished")

#         trasncript_text = " ".join(
#             seg["text"] if isinstance(seg, dict) and "text" in seg else str(seg)
#             for seg in result
#         )

#         # Save transcript to DB
#         save_transcript_sqlalchemy(
#             meeting_id=meeting_id,
#             participant_id=participant_id,
#             transcript_text=trasncript_text
#         )

        
#         return JSONResponse({"transcriptions": result})

#     except Exception as e:
#         print("Transcription error:", e)
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze_audio")
async def analyze_audio(
    file: UploadFile = File(...),
    meeting_id: str = Query(...),
    participant_id: str = Query(...)
):
    print("=== analyze_audio request started ===")

    contents = await file.read()
    print(f"Read {len(contents)} bytes from uploaded file")

    print("Running transcription...")
    try:
        # Create a new instance per request (no global)
        from detection.audio_processor import AudioProcessor  # lazy import
        audio_proc = AudioProcessor(model_name="models/tiny", device="cpu")

        # Run transcription in a thread to avoid blocking
        result = await asyncio.to_thread(audio_proc.transcribe_bytes, contents)
        print("Transcription finished")

        transcript_text = " ".join(
            seg[1] if isinstance(seg, tuple) else str(seg)
            for seg in result
        )

        # Save transcript to DB
        save_transcript_sqlalchemy(
            meeting_id=meeting_id,
            participant_id=participant_id,
            transcript_text=transcript_text
        )

        return JSONResponse({"transcriptions": result})

    except Exception as e:
        print("Transcription error:", e)
        raise HTTPException(status_code=500, detail=str(e))



def get_db_writer():
    """
    Dependency to provide the DB writer function.
    Replace with actual DB writer in production.
    """
    return db_writer_stub


@app.websocket("/ws/frames")
async def websocket_frames(
    websocket: WebSocket,
    meeting_id: str = Query(...),
    participant_id: str = Query(...),
    db_writer=Depends(get_db_writer),
):
    """
    WebSocket endpoint for per-participant real-time frame analysis.

    Connect as:
      wss://host/ws/frames?meeting_id=room123&participant_id=user456
    """
    await websocket.accept()
    proc = None

    try:
        # create or fetch participant processor (lazy)
        async with processors_lock:
            proc = video_processors.get(participant_id)
            if proc is None:
                # lazy import VideoProcessor only when needed
                from detection.video_processor import VideoProcessor  # lazy import
                proc = VideoProcessor()
                video_processors[participant_id] = proc
            last_active[participant_id] = time.time()

        while True:
            # Receive binary frame bytes (blocks until a message)
            try:
                frame_bytes = await websocket.receive_bytes()
            except Exception as e:
                # non-bytes or connection error
                raise

            # update last active timestamp
            async with processors_lock:
                last_active[participant_id] = time.time()

            # Offload CPU-bound processing to thread
            try:
                result = await asyncio.to_thread(proc.process_frame_bytes, frame_bytes)
            except Exception as e:
                # respond with error but keep connection open
                await websocket.send_json({"error": str(e)})
                continue

            # Persist metrics via provided db_writer (db_writer can be sync or async)
            try:
                # Allow db_writer to be async or sync callable
                if asyncio.iscoroutinefunction(db_writer):
                    await db_writer({
                        "meeting_id": meeting_id,
                        "participant_id": participant_id,
                        "timestamp": time.time(),
                        "attention_instant": result.get("attention_instant"),
                        "fatigue_instant": result.get("fatigue_instant"),
                        "hand_instant": result.get("hand_instant"),
                        "events_logged": result.get("events_logged"),
                    })
                else:
                    # run sync writer in thread to avoid blocking
                    await asyncio.to_thread(db_writer, {
                        "meeting_id": meeting_id,
                        "participant_id": participant_id,
                        "timestamp": time.time(),
                        "attention_instant": result.get("attention_instant"),
                        "fatigue_instant": result.get("fatigue_instant"),
                        "hand_instant": result.get("hand_instant"),
                        "events_logged": result.get("events_logged"),
                    })
            except Exception as e:
                # log writer error and continue; don't crash the WS
                try:
                    await websocket.send_json({"db_error": str(e)})
                except Exception:
                    pass

            # Send analysis result back to the client
            result_with_meta = {"participant_id": participant_id, "analysis": result}
            await websocket.send_json(result_with_meta)

    except WebSocketDisconnect:
        # client disconnected; free resources promptly
        async with processors_lock:
            proc = video_processors.pop(participant_id, None)
            last_active.pop(participant_id, None)
        if proc:
            try:
                await _close_processor(proc)
            except Exception:
                pass
        print(f"WS disconnected: {participant_id}")
    except Exception as e:
        # unexpected error: try to close proc and websocket
        print("WS error for participant", participant_id, ":", e)
        try:
            async with processors_lock:
                proc = video_processors.pop(participant_id, None)
                last_active.pop(participant_id, None)
            if proc:
                await _close_processor(proc)
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass