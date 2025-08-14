import tempfile, os
from faster_whisper import WhisperModel
from datetime import datetime

class AudioProcessor:
    def __init__(self, model_name="models/tiny", device="cpu"):
        try:
            self.model = WhisperModel(model_name, device=device, compute_type="int8")
        except Exception as e:
            raise RuntimeError(f"Could not load Whisper model: {e}")

    def transcribe_bytes(self, audio_bytes):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp_path = tmp.name
            tmp.write(audio_bytes)
        try:
            segments, _ = self.model.transcribe(tmp_path)
            results = []
            for seg in segments:
                ts = datetime.now().strftime("%H:%M:%S")
                results.append((ts, seg.text.strip()))
            return results
        finally:
            try:
                os.remove(tmp_path)
            except:
                pass
