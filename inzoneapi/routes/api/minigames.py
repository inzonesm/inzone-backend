# routes/api/minigames.py
from flask import Blueprint, request, jsonify
from services.minigames.gameover_service import MinigameGameoverService

minigames_api_bp = Blueprint('minigames_api', __name__)


@minigames_api_bp.route('/api/minigames/gameover', methods=['POST', 'GET'])
def gameover_payload():
    """Build the gameover invite/share payload for a minigame session."""
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
        else:
            data = request.args.to_dict()
        return MinigameGameoverService.build_payload(data)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        return jsonify({'error': 'Internal server error'}), 500
