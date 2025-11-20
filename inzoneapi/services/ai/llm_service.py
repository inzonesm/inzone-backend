# services/ai/llm_service.py
import logging
import json
import requests
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# LLM configuration
AI_CHAT_API_URL = "https://ai-apis-912424781531.us-east1.run.app/chat/popularCharacter"
LLM_TIMEOUT = 15


class LLMService:
    """Service for LLM (Language Model) integration"""

    @staticmethod
    def generate_ai_text(
        message: str,
        ai_character_id: str,
        user_id: str,
        chat_history: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[str]:
        """
        Generate AI text response using the chat API.

        Args:
            message: User's message
            ai_character_id: AI character ID
            user_id: User ID
            chat_history: Optional chat history

        Returns:
            AI response text if successful, None otherwise
        """
        url = AI_CHAT_API_URL
        payload = {
            "message": message,
            "ai_id": ai_character_id,
            "user_id": user_id,
            "chat_history": chat_history or []
        }

        try:
            # Make API call
            r = requests.post(
                url,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                data=json.dumps(payload),
                timeout=LLM_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.exception(f"[llm] request error: {e}")
            return None

        # Log response details
        ct = r.headers.get("Content-Type", "")
        body_preview = r.text[:500] if r.text else ""
        logger.info(f"[llm] status={r.status_code} ct={ct} len={len(r.content)} preview={body_preview}")

        # Check status code
        if r.status_code < 200 or r.status_code >= 300:
            return None

        # Parse JSON response
        try:
            resp = r.json()
        except ValueError:
            logger.error("[llm] non-JSON response")
            return None

        # Extract message from various possible response formats
        # 1) {"data":{"message":"..."}}
        # 2) {"message":"..."}
        # 3) {"output":"..."}
        msg = (
            (resp.get("data") or {}).get("message")
            or resp.get("message")
            or resp.get("output")
        )

        if not msg or not isinstance(msg, str):
            logger.error(f"[llm] missing message in response keys={list(resp.keys())}")
            return None

        return msg.strip()
