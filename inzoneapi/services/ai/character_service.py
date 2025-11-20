# services/ai/character_service.py
import logging
import random
import uuid
from typing import Dict, Any
from flask import jsonify
from google.cloud import firestore
from dependencies import db, openai_client

logger = logging.getLogger(__name__)


class AICharacterService:
    """Service for AI character management operations"""

    @staticmethod
    def generate_ai_response(message: str, ai_character_id: str) -> str:
        """Generate AI response based on character personality"""
        try:
            ai_character = None
            if ai_character_id:
                doc_ref = db.collection("popularCharacters").document(ai_character_id)
                snapshot = doc_ref.get()
                ai_character = snapshot.to_dict()

            personality = ai_character.get('personality', ai_character.get('Personality', 'friendly and helpful'))

            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": f"You are an AI character with the following personality: {personality}. Respond as this character would, staying true to their personality. Keep responses conversational and engaging."},
                    {"role": "user", "content": message}
                ],
                max_tokens=150,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()
        except Exception as ex:
            logger.error("Error generating AI response: %s", ex)
            return "Sorry, I'm having trouble responding right now."

    @staticmethod
    def chat(data: Dict[str, Any]) -> tuple:
        """Simple AI chat endpoint"""
        try:
            response_text = AICharacterService.generate_ai_response(
                data.get("Message"),
                data.get("AICharacterId")
            )

            chat_response = {
                "Message": response_text,
                "ConversationId": str(uuid.uuid4())
            }

            return jsonify({"success": True, "data": chat_response}), 200
        except Exception as ex:
            logger.error("Error in chat: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def update_character_name(doc_id: str, name: str) -> tuple:
        """Update popular character name"""
        try:
            if not doc_id:
                return jsonify({"success": False, "error": "Document ID (docId) is required"}), 400

            if not name:
                return jsonify({"success": False, "error": "Name is required"}), 400

            character_ref = db.collection('popularCharacters').document(doc_id)
            character_ref.set({'name': name}, merge=True)

            return jsonify({"success": True, "message": "Name field updated successfully."}), 200

        except Exception as ex:
            logger.error("Error updating name field: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def upvote(name: str) -> tuple:
        """Upvote a character"""
        try:
            if not name:
                return jsonify({"success": False, "error": "Popular character's name is required"}), 400

            character_ref = db.collection('popularCharacters').document(name)
            character_doc = character_ref.get()

            if not character_doc.exists:
                return jsonify({"success": False, "error": "Character not found"}), 404

            data = character_doc.to_dict()
            if 'upvotes' in data:
                character_ref.update({'upvotes': firestore.Increment(1)})
            else:
                character_ref.update({'upvotes': 1})

            return jsonify({"success": True, "message": "Upvote successful."}), 200
        except Exception as ex:
            logger.error("Error upvoting: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def downvote(name: str) -> tuple:
        """Downvote a character"""
        try:
            if not name:
                return jsonify({"success": False, "error": "Popular character's name is required"}), 400

            character_ref = db.collection('popularCharacters').document(name)
            character_doc = character_ref.get()

            if not character_doc.exists:
                return jsonify({"success": False, "error": "Character not found"}), 404

            data = character_doc.to_dict()
            if 'downvotes' in data:
                character_ref.update({'downvotes': firestore.Increment(1)})
            else:
                character_ref.update({'downvotes': 1})

            return jsonify({"success": True, "message": "Downvote successful."}), 200
        except Exception as ex:
            logger.error("Error downvoting: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_chat_counter(name: str) -> tuple:
        """Get chat counter for a character"""
        try:
            if not name:
                return jsonify({"success": False, "error": "Popular character's name is required"}), 400

            character_ref = db.collection('popularCharacters').document(name)
            character_doc = character_ref.get()

            if not character_doc.exists:
                return jsonify({"success": False, "error": "Character not found"}), 404

            data = character_doc.to_dict()
            return jsonify({"success": True, "numberOfChats": data.get('numberOfChats', 0)}), 200
        except Exception as ex:
            logger.error("Error retrieving numberOfChats: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_carousel_characters(show_popular_first: bool = False) -> tuple:
        """Get characters for carousel display"""
        try:
            # Build the query
            characters_ref = db.collection('popularCharacters')
            if show_popular_first:
                query = characters_ref.where('showFirst', '==', True)
            else:
                query = characters_ref

            # Fetch documents
            snapshot = query.stream()

            # Convert docs to dicts with ID
            filtered_characters = []
            for doc in snapshot:
                character = doc.to_dict()
                character['id'] = doc.id
                filtered_characters.append(character)

            # Limit to 20 random characters
            num_characters_to_show = 20
            if len(filtered_characters) <= num_characters_to_show:
                selected_characters = filtered_characters
            else:
                random.shuffle(filtered_characters)
                selected_characters = filtered_characters[:num_characters_to_show]

            return jsonify(selected_characters), 200

        except Exception as ex:
            logger.error("Error retrieving carousel characters: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def generate_image() -> tuple:
        """Generate image placeholder (implement actual logic later)"""
        try:
            # Add image generation logic here
            image_url = f"https://storage.googleapis.com/inzonebackend.appspot.com/generated-images/{uuid.uuid4().hex}.png"

            return jsonify({"success": True, "data": {"ImageUrl": image_url}}), 200
        except Exception as ex:
            logger.error("Error generating image: %s", ex)
            return jsonify({"success": False, "error": "Failed to generate image", "code": "IMAGE_GENERATION_ERROR"}), 500
