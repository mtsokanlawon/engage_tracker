import tempfile
import os
from datetime import datetime

class AudioProcessor:
    def __init__(self, model_name="base", device="cpu"):
        self.model_name = model_name
        self.device = device
        self.model = None  # Delay loading until needed

    def _load_model(self):
        if self.model is None:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.model_name, device=self.device, compute_type="int8")

    def transcribe_bytes(self, audio_bytes):
        self._load_model()
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
