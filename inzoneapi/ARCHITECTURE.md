# InZone Backend Architecture

## Overview

This document describes the modular architecture of the InZone backend API. The codebase is organized using a domain-driven design approach with clear separation between routes (HTTP layer) and services (business logic layer).

## Directory Structure

```
inzoneapi/
├── app.py                          # Main Flask application (blueprint registration only)
├── config.py                       # Application configuration and constants
├── dependencies.py                 # Shared dependencies (Firebase, OpenAI, etc.)
│
├── models/                         # Data models & schemas
│   ├── __init__.py
│   └── schemas.py
│
├── services/                       # Business logic layer
│   ├── user/                       # User domain services
│   ├── content/                    # Content domain services
│   ├── monetization/              # Monetization services
│   ├── ai/                        # AI domain services
│   ├── recommendation/            # Recommendation engine
│   ├── notifications/             # Notification services
│   ├── media/                     # Media processing
│   └── groups/                    # Group chat services
│
├── routes/                        # API endpoints (thin controllers)
│   ├── core/                      # Core routes
│   ├── user/                      # User domain routes
│   ├── content/                   # Content domain routes
│   ├── monetization/              # Monetization routes
│   ├── ai/                        # AI domain routes
│   ├── groups/                    # Group chat routes
│   ├── notifications/             # Notification routes
│   └── admin/                     # Admin routes
│
└── utils/                         # Shared utilities
```

---

## Services Layer (Business Logic)

### 1. User Domain (`services/user/`)

Handles all user-related business logic.

#### `profile_service.py`
- User profile CRUD operations
- Profile updates (name, username, bio, interests, profile picture)
- Profile retrieval

#### `social_service.py`
- Follow/unfollow logic
- Follower/following management
- Remove from followers/following

#### `referral_service.py`
- Referral code generation
- Referral application
- Referral reward distribution
- Referral statistics

**Key Functions:**
- `create_user_profile()`
- `update_profile_field()`
- `follow_user()`, `unfollow_user()`
- `generate_referral_code()`, `apply_referral()`

---

### 2. Content Domain (`services/content/`)

Manages all content-related functionality.

#### `post_service.py`
- Post CRUD operations (create, update, delete)
- Like/unlike posts
- Post retrieval by ID
- User's liked posts

#### `feed_service.py`
- Feed generation algorithms
- Feed ranking and personalization
- Posts flow (retrieval + ranking pipeline)
- Feed quality testing

#### `comment_service.py`
- Comment creation
- Comment replies
- Comment notifications

#### `category_service.py`
- Automatic category generation for posts using AI
- Content classification

**Key Functions:**
- `create_post()`, `update_post()`, `delete_post()`
- `like_post()`, `unlike_post()`
- `generate_feed()`, `rank_posts()`
- `generate_categories()`

---

### 3. Monetization Domain (`services/monetization/`)

Handles all payment and monetization features.

#### `wallet_service.py`
- Wallet balance management
- InCash transactions
- Spending operations

#### `subscription_service.py`
- iOS subscription verification
- Android subscription verification
- Subscription status tracking
- Monthly subscription rewards processing

#### `tipping_service.py`
- Send tips between users
- Tip transaction history
- Tip notifications

#### `store_service.py`
- Asset store items management
- Item purchases
- User inventory

**Key Functions:**
- `get_balance()`, `purchase_incash()`, `spend_incash()`
- `verify_ios_subscription()`, `verify_android_subscription()`
- `send_tip()`, `get_tip_transactions()`
- `purchase_item()`, `get_inventory()`

---

### 4. AI Domain (`services/ai/`)

All AI-related services organized by functionality.

#### Voice Sub-domain (`ai/voice/`)

##### `elevenlabs_service.py`
- ElevenLabs API integration
- Voice creation and management
- TTS generation
- Voice ID caching

##### `voice_chat_service.py`
- AI voice chat sessions
- Voice character setup
- Batch voice setup for characters

#### Chat Sub-domain (`ai/chat/`)

##### `chat_service.py`
- AI text chat
- Character-based responses
- Chat history management
- Sentiment analysis integration

#### Engagement Sub-domain (`ai/engagement/`)

##### `ai_engagement_service.py`
- AI user engagement logic
- Engagement analytics

##### `inzone_ai_engagement.py`
- Advanced AI engagement features
- Multi-character engagement

##### `ai_engagement_scheduler.py`
- Scheduled AI engagement tasks
- Engagement automation

##### `dm_responder_service.py`
- Automatic DM responses
- DM monitoring and replies

#### Other AI Services

##### `content_generation_service.py`
- AI-generated posts
- Content creation for AI characters

##### `ai_user_service.py`
- AI user profile management
- AI character CRUD
- AI user follow/unfollow
- Popular character tracking
- Upvote/downvote system

**Key Functions:**
- `create_voice()`, `tts_generate()`, `ensure_voice_id_for_character()`
- `generate_ai_response()`, `ai_voice_chat()`
- `schedule_ai_engagement()`, `execute_scheduled_engagement()`
- `ai_send_dm()`, `ai_like_post()`, `ai_comment_on_post()`
- `create_ai_user()`, `update_ai_profile()`

---

### 5. Recommendation Domain (`services/recommendation/`)

#### `gorse_client.py`
- Gorse recommendation system integration
- User item tracking (views, likes, comments, shares)
- Similar post recommendations
- Personalized feed recommendations

**Key Functions:**
- `track_view()`, `track_like()`, `track_comment()`, `track_share()`
- `get_similar_posts()`, `get_recommendations()`

---

### 6. Notifications Domain (`services/notifications/`)

#### `notification_service.py`
- FCM token management
- Push notification sending
- Notification preferences
- Notification queueing

#### `ai_nudge_scheduler.py`
- Daily AI nudges
- Scheduled notification campaigns

#### `rare_offer_service.py`
- Weekly rare offer notifications
- Offer eligibility checking
- Offer logging and tracking

**Key Functions:**
- `register_fcm_token()`, `send_push_notification()`
- `queue_notification()`, `send_batch_notifications()`
- `trigger_daily_nudges()`, `trigger_weekly_rare_offers()`

---

### 7. Media Domain (`services/media/`)

#### `media_analysis_service.py`
- Media content analysis
- Content moderation

#### `image_service.py`
- Image generation (DALL-E, Meshy)
- Image processing
- Base64 encoding/decoding
- 3D avatar generation

**Key Functions:**
- `image_generate()`, `generate_3d_avatar()`
- `image_to_base64()`

---

### 8. Groups Domain (`services/groups/`)

#### `group_service.py`
- Group chat creation
- Participant management (add/remove)
- AI character integration in groups
- Premium group access control

**Key Functions:**
- `create_group_chat()`, `add_participant()`, `delete_participant()`
- `add_ai_character()`, `delete_ai_character()`
- `check_group_access()`

---

## Routes Layer (HTTP Endpoints)

Routes are thin controllers that handle HTTP requests/responses and delegate to services.

### 1. Core Routes (`routes/core/`)

#### `health.py`
- `GET /` - Test endpoint
- `GET /health` - Health check

---

### 2. User Routes (`routes/user/`)

#### `profile.py` (14 endpoints)
- `POST /user/create-profile` - Create user profile
- `POST /user/update-name` - Update name
- `POST /user/update-username` - Update username
- `POST /user/update-profile` - Update entire profile
- `POST /user/update-profile-picture` - Update profile picture
- `POST /user/update-bio` - Update bio
- `POST /user/update-interests` - Update interests
- `GET /user/get-profile` - Get user profile
- `POST /feedback` - Send feedback

#### `social.py` (4 endpoints)
- `POST /user/follow` - Follow a user
- `POST /user/unfollow` - Unfollow a user
- `POST /user/remove-from-following` - Remove from following list
- `POST /user/remove-from-followers` - Remove from followers list

#### `referral.py` (3 endpoints)
- `POST /user/generate-referral-code` - Generate referral code
- `POST /user/apply-referral` - Apply referral code
- `GET /user/referral-stats` - Get referral statistics

---

### 3. Content Routes (`routes/content/`)

#### `posts.py` (6 endpoints)
- `POST /feed/create-human-post` - Create human post
- `POST /feed/update-human-post` - Update human post
- `POST /feed/repost` - Repost a post
- `POST /feed/create-repost` - Create repost
- `POST /user/like-post` - Like a post
- `POST /user/unlike-post` - Unlike a post
- `POST /user/get-liked-posts` - Get user's liked posts

#### `feed.py` (4 endpoints)
- `POST /feed/get-feed` - Get personalized feed
- `GET /feed/posts-flow` - Get posts flow
- `GET /feed/test-feed-quality` - Test feed quality
- `POST /feed/get-user-posts` - Get user's posts

#### `comments.py` (2 endpoints)
- `POST /feed/write-comment` - Write a comment
- `POST /api/notifications/events/comment-reply` - Comment reply notification

#### `gorse.py` (5 endpoints)
- `POST /feed/track-view` - Track post view
- `POST /feed/track-like` - Track post like
- `POST /feed/track-comment` - Track post comment
- `POST /feed/track-share` - Track post share
- `GET /feed/similar-posts/<post_id>` - Get similar posts

---

### 4. Monetization Routes (`routes/monetization/`)

#### `wallet.py` (6 endpoints)
- `GET /wallet/balance` - Get wallet balance
- `POST /wallet/purchase-incash` - Purchase InCash
- `POST /wallet/spend-incash` - Spend InCash
- `POST /wallet/update-subscription` - Update subscription
- `GET /wallet/subscription-status` - Check subscription status
- `POST /wallet/process-subscription-rewards` - Process monthly rewards

#### `tipping.py` (2 endpoints)
- `POST /user/tip/send` - Send tip
- `GET /user/tip/transactions/<user_id>` - Get tip transactions

#### `store.py` (3 endpoints)
- `GET /store/items` - Get store items
- `POST /store/purchase` - Purchase item
- `GET /store/inventory` - Get user inventory

---

### 5. AI Routes (`routes/ai/`)

#### `voice.py` (6 endpoints)
- `GET /api/ai/voice/debug-character` - Debug character voice
- `POST /api/ai/voice/test` - Test voice endpoint
- `POST /api/ai/voice/ensure` - Ensure voice for character
- `POST /api/ai/voice/chat` - AI voice chat
- `POST /api/ai/voice/batch-setup-voices` - Batch setup voices

#### `chat.py` (3 endpoints)
- `POST /api/ai/chat` - Text chat with AI
- `POST /api/sentiment-analysis` - Sentiment analysis
- `POST /api/main-ai-chat` - Main AI chat endpoint

#### `users.py` (8 endpoints)
- `POST /api/ai/create-ai-user` - Create AI user
- `POST /api/ai/update-ai-user` - Update AI profile
- `GET /api/ai/get-ai-user` - Get AI profile
- `GET /api/ai/carousel/characters` - Get carousel characters
- `POST /api/ai/popular-character-name` - Update popular character name
- `POST /api/ai/upvote` - Upvote character
- `POST /api/ai/downvote` - Downvote character
- `GET /api/ai/chat-counter` - Get chat counter

#### `social.py` (6 endpoints)
- `POST /api/ai/follow` - Follow AI user
- `POST /api/ai/unfollow` - Unfollow AI user
- `POST /api/ai/get-followers` - Get AI followers
- `POST /api/ai/get-following` - Get AI following
- `POST /api/ai/remove-from-followers` - Remove AI follower
- `POST /api/ai/remove-from-following` - Remove AI following

#### `content.py` (3 endpoints)
- `POST /ai-content/generate-post` - Generate AI post
- `POST /feed/create-ai-post` - Create AI post
- `POST /api/ai/generate-image` - Generate image

#### `engagement.py` (20+ endpoints)
- `POST /api/ai/send-dm` - AI send DM
- `POST /api/ai/like-post` - AI like post
- `POST /api/ai/comment-on-post` - AI comment on post
- `POST /api/ai/bulk-engage` - Bulk AI engagement
- `GET /api/ai/engagement-stats` - Get engagement stats
- `GET /api/ai/get-popular-characters` - Get popular characters for DM
- `POST /api/ai/dm-auto-responder` - DM auto responder
- `POST /api/ai/monitor-dms` - Monitor and respond to DMs

#### `scheduler.py` (6 endpoints)
- `POST /api/ai/schedule-character-engagement` - Schedule character engagement
- `POST /api/ai/schedule-all-characters` - Schedule all characters
- `POST /api/ai/schedule-engagement-auto` - Auto schedule engagement
- `POST /api/ai/execute-scheduled-engagement` - Execute scheduled engagement
- `GET /api/ai/engagement-status` - Get engagement status
- `GET /api/ai/engagement/scheduler/status` - Get scheduler status
- `POST /api/ai/engagement/scheduler/control` - Control scheduler

---

### 6. Groups Routes (`routes/groups/`)

#### `management.py` (5 endpoints)
- `POST /group/create-groupchat` - Create group chat
- `POST /group/add-participant` - Add participant
- `POST /group/delete-participant` - Delete participant
- `POST /group/add-ai-character` - Add AI character to group
- `POST /group/delete-ai-character` - Delete AI character from group

#### `access.py` (2 endpoints)
- `GET /groups/available` - Get available groups
- `POST /groups/join` - Join group
- `GET /groups/user-access` - Check user access

---

### 7. Notifications Routes (`routes/notifications/`)

#### `events.py` (7 endpoints)
- `POST /api/notifications/events/group-message` - Group message notification
- `POST /api/notifications/events/group-mention` - Group mention notification
- `POST /api/notifications/events/direct-message` - Direct message notification
- `POST /api/notifications/events/post-engagement` - Post engagement notification
- `POST /api/notifications/events/user-follow` - User follow notification
- `POST /api/notifications/events/rare-offer` - Rare offer notification
- `POST /api/notifications/events/ai-nudge` - AI nudge notification

#### `preferences.py` (1 endpoint)
- `POST /api/notifications/preferences` - Update notification preferences

#### `push.py` (2 endpoints)
- `POST /api/notifications/register-token` - Register FCM token
- `POST /api/notifications/send-push` - Send push notification

#### `debug.py` (3 endpoints)
- `GET /api/notifications/debug/count` - Debug notification count
- `GET /api/notifications/user/<user_id>/all` - Get all user notifications
- `POST /api/notifications/test/create-sample` - Create sample notifications

#### Scheduler endpoints (2 endpoints)
- `POST /api/scheduler/daily-nudges` - Trigger daily nudges
- `POST /api/scheduler/rare-offers` - Trigger weekly rare offers

---

### 8. Admin Routes (`routes/admin/`)

#### `store.py` (1 endpoint)
- `POST /admin/store/add-item` - Add store item

#### `groups.py` (1 endpoint)
- `POST /admin/groups/create` - Create group

#### `users.py` (1 endpoint)
- `GET /api/admin/search-user` - Search human users

#### `maintenance.py` (5+ endpoints)
- `GET /api/ai/comments/debug` - Debug comments
- `POST /api/ai/comments/cleanup-incorrect-structure` - Cleanup AI comments
- `POST /api/ai/migrate-post-likes` - Migrate post likes
- `GET /api/ai/verify-post-likes-migration` - Verify migration
- `POST /api/admin/fix-missing-uid` - Fix missing UIDs

---

## Utilities (`utils/`)

### `helpers.py`
- `get_user_name()` - Get username by user ID
- General helper functions

### `image_utils.py`
- `image_to_base64()` - Convert image to base64
- Image processing utilities

### `validators.py`
- Input validation functions
- Request data validation

### `formatters.py`
- Response formatting
- Data transformation utilities

---

## Configuration Files

### `config.py`
Contains all configuration constants:
- API keys (OpenAI, Meshy, ElevenLabs)
- Firebase configuration
- Gorse configuration
- Feature flags
- Environment-specific settings

### `dependencies.py`
Shared dependencies initialization:
- Firebase/Firestore client
- OpenAI client
- Gorse client
- ElevenLabs service
- Other shared instances

---

## Design Principles

### 1. Separation of Concerns
- **Routes**: Handle HTTP (request/response, validation, error handling)
- **Services**: Contain business logic (no HTTP concerns)
- **Utils**: Shared utilities used across domains

### 2. Domain-Driven Design
- Code organized by business domain (user, content, AI, etc.)
- Each domain is self-contained and can evolve independently

### 3. Single Responsibility
- Each file/class has one clear purpose
- Easy to locate and modify specific functionality

### 4. DRY (Don't Repeat Yourself)
- Shared logic in services and utils
- Reusable across multiple routes

### 5. Testability
- Services can be tested without HTTP layer
- Routes can be tested with mocked services

---

## Common Patterns

### Route Pattern
```python
# routes/user/profile.py
from flask import Blueprint, request, jsonify
from services.user.profile_service import ProfileService

user_profile_bp = Blueprint('user_profile', __name__)

@user_profile_bp.route('/user/update-name', methods=['POST'])
def update_name():
    try:
        data = request.get_json()
        result = ProfileService.update_name(data['user_id'], data['name'])
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### Service Pattern
```python
# services/user/profile_service.py
from dependencies import db

class ProfileService:
    @staticmethod
    def update_name(user_id: str, name: str) -> dict:
        # Validate input
        if not name or len(name) < 2:
            raise ValueError("Name must be at least 2 characters")

        # Business logic
        user_ref = db.collection('users').document(user_id)
        user_ref.update({'name': name})

        return {'success': True, 'message': 'Name updated'}
```

### Blueprint Registration
```python
# app.py
from flask import Flask
from routes.user.profile import user_profile_bp
from routes.user.social import user_social_bp

app = Flask(__name__)

# Register blueprints
app.register_blueprint(user_profile_bp)
app.register_blueprint(user_social_bp)
```

---

## Migration Status

- [ ] Phase 1: Extract Services
- [ ] Phase 2: Create Route Blueprints
- [ ] Phase 3: Move Business Logic to Services
- [ ] Phase 4: Configuration Cleanup

---

## Contributing

When adding new features:

1. **Identify the domain** - Which domain does this feature belong to?
2. **Create service first** - Add business logic to appropriate service
3. **Create route** - Add thin controller in appropriate route file
4. **Update this document** - Document new endpoints and services
5. **Write tests** - Test services and routes separately

---

## Questions?

For questions about architecture decisions or where to add new code, refer to this document or contact the backend team lead.
