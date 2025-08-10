# generate_token.py
import jwt
import time

# === Your JAAS credentials ===
APP_ID = "vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc"  # from JAAS console
PRIVATE_KEY_PATH = "Key 8_10_2025, 1_40_57 PM.pk"  # path to your private key file

def generate_token(room_name, is_moderator=False, user_name="Guest"):
    with open(PRIVATE_KEY_PATH, "r") as f:
        private_key = f.read()

    now = int(time.time())
    payload = {
        "aud": "jitsi",  # audience is always 'jitsi'
        "iss": APP_ID,   # your AppID
        "sub": "meet.jit.si",  # subdomain for JAAS
        "room": room_name,
        "exp": now + 3600,  # token expires in 1 hour
        "moderator": is_moderator,
        "context": {
            "user": {
                "name": user_name,
                "email": "guest@example.com",
                "avatar": "https://example.com/avatar.png"
            }
        }
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token

if __name__ == "__main__":
    # Example usage:
    print("Host Token:")
    print(generate_token("EngageTrackRoomDemo123", is_moderator=True, user_name="Host"))

    print("\nAttendee Token:")
    print(generate_token("EngageTrackRoomDemo123", is_moderator=False, user_name="Student1"))
