# services/ai/elevenlabs_service.py
import os
import re
import json
import time
import logging
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ElevenLabs configuration
ELEVEN_MODEL_ID = "eleven_multilingual_v2"
ELEVEN_API_BASE = "https://api.elevenlabs.io"
ELEVEN_API_KEY = os.getenv("ELEVENLABS_API_KEY")
DEFAULT_VOICE_ID = os.getenv("DEFAULT_VOICE_ID", "NOpBlnGInO9m6vDvFkFC")

# Session for API calls
_session = requests.Session()
_session.headers.update({
    "xi-api-key": ELEVEN_API_KEY,
    "Content-Type": "application/json"
})


class ElevenLabsService:
    """Service for ElevenLabs API integration"""

    @staticmethod
    def log_error(where: str, resp: requests.Response):
        """Log ElevenLabs API errors"""
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        logger.error(f"[ElevenLabs]{where} status={resp.status_code} body={body}")

    @staticmethod
    def sanitize_voice_name(raw_name: str) -> str:
        """Sanitize voice name for ElevenLabs API"""
        name = re.sub(r"[^A-Za-z0-9 _-]", "", str(raw_name)).strip()
        if len(name) < 3:
            name = "Custom Character"
        return f"{name} Style"

    @staticmethod
    def personality_to_description(name: str, personality: str) -> str:
        """
        Convert personality description to voice description for ElevenLabs.
        Returns a voice description based on personality traits.
        """
        text = (personality or "").lower()
        gender = "female" if any(k in text for k in ["diva", "queen", "female", "she", "her"]) else "male"
        age = "young" if any(k in text for k in ["young", "youthful", "teen"]) else "middle-aged"

        if any(k in text for k in ["british", "uk", "london"]):
            accent = "british"
        elif any(k in text for k in ["spanish", "latin", "argentin"]):
            accent = "spanish"
        else:
            accent = "american"

        tone = "confident and bright" if any(k in text for k in ["confident", "bright", "upbeat", "lively", "pop"]) else "natural"
        pacing = "medium to fast" if any(k in text for k in ["upbeat", "lively", "pop"]) else "medium"
        emotion = "upbeat and lively" if any(k in text for k in ["upbeat", "lively", "pop"]) else "warm"

        desc = (
            f"A {gender} {age} {accent} voice. "
            f"Tone {tone}. Pacing {pacing}. Emotional color {emotion}. "
            f"Broadcast clarity. Noise suppressed. Natural, not over-acted."
        )

        # Ensure minimum length (API requires at least 20 characters)
        if len(desc) < 20:
            desc = "A natural, warm, clear speaking voice suitable for conversation. Broadcast clarity."

        return desc[:1000]

    @staticmethod
    def create_voice(name: str, description: str) -> Optional[str]:
        """
        Create a new voice using ElevenLabs text-to-voice API.

        Flow:
          1) POST /v1/text-to-voice/design  -> previews[].generated_voice_id
          2) POST /v1/text-to-voice         -> voice_id

        Returns:
            voice_id if successful, None otherwise
        """
        # Step 1: Create preview
        design_payload = {
            "voice_description": description,
            "auto_generate_text": True
        }

        r1 = _session.post(
            f"{ELEVEN_API_BASE}/v1/text-to-voice/design",
            json=design_payload,
            timeout=60
        )

        if r1.status_code != 200:
            ElevenLabsService.log_error("design", r1)
            return None

        j1 = r1.json() or {}
        previews = j1.get("previews") or []

        if not previews or not previews[0].get("generated_voice_id"):
            logger.error(f"[ElevenLabs] design returned no previews name={name} desc_head={description[:60]}")
            return None

        generated_voice_id = previews[0]["generated_voice_id"]

        # Step 2: Create actual voice
        create_payload = {
            "voice_name": ElevenLabsService.sanitize_voice_name(name),
            "voice_description": description,
            "generated_voice_id": generated_voice_id
        }

        r2 = _session.post(
            f"{ELEVEN_API_BASE}/v1/text-to-voice",
            json=create_payload,
            timeout=60
        )

        if r2.status_code != 200:
            ElevenLabsService.log_error("create", r2)
            return None

        vid = (r2.json() or {}).get("voice_id")
        logger.info(f"[create_voice] new voice_id={vid} for name={name}")
        return vid

    @staticmethod
    def tts_generate(voice_id: str, text: str) -> Tuple[Optional[bytes], Optional[dict]]:
        """
        Generate speech from text using ElevenLabs TTS.

        Returns:
            Tuple of (audio_bytes, error_dict)
            - If successful: (audio_bytes, None)
            - If failed: (None, error_dict)
        """
        url = f"{ELEVEN_API_BASE}/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": ELEVEN_API_KEY or "",
        }

        # Text length protection
        safe_text = (text or "").strip()
        if len(safe_text) > 5000:
            safe_text = safe_text[:5000]

        attempts = []

        def _call(payload, tag, timeout=120):
            r = _session.post(url, data=json.dumps(payload), timeout=timeout, headers=headers)
            rid = r.headers.get("x-request-id") or r.headers.get("x-eleven-request-id")
            ct = r.headers.get("Content-Type", "")
            prev = r.text[:500] if r.text else ""
            logger.error(f"[ElevenLabs]{tag} status={r.status_code} ct={ct} req_id={rid} prev={prev}")
            return r

        # Try 1: with specified model
        payload1 = {
            "text": safe_text,
            "model_id": ELEVEN_MODEL_ID,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        r1 = _call(payload1, "tts-try1")
        if r1.status_code == 200:
            return r1.content, None
        attempts.append(("try1", r1.status_code, r1.text[:500]))

        # Try 2: without model_id (server auto-selects)
        payload2 = dict(payload1)
        payload2.pop("model_id", None)
        r2 = _call(payload2, "tts-try2")
        if r2.status_code == 200:
            return r2.content, None
        attempts.append(("try2", r2.status_code, r2.text[:500]))

        # Try 3: ping with short text
        payload3 = dict(payload2)
        payload3["text"] = "Hello."
        r3 = _call(payload3, "tts-try3", timeout=60)
        if r3.status_code == 200:
            logger.warning("[ElevenLabs] TTS ping ok but main text failed → content/length/safety suspected")
            return None, {"reason": "ping_ok_main_failed", "code": r2.status_code}

        attempts.append(("try3", r3.status_code, r3.text[:500]))
        return None, {"attempts": attempts}

    @staticmethod
    def tts_ping(voice_id: str) -> bool:
        """Ping voice to check if it's ready"""
        audio, error = ElevenLabsService.tts_generate(voice_id, "Voice check for initialization.")
        return audio is not None

    @staticmethod
    def tts_ping_retry(voice_id: str, attempts: int = 3, first_wait: float = 0.8) -> bool:
        """Retry ping with exponential backoff"""
        wait = first_wait
        for i in range(attempts):
            if ElevenLabsService.tts_ping(voice_id):
                return True
            logger.warning(f"[tts_ping] retry {i+1}/{attempts} voice_id={voice_id}")
            time.sleep(wait)
            wait *= 2
        return False


# Check if API key is set
if not ELEVEN_API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY is not set in environment")
logger.info(f"[boot] XI={ELEVEN_API_KEY[:6]}*** DEFAULT_VOICE_ID={DEFAULT_VOICE_ID}")
