from typing import Any, Dict, List
import logging
from flask import jsonify
from google.cloud import firestore
from dependencies import db

logger = logging.getLogger(__name__)


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_number(value: Any):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _first_present(data: Dict[str, Any], *keys: str):
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return default


def _format_game_name(game_id: str, provided: str) -> str:
    if provided:
        return provided
    if not game_id:
        return "Unknown"
    return game_id.replace("_", " ").replace("-", " ").title()


def _format_score_value(value: Any):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class MinigameGameoverService:
    """Service for minigame gameover payloads."""

    @staticmethod
    def build_payload(data: Dict[str, Any]) -> tuple:
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        if not game_id:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "gameId is required",
                        "code": "VALIDATION_ERROR",
                    }
                ),
                400,
            )

        score_value = _parse_number(_first_present(data, "score", "Score"))
        if score_value is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "score is required",
                        "code": "VALIDATION_ERROR",
                    }
                ),
                400,
            )

        score_value = _format_score_value(score_value)
        player_id = _normalize_string(data.get("playerId") or data.get("PlayerId"))
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        game_name = _format_game_name(
            game_id,
            _normalize_string(data.get("gameName") or data.get("GameName")),
        )
        display_name = _normalize_string(
            data.get("displayName")
            or data.get("DisplayName")
            or data.get("playerName")
            or data.get("PlayerName")
        )
        if not display_name:
            display_name = "Player"

        duration_ms = _parse_number(_first_present(data, "durationMs", "DurationMs"))
        duration_ms = _format_score_value(duration_ms)
        platform = _normalize_string(data.get("platform") or data.get("Platform"))
        client_build = _normalize_string(
            data.get("clientBuild") or data.get("ClientBuild")
        )
        record_score = _parse_bool(data.get("recordScore"), default=True)

        if record_score and player_id:
            try:
                db.collection("minigame_scores").add(
                    {
                        "game_id": game_id,
                        "player_id": player_id,
                        "display_name": display_name,
                        "score": score_value,
                        "session_id": session_id,
                        "platform": platform,
                        "client_build": client_build,
                        "duration_ms": duration_ms,
                        "created_at": firestore.SERVER_TIMESTAMP,
                    }
                )
            except Exception as exc:
                logger.warning("Failed to record minigame score: %s", exc)

        try:
            db.collection("html_games").document(game_id).collection("scores").add(
                {
                    "game_id": game_id,
                    "game_name": game_name,
                    "player_id": player_id or None,
                    "display_name": display_name,
                    "score": score_value,
                    "session_id": session_id or None,
                    "platform": platform,
                    "client_build": client_build,
                    "duration_ms": duration_ms,
                    "source": "game-sdk",
                    "created_at": firestore.SERVER_TIMESTAMP,
                }
            )
        except Exception as exc:
            logger.warning("Failed to record html game score: %s", exc)

        leaderboard_entries: List[Dict[str, Any]] = []
        player_rank = None

        try:
            query = (
                db.collection("html_games")
                .document(game_id)
                .collection("scores")
                .order_by("score", direction=firestore.Query.DESCENDING)
                .limit(10)
                .stream()
            )
            for idx, doc in enumerate(query, start=1):
                item = doc.to_dict() or {}
                entry = {
                    "rank": idx,
                    "playerId": item.get("player_id"),
                    "displayName": item.get("display_name") or "Player",
                    "score": _format_score_value(item.get("score") or 0),
                }
                leaderboard_entries.append(entry)
                if player_id and entry["playerId"] == player_id:
                    player_rank = idx
        except Exception as exc:
            logger.warning("Failed to fetch minigame leaderboard: %s", exc)

        if not leaderboard_entries and player_id:
            leaderboard_entries.append(
                {
                    "rank": 1,
                    "playerId": player_id,
                    "displayName": display_name,
                    "score": score_value,
                }
            )
            player_rank = 1

        share_title = _normalize_string(
            data.get("shareTitle") or f"I scored {score_value} in {game_name}!"
        )
        share_message = _normalize_string(
            data.get("shareMessage") or "Can you beat me?"
        )
        share_url = _normalize_string(
            data.get("shareUrl") or f"https://inzone.app/game/{game_id}"
        )
        invite_code = _normalize_string(data.get("inviteCode"))
        if not invite_code and session_id:
            invite_code = session_id[-6:]

        payload = {
            "success": True,
            "game": {"id": game_id, "name": game_name},
            "player": {
                "id": player_id or None,
                "displayName": display_name,
                "rank": player_rank,
            },
            "score": {"value": score_value, "best": score_value},
            "leaderboard": {
                "scope": _normalize_string(data.get("leaderboardScope") or "global"),
                "entries": leaderboard_entries,
            },
            "share": {
                "title": share_title,
                "message": share_message,
                "url": share_url,
                "inviteCode": invite_code or None,
            },
            "letterhead": {
                "title": _normalize_string(data.get("letterheadTitle") or "Top gamers"),
                "subtitle": _normalize_string(
                    data.get("letterheadSubtitle") or "Global this week"
                ),
            },
            "sessionId": session_id or None,
        }

        return jsonify(payload), 200
