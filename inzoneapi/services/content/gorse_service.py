# services/content/gorse_service.py
from typing import Dict, Any, List
from flask import jsonify
from services.recommendation.gorse_client import gorse_client
from services.content.post_retrieval_service import PostRetrievalService


class GorseService:
    """Service for Gorse recommendation tracking operations"""

    @staticmethod
    def track_view(data: Dict[str, Any]) -> tuple:
        """Track when a user views a post"""
        user_id = data.get('user_id')
        post_id = data.get('post_id')

        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400

        # Record in Gorse as 'read' feedback
        gorse_client.record_interaction(user_id, post_id, 'read')
        print(f"👁️  User {user_id[:8]}... viewed post {post_id[:8]}... (tracked as 'read')")

        return jsonify({'success': True}), 200

    @staticmethod
    def track_like(data: Dict[str, Any]) -> tuple:
        """Track when a user likes a post"""
        user_id = data.get('user_id')
        post_id = data.get('post_id')

        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400

        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'like')

        return jsonify({'success': True}), 200

    @staticmethod
    def track_comment(data: Dict[str, Any]) -> tuple:
        """Track when a user comments on a post"""
        user_id = data.get('user_id')
        post_id = data.get('post_id')

        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400

        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'comment')

        return jsonify({'success': True}), 200

    @staticmethod
    def track_share(data: Dict[str, Any]) -> tuple:
        """Track when a user shares a post"""
        user_id = data.get('user_id')
        post_id = data.get('post_id')

        if not user_id or not post_id:
            return jsonify({'error': 'user_id and post_id required'}), 400

        # Record in Gorse
        gorse_client.record_interaction(user_id, post_id, 'share')

        return jsonify({'success': True}), 200

    @staticmethod
    def get_similar_posts(post_id: str, limit: int = 5) -> tuple:
        """Get similar posts for 'You may also like' section"""
        # Get similar posts from Gorse
        similar_post_ids = gorse_client.get_similar_posts(post_id, limit=limit)

        # Fetch actual post data
        posts = []
        for pid in similar_post_ids:
            post_data = PostRetrievalService.get_post_by_id(pid)
            if post_data:
                posts.append(post_data)

        return jsonify({'posts': posts}), 200
