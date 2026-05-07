# InZone Game SDK - Social Loop

This contract is for game developers integrating HTML placeholders today and Unity-based games later. It is isolated from the rest of the InZone backend and only covers gameplay, coin commerce, and the game dashboard.

## Quick Navigation

- [Base Path](#base-path)
- [Gameplay Endpoints](#gameplay-endpoints)
- [Coin Commerce](#coin-commerce)
- [Dashboard](#dashboard)
- [Error Codes](#error-codes)
- [Response Shape](#response-shape)

## Base Path

All endpoints live under:

`/api/game-sdk`

## Gameplay Endpoints

### 1. Open Social Screen

`GET` or `POST` `/api/game-sdk/open-social-screen`

Use this first from Unity or any game shell to fetch the contract, coin tiers, and action list.

Example request:

```json
{
  "gameId": "post-session",
  "gameName": "Nova Arena",
  "sessionId": "sess_123",
  "playerId": "user_42",
  "platform": "unity",
  "clientBuild": "1.0.0"
}
```

The response includes:

- `screen` title + subtitle
- `economy` coin tiers + commission rate
- `actions` for all gameplay, coin, and dashboard endpoints
            

### 2. Post Score

`POST` `/api/game-sdk/post-score`

Submits a result, stores leaderboard data, and returns share/leaderboard context.

Example request:

```json
{
  "gameId": "post-session",
  "gameName": "Nova Arena",
  "playerId": "user_42",
  "score": 4820,
  "level": 12,
  "durationMs": 92447,
  "sessionId": "sess_123",
  "platform": "unity"
}
```

### 3. Send Challenge

`POST` `/api/game-sdk/send-challenge`

Creates a 24-hour duel challenge for another player.

Example request:

```json
{
  "gameId": "post-session",
  "senderId": "user_42",
  "recipientId": "friend_99",
  "score": 4820,
  "message": "Beat this if you can",
  "sessionId": "sess_123"
}
```

### 4. Share Card

`POST` `/api/game-sdk/share-card`

Generates a branded social share payload for iMessage, Discord, TikTok, Instagram, X, and similar share sheets.

Example request:

```json
{
  "gameId": "post-session",
  "userId": "user_42",
  "score": 4820,
  "title": "I scored 4820 in Nova Arena!",
  "message": "Can you beat me?",
  "template": "default"
}
```

### 5. Open Chat

`POST` `/api/game-sdk/open-chat`

Creates or reuses a Firestore `conversations` document for the post-session game thread.

Example request:

```json
{
  "gameId": "post-session",
  "userId": "user_42",
  "sessionId": "sess_123",
  "characters": ["nova", "orin"],
  "context": {
    "score": 4820,
    "result": "win"
  }
}
```

## Coin Commerce

These endpoints are the in-game payment hooks for Unity and HTML games. Each one is a fixed-value purchase and requires the same three core fields: `userId`, `gameId`, and a human-readable `title` for the transaction.

Game Developers Receive a 90% cut from any microtransaction

### Tier 1 - 10 Coins

`POST` `/api/game-sdk/coins/tier-10`

Use this for impulse moments: retries, small boosts, cosmetic changes for one session.

Example request:

```json
{
  "userId": "user_42",
  "gameId": "post-session",
  "title": "Extra attempt after fail state",
  "description": "Grants one more run without breaking game flow",
  "sessionId": "sess_123"
}
```

### Tier 2 - 50 Coins

`POST` `/api/game-sdk/coins/tier-50`

Use this for meaningful advantages: full-game power-ups, harder modes, leaderboard entry fees.

### Tier 3 - 150 Coins

`POST` `/api/game-sdk/coins/tier-150`

Use this for lasting unlocks: skins, permanent abilities, exclusive modes.

### Tier 4 - 400 Coins

`POST` `/api/game-sdk/coins/tier-400`

Use this sparingly for season passes, full game unlocks, or bundles.

### Payment Response

Every tier endpoint returns `data` with:

- `transactionId`
- `title`
- `description`
- `coins`
- `commissionCoins`
- `developerCoins`
- `commissionRate`
- `newBalance`
- `currency`
- `confirmation`

## Dashboard

`GET` `/api/game-sdk/dashboard`

Query parameters:

- `gameId` required
- `userId` optional

This endpoint returns:

- retention metrics: `day1Retention`, `day3Retention`, `day7Retention`
- session activity: `sessionCount`, `totalPlaySeconds`, `averageSessionSeconds`
- player activity: `totalPlayers`, `activePlayers7d`
- microtransactions: `totalCoinsUsed`, `averageCoinsPerSession`, `sessionsWithCoins`
- payout summary: `grossCoins`, `commissionCoins`, `developerPayoutCoins`, `netPayoutCoins`, `commissionRate`, `status`

Example request:

```text
/api/game-sdk/dashboard?gameId=post-session
```

Use `userId` when you want a player-scoped dashboard view.

## Error Codes

- `MISSING_GAME_ID`
- `MISSING_USER_ID`
- `MISSING_TITLE`
- `MISSING_SCORE`
- `MISSING_SENDER_ID`
- `MISSING_RECIPIENT_ID`
- `MISSING_GAME_OR_THREAD`
- `INVALID_COIN_TIER`
- `INSUFFICIENT_BALANCE`
- `USER_NOT_FOUND`
- `INVALID_REQUEST`
- `INTERNAL_ERROR`


## Rate Limits
-- REMOVED: Rate limits are not enforced by the SDK endpoints.

## Response Shape

Success responses include `success: true` with endpoint-specific payload fields.

Error responses include:

```json
{
  "success": false,
  "error": "Human readable message",
  "code": "MISSING_GAME_ID",
  "details": {
    "optional": "context"
  }
}
```
