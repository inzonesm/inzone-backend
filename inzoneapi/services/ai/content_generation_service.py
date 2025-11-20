# services/ai/content_generation_service.py
from flask import jsonify
from google.cloud import firestore
from dependencies import db
import logging

logger = logging.getLogger(__name__)


class AIContentService:
    """Service for AI content generation"""

    @staticmethod
    def generate_ai_post(ai_user_id: str) -> tuple:
        """
        Generate and save an AI post

        Args:
            ai_user_id: The AI user ID to generate post for

        Returns:
            tuple: (response_dict, status_code)
        """
        try:
            # Mock implementation of AI post generation
            post = {
                "Category": "Tech",
                "MainCategory": "AI",
                "SubCategory": "Machine Learning",
                "Comments": [],
                "DatePosted": firestore.SERVER_TIMESTAMP,
                "Likes": 0,
                "Post": {
                    "ImageContent": [],
                    "TextContent": "This is a generated AI post.",
                    "VideoContent": []
                },
                "UserName": ai_user_id,
                "UserReferences": f"aiUsers/{ai_user_id}/"
            }

            # Save the generated post
            post_data = {
                "category": post["Category"],
                "main_category": post["MainCategory"],
                "sub_category": post["SubCategory"],
                "comments": post["Comments"],
                "date_posted": firestore.SERVER_TIMESTAMP,
                "likes": post["Likes"],
                "post": {
                    "image_content": post["Post"]["ImageContent"],
                    "textContent": post["Post"]["TextContent"],
                    "video_content": post["Post"]["VideoContent"]
                },
                "username": post["UserName"],
                "user_references": post["UserReferences"]
            }

            doc_ref = db.collection('posts').add(post_data)
            post_id = doc_ref[1].id

            return jsonify({"success": True, "data": {**post, "Id": post_id}}), 200

        except Exception as ex:
            logger.error("Error generating AI post: %s", ex)
            return jsonify({
                "success": False,
                "error": "Failed to generate post",
                "code": "POST_GENERATION_ERROR"
            }), 500
