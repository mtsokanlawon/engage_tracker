import jwt
import time

# ==== CONFIGURATION ====
APP_ID = "vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc"        # JAAS AppID
API_KEY_ID = "vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc/b7e0d2"  # JAAS API Key ID
PRIVATE_KEY_FILE = "Key 8_10_2025, 1_40_57 PM.pk"  # Path to your private key
ROOM_NAME = "*"     # "*" for all rooms
USER_NAME = "EngageTrack Bot"
IS_MODERATOR = False
TOKEN_EXPIRY_SECONDS = 3600

# ==== READ PRIVATE KEY ====
with open(PRIVATE_KEY_FILE, "r") as f:
    private_key = f.read()

# ==== JWT PAYLOAD ====
now = int(time.time())
payload = {
    "aud": "jitsi",
    "iss": "chat",              # <-- FIXED: Always "chat"
    "sub": APP_ID,               # Your JAAS AppID here
    "room": ROOM_NAME,
    "moderator": IS_MODERATOR,
    "context": {
        "user": {
            "name": USER_NAME,
            "email": "bot@example.com"
        },
        "features": {           # <-- FIXED: Added features object
            "recording": True,
            "livestreaming": True,
            "screen-sharing": True,
            "outbound-call": True,
            "transcription": True
        }
    },
    "exp": now + TOKEN_EXPIRY_SECONDS,
    "nbf": now
}

# ==== JWT HEADERS ====
headers = {
    "alg": "RS256",
    "kid": API_KEY_ID
}

# ==== GENERATE TOKEN ====
token = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
print("\n=== JAAS JWT Token ===\n")
print(token)
print("\nCopy this token into your HTML config.\n")
