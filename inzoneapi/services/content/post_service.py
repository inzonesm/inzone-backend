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
        """Get a post by ID, searching across all post collections"""
        try:
            # Search across all post collections
            collections = ['humanPosts', 'aiPosts', 'reposts', 'posts']
            
            for collection in collections:
                try:
                    doc = db.collection(collection).document(post_id).get()
                    if doc.exists:
                        post_data = doc.to_dict()
                        post_data['collection'] = collection
                        return jsonify(post_data), 200
                except Exception as e:
                    logger.warning(f"Error checking {collection} for post {post_id}: {e}")
                    continue
            
            return jsonify({"error": "Post not found"}), 404
        
        except Exception as e:
            logger.error(f"Error fetching post {post_id}: {e}")
            return jsonify({"error": str(e)}), 500

    @staticmethod
    def delete_post(post_id: str, user_id: str) -> Dict[str, Any]:
        """Delete a post with ownership verification and cleanup"""
        try:
            if not post_id or not user_id:
                return jsonify({"error": "PostId and UserId are required"}), 400
            
            # Search for the post across collections
            collections = ['humanPosts', 'aiPosts', 'reposts', 'posts']
            post_doc = None
            collection_name = None
            
            for collection in collections:
                try:
                    doc = db.collection(collection).document(post_id).get()
                    if doc.exists:
                        post_doc = doc
                        collection_name = collection
                        break
                except Exception as e:
                    logger.warning(f"Error checking {collection} for post {post_id}: {e}")
                    continue
            
            if not post_doc:
                return jsonify({"error": "POST_NOT_FOUND"}), 404
            
            post_data = post_doc.to_dict()
            
            # Check ownership - look for various owner fields
            owner_id = None
            for field in ['author_id', 'user_id', 'user_document_id', 'owner_id', 'author']:
                if field in post_data:
                    owner_id = post_data[field]
                    break
            
            if not owner_id:
                return jsonify({"error": "NO_OWNER"}), 403
            
            if owner_id != user_id:
                return jsonify({"error": "NOT_AUTHORIZED"}), 403
            
            # Best-effort cleanup of related resources
            try:
                # Try to delete storage blobs if referenced
                for field in ['image', 'mediaUrl', 'videoUrl', 'audioUrl']:
                    if field in post_data and post_data[field]:
                        try:
                            # Extract blob name from URL and attempt deletion
                            url = post_data[field]
                            if 'storage.googleapis.com' in url or 'firebasestorage.googleapis.com' in url:
                                # Extract blob path from URL
                                import re
                                match = re.search(r'/o/([^?]+)', url)
                                if match:
                                    blob_name = match.group(1).replace('%2F', '/')
                                    from firebase_admin import storage
                                    bucket = storage.bucket()
                                    blob = bucket.blob(blob_name)
                                    if blob.exists():
                                        blob.delete()
                                        logger.info(f"Deleted storage blob: {blob_name}")
                        except Exception as blob_err:
                            logger.warning(f"Failed to delete blob for {field}: {blob_err}")
                
                # Delete comments subcollection
                try:
                    comments_ref = db.collection('postComments').where('postId', '==', post_id)
                    comments = comments_ref.stream()
                    for comment in comments:
                        comment.reference.delete()
                    logger.info(f"Deleted comments for post {post_id}")
                except Exception as comment_err:
                    logger.warning(f"Failed to delete comments for post {post_id}: {comment_err}")
                
            except Exception as cleanup_err:
                logger.warning(f"Cleanup failed for post {post_id}: {cleanup_err}")
            
            # Delete the main post document
            db.collection(collection_name).document(post_id).delete()
            logger.info(f"Deleted post {post_id} from {collection_name}")
            
            return jsonify({"success": True}), 200
        
        except Exception as e:
            logger.error(f"Error deleting post {post_id}: {e}")
            return jsonify({"error": str(e)}), 500
