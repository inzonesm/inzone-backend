from __future__ import annotations

import logging
import math
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from flask import jsonify
from google.cloud import firestore

from dependencies import db
from services.minigames.gameover_service import MinigameGameoverService

logger = logging.getLogger(__name__)

COIN_COMMISSION_RATE = 0.10
GAME_SDK_BASE_PATH = "/api/game-sdk"
GAME_REGISTRY_COLLECTION = "html_games"
GAME_DEVELOPERS_COLLECTION = "game_developers"

COIN_TIERS: Dict[int, Dict[str, Any]] = {
    10: {
        "tier": "tier-10",
        "title": "Tier 1",
        "name": "Impulse",
        "summary": "The smallest meaningful action.",
    },
    50: {
        "tier": "tier-50",
        "title": "Tier 2",
        "name": "Investment",
        "summary": "A meaningful advantage or unlock.",
    },
    150: {
        "tier": "tier-150",
        "title": "Tier 3",
        "name": "Identity",
        "summary": "A significant unlock with lasting value.",
    },
    400: {
        "tier": "tier-400",
        "title": "Tier 4",
        "name": "Momentum",
        "summary": "A premium unlock with the largest impact.",
    },
}

METRICS_COLLECTION = "game_sdk_metrics"
# Maximum latency samples stored per hourly bucket (for percentile calculations)
MAX_LATENCY_SAMPLES_PER_BUCKET = 200


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _record_request_metric(
    *,
    game_id: str,
    endpoint: str,
    latency_ms: float,
    status_code: int,
    is_error: bool = False,
) -> None:
    """Record a single API request metric into an hourly bucket document.

    Collection: game_sdk_metrics
    Document ID: {game_id}_{YYYY-MM-DDTHH}  (one doc per game per hour)

    Each doc aggregates: request count, error count, total latency (for avg),
    and a capped array of latency samples (for percentile calculations).
    """
    if not game_id:
        return
    try:
        now = _utc_now()
        hour_key = now.strftime("%Y-%m-%dT%H")
        doc_id = f"{game_id}_{hour_key}"
        ref = db.collection(METRICS_COLLECTION).document(doc_id)

        ref.set(
            {
                "game_id": game_id,
                "hour": hour_key,
                "requests": firestore.Increment(1),
                "errors": firestore.Increment(1 if is_error else 0),
                "total_latency_ms": firestore.Increment(latency_ms),
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

        # Append latency sample (capped at MAX_LATENCY_SAMPLES_PER_BUCKET).
        # ArrayUnion won't duplicate the exact same float, so we add a tiny
        # random jitter to keep every sample unique.
        jittered = round(latency_ms, 3)
        ref.update(
            {
                "latency_samples": firestore.ArrayUnion([jittered]),
                "endpoints_hit": firestore.ArrayUnion([endpoint]),
            }
        )
    except Exception:
        # Metrics recording is best-effort — never fail the request.
        logger.debug("Failed to record request metric for %s", game_id, exc_info=True)


def _normalize_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _parse_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _format_number(value: Any) -> float | int:
    parsed_value = _parse_number(value)
    if parsed_value is None:
        return 0
    if float(parsed_value).is_integer():
        return int(parsed_value)
    return parsed_value


def _first_present(data: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return None


def _to_utc_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        cleaned_value = value.strip().replace("Z", "+00:00")
        try:
            parsed_value = datetime.fromisoformat(cleaned_value)
        except ValueError:
            return None
        return parsed_value.astimezone(timezone.utc) if parsed_value.tzinfo else parsed_value.replace(tzinfo=timezone.utc)
    return None


def _error_response(code: str, message: str, status: int, details: Optional[Dict[str, Any]] = None):
    payload: Dict[str, Any] = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "status": status,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload), status


def _require_game_key(game_id: str, game_key: str):
    if not game_key:
        return _error_response("MISSING_GAME_KEY", "gameKey is required", 400)

    game_doc = db.collection("html_games").document(game_id).get()
    if not game_doc.exists:
        return _error_response("GAME_NOT_FOUND", "Game not found", 404)

    game_data = game_doc.to_dict() or {}
    stored_key = _normalize_string(game_data.get("game_key") or game_data.get("gameKey"))
    if stored_key and stored_key != game_key:
        return _error_response("INVALID_GAME_KEY", "Invalid gameKey", 403)

    return None


def _record_game_activity(
    *,
    user_id: str,
    game_id: str,
    session_id: Optional[str],
    activity_type: str,
    is_transaction: bool = False,
) -> None:
    now = _utc_now()
    day_key = now.date().isoformat()
    activity_ref = db.collection("game_activity").document(f"{game_id}_{user_id}")
    activity_doc = activity_ref.get()
    activity_data = activity_doc.to_dict() if activity_doc.exists else {}
    active_days = set(activity_data.get("active_days", []))
    active_days.add(day_key)

    update_data = {
        "user_id": user_id,
        "game_id": game_id,
        "session_id": session_id or activity_data.get("session_id"),
        "activity_type": activity_type,
        "last_seen_at": now,
        "first_seen_at": activity_data.get("first_seen_at") or now,
        "active_days": sorted(active_days),
        "activity_count": int(activity_data.get("activity_count", 0)) + 1,
        "transaction_count": int(activity_data.get("transaction_count", 0)) + (1 if is_transaction else 0),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }

    if is_transaction:
        update_data["last_transaction_at"] = now

    activity_ref.set(update_data, merge=True)


def _get_social_loop_economy() -> List[Dict[str, Any]]:
    economy: List[Dict[str, Any]] = []
    for coins, tier_data in sorted(COIN_TIERS.items()):
        commission_coins = int(round(coins * COIN_COMMISSION_RATE))
        economy.append(
            {
                "coins": coins,
                **tier_data,
                "commissionRate": COIN_COMMISSION_RATE,
                "commissionCoins": commission_coins,
                "developerCoins": coins - commission_coins,
            }
        )
    return economy


def _increment_summary(current: Dict[str, Any], key: str, amount: int) -> int:
    return int(current.get(key, 0)) + amount


def _build_coin_response(
    *,
    user_id: str,
    game_id: str,
    title: str,
    description: str,
    coins: int,
    session_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> tuple:
    if not user_id:
        return _error_response("MISSING_USER_ID", "userId is required", 400)
    if not game_id:
        return _error_response("MISSING_GAME_ID", "gameId is required", 400)
    if not title:
        return _error_response("MISSING_TITLE", "title is required", 400)

    user_ref = db.collection("humanUsers").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return _error_response("USER_NOT_FOUND", "User not found", 404)

    user_data = user_doc.to_dict() or {}
    current_balance = int(user_data.get("balance", 200))
    if current_balance < coins:
        return _error_response(
            "INSUFFICIENT_BALANCE",
            "Insufficient balance",
            400,
            details={
                "currentBalance": current_balance,
                "required": coins,
            },
        )

    commission_coins = int(round(coins * COIN_COMMISSION_RATE))
    developer_coins = coins - commission_coins
    new_balance = current_balance - coins
    transaction_id = transaction_id or uuid.uuid4().hex
    now = datetime.now(timezone.utc)

    transaction_payload = {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "game_id": game_id,
        "title": title,
        "description": description or title,
        "coins": coins,
        "commission_coins": commission_coins,
        "developer_coins": developer_coins,
        "commission_rate": COIN_COMMISSION_RATE,
        "status": "confirmed",
        "currency": "Coin",
        "created_at": firestore.SERVER_TIMESTAMP,
        "created_at_local": now.isoformat(),
    }

    user_ref.update({"balance": new_balance})
    db.collection("game_coin_transactions").document(transaction_id).set(transaction_payload)

    summary_ref = db.collection("game_revenue_summary").document(game_id)
    summary_doc = summary_ref.get()
    summary_data = summary_doc.to_dict() if summary_doc.exists else {}
    tier_breakdown = dict(summary_data.get("tier_breakdown", {}))
    tier_breakdown[str(coins)] = _increment_summary(tier_breakdown, str(coins), 1)

    summary_ref.set(
        {
            "game_id": game_id,
            "transaction_count": _increment_summary(summary_data, "transaction_count", 1),
            "gross_coins": _increment_summary(summary_data, "gross_coins", coins),
            "commission_coins": _increment_summary(summary_data, "commission_coins", commission_coins),
            "developer_payout_coins": _increment_summary(
                summary_data, "developer_payout_coins", developer_coins
            ),
            "tier_breakdown": tier_breakdown,
            "last_transaction_title": title,
            "last_transaction_description": description or title,
            "last_transaction_at": firestore.SERVER_TIMESTAMP,
            "commission_rate": COIN_COMMISSION_RATE,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )

    _record_game_activity(
        user_id=user_id,
        game_id=game_id,
        session_id=session_id or _normalize_string(summary_data.get("last_session_id")),
        activity_type="coin_transaction",
        is_transaction=True,
    )

    return (
        jsonify(
            {
                "success": True,
                "data": {
                    "transactionId": transaction_id,
                    "userId": user_id,
                    "gameId": game_id,
                    "title": title,
                    "description": description or title,
                    "coins": coins,
                    "commissionCoins": commission_coins,
                    "developerCoins": developer_coins,
                    "commissionRate": COIN_COMMISSION_RATE,
                    "newBalance": new_balance,
                    "currency": "Coin",
                    "confirmation": "Coin transaction confirmed",
                },
            }
        ),
        200,
    )


def _build_dashboard_summary(game_id: str, user_id: str = "") -> tuple:
    if not game_id:
        return _error_response("MISSING_GAME_ID", "gameId is required", 400)

    session_query = db.collection_group("gameSessions").where("game_id", "==", game_id)
    if user_id:
        session_query = session_query.where("user_id", "==", user_id)
    session_docs = list(session_query.stream())

    now = datetime.now(timezone.utc)
    retention_windows = {1: {"eligible": 0, "retained": 0}, 3: {"eligible": 0, "retained": 0}, 7: {"eligible": 0, "retained": 0}}
    total_sessions = len(session_docs)
    total_play_seconds = 0
    total_coins_used = 0
    sessions_with_coins = 0
    per_user: Dict[str, Dict[str, Any]] = {}

    for doc in session_docs:
        data = doc.to_dict() or {}
        session_user_id = _normalize_string(data.get("user_id") or data.get("userId"))
        opened_at = _to_utc_datetime(data.get("opened_at") or data.get("openedAt"))
        closed_at = _to_utc_datetime(data.get("closed_at") or data.get("closedAt"))

        duration_seconds = _parse_number(data.get("duration_seconds") or data.get("durationSeconds"))
        if duration_seconds is None and opened_at and closed_at:
            duration_seconds = (closed_at - opened_at).total_seconds()
        duration_seconds = int(duration_seconds) if duration_seconds else 0
        total_play_seconds += max(duration_seconds, 0)

        coins_used = int(data.get("coins_used") or data.get("coinsUsed") or 0)
        total_coins_used += coins_used
        if coins_used > 0:
            sessions_with_coins += 1

        if not session_user_id:
            continue

        user_stats = per_user.setdefault(
            session_user_id,
            {"first_seen": None, "last_seen": None, "active_days": set()},
        )

        if opened_at:
            user_stats["active_days"].add(opened_at.astimezone(timezone.utc).date().isoformat())
            if user_stats["first_seen"] is None or opened_at < user_stats["first_seen"]:
                user_stats["first_seen"] = opened_at

        session_last_seen = closed_at or opened_at
        if session_last_seen:
            if user_stats["last_seen"] is None or session_last_seen > user_stats["last_seen"]:
                user_stats["last_seen"] = session_last_seen

    total_players = len(per_user)
    active_players = 0
    for stats in per_user.values():
        last_seen = stats.get("last_seen")
        if last_seen and (now - last_seen).days <= 7:
            active_players += 1

        first_seen = stats.get("first_seen")
        if not first_seen:
            continue

        first_day = first_seen.astimezone(timezone.utc).date()
        active_days = stats.get("active_days", set())
        for window in retention_windows:
            if (now.date() - first_day).days >= window:
                retention_windows[window]["eligible"] += 1
                retained_day = (first_day + timedelta(days=window)).isoformat()
                if retained_day in active_days:
                    retention_windows[window]["retained"] += 1

    def _retention_rate(window: int) -> float:
        eligible = retention_windows[window]["eligible"]
        retained = retention_windows[window]["retained"]
        return round((retained / eligible) * 100, 1) if eligible else 0.0

    transaction_query = db.collection("game_coin_transactions").where("game_id", "==", game_id)
    if user_id:
        transaction_query = transaction_query.where("user_id", "==", user_id)
    transaction_docs = list(transaction_query.stream())

    gross_coins = 0
    commission_coins = 0
    developer_coins = 0
    tier_breakdown = {"10": 0, "50": 0, "150": 0, "400": 0}
    recent_transactions: List[Dict[str, Any]] = []

    for doc in transaction_docs:
        data = doc.to_dict() or {}
        coins = int(data.get("coins", 0))
        gross_coins += coins
        commission_coins += int(data.get("commission_coins", 0))
        developer_coins += int(data.get("developer_coins", 0))
        if str(coins) in tier_breakdown:
            tier_breakdown[str(coins)] += 1

        recent_transactions.append(
            {
                "transactionId": doc.id,
                "title": data.get("title", "Untitled transaction"),
                "description": data.get("description", ""),
                "coins": coins,
                "commissionCoins": int(data.get("commission_coins", 0)),
                "developerCoins": int(data.get("developer_coins", 0)),
                "createdAt": data.get("created_at_local") or _utc_now(),
            }
        )

    recent_transactions.sort(key=lambda item: item["createdAt"], reverse=True)
    recent_transactions = recent_transactions[:10]

    summary_doc = db.collection("game_revenue_summary").document(game_id).get()
    summary_data = summary_doc.to_dict() if summary_doc.exists else {}
    payout_gross = int(summary_data.get("gross_coins", gross_coins))
    payout_commission = int(summary_data.get("commission_coins", commission_coins))
    payout_developer = int(summary_data.get("developer_payout_coins", developer_coins))
    payout = {
        "grossCoins": payout_gross,
        "commissionCoins": payout_commission,
        "developerPayoutCoins": payout_developer,
        "netPayoutCoins": payout_developer,
        "commissionRate": COIN_COMMISSION_RATE,
        "lastPayoutAt": summary_data.get("last_payout_at"),
        "status": "ready" if payout_gross else "empty",
    }

    payload = {
        "success": True,
        "dashboard": {
            "scope": "user" if user_id else "game",
            "gameId": game_id,
            "userId": user_id or None,
            "title": "Game Dashboard",
            "subtitle": "Sessions, retention, and payout in one place.",
        },
        "metrics": {
            "totalPlayers": total_players,
            "activePlayers7d": active_players,
            "sessionCount": total_sessions,
            "totalPlaySeconds": total_play_seconds,
            "averageSessionSeconds": round(total_play_seconds / total_sessions, 1) if total_sessions else 0,
            "day1Retention": _retention_rate(1),
            "day3Retention": _retention_rate(3),
            "day7Retention": _retention_rate(7),
        },
        "microtransactions": {
            "sessionCount": total_sessions,
            "totalCoinsUsed": total_coins_used,
            "averageCoinsPerSession": round(total_coins_used / total_sessions, 1) if total_sessions else 0,
            "sessionsWithCoins": sessions_with_coins,
            "transactionCount": len(transaction_docs),
            "grossCoins": gross_coins,
            "averageTransactionCoins": round(gross_coins / len(transaction_docs), 1) if transaction_docs else 0,
            "tierBreakdown": tier_breakdown,
            "recentTransactions": recent_transactions,
        },
        "payout": payout,
        "economy": _get_social_loop_economy(),
        "timestamp": _utc_now(),
    }

    return jsonify(payload), 200


def _build_game_state(game_id: str, user_id: str, game_key: str) -> tuple:
    if not user_id:
        return _error_response("MISSING_USER_ID", "userId is required", 400)

    key_error = _require_game_key(game_id, game_key)
    if key_error is not None:
        return key_error

    user_ref = db.collection("humanUsers").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        return _error_response("USER_NOT_FOUND", "User not found", 404)

    user_data = user_doc.to_dict() or {}
    balance = int(user_data.get("balance", 0))

    transactions_query = (
        db.collection("game_coin_transactions")
        .where("game_id", "==", game_id)
        .where("user_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(50)
    )

    transactions: List[Dict[str, Any]] = []
    for doc in transactions_query.stream():
        data = doc.to_dict() or {}
        transactions.append(
            {
                "transactionId": doc.id,
                "title": data.get("title"),
                "description": data.get("description"),
                "coins": int(data.get("coins", 0)),
                "commissionCoins": int(data.get("commission_coins", 0)),
                "developerCoins": int(data.get("developer_coins", 0)),
                "status": data.get("status", "confirmed"),
                "createdAt": data.get("created_at_local") or _utc_now(),
            }
        )

    scores_query = (
        db.collection("minigame_scores")
        .where("game_id", "==", game_id)
        .where("player_id", "==", user_id)
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(50)
    )

    scores: List[Dict[str, Any]] = []
    for doc in scores_query.stream():
        data = doc.to_dict() or {}
        scores.append(
            {
                "scoreId": doc.id,
                "score": _format_number(data.get("score")),
                "durationMs": _format_number(data.get("duration_ms")),
                "displayName": data.get("display_name"),
                "createdAt": data.get("created_at") or data.get("created_at_local") or _utc_now(),
            }
        )

    return (
        jsonify(
            {
                "success": True,
                "data": {
                    "gameId": game_id,
                    "userId": user_id,
                    "balance": balance,
                    "currency": "Coin",
                    "transactions": transactions,
                    "scores": scores,
                },
            }
        ),
        200,
    )


def _build_sdk_contract(game_id: str, session_id: str) -> Dict[str, Any]:
    return {
        "name": "InZone Game SDK",
        "basePath": GAME_SDK_BASE_PATH,
        "methods": [
            "OpenSocialScreen",
            "PostScore",
            "SendChallenge",
            "ShareCard",
            "OpenChat",
        ],
        "defaultGameId": game_id or None,
        "defaultSessionId": session_id or None,
    }


class SocialLoopService:
    """Service for the InZone game social-loop SDK contract."""

    @staticmethod
    def open_social_screen(data: Dict[str, Any]):
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        game_name = _normalize_string(data.get("gameName") or data.get("GameName"))
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        player_id = _normalize_string(data.get("playerId") or data.get("PlayerId"))
        platform = _normalize_string(data.get("platform") or data.get("Platform"))
        client_build = _normalize_string(data.get("clientBuild") or data.get("ClientBuild"))

        payload = {
            "success": True,
            "screen": {
                "title": "Five endpoints. One social loop.",
                "subtitle": "Gameplay, coin moments, and retention in one contract.",
            },
            "game": {
                "id": game_id or None,
                "name": game_name or (game_id.replace("_", " ").title() if game_id else "Social Loop"),
                "sessionId": session_id or None,
                "playerId": player_id or None,
                "platform": platform or None,
                "clientBuild": client_build or None,
            },
            "economy": _get_social_loop_economy(),
            "actions": [
                {
                    "name": "GameState",
                    "method": "GET",
                    "path": f"{GAME_SDK_BASE_PATH}/game-state",
                    "description": "Fetch balance, transactions, and scores for a player.",
                },
                {
                    "name": "PostScore",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/post-score",
                    "description": "Submit a result and receive leaderboard context.",
                },
                {
                    "name": "SendChallenge",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/send-challenge",
                    "description": "Turn a score into a 24-hour duel with a friend.",
                },
                {
                    "name": "ShareCard",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/share-card",
                    "description": "Generate a branded share payload for social platforms.",
                },
                {
                    "name": "OpenChat",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/open-chat",
                    "description": "Open the per-game group thread with the right context.",
                },
                {
                    "name": "Dashboard",
                    "method": "GET",
                    "path": f"{GAME_SDK_BASE_PATH}/dashboard",
                    "description": "Fetch retention, microtransaction, and payout metrics.",
                },
                {
                    "name": "CoinTier10",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/coins/tier-10",
                    "description": "Impulse purchase moment.",
                },
                {
                    "name": "CoinTier50",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/coins/tier-50",
                    "description": "Investment purchase moment.",
                },
                {
                    "name": "CoinTier150",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/coins/tier-150",
                    "description": "Identity purchase moment.",
                },
                {
                    "name": "CoinTier400",
                    "method": "POST",
                    "path": f"{GAME_SDK_BASE_PATH}/coins/tier-400",
                    "description": "Commitment purchase moment.",
                },
            ],
            "sdk": _build_sdk_contract(game_id, session_id),
            "timestamp": _utc_now(),
        }
        return jsonify(payload), 200

    @staticmethod
    def dashboard(data: Dict[str, Any]):
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        user_id = _normalize_string(data.get("userId") or data.get("UserId"))
        game_key = _normalize_string(data.get("gameKey") or data.get("GameKey") or data.get("game_key"))
        key_error = _require_game_key(game_id, game_key)
        if key_error is not None:
            return key_error
        return _build_dashboard_summary(game_id=game_id, user_id=user_id)

    @staticmethod
    def game_state(data: Dict[str, Any]):
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        user_id = _normalize_string(data.get("userId") or data.get("UserId") or data.get("playerId") or data.get("PlayerId"))
        game_key = _normalize_string(data.get("gameKey") or data.get("GameKey") or data.get("game_key"))
        return _build_game_state(game_id=game_id, user_id=user_id, game_key=game_key)

    @staticmethod
    def purchase_coin_tier(data: Dict[str, Any], coins: int):
        title = _normalize_string(data.get("title") or data.get("Title"))
        description = _normalize_string(data.get("description") or data.get("Description")) or title
        user_id = _normalize_string(data.get("userId") or data.get("UserId") or data.get("playerId") or data.get("PlayerId"))
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        transaction_id = _normalize_string(data.get("transactionId") or data.get("TransactionId")) or None
        game_key = _normalize_string(data.get("gameKey") or data.get("GameKey") or data.get("game_key"))

        key_error = _require_game_key(game_id, game_key)
        if key_error is not None:
            return key_error

        tier_data = COIN_TIERS.get(coins)
        if not tier_data:
            return _error_response("INVALID_COIN_TIER", "Invalid coin tier", 400)

        response = _build_coin_response(
            user_id=user_id,
            game_id=game_id,
            title=title,
            description=description,
            coins=coins,
            session_id=_normalize_string(data.get("sessionId") or data.get("SessionId")),
            transaction_id=transaction_id,
        )
        response_obj, status_code = response if isinstance(response, tuple) else (response, 200)
        if status_code != 200:
            return response

        payload = response_obj.get_json(silent=True) or {}
        payload["tier"] = tier_data
        payload["sdk"] = _build_sdk_contract(game_id, _normalize_string(data.get("sessionId") or data.get("SessionId")))
        payload["payment"] = {
            "title": title,
            "description": description,
            "commissionRate": COIN_COMMISSION_RATE,
        }
        return jsonify(payload), 200

    @staticmethod
    def list_games(data: Dict[str, Any]):
        """Return every game registered under a developer (or a single game
        when gameId is supplied). Used by the Studio portal sidebar."""
        developer_id = _normalize_string(data.get("developerId") or data.get("developer_id"))
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        game_key = _normalize_string(data.get("gameKey") or data.get("game_key"))

        if not developer_id and not game_id:
            return _error_response(
                "MISSING_DEVELOPER_ID",
                "developerId or gameId is required",
                400,
            )

        if game_id:
            key_error = _require_game_key(game_id, game_key)
            if key_error is not None:
                return key_error
            doc = db.collection(GAME_REGISTRY_COLLECTION).document(game_id).get()
            games = [doc.to_dict()] if doc.exists else []
        else:
            query = db.collection(GAME_REGISTRY_COLLECTION).where(
                "developer_id", "==", developer_id
            )
            games = [snap.to_dict() for snap in query.stream()]

        formatted = [
            {
                "gameId": g.get("game_id"),
                "name": g.get("game_name"),
                "description": g.get("description"),
                "iconUrl": g.get("icon_url"),
                "developerId": g.get("developer_id"),
                "developerName": g.get("developer_name"),
                "liveUrl": g.get("live_url"),
                "status": g.get("status") or "live",
            }
            for g in games
            if isinstance(g, dict)
        ]
        return jsonify({"success": True, "games": formatted}), 200

    @staticmethod
    def register_games(data: Dict[str, Any]):
        developer_id = _normalize_string(data.get("developerId") or data.get("developer_id"))
        games = data.get("games") or []
        if not developer_id:
            return _error_response("MISSING_DEVELOPER_ID", "developerId is required", 400)
        if not isinstance(games, list) or not games:
            return _error_response("MISSING_GAMES", "games list is required", 400)

        developer_ref = db.collection(GAME_DEVELOPERS_COLLECTION).document(developer_id)
        developer_doc = developer_ref.get()
        developer_data = developer_doc.to_dict() if developer_doc.exists else {}
        stored_key = _normalize_string(developer_data.get("game_key") or developer_data.get("gameKey"))

        incoming_key = _normalize_string(data.get("gameKey") or data.get("game_key"))
        if stored_key and incoming_key and stored_key != incoming_key:
            return _error_response("INVALID_GAME_KEY", "Invalid gameKey", 403)

        game_key = stored_key or incoming_key or uuid.uuid4().hex

        developer_ref.set(
            {
                "developer_id": developer_id,
                "game_key": game_key,
                "game_count": len(games),
                "updated_at": firestore.SERVER_TIMESTAMP,
                "created_at": developer_data.get("created_at") or firestore.SERVER_TIMESTAMP,
            },
            merge=True,
        )

        batch = db.batch()
        saved_games: List[str] = []

        for game in games:
            if not isinstance(game, dict):
                continue
            game_id = _normalize_string(game.get("gameId") or game.get("id"))
            if not game_id:
                continue

            game_payload = {
                "game_id": game_id,
                "game_name": _normalize_string(game.get("gameName") or game.get("name")),
                "description": _normalize_string(game.get("description")),
                "icon_url": _normalize_string(game.get("iconUrl") or game.get("icon")),
                "game_url": _normalize_string(game.get("gameUrl") or game.get("url")),
                "genre": _normalize_string(game.get("genre")),
                "developer_id": developer_id,
                "game_key": game_key,
                "updated_at": firestore.SERVER_TIMESTAMP,
                "created_at": game.get("created_at") or firestore.SERVER_TIMESTAMP,
            }

            doc_ref = db.collection(GAME_REGISTRY_COLLECTION).document(game_id)
            batch.set(doc_ref, game_payload, merge=True)
            saved_games.append(game_id)

        if saved_games:
            batch.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "developerId": developer_id,
                    "gameKey": game_key,
                    "gamesSaved": saved_games,
                }
            ),
            200,
        )

    @staticmethod
    def post_score(data: Dict[str, Any]):
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        player_id = _normalize_string(data.get("playerId") or data.get("PlayerId"))
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        score_value = _format_number(_parse_number(_first_present(data, "score", "Score")))
        player_name = _normalize_string(data.get("playerName") or data.get("PlayerName")) or player_id
        metadata = data.get("metadata") or data.get("Metadata") or {}

        # Delegate to gameover service for legacy processing
        response = MinigameGameoverService.build_payload(data)
        response_obj, status_code = response if isinstance(response, tuple) else (response, 200)
        if status_code != 200:
            return response

        payload = response_obj.get_json(silent=True) or {}

        # ── Write to html_games/{gameId}/leaderboard subcollection ──
        if game_id and score_value is not None:
            entry_id = f"{player_id}_{uuid.uuid4().hex[:8]}" if player_id else uuid.uuid4().hex
            leaderboard_entry = {
                "entry_id": entry_id,
                "game_id": game_id,
                "player_id": player_id or None,
                "player_name": player_name,
                "score": score_value,
                "session_id": session_id or None,
                "metadata": metadata if isinstance(metadata, dict) else {},
                "created_at": firestore.SERVER_TIMESTAMP,
            }
            db.collection("html_games").document(game_id).collection("leaderboard").document(entry_id).set(leaderboard_entry)

        payload["economy"] = _get_social_loop_economy()
        payload["sdk"] = _build_sdk_contract(game_id, session_id)
        payload["endpoint"] = "post-score"
        _record_game_activity(
            user_id=player_id,
            game_id=game_id,
            session_id=session_id,
            activity_type="post_score",
        )
        return jsonify(payload), 200

    @staticmethod
    def send_challenge(data: Dict[str, Any]):
        """Send a challenge to a friend — merges the old share-card + send-challenge
        into one endpoint that works like Flutter's 'Challenge a Friend' button.
        Sends game link + score, generates a share card, and writes to both
        game_challenges and game_share_cards collections."""
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        sender_id = _normalize_string(
            data.get("senderId") or data.get("SenderId") or data.get("playerId") or data.get("PlayerId")
        )
        recipient_id = _normalize_string(
            data.get("recipientId") or data.get("RecipientId") or data.get("friendId") or data.get("FriendId")
        )
        challenge_score = _format_number(_parse_number(_first_present(data, "score", "Score")))
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        expires_hours = _parse_number(data.get("expiresHours") or data.get("ExpiresHours")) or 24
        challenge_message = _normalize_string(data.get("message") or data.get("Message")) or "Can you beat this score?"
        challenge_type = _normalize_string(data.get("challengeType") or data.get("ChallengeType")) or "duel"
        share_url = _normalize_string(data.get("shareUrl") or data.get("ShareUrl")) or f"https://inzone.app/game/{game_id}"

        # Share card fields (merged from old share-card endpoint)
        title = _normalize_string(data.get("title") or data.get("Title")) or (
            f"I just scored {challenge_score} — beat me 🎯" if challenge_score else f"Beat my score in {game_id}!"
        )
        template = _normalize_string(data.get("template") or data.get("Template")) or "default"
        image_url = _normalize_string(data.get("imageUrl") or data.get("ImageUrl")) or None

        share_text_parts = [title, challenge_message, share_url]
        share_text = "\n".join([part for part in share_text_parts if part])

        if not game_id:
            return _error_response("MISSING_GAME_ID", "gameId is required", 400)
        if not sender_id:
            return _error_response("MISSING_SENDER_ID", "senderId is required", 400)

        challenge_id = _normalize_string(data.get("challengeId") or data.get("ChallengeId")) or uuid.uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(hours=float(expires_hours))

        # ── Write challenge doc ──
        challenge_data = {
            "challenge_id": challenge_id,
            "game_id": game_id,
            "sender_id": sender_id,
            "recipient_id": recipient_id or None,
            "challenge_type": challenge_type,
            "score": challenge_score,
            "message": challenge_message,
            "share_url": share_url,
            "session_id": session_id or None,
            "status": "pending",
            "expires_at": expires_at,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("game_challenges").document(challenge_id).set(challenge_data)

        # ── Write share card doc (merged from old share-card endpoint) ──
        share_card_id = uuid.uuid4().hex
        share_card_data = {
            "share_card_id": share_card_id,
            "game_id": game_id,
            "user_id": sender_id,
            "score": challenge_score,
            "title": title,
            "message": challenge_message,
            "share_url": share_url,
            "template": template,
            "image_url": image_url,
            "session_id": session_id or None,
            "challenge_id": challenge_id,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("game_share_cards").document(share_card_id).set(share_card_data)

        _record_game_activity(
            user_id=sender_id,
            game_id=game_id,
            session_id=session_id,
            activity_type="send_challenge",
        )

        payload = {
            "success": True,
            "endpoint": "send-challenge",
            "challenge": {
                "challengeId": challenge_id,
                "gameId": game_id,
                "senderId": sender_id,
                "recipientId": recipient_id or None,
                "type": challenge_type,
                "score": challenge_score,
                "message": challenge_message,
                "expiresAt": expires_at.isoformat().replace("+00:00", "Z"),
                "status": "pending",
            },
            "shareCard": {
                "shareCardId": share_card_id,
                "title": title,
                "message": challenge_message,
                "url": share_url,
                "template": template,
                "imageUrl": image_url,
            },
            "share": {
                "title": title,
                "message": challenge_message,
                "url": share_url,
                "text": share_text,
                "subject": title,
            },
            "shareTargets": ["iMessage", "WhatsApp", "Discord", "TikTok", "Instagram", "X"],
            "economy": _get_social_loop_economy(),
            "sdk": _build_sdk_contract(game_id, session_id),
        }
        return jsonify(payload), 200

    @staticmethod
    def progress_share(data: Dict[str, Any]):
        """Share game progress — generates a shareable visual/snapshot of an
        achievement or run, like Flutter's 'Share Progress' button.
        Writes to game_share_cards with type='progress'."""
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        user_id = _normalize_string(
            data.get("userId") or data.get("UserId") or data.get("playerId") or data.get("PlayerId")
        )
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        score_value = _format_number(_parse_number(_first_present(data, "score", "Score")))
        title = _normalize_string(data.get("title") or data.get("Title")) or (
            f"New high score — {score_value}!" if score_value else "Check out my progress!"
        )
        message = _normalize_string(data.get("message") or data.get("Message")) or "Check out what I just did 🔥"
        share_url = _normalize_string(data.get("shareUrl") or data.get("ShareUrl")) or f"https://inzone.app/game/{game_id}"
        visual = _normalize_string(data.get("visual") or data.get("Visual")) or "auto"
        metrics = data.get("metrics") or data.get("Metrics") or {}
        if not isinstance(metrics, dict):
            metrics = {"value": metrics}
        achievements = data.get("achievements") or data.get("Achievements") or []
        if not isinstance(achievements, list):
            achievements = [achievements]
        template = _normalize_string(data.get("template") or data.get("Template")) or "progress"
        image_url = _normalize_string(data.get("imageUrl") or data.get("ImageUrl")) or None

        if not game_id:
            return _error_response("MISSING_GAME_ID", "gameId is required", 400)
        if not user_id:
            return _error_response("MISSING_USER_ID", "userId is required", 400)

        share_card_id = uuid.uuid4().hex
        share_card_data = {
            "share_card_id": share_card_id,
            "type": "progress",
            "game_id": game_id,
            "user_id": user_id,
            "score": score_value,
            "title": title,
            "message": message,
            "share_url": share_url,
            "visual": visual,
            "metrics": metrics,
            "achievements": achievements,
            "template": template,
            "image_url": image_url,
            "session_id": session_id or None,
            "created_at": firestore.SERVER_TIMESTAMP,
        }
        db.collection("game_share_cards").document(share_card_id).set(share_card_data)

        _record_game_activity(
            user_id=user_id,
            game_id=game_id,
            session_id=session_id,
            activity_type="progress_share",
        )

        payload = {
            "success": True,
            "endpoint": "progress/share",
            "shareCard": {
                "shareCardId": share_card_id,
                "gameId": game_id,
                "userId": user_id,
                "score": score_value,
                "title": title,
                "message": message,
                "url": share_url,
                "visual": visual,
                "metrics": metrics,
                "achievements": achievements,
                "template": template,
                "imageUrl": image_url,
            },
            "share": {
                "title": title,
                "message": message,
                "url": share_url,
            },
            "shareTargets": ["iMessage", "WhatsApp", "Discord", "TikTok", "Instagram", "X"],
            "economy": _get_social_loop_economy(),
            "sdk": _build_sdk_contract(game_id, session_id),
        }
        return jsonify(payload), 200

    @staticmethod
    def get_leaderboard(data: Dict[str, Any]):
        """Retrieve the leaderboard for a game from html_games/{gameId}/leaderboard."""
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        limit = int(_parse_number(data.get("limit") or data.get("Limit")) or 50)
        scope = _normalize_string(data.get("scope") or data.get("Scope")) or "global"

        if not game_id:
            return _error_response("MISSING_GAME_ID", "gameId is required", 400)
        if limit < 1:
            limit = 50
        if limit > 200:
            limit = 200

        leaderboard_ref = (
            db.collection("html_games")
            .document(game_id)
            .collection("leaderboard")
            .order_by("score", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        docs = leaderboard_ref.stream()

        entries = []
        rank = 0
        for doc in docs:
            rank += 1
            entry = doc.to_dict() or {}
            created_at = entry.get("created_at")
            if hasattr(created_at, "isoformat"):
                created_at = created_at.isoformat().replace("+00:00", "Z")
            else:
                created_at = str(created_at) if created_at else None

            entries.append({
                "rank": rank,
                "entryId": entry.get("entry_id", doc.id),
                "playerId": entry.get("player_id"),
                "playerName": entry.get("player_name"),
                "score": entry.get("score", 0),
                "metadata": entry.get("metadata", {}),
                "createdAt": created_at,
            })

        payload = {
            "success": True,
            "endpoint": "leaderboard",
            "gameId": game_id,
            "scope": scope,
            "totalEntries": len(entries),
            "entries": entries,
        }
        return jsonify(payload), 200

    @staticmethod
    def open_chat(data: Dict[str, Any]):
        """Open or join the game's designated group chat. Sends a message to
        the conversation thread tied to the game. If the conversation doesn't
        exist yet it's created; if it does, participants are merged in."""
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        session_id = _normalize_string(data.get("sessionId") or data.get("SessionId"))
        thread_id = _normalize_string(data.get("threadId") or data.get("ThreadId"))
        user_id = _normalize_string(data.get("userId") or data.get("UserId") or data.get("playerId") or data.get("PlayerId"))
        message = _normalize_string(data.get("message") or data.get("Message")) or "A new player joined the game thread"
        characters = data.get("characters") or data.get("Characters") or []
        if not isinstance(characters, list):
            characters = [characters]
        context = data.get("context") or data.get("Context") or {}
        if not isinstance(context, dict):
            context = {"value": context}

        if not game_id and not thread_id:
            return _error_response("MISSING_GAME_OR_THREAD", "gameId or threadId is required", 400)

        conversation_id = thread_id or f"post-session-{game_id}"
        conversation_ref = db.collection("conversations").document(conversation_id)
        conversation_doc = conversation_ref.get()

        participants = []
        if user_id:
            participants.append(user_id)
        for character in characters:
            character_name = _normalize_string(character)
            if character_name and character_name not in participants:
                participants.append(character_name)

        conversation_data = {
            "conversationId": conversation_id,
            "isGameChat": True,
            "gameId": game_id or None,
            "sessionId": session_id or None,
            "participants": participants,
            "characters": characters,
            "context": context,
            "lastMessage": message,
            "lastMessageTime": firestore.SERVER_TIMESTAMP,
            "updatedAt": firestore.SERVER_TIMESTAMP,
            "createdAt": firestore.SERVER_TIMESTAMP,
            "source": "social-loop",
        }

        if conversation_doc.exists:
            existing_data = conversation_doc.to_dict() or {}
            existing_participants = list(existing_data.get("participants", []))
            for participant in participants:
                if participant not in existing_participants:
                    existing_participants.append(participant)
            conversation_data["participants"] = existing_participants
            conversation_data["createdAt"] = existing_data.get("createdAt", firestore.SERVER_TIMESTAMP)

        conversation_ref.set(conversation_data)
        _record_game_activity(
            user_id=user_id,
            game_id=game_id,
            session_id=session_id,
            activity_type="open_chat",
        )

        payload = {
            "success": True,
            "endpoint": "open-chat",
            "conversation": {
                "conversationId": conversation_id,
                "gameId": game_id or None,
                "sessionId": session_id or None,
                "participants": conversation_data["participants"],
                "characters": characters,
                "context": context,
            },
            "ui": {
                "title": "Group chat",
                "subtitle": "Drop the player into a per-game thread that keeps the room alive.",
            },
            "economy": _get_social_loop_economy(),
            "sdk": _build_sdk_contract(game_id, session_id),
        }
        return jsonify(payload), 200

    # ────────────────────────────────────────────────────────────────
    # Integration Health
    # ────────────────────────────────────────────────────────────────

    @staticmethod
    def integration_health(data: Dict[str, Any]):
        """Return integration health stats for a game over the last 24 hours.

        Aggregates from game_sdk_metrics hourly bucket docs:
          - Total request count
          - Error count / error rate %
          - Average latency (ms)
          - p95 latency (ms)
          - Endpoints hit
          - Hourly breakdown for sparklines
        """
        game_id = _normalize_string(data.get("gameId") or data.get("GameId"))
        hours_back = int(_parse_number(data.get("hours") or data.get("Hours")) or 24)
        if hours_back < 1:
            hours_back = 24
        if hours_back > 168:  # cap at 7 days
            hours_back = 168

        if not game_id:
            return _error_response("MISSING_GAME_ID", "gameId is required", 400)

        now = _utc_now()
        hour_keys = []
        for i in range(hours_back):
            h = now - timedelta(hours=i)
            hour_keys.append(f"{game_id}_{h.strftime('%Y-%m-%dT%H')}")

        total_requests = 0
        total_errors = 0
        total_latency_ms = 0.0
        all_latency_samples: List[float] = []
        endpoints_hit: set = set()
        hourly_breakdown: List[Dict[str, Any]] = []

        # Fetch all hourly bucket docs (batch get)
        refs = [db.collection(METRICS_COLLECTION).document(doc_id) for doc_id in hour_keys]
        docs = db.get_all(refs)

        for doc in docs:
            if not doc.exists:
                continue
            bucket = doc.to_dict() or {}
            reqs = int(bucket.get("requests", 0))
            errs = int(bucket.get("errors", 0))
            lat_sum = float(bucket.get("total_latency_ms", 0))
            samples = bucket.get("latency_samples", [])
            eps = bucket.get("endpoints_hit", [])

            total_requests += reqs
            total_errors += errs
            total_latency_ms += lat_sum
            if isinstance(samples, list):
                all_latency_samples.extend(samples)
            if isinstance(eps, list):
                endpoints_hit.update(eps)

            hourly_breakdown.append({
                "hour": bucket.get("hour", doc.id),
                "requests": reqs,
                "errors": errs,
                "avgLatencyMs": round(lat_sum / reqs, 1) if reqs > 0 else 0,
            })

        # Sort hourly breakdown chronologically
        hourly_breakdown.sort(key=lambda x: x["hour"])

        # Calculate percentiles
        avg_latency_ms = round(total_latency_ms / total_requests, 1) if total_requests > 0 else 0
        error_rate = round((total_errors / total_requests) * 100, 3) if total_requests > 0 else 0

        p50_latency = 0.0
        p95_latency = 0.0
        p99_latency = 0.0
        if all_latency_samples:
            sorted_samples = sorted(all_latency_samples)
            n = len(sorted_samples)
            p50_latency = round(sorted_samples[int(n * 0.50)], 1)
            p95_latency = round(sorted_samples[min(int(n * 0.95), n - 1)], 1)
            p99_latency = round(sorted_samples[min(int(n * 0.99), n - 1)], 1)

        # Format for display
        def _fmt_count(count: int) -> str:
            if count >= 1_000_000:
                return f"{count / 1_000_000:.2f}M"
            if count >= 1_000:
                return f"{count / 1_000:.1f}K"
            return str(count)

        payload = {
            "success": True,
            "endpoint": "integration-health",
            "gameId": game_id,
            "period": f"last {hours_back}h",
            "summary": {
                "requests": total_requests,
                "requestsFormatted": _fmt_count(total_requests),
                "errors": total_errors,
                "errorRate": error_rate,
                "errorRateFormatted": f"{error_rate}%",
                "avgLatencyMs": avg_latency_ms,
                "p50LatencyMs": p50_latency,
                "p95LatencyMs": p95_latency,
                "p99LatencyMs": p99_latency,
                "p95LatencyFormatted": f"{p95_latency}ms" if p95_latency > 0 else "—",
                "endpointsHit": sorted(endpoints_hit),
            },
            "hourly": hourly_breakdown,
        }
        return jsonify(payload), 200
