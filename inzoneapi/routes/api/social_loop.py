from flask import Blueprint, request, jsonify

from services.minigames.social_loop_service import SocialLoopService

game_sdk_bp = Blueprint("game_sdk_api", __name__)


def _error_response(code: str, message: str, status: int):
    return jsonify({"success": False, "error": message, "code": code}), status


def _attach_game_key(data: dict) -> dict:
    game_key = request.headers.get("X-Game-Key") or request.headers.get("x-game-key")
    if game_key and isinstance(data, dict):
        data.setdefault("gameKey", game_key)
    return data


@game_sdk_bp.route("/api/game-sdk/open-social-screen", methods=["GET", "POST"])
def open_social_screen():
    try:
        data = request.get_json(silent=True) if request.method == "POST" else request.args.to_dict()
        return SocialLoopService.open_social_screen(data or {})
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/post-score", methods=["POST"])
def post_score():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.post_score(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/send-challenge", methods=["POST"])
def send_challenge():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.send_challenge(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/share-card", methods=["POST"])
def share_card():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.share_card(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/open-chat", methods=["POST"])
def open_chat():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.open_chat(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/dashboard", methods=["GET"])
def dashboard():
    try:
        data = request.args.to_dict()
        data = _attach_game_key(data)
        return SocialLoopService.dashboard(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/coins/tier-10", methods=["POST"])
def tier_10():
    try:
        data = request.get_json(silent=True) or {}
        data = _attach_game_key(data)
        return SocialLoopService.purchase_coin_tier(data, 10)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/coins/tier-50", methods=["POST"])
def tier_50():
    try:
        data = request.get_json(silent=True) or {}
        data = _attach_game_key(data)
        return SocialLoopService.purchase_coin_tier(data, 50)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/coins/tier-150", methods=["POST"])
def tier_150():
    try:
        data = request.get_json(silent=True) or {}
        data = _attach_game_key(data)
        return SocialLoopService.purchase_coin_tier(data, 150)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/coins/tier-400", methods=["POST"])
def tier_400():
    try:
        data = request.get_json(silent=True) or {}
        data = _attach_game_key(data)
        return SocialLoopService.purchase_coin_tier(data, 400)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/game-state", methods=["GET"])
def game_state():
    try:
        data = request.args.to_dict()
        data = _attach_game_key(data)
        return SocialLoopService.game_state(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/games/register", methods=["POST"])
def register_games():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.register_games(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)
