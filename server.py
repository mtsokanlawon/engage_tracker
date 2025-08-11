import time
import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, Request, HTTPException

# ==== CONFIGURATION ====
APP_ID = "vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc"
API_KEY_ID = "vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc/b7e0d2"
PRIVATE_KEY_FILE = "Key_8_10_2025_1_40_57_PM.pk"
ROOM_NAME = "*"  # allow all rooms or specify a room name
IS_MODERATOR = True
TOKEN_EXPIRY_SECONDS = 3600


# ==== READ PRIVATE KEY ====
with open(PRIVATE_KEY_FILE, "r") as f:
    private_key = f.read()

app = FastAPI()

# Allow CORS for all origins (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/get-token")
def get_token(request: Request):  # sourcery skip: raise-from-previous-error
    try:
        user_name = request.query_params.get("user_name", "EngageTrack Participant")
        now = int(time.time())

        payload = {
            "aud": "jitsi",
            "iss": "chat",
            "sub": APP_ID,
            "room": ROOM_NAME,
            "moderator": IS_MODERATOR,
            "context": {
                "user": {
                    "name": user_name,
                    "email": f"{user_name.replace(' ', '').lower()}@example.com"
                },
                "features": {
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

        headers = {
            "alg": "RS256",
            "kid": API_KEY_ID
        }

        token = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)
        return {"token": token}

    except Exception as e:
        # Raise a HTTP 500 with detailed message
        raise HTTPException(status_code=500, detail=f"Token generation error: {str(e)}")
