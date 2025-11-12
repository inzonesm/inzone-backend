# services/content/post_service.py
from dependencies import db
from typing import Dict, Any
import logging
from flask import jsonify

logger = logging.getLogger(__name__)

class PostService:
    """Service for post operations"""

    @staticmethod
    def get_post(post_id: str) -> Dict[str, Any]:
        """Get a post by ID"""
        try:
            # Fetch the post from Firestore
            post_ref = db.collection('posts').document(post_id)
            post_doc = post_ref.get()

            if post_doc.exists:
                return jsonify(post_doc.to_dict()), 200
            else:
                return jsonify({"error": "Post not found"}), 404

        except Exception as e:
            logger.error(f"Error fetching post {post_id}: {e}")
            return jsonify({"error": str(e)}), 500
