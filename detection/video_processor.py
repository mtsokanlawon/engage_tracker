import cv2
import numpy as np
import mediapipe as mp
from utils.landmark_utils import get_eye_aspect_ratio, get_mouth_aspect_ratio, get_head_pose
from detection.engagement_logic import EngagementLogic
from datetime import datetime
from collections import deque

# A simple in-memory logger callback used by EngagementLogic
class SimpleLogger:
    def __init__(self):
        self.events = []
    def __call__(self, event_type, description, timestamp):
        ts_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        self.events.append((ts_str, event_type, description, ""))

# Processor class: maintains MediaPipe instances and an EngagementLogic instance
class VideoProcessor:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)
        self.mp_hands = mp.solutions.hands.Hands(max_num_hands=1)
        self.logger = SimpleLogger()
        self.logic = EngagementLogic(self._log_event)

        # Buffers similar to original
        self.ear_history = deque(maxlen=10)
        self.mar_history = deque(maxlen=10)
        self.hand_y_positions = deque(maxlen=90)

    def _log_event(self, event_type, description, timestamp):
        ts_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        self.logger.events.append((ts_str, event_type, description, ""))

    def process_frame_bytes(self, frame_bytes):
        # frame_bytes: JPEG/PNG bytes
        nparr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"error": "could not decode frame"}
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, _ = frame.shape

        face_results = self.mp_face_mesh.process(rgb_frame)
        hand_results = self.mp_hands.process(rgb_frame)

        response = {
            "attention_instant": "N/A",
            "fatigue_instant": "N/A",
            "hand_instant": "N/A",
            "events_logged": []
        }

        if face_results.multi_face_landmarks:
            lm = face_results.multi_face_landmarks[0].landmark
            coords = lambda idxs: [(int(lm[i].x * w), int(lm[i].y * h)) for i in idxs]
            left_eye_indices = [362, 385, 387, 263, 373, 380]
            right_eye_indices = [33, 160, 158, 133, 153, 144]
            mouth_indices = [61, 81, 13, 311, 402, 14]
            left_eye_coords = coords(left_eye_indices)
            right_eye_coords = coords(right_eye_indices)
            mouth_coords = coords(mouth_indices)
            ear = (get_eye_aspect_ratio(left_eye_coords) + get_eye_aspect_ratio(right_eye_coords)) / 2
            mar = get_mouth_aspect_ratio(mouth_coords)
            self.ear_history.append(ear)
            self.mar_history.append(mar)
            self.logic.detect_and_register_blink(ear)
            self.logic.detect_and_register_yawn(mar)
            pitch, yaw, roll = get_head_pose(lm, frame.shape)
            is_currently_focused = (abs(yaw) <= 25) and (abs(pitch) >= 90)
            response['attention_instant'] = 'Focused' if is_currently_focused else 'Distracted'
            self.logic.update_attention(is_currently_focused, pitch, yaw)
            if self.logic._is_eye_closed or self.logic._is_mouth_open:
                response['fatigue_instant'] = 'Potential Fatigue'
            elif self.logic.blink_cooldown_end_time > self.logic._now() or self.logic.yawn_cooldown_end_time > self.logic._now():
                response['fatigue_instant'] = 'Fatigue Detected'
            else:
                response['fatigue_instant'] = 'Normal'
        else:
            response['attention_instant'] = 'No Face Detected'
            response['fatigue_instant'] = 'N/A'
            self.logic.update_attention(False, 0, 0)
            self.ear_history.clear()
            self.mar_history.clear()
            self.hand_y_positions.clear()

        # Hand processing
        is_hand_raised_now = False
        current_hand_std = 0
        current_hand_state_instant = 'No Hand Detected'
        if hand_results.multi_hand_landmarks:
            for hand_landmarks in hand_results.multi_hand_landmarks:
                wrist_y_norm = hand_landmarks.landmark[0].y
                if face_results.multi_face_landmarks:
                    eye_y_norm = (lm[33].y + lm[263].y) / 2
                else:
                    eye_y_norm = 0.5
                if wrist_y_norm < eye_y_norm * 0.4:
                    is_hand_raised_now = True
                    current_hand_state_instant = 'Hand Raised'
                self.hand_y_positions.append(wrist_y_norm)
                if len(self.hand_y_positions) == self.hand_y_positions.maxlen:
                    current_hand_std = float(np.std(list(self.hand_y_positions)))
                    if current_hand_std > 0.04:
                        current_hand_state_instant = 'Hand Detected'
        response['hand_instant'] = current_hand_state_instant
        # Register hand event
        self.logic.register_hand_event(is_hand_raised_now, current_hand_std)

        # Attach newly logged events
        response['events_logged'] = list(self.logger.events)
        # Clear logger.events after returning (so API consumer gets only new events next call)
        self.logger.events = []
        return response
    def close(self):
        """
        Cleanly close MediaPipe resources. Call this before discarding the processor.
        """
        try:
            if hasattr(self, "mp_face_mesh") and self.mp_face_mesh is not None:
                self.mp_face_mesh.close()
        except Exception:
            pass
        try:
            if hasattr(self, "mp_hands") and self.mp_hands is not None:
                self.mp_hands.close()
        except Exception:
            pass
