# routes/ai/maintenance.py
from flask import Blueprint, jsonify

ai_maintenance_bp = Blueprint('ai_maintenance', __name__)

# Service instance to be injected
maintenance_service = None


def init_maintenance_service(service):
    """Initialize the AI data maintenance service"""
    global maintenance_service
    maintenance_service = service


@ai_maintenance_bp.route('/api/ai/comments/debug', methods=['GET'])
def debug_comments():
    """Debug the structure of comments in postComments collection"""
    result, status = maintenance_service.debug_comments()
    return jsonify(result), status


@ai_maintenance_bp.route('/api/ai/comments/cleanup-incorrect-structure', methods=['POST'])
def cleanup_incorrect_ai_comments():
    """
    Remove all AI comments that were incorrectly stored as separate documents
    instead of being added to the comments array of the post document.
    """
    result, status = maintenance_service.cleanup_incorrect_ai_comments()
    return jsonify(result), status


@ai_maintenance_bp.route('/api/ai/migrate-post-likes', methods=['POST'])
def migrate_post_likes_collection():
    """
    Migrate all documents from post_likes collection to postLikes collection
    """
    result, status = maintenance_service.migrate_post_likes()
    return jsonify(result), status


@ai_maintenance_bp.route('/api/ai/verify-post-likes-migration', methods=['GET'])
def verify_post_likes_migration():
    """
    Verify the migration by checking both collections
    """
    result, status = maintenance_service.verify_post_likes_migration()
    return jsonify(result), status
