# services/ai/voice_service.py
import logging
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from flask import jsonify
from dependencies import db
from services.ai.elevenlabs_service import ElevenLabsService, DEFAULT_VOICE_ID

logger = logging.getLogger(__name__)

# AI Chat API configuration
AI_CHAT_API_URL = "https://ai-apis-912424781531.us-east1.run.app/chat/popularCharacter"
VOICE_CHAT_COST = 25


class AIVoiceService:
    """Service for AI voice management"""

    @staticmethod
    def ensure_voice_id_for_character(ai_character_id: str, force_create: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """
        Ensure a voice ID exists for an AI character.
        Creates a new voice if needed or uses existing one.

        Args:
            ai_character_id: The character's document ID
            force_create: Force creation of new voice even if one exists

        Returns:
            Tuple of (data_dict, error_message, status_code)
        """
        char_ref = db.collection("popularCharacters").document(ai_character_id)
        snap = char_ref.get()

        if not snap.exists:
            return None, "AI character not found", 404

        char = snap.to_dict() or {}

        if char.get("voice_enabled", True) is False:
            return None, "Voice disabled for this character", 400

        name = char.get("name", "Character")
        now_iso = datetime.now(timezone.utc).isoformat()

        existing_voice_id = char.get("voice_id")
        logger.info(f"[ensure] start ai_character_id={ai_character_id} name={name} existing_voice_id={existing_voice_id} force_create={force_create}")

        # If voice_id exists and not forcing recreation, return it
        if existing_voice_id and not force_create:
            data = {
                "voice_id": existing_voice_id,
                "was_created": False,
                "name": name,
                "description_used": char.get("voice_description_used", ""),
                "source": char.get("last_voice_source", "existing"),
                "checked_at": now_iso
            }
            try:
                char_ref.update({
                    "last_voice_check_at": datetime.now(timezone.utc),
                    "last_voice_source": data["source"]
                })
            except Exception as e:
                logger.error(f"[ensure] Firestore update failed(existing): {e}")
            return data, None, 200

        # Create new voice
        full_personality = f"{name} - {char.get('personality', '')}"
        desc = ElevenLabsService.personality_to_description(name, full_personality)
        logger.info(f"[ensure] creating voice for {name} desc_head={desc[:60]}...")

        new_voice_id = ElevenLabsService.create_voice(name, desc)

        if not new_voice_id:
            logger.error(f"[ensure] create_voice failed ai_character_id={ai_character_id} name={name}")
            # Fallback to default voice
            if DEFAULT_VOICE_ID:
                logger.warning(f"Falling back to DEFAULT_VOICE_ID={DEFAULT_VOICE_ID} ai_character_id={ai_character_id} name={name}")
                try:
                    char_ref.update({
                        "voice_id": DEFAULT_VOICE_ID,
                        "voice_description_used": "[fallback default voice]",
                        "voice_verified": True,
                        "last_voice_check_at": datetime.now(timezone.utc),
                        "last_voice_source": "fallback",
                        "last_voice_create_failed_at": datetime.now(timezone.utc)
                    })
                except Exception as e:
                    logger.error(f"[ensure] Firestore update failed(fallback): {e}")

                data = {
                    "voice_id": DEFAULT_VOICE_ID,
                    "was_created": False,
                    "name": name,
                    "description_used": "[fallback default voice]",
                    "source": "fallback",
                    "checked_at": now_iso
                }
                return data, None, 200
            return None, "Failed to create voice", 502

        # Verify new voice with ping
        if not ElevenLabsService.tts_ping_retry(new_voice_id):
            logger.error(f"[ensure] TTS ping failed for new_voice_id={new_voice_id}")
            if DEFAULT_VOICE_ID:
                logger.warning(f"Falling back to DEFAULT_VOICE_ID={DEFAULT_VOICE_ID} ai_character_id={ai_character_id} name={name}")
                try:
                    char_ref.update({
                        "voice_id": DEFAULT_VOICE_ID,
                        "voice_description_used": "[fallback default voice]",
                        "voice_verified": True,
                        "last_voice_check_at": datetime.now(timezone.utc),
                        "last_voice_source": "fallback",
                        "last_voice_create_failed_at": datetime.now(timezone.utc)
                    })
                except Exception as e:
                    logger.error(f"[ensure] Firestore update failed(fallback2): {e}")

                data = {
                    "voice_id": DEFAULT_VOICE_ID,
                    "was_created": False,
                    "name": name,
                    "description_used": "[fallback default voice]",
                    "source": "fallback",
                    "checked_at": now_iso
                }
                return data, None, 200
            return None, "Failed to create voice", 502

        # Success - save to Firestore
        try:
            char_ref.update({
                "voice_id": new_voice_id,
                "voice_description_used": desc,
                "voice_verified": True,
                "last_voice_check_at": datetime.now(timezone.utc),
                "last_voice_source": "created",
                "last_voice_create_failed_at": None
            })
        except Exception as e:
            logger.error(f"[ensure] Firestore update failed(created): {e}")

        data = {
            "voice_id": new_voice_id,
            "was_created": True,
            "name": name,
            "description_used": desc,
            "source": "created",
            "checked_at": now_iso
        }
        return data, None, 200

    @staticmethod
    def ensure_voice_endpoint(data: Dict[str, Any]) -> tuple:
        """
        Endpoint handler for ensuring voice for a character.

        Args:
            data: Request data with ai_character_id and optional force_create

        Returns:
            Flask response tuple
        """
        ai_character_id = data.get("ai_character_id")
        force_create = bool(data.get("force_create"))  # For debugging/admin use

        if not ai_character_id:
            return jsonify({"success": False, "error": "Missing ai_character_id"}), 400

        result_data, err_msg, code = AIVoiceService.ensure_voice_id_for_character(
            ai_character_id,
            force_create=force_create
        )

        if err_msg:
            return jsonify({"success": False, "error": err_msg}), code

        return jsonify({
            "success": True,
            "data": {
                "voice_id": result_data["voice_id"],
                "was_created": result_data["was_created"],
                "character_name": result_data["name"],
                "description_used": result_data["description_used"],
                "voice_source": result_data["source"],
                "checked_at": result_data["checked_at"]
            }
        }), 200

    @staticmethod
    def debug_character(character_id: str) -> tuple:
        """Debug endpoint to test popularCharacters collection access"""
        try:
            debug_info = {
                "timestamp": datetime.now().isoformat(),
                "character_id": character_id,
                "tests": {}
            }

            # Test 1: Check if popularCharacters collection exists
            try:
                collections = db.collections()
                collection_names = [col.id for col in collections]
                debug_info["tests"]["collection_exists"] = {
                    "success": "popularCharacters" in collection_names,
                    "all_collections": collection_names
                }
            except Exception as e:
                debug_info["tests"]["collection_exists"] = {
                    "success": False,
                    "error": str(e)
                }

            # Test 2: Try to get the specific document
            try:
                char_doc = db.collection('popularCharacters').document(character_id).get()
                debug_info["tests"]["document_lookup"] = {
                    "success": char_doc.exists,
                    "document_data": char_doc.to_dict() if char_doc.exists else None
                }
            except Exception as e:
                debug_info["tests"]["document_lookup"] = {
                    "success": False,
                    "error": str(e)
                }

            # Test 3: List some documents in popularCharacters
            try:
                chars_ref = db.collection('popularCharacters').limit(5)
                sample_docs = []
                for doc in chars_ref.stream():
                    sample_docs.append({
                        "id": doc.id,
                        "data": doc.to_dict()
                    })
                debug_info["tests"]["sample_documents"] = {
                    "success": True,
                    "count": len(sample_docs),
                    "documents": sample_docs
                }
            except Exception as e:
                debug_info["tests"]["sample_documents"] = {
                    "success": False,
                    "error": str(e)
                }

            return jsonify({"success": True, "debug_info": debug_info}), 200

        except Exception as ex:
            logger.error("Error in debug character voice: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def test_voice_endpoint(data: Dict[str, Any]) -> tuple:
        """Simple test endpoint to verify JSON processing"""
        try:
            logger.info(f"[Voice Test] Received data: {data}")

            return jsonify({
                "success": True,
                "received_data": data,
                "data_type": str(type(data))
            }), 200

        except Exception as ex:
            logger.error("Error in test voice endpoint: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def batch_setup_voices(data: Dict[str, Any]) -> tuple:
        """Setup voice settings for multiple characters in popularCharacters collection"""
        try:
            force_update = data.get('force_update', False)
            limit = data.get('limit', 50)  # Process up to 50 characters at a time

            # Get characters
            query = db.collection('popularCharacters').limit(limit)

            characters = []
            updated_count = 0

            for doc in query.stream():
                character_data = doc.to_dict()
                character_id = doc.id

                # Skip if voice settings exist and not forcing update
                if character_data.get('voice_settings') and not force_update:
                    continue

                # Generate voice for character
                voice_result, err_msg, code = AIVoiceService.ensure_voice_id_for_character(character_id)
                
                if err_msg:
                    logger.warning(f"Failed to create voice for {character_id}: {err_msg}")
                    continue

                voice_id = voice_result["voice_id"]

                voice_settings = {
                    "voice_id": voice_id,
                    "voice_enabled": True
                }

                # Update the character
                db.collection('popularCharacters').document(character_id).update({
                    'voice_settings': voice_settings
                })

                characters.append({
                    "character_id": character_id,
                    "name": character_data.get('name', ''),
                    "voice_id": voice_id
                })

                updated_count += 1

            return jsonify({
                "success": True,
                "message": f"Updated voice settings for {updated_count} characters",
                "updated_characters": characters
            }), 200

        except Exception as ex:
            logger.error("Error batch setting up voices: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
