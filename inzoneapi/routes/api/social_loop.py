import time

from flask import Blueprint, request, jsonify, g

from services.minigames.social_loop_service import SocialLoopService, _record_request_metric

game_sdk_bp = Blueprint("game_sdk_api", __name__)


def _error_response(code: str, message: str, status: int):
    return jsonify({"success": False, "error": message, "code": code}), status


def _attach_game_key(data: dict) -> dict:
    game_key = request.headers.get("X-Game-Key") or request.headers.get("x-game-key")
    if game_key and isinstance(data, dict):
        data.setdefault("gameKey", game_key)
    return data


# ────────────────────────────────────────────────────────────────
# Request metrics hooks — time every game-sdk request and record
# hourly metric buckets to Firestore (game_sdk_metrics collection).
# ────────────────────────────────────────────────────────────────

@game_sdk_bp.before_request
def _start_timer():
    g._sdk_request_start = time.monotonic()


@game_sdk_bp.after_request
def _record_metric(response):
    start = getattr(g, "_sdk_request_start", None)
    if start is None:
        return response

    latency_ms = round((time.monotonic() - start) * 1000, 2)
    # Extract gameId from the request body or query params
    game_id = ""
    try:
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            game_id = body.get("gameId") or body.get("GameId") or ""
        if not game_id:
            game_id = request.args.get("gameId") or request.args.get("GameId") or ""
        if not game_id:
            # Try X-Game-Key header as fallback identifier
            game_id = request.headers.get("X-Game-Key") or request.headers.get("x-game-key") or ""
    except Exception:
        pass

    if game_id:
        is_error = response.status_code >= 400
        endpoint_path = request.path or request.url_rule.rule if request.url_rule else "unknown"
        try:
            _record_request_metric(
                game_id=game_id,
                endpoint=endpoint_path,
                latency_ms=latency_ms,
                status_code=response.status_code,
                is_error=is_error,
            )
        except Exception:
            pass  # best-effort

    return response


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


@game_sdk_bp.route("/api/game-sdk/progress/share", methods=["POST"])
def progress_share():
    try:
        data = request.get_json(silent=True) or {}
        return SocialLoopService.progress_share(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/leaderboard", methods=["GET"])
def get_leaderboard():
    try:
        data = request.args.to_dict()
        data = _attach_game_key(data)
        return SocialLoopService.get_leaderboard(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/integration-health", methods=["GET"])
def integration_health():
    try:
        data = request.args.to_dict()
        data = _attach_game_key(data)
        return SocialLoopService.integration_health(data)
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
        # The Studio web portal posts multipart/form-data (gameTitle, description,
        # developerName, iconPreviewUrl, gameIcon, bundleFile). Legacy SDK clients
        # post JSON with developerId + games[]. Dispatch on content type.
        content_type = (request.content_type or "").lower()
        if "multipart/form-data" in content_type or request.files:
            form_data = {
                "gameTitle": request.form.get("gameTitle", ""),
                "description": request.form.get("description", ""),
                "developerName": request.form.get("developerName", ""),
                "iconPreviewUrl": request.form.get("iconPreviewUrl", ""),
                "developerId": request.form.get("developerId", ""),
                "gameKey": request.form.get("gameKey", ""),
            }
            files = {
                "gameIcon": request.files.get("gameIcon"),
                "bundleFile": request.files.get("bundleFile"),
            }
            return SocialLoopService.register_game_from_bundle(form_data, files)

        data = request.get_json(silent=True) or {}
        return SocialLoopService.register_games(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)


@game_sdk_bp.route("/api/game-sdk/games/list", methods=["GET"])
def list_developer_games():
    try:
        data = request.args.to_dict()
        data = _attach_game_key(data)
        return SocialLoopService.list_games(data)
    except ValueError as exc:
        return _error_response("INVALID_REQUEST", str(exc), 400)
    except Exception:
        return _error_response("INTERNAL_ERROR", "Internal server error", 500)
