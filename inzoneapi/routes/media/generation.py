# routes/media/generation.py
from flask import Blueprint, request, jsonify
from services.media.media_generation_service import MediaGenerationService

media_generation_bp = Blueprint('media_generation', __name__)

@media_generation_bp.route('/api/image', methods=['POST'])
def image_generate():
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"error": "Missing 'prompt' in request"}), 400

        prompt = data['prompt']
        return MediaGenerationService.generate_image(prompt)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@media_generation_bp.route("/api/generate_3d_avatar", methods=["POST"])
def generate_3d_avatar():
    try:
        body = request.get_json(silent=True) or {}
        prompt = body.get("prompt")
        return MediaGenerationService.generate_3d_avatar(prompt)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
