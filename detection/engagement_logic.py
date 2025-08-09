import time
from collections import deque
from config import *  # import thresholds

class EngagementLogic:
    def __init__(self, logger_callback):
        self.logger = logger_callback

        # Attention tracking
        self._current_attention_state = "Focused"
        self._distraction_start_time = 0
        self.last_logged_attention_state = "Focused"

        # Hand tracking
        self.hand_events_deque = deque()
        self.hand_cooldown_end_time = 0
        self.last_hand_raised_log_time = 0

        # Fatigue tracking
        self.yawn_events_deque = deque()
        self.yawn_cooldown_end_time = 0

        self.blink_events_deque = deque()
        self.blink_cooldown_end_time = 0

        # Raw blink/yawn detection state
        self._is_eye_closed = False
        self._frames_eye_closed = 0
        self._is_mouth_open = False
        self._frames_mouth_open = 0

    def _now(self):
        return time.time()

    def update_attention(self, is_currently_focused: bool, current_yaw: float, current_pitch: float):
        now = self._now()
        if self._current_attention_state == "Focused":
            if not is_currently_focused:
                self._distraction_start_time = now
                self._current_attention_state = "Distracted"
        elif self._current_attention_state == "Distracted":
            if is_currently_focused:
                self._current_attention_state = "Focused"
            else:
                distraction_duration = now - self._distraction_start_time
                if distraction_duration >= ATTENTION_CONSISTENCY_SECONDS:
                    direction = ""
                    if abs(current_yaw) > ATTENTION_YAW_THRESHOLD:
                        direction = "sideways"
                    if abs(current_pitch) < PITCH_FOCUSED_MIN_ABS_THRESHOLD:
                        if current_pitch > 0:
                            direction = "down" if not direction else direction + " and down"
                        else:
                            direction = "up" if not direction else direction + " and up"
                    log_description = f"Distracted (looking {direction})" if direction else "Distracted"
                    self.logger(event_type="Attention", description=log_description, timestamp=now)
                    self.last_logged_attention_state = log_description
                    self._current_attention_state = "Logged_Distraction"
        elif self._current_attention_state == "Logged_Distraction":
            if is_currently_focused:
                self.logger(event_type="Attention", description="Focused", timestamp=now)
                self.last_logged_attention_state = "Focused"
                self._current_attention_state = "Focused"

    def detect_and_register_blink(self, ear):
        now = self._now()
        if now < self.blink_cooldown_end_time:
            return
        if ear < EAR_THRESHOLD:
            self._frames_eye_closed += 1
            if not self._is_eye_closed and self._frames_eye_closed >= EAR_CONSEC_FRAMES_CLOSED:
                self._is_eye_closed = True
        else:
            if self._is_eye_closed:
                if self._frames_eye_closed >= EAR_CONSEC_FRAMES_CLOSED:
                    self.blink_events_deque.append(now)
                    while self.blink_events_deque and now - self.blink_events_deque[0] > FATIGUE_BLINK_WINDOW_SECONDS:
                        self.blink_events_deque.popleft()
                    if len(self.blink_events_deque) >= FATIGUE_BLINK_COUNT:
                        self.logger(event_type="Fatigue", description="Blink: tired fatigue", timestamp=now)
                        self.blink_cooldown_end_time = now + FATIGUE_BLINK_COOLDOWN_SECONDS
                self._is_eye_closed = False
            self._frames_eye_closed = 0

    def detect_and_register_yawn(self, mar):
        now = self._now()
        if now < self.yawn_cooldown_end_time:
            return
        if mar > MAR_THRESHOLD:
            self._frames_mouth_open += 1
            if not self._is_mouth_open and self._frames_mouth_open >= MAR_CONSEC_FRAMES_OPEN:
                self._is_mouth_open = True
        else:
            if self._is_mouth_open:
                if self._frames_mouth_open >= MAR_CONSEC_FRAMES_OPEN:
                    self.yawn_events_deque.append(now)
                    while self.yawn_events_deque and now - self.yawn_events_deque[0] > FATIGUE_YAWN_WINDOW_SECONDS:
                        self.yawn_events_deque.popleft()
                    if len(self.yawn_events_deque) >= FATIGUE_YAWN_COUNT:
                        self.logger(event_type="Fatigue", description="Yawning", timestamp=now)
                        self.yawn_cooldown_end_time = now + FATIGUE_YAWN_COOLDOWN_SECONDS
                self._is_mouth_open = False
            self._frames_mouth_open = 0

    def register_hand_event(self, is_hand_raised_now: bool, hand_positions_std: float):
        now = self._now()
        if is_hand_raised_now and now - self.last_hand_raised_log_time > HAND_RAISE_COOLDOWN_SECONDS:
            self.logger(event_type="Hand Motion", description="Hand Raised", timestamp=now)
            self.last_hand_raised_log_time = now
            self.hand_cooldown_end_time = now + HAND_MOVEMENT_COOLDOWN_SECONDS
            return
        if now < self.hand_cooldown_end_time:
            return
        self.hand_events_deque.append(now)
        while self.hand_events_deque and now - self.hand_events_deque[0] > HAND_MOVEMENT_WINDOW_FRAMES / VIDEO_FPS_TARGET:
            self.hand_events_deque.popleft()
        if len(self.hand_events_deque) >= (HAND_MOVEMENT_WINDOW_FRAMES / VIDEO_FPS_TARGET) * 1 and            hand_positions_std > HAND_MOVEMENT_STD_THRESHOLD:
            self.logger(event_type="Hand Motion", description="Hand Detected", timestamp=now)
            self.hand_cooldown_end_time = now + HAND_MOVEMENT_COOLDOWN_SECONDS
