# routes/core/health.py
from flask import Blueprint, jsonify

health_bp = Blueprint('health', __name__)

@health_bp.route("/", methods=["GET"])
def test():
    return "Backend is running!"

@health_bp.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint for monitoring services
    """
    return jsonify({
        "status": "healthy",
        "service": "inzone-api"
    }), 200