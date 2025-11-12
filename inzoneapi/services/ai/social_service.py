# services/ai/social_service.py
import logging
from typing import Dict, Any
from flask import jsonify
from google.cloud import firestore
from dependencies import db

logger = logging.getLogger(__name__)


class AISocialService:
    """Service for AI user social interactions (follow/unfollow)"""

    @staticmethod
    def follow(data: Dict[str, Any]) -> tuple:
        """Follow an AI user"""
        try:
            follower_id = data.get("FollowerId")  # A (authenticated AI user)
            following_id = data.get("FollowingId")  # B (AI user to follow)

            follower_ref = db.collection('aiUsers').document(follower_id)
            following_ref = db.collection('aiUsers').document(following_id)

            follower_doc = follower_ref.get()
            following_doc = following_ref.get()

            if not follower_doc.exists or not following_doc.exists:
                return jsonify({"success": False, "error": "AI User not found"}), 404

            follower_data = follower_doc.to_dict()
            if following_id not in follower_data.get("following", []):
                follower_data["following"].append(following_id)
                follower_ref.update({
                    "following": follower_data["following"],
                    "following_count": firestore.Increment(1)
                })

            following_data = following_doc.to_dict()
            if follower_id not in following_data.get("followers", []):
                following_data["followers"].append(follower_id)
                following_ref.update({
                    "followers": following_data["followers"],
                    "followers_count": firestore.Increment(1)
                })

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error adding AI follow relationship: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def unfollow(data: Dict[str, Any]) -> tuple:
        """Unfollow an AI user"""
        try:
            follower_id = data.get("FollowerId")
            following_id = data.get("FollowingId")

            follower_ref = db.collection('aiUsers').document(follower_id)
            following_ref = db.collection('aiUsers').document(following_id)

            follower_ref.update({
                "following": firestore.ArrayRemove([following_id]),
                "following_count": firestore.Increment(-1)
            })
            following_ref.update({
                "followers": firestore.ArrayRemove([follower_id]),
                "followers_count": firestore.Increment(-1)
            })

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error removing AI follow relationship: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_followers(user_id: str) -> tuple:
        """Get followers of an AI user"""
        try:
            user_doc = db.collection('aiUsers').document(user_id).get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "AI User not found"}), 404

            user_data = user_doc.to_dict()
            return jsonify({"followers": user_data.get("followers", [])}), 200
        except Exception as ex:
            logger.error("Error getting AI followers: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def get_following(user_id: str) -> tuple:
        """Get who an AI user is following"""
        try:
            user_doc = db.collection('aiUsers').document(user_id).get()
            if not user_doc.exists:
                return jsonify({"success": False, "error": "AI User not found"}), 404

            user_data = user_doc.to_dict()
            return jsonify({"following": user_data.get("following", [])}), 200
        except Exception as ex:
            logger.error("Error getting AI following: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def remove_follower(data: Dict[str, Any]) -> tuple:
        """Remove a follower from an AI user"""
        try:
            user_id = data.get("UserId")
            follower_id = data.get("FollowerId")

            user_ref = db.collection('aiUsers').document(user_id)
            follower_ref = db.collection('aiUsers').document(follower_id)

            user_ref.update({
                "followers": firestore.ArrayRemove([follower_id]),
                "followers_count": firestore.Increment(-1)
            })
            follower_ref.update({
                "following": firestore.ArrayRemove([user_id]),
                "following_count": firestore.Increment(-1)
            })

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error removing AI follower: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500

    @staticmethod
    def remove_following(data: Dict[str, Any]) -> tuple:
        """Remove someone from following list"""
        try:
            user_id = data.get("UserId")
            following_id = data.get("FollowingId")

            user_ref = db.collection('aiUsers').document(user_id)
            following_ref = db.collection('aiUsers').document(following_id)

            user_ref.update({
                "following": firestore.ArrayRemove([following_id]),
                "following_count": firestore.Increment(-1)
            })
            following_ref.update({
                "followers": firestore.ArrayRemove([user_id]),
                "followers_count": firestore.Increment(-1)
            })

            return jsonify({"success": True}), 200
        except Exception as ex:
            logger.error("Error removing AI following: %s", ex)
            return jsonify({"success": False, "error": str(ex)}), 500
