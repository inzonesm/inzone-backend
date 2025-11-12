# routes/api/sentiment.py
from flask import Blueprint, request, jsonify
from services.ai.sentiment_service import sentiment_service

sentiment_bp = Blueprint('sentiment', __name__)

@sentiment_bp.route('/api/sentiment-analysis', methods=['POST'])
def analyze_sentiment():
    """Analyze sentiment of text, images, and videos"""
    try:
        content = request.get_json()
        if not content:
            return jsonify({"success": False, "error": "Missing request body", "code": "INVALID_REQUEST"}), 400

        return sentiment_service.analyze_sentiment(content)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
