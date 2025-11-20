# services/ai/voice_chat_service.py
import logging
import base64
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from flask import jsonify
from dependencies import db
from services.ai.voice_service import AIVoiceService, VOICE_CHAT_COST
from services.ai.llm_service import LLMService
from services.ai.elevenlabs_service import ElevenLabsService

logger = logging.getLogger(__name__)


class AIVoiceChatService:
    """Service for AI voice chat workflow"""

    @staticmethod
    def voice_chat(data: Dict[str, Any]) -> tuple:
        """
        Complete voice chat workflow:
        1. Ensure voice exists for character
        2. Generate AI text response
        3. Convert to speech
        4. Deduct coins
        5. Persist conversation

        Args:
            data: Request data with user_id, ai_character_id, message, chat_history

        Returns:
            Flask response tuple
        """
        user_id = data.get("user_id")
        ai_character_id = data.get("ai_character_id")
        message = data.get("message", "")
        chat_history = data.get("chat_history") or []

        try:
            if not user_id or not ai_character_id or not message:
                return jsonify({
                    "success": False,
                    "error": "Missing required fields",
                    "stage": "input"
                }), 400

            # Step 1: Ensure voice exists
            try:
                voice_data, err_msg, code = AIVoiceService.ensure_voice_id_for_character(ai_character_id)
                if err_msg:
                    logger.warning(f"[chat] ensure failed code={code} err={err_msg}")
                    return jsonify({
                        "success": False,
                        "error": err_msg,
                        "stage": "ensure"
                    }), code

                voice_id = voice_data["voice_id"]
                logger.info(f"[chat] voice_id={voice_id} source={voice_data.get('source')}")
            except Exception as e:
                logger.exception("[chat] ensure crash")
                return jsonify({
                    "success": False,
                    "error": "Ensure crashed",
                    "stage": "ensure"
                }), 500

            # Step 2: Generate AI text
            try:
                ai_text = LLMService.generate_ai_text(message, ai_character_id, user_id, chat_history)
                if not ai_text:
                    return jsonify({
                        "success": False,
                        "error": "AI generation failed",
                        "stage": "llm"
                    }), 500
                logger.info(f"[chat] ai_text_len={len(ai_text)}")
            except Exception as e:
                logger.exception("[chat] llm crash")
                return jsonify({
                    "success": False,
                    "error": "AI generation crashed",
                    "stage": "llm"
                }), 500

            # Step 3: Generate TTS audio
            try:
                audio_bytes, tts_err = ElevenLabsService.tts_generate(voice_id, ai_text)
                if not audio_bytes:
                    logger.error(f"[chat] tts failed detail={tts_err}")
                    return jsonify({
                        "success": False,
                        "error": "TTS failed",
                        "stage": "tts",
                        "detail": tts_err
                    }), 502
                logger.info(f"[chat] tts_ok bytes={len(audio_bytes)}")
            except Exception:
                logger.exception("[chat] tts crash")
                return jsonify({
                    "success": False,
                    "error": "TTS crashed",
                    "stage": "tts"
                }), 500

            # Step 4: Deduct coins
            try:
                user_ref = db.collection("humanUsers").document(user_id)
                user_snap = user_ref.get()

                if not getattr(user_snap, "exists", False):
                    return jsonify({
                        "success": False,
                        "error": "User not found",
                        "stage": "coins"
                    }), 404

                balance = int((user_snap.to_dict() or {}).get("balance", 0))

                if balance < VOICE_CHAT_COST:
                    return jsonify({
                        "success": False,
                        "error": "Insufficient balance",
                        "current_balance": balance,
                        "required_coins": VOICE_CHAT_COST,
                        "stage": "coins"
                    }), 402

                user_ref.update({"balance": balance - VOICE_CHAT_COST})
                new_balance = balance - VOICE_CHAT_COST
                logger.info(f"[chat] coins ok new_balance={new_balance}")
            except Exception as e:
                logger.exception("[chat] coins crash")
                return jsonify({
                    "success": False,
                    "error": "Coin deduction crashed",
                    "stage": "coins"
                }), 500

            # Step 5: Persist conversation
            try:
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                conv_ref = db.collection("voice_conversations").document()
                conv_ref.set({
                    "user_id": user_id,
                    "ai_character_id": ai_character_id,
                    "user_message": message,
                    "ai_response": ai_text,
                    "voice_id": voice_id,
                    "coins_spent": VOICE_CHAT_COST,
                    "timestamp": datetime.now(timezone.utc)
                })

                db.collection("voice_analytics").add({
                    "user_id": user_id,
                    "ai_character_id": ai_character_id,
                    "conversation_id": conv_ref.id,
                    "timestamp": datetime.now(timezone.utc),
                    "platform": "server"
                })
            except Exception as e:
                logger.exception("[chat] persist crash")
                return jsonify({
                    "success": False,
                    "error": "Persist crashed",
                    "stage": "persist"
                }), 500

            return jsonify({
                "success": True,
                "data": {
                    "user_message_text": message,
                    "ai_response_text": ai_text,
                    "ai_response_audio": audio_b64,
                    "conversation_id": conv_ref.id,
                    "coins_spent": VOICE_CHAT_COST,
                    "new_balance": new_balance,
                    "voice_id": voice_id,
                    "voice_source": voice_data.get("source", "existing"),
                    "voice_description_used": voice_data.get("description_used", ""),
                    "character_name": voice_data.get("name", "")
                }
            }), 200

        except Exception:
            logger.exception("[chat] unhandled top")
            return jsonify({
                "success": False,
                "error": "Internal error",
                "stage": "top"
            }), 500
