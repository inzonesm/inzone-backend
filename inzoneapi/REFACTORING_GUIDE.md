# InZone Backend Refactoring Guide

## Overview

This guide provides step-by-step instructions for refactoring the monolithic `app.py` (9,221 lines) into a modular, maintainable architecture. The refactoring is divided into phases to minimize risk and ensure the application remains functional throughout the process.

**⚠️ Important:** Always work on a separate branch and test thoroughly before merging to main.

---

## Prerequisites

1. **Create a backup branch**
   ```bash
   git checkout -b backup/pre-refactoring
   git push origin backup/pre-refactoring
   ```

2. **Create working branch**
   ```bash
   git checkout main
   git checkout -b refactor/modularize-backend
   ```

3. **Ensure tests exist** (or create basic smoke tests)
   - Test critical endpoints after each phase
   - Keep a list of endpoints to verify

4. **Set up local development environment**
   ```bash
   pip install -r requirements.txt
   ```

---

## Refactoring Phases

### Phase 1: Prepare Foundation (Low Risk)
**Goal:** Set up the directory structure and configuration files without breaking existing code.

**Estimated Time:** 2-3 hours

#### Step 1.1: Create Directory Structure

```bash
cd inzoneapi

# Create main directories
mkdir -p routes/{core,user,content,monetization,ai,groups,notifications,admin}
mkdir -p services/{user,content,monetization,ai/voice,ai/chat,ai/engagement,recommendation,notifications,media,groups}
mkdir -p models
mkdir -p utils

# Create __init__.py files
touch routes/__init__.py
touch routes/core/__init__.py
touch routes/user/__init__.py
touch routes/content/__init__.py
touch routes/monetization/__init__.py
touch routes/ai/__init__.py
touch routes/groups/__init__.py
touch routes/notifications/__init__.py
touch routes/admin/__init__.py

touch services/__init__.py
touch services/user/__init__.py
touch services/content/__init__.py
touch services/monetization/__init__.py
touch services/ai/__init__.py
touch services/ai/voice/__init__.py
touch services/ai/chat/__init__.py
touch services/ai/engagement/__init__.py
touch services/recommendation/__init__.py
touch services/notifications/__init__.py
touch services/media/__init__.py
touch services/groups/__init__.py

touch models/__init__.py
touch utils/__init__.py
```

#### Step 1.2: Create Configuration Files

**Create `config.py`:**

```python
# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""

    # API Keys
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    MESHY_API_KEY = os.environ.get("MESH_API_KEY")
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "sk_a7adae8a80cf5bfe52afd8e5ca8fb1307cd06c0e4d8e2789")

    # Firebase
    GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "key.json")

    # Gorse Recommendation System
    GORSE_API_URL = os.getenv('GORSE_API_URL', 'http://localhost:8087')
    GORSE_API_KEY = os.getenv('GORSE_API_KEY', '')

    # Flask
    SECRET_KEY = 'INZONE1234'

    # ElevenLabs
    ELEVEN_MODEL_ID = "eleven_multilingual_v2"

    # Meshy API
    MESHY_HEADERS = {
        "Authorization": f"Bearer {MESHY_API_KEY}",
        "Content-Type": "application/json",
    }

    @classmethod
    def validate(cls):
        """Validate required configuration"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
```

**Create `dependencies.py`:**

```python
# dependencies.py
import os
from firebase_admin import credentials, initialize_app, firestore
from openai import OpenAI
from config import Config

# Validate configuration
Config.validate()

# Firebase initialization
credential_path = Config.GOOGLE_APPLICATION_CREDENTIALS
if not os.path.isabs(credential_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credential_path = os.path.join(script_dir, credential_path)

cred = credentials.Certificate(credential_path)
default_app = initialize_app(cred)

# Firestore client
db = firestore.client()

# OpenAI client
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

# Import services (will be initialized after services are created)
# These will be imported by routes
```

#### Step 1.3: Test the Foundation

Update `app.py` to use new config (temporarily):

```python
# At the top of app.py, add:
from config import Config
from dependencies import db, openai_client

# Verify everything still works
# Run: python app.py
```

**Checkpoint:** Ensure the application still runs without errors.

---

### Phase 2: Extract Utility Functions (Low Risk)
**Goal:** Move helper functions to utils module.

**Estimated Time:** 2-3 hours

#### Step 2.1: Extract General Helpers

**Create `utils/helpers.py`:**

```python
# utils/helpers.py
from dependencies import db

def get_user_name(user_id):
    """
    Retrieves the username for a given user_id from Firestore.
    """
    try:
        user_ref = db.collection('users').document(user_id)
        user_doc = user_ref.get()

        if user_doc.exists:
            user_data = user_doc.to_dict()
            username = user_data.get('username', 'Unknown User')
            return username
        else:
            return 'User Not Found'
    except Exception as e:
        print(f"Error retrieving user name: {e}")
        return 'Error Retrieving User'

# Add other helper functions from app.py:
# - _get_character_name()
# - _get_random_character_name()
# - etc.
```

**Create `utils/image_utils.py`:**

```python
# utils/image_utils.py
import base64

def image_to_base64(image_path):
    """Convert image to base64 string"""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
```

#### Step 2.2: Update app.py to use utils

```python
# In app.py, replace the helper functions with imports:
from utils.helpers import get_user_name
from utils.image_utils import image_to_base64

# Delete the original helper function definitions from app.py
```

**Checkpoint:** Run the application and test endpoints that use these helpers.

---

### Phase 3: Extract Service Classes (Medium Risk)
**Goal:** Move existing service classes and create new ones.

**Estimated Time:** 4-6 hours

#### Step 3.1: Move Existing Service Classes

**Move GorseClient:**

```bash
# Extract GorseClient class from app.py (lines 97-307)
# and place in services/recommendation/gorse_client.py
```

```python
# services/recommendation/gorse_client.py
import requests
import logging
from typing import List, Optional
from config import Config

class GorseClient:
    """Client for Gorse Recommendation System"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.logger = logging.getLogger(__name__)
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }

    # ... copy rest of GorseClient class from app.py ...

# Create singleton instance
gorse_client = GorseClient(Config.GORSE_API_URL, Config.GORSE_API_KEY)
```

**Update app.py:**

```python
# In app.py, replace GorseClient class definition with:
from services.recommendation.gorse_client import gorse_client
```

**Move ElevenLabsVoiceService:**

```bash
# Extract ElevenLabsVoiceService class from app.py (lines 344-522)
# and place in services/ai/voice/elevenlabs_service.py
```

```python
# services/ai/voice/elevenlabs_service.py
import requests
import logging
from functools import lru_cache
from config import Config

class ElevenLabsVoiceService:
    """Service for ElevenLabs voice generation"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.elevenlabs.io/v1"
        self.logger = logging.getLogger(__name__)

    # ... copy rest of ElevenLabsVoiceService class from app.py ...

# Create singleton instance
elevenlabs_service = ElevenLabsVoiceService(Config.ELEVENLABS_API_KEY)
```

**Update app.py:**

```python
# In app.py, replace ElevenLabsVoiceService class definition with:
from services.ai.voice.elevenlabs_service import elevenlabs_service
```

#### Step 3.2: Move Existing Service Files

Move already-separated services to the proper location:

```bash
# Move existing services
mv notification_service.py services/notifications/
mv ai_engagement_service.py services/ai/engagement/
mv inzone_ai_engagement.py services/ai/engagement/
mv ai_engagement_scheduler.py services/ai/engagement/
mv ai_nudge_scheduler.py services/notifications/
mv rare_offer_service.py services/notifications/
mv media_analysis_service.py services/media/
```

**Update imports in app.py:**

```python
# Old imports:
from notification_service import notification_service
from ai_nudge_scheduler import AINudgeScheduler
# ... etc

# New imports:
from services.notifications.notification_service import notification_service
from services.notifications.ai_nudge_scheduler import AINudgeScheduler
from services.ai.engagement.ai_engagement_service import ...
# ... etc
```

**Checkpoint:** Run the application and test that services are working correctly.

---

### Phase 4: Create Simple Route Blueprints (Medium Risk)
**Goal:** Start with simple, independent routes.

**Estimated Time:** 6-8 hours

#### Step 4.1: Create Health Check Routes (Simplest)

**Create `routes/core/health.py`:**

```python
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
```

**Register blueprint in app.py:**

```python
# In app.py, add:
from routes.core.health import health_bp

# After app = Flask(__name__), add:
app.register_blueprint(health_bp)

# Remove the original route definitions
```

**Test:**
```bash
curl http://localhost:5000/
curl http://localhost:5000/health
```

#### Step 4.2: Create Store Routes (Simple CRUD)

**Create `routes/monetization/store.py`:**

```python
# routes/monetization/store.py
from flask import Blueprint, request, jsonify
from dependencies import db

store_bp = Blueprint('store', __name__)

@store_bp.route('/store/items', methods=['GET'])
def get_items():
    # Copy implementation from app.py
    pass

@store_bp.route('/store/purchase', methods=['POST'])
def purchase_item():
    # Copy implementation from app.py
    pass

@store_bp.route('/store/inventory', methods=['GET'])
def get_inventory():
    # Copy implementation from app.py
    pass
```

**Register in app.py:**

```python
from routes.monetization.store import store_bp
app.register_blueprint(store_bp)
```

#### Step 4.3: Extract Routes Systematically

**Create a tracking spreadsheet:**

| Route | Original Line | New Location | Status | Tested |
|-------|---------------|--------------|---------|---------|
| GET / | 524 | routes/core/health.py | ✅ | ✅ |
| GET /health | 2248 | routes/core/health.py | ✅ | ✅ |
| GET /store/items | 2850 | routes/monetization/store.py | ✅ | ✅ |
| ... | ... | ... | ... | ... |

**For each route:**

1. Copy the route function to the appropriate blueprint file
2. Update imports (use `from dependencies import db, openai_client`)
3. Test the endpoint
4. Comment out the original in app.py (don't delete yet)
5. Mark as complete in tracking sheet

**Order of extraction (recommended):**

1. ✅ Core routes (health checks)
2. Store routes (simple CRUD)
3. Tipping routes (simple)
4. User profile routes (medium complexity)
5. Social routes (medium complexity)
6. Feed routes (complex)
7. AI routes (complex)
8. Notification routes (complex)
9. Admin routes (last)

**Checkpoint:** After each route file, test all endpoints in that file.

---

### Phase 5: Create Service Layer for Business Logic (High Value)
**Goal:** Extract business logic from routes into services.

**Estimated Time:** 10-15 hours

#### Step 5.1: Create User Profile Service

**Create `services/user/profile_service.py`:**

```python
# services/user/profile_service.py
from dependencies import db
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ProfileService:
    """Service for user profile operations"""

    @staticmethod
    def create_profile(user_id: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user profile"""
        try:
            # Extract from create_profile() route
            user_ref = db.collection('users').document(user_id)
            user_ref.set(profile_data)
            return {'success': True, 'message': 'Profile created'}
        except Exception as e:
            logger.error(f"Error creating profile: {e}")
            raise

    @staticmethod
    def update_name(user_id: str, name: str) -> Dict[str, Any]:
        """Update user's name"""
        try:
            # Extract logic from update_name() route
            if not name or len(name) < 2:
                raise ValueError("Name must be at least 2 characters")

            user_ref = db.collection('users').document(user_id)
            user_ref.update({'name': name})
            return {'success': True, 'message': 'Name updated'}
        except Exception as e:
            logger.error(f"Error updating name: {e}")
            raise

    # Add other profile methods...
```

**Update route to use service:**

```python
# routes/user/profile.py
from flask import Blueprint, request, jsonify
from services.user.profile_service import ProfileService

user_profile_bp = Blueprint('user_profile', __name__)

@user_profile_bp.route('/user/update-name', methods=['POST'])
def update_name():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        name = data.get('name')

        result = ProfileService.update_name(user_id, name)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500
```

#### Step 5.2: Pattern for Each Domain

Repeat this pattern for each domain:

1. **Identify business logic** in route functions
2. **Create service class** in appropriate service folder
3. **Extract logic** to service methods
4. **Update route** to call service
5. **Add error handling** in both layers
6. **Test thoroughly**

**Example domains to extract:**

- `services/user/social_service.py` - Follow/unfollow logic
- `services/user/referral_service.py` - Referral system
- `services/content/post_service.py` - Post CRUD
- `services/content/feed_service.py` - Feed generation
- `services/monetization/wallet_service.py` - Wallet operations
- `services/monetization/subscription_service.py` - Subscriptions
- `services/ai/chat/chat_service.py` - AI chat
- `services/ai/engagement/engagement_service.py` - AI engagement

**Checkpoint:** After each service, test all related endpoints.

---

### Phase 6: Update dependencies.py (Final Integration)
**Goal:** Centralize all service initialization.

**Estimated Time:** 2-3 hours

#### Step 6.1: Update dependencies.py

```python
# dependencies.py
import os
from firebase_admin import credentials, initialize_app, firestore
from openai import OpenAI
from config import Config

# Validate configuration
Config.validate()

# Firebase initialization
credential_path = Config.GOOGLE_APPLICATION_CREDENTIALS
if not os.path.isabs(credential_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    credential_path = os.path.join(script_dir, credential_path)

cred = credentials.Certificate(credential_path)
default_app = initialize_app(cred)

# Firestore client
db = firestore.client()

# OpenAI client
openai_client = OpenAI(api_key=Config.OPENAI_API_KEY)

# Import and initialize services
from services.recommendation.gorse_client import gorse_client
from services.ai.voice.elevenlabs_service import elevenlabs_service
from services.notifications.notification_service import notification_service
from services.notifications.ai_nudge_scheduler import AINudgeScheduler
from services.notifications.rare_offer_service import rare_offer_service
from services.ai.engagement.inzone_ai_engagement import InZoneAIEngagementService
from services.ai.engagement.ai_engagement_scheduler import AIEngagementScheduler
from services.media.media_analysis_service import MediaAnalysisService

# Initialize enhanced AI engagement service
inzone_ai_service = InZoneAIEngagementService(db, openai_client)

# Initialize AI engagement scheduler
ai_engagement_scheduler = AIEngagementScheduler(inzone_ai_service)

# Initialize media analysis service
media_analysis = MediaAnalysisService()
```

#### Step 6.2: Clean up app.py

```python
# app.py (final minimal version)
import logging
from flask import Flask
from flask_cors import CORS
from config import Config
from dependencies import db, openai_client

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = Config.SECRET_KEY

# Register all blueprints
from routes.core.health import health_bp
from routes.user.profile import user_profile_bp
from routes.user.social import user_social_bp
from routes.user.referral import user_referral_bp
from routes.content.posts import posts_bp
from routes.content.feed import feed_bp
from routes.content.comments import comments_bp
from routes.content.gorse import gorse_bp
from routes.monetization.wallet import wallet_bp
from routes.monetization.tipping import tipping_bp
from routes.monetization.store import store_bp
from routes.ai.voice import ai_voice_bp
from routes.ai.chat import ai_chat_bp
from routes.ai.users import ai_users_bp
from routes.ai.social import ai_social_bp
from routes.ai.content import ai_content_bp
from routes.ai.engagement import ai_engagement_bp
from routes.ai.scheduler import ai_scheduler_bp
from routes.groups.management import groups_mgmt_bp
from routes.groups.access import groups_access_bp
from routes.notifications.events import notif_events_bp
from routes.notifications.preferences import notif_prefs_bp
from routes.notifications.push import notif_push_bp
from routes.notifications.debug import notif_debug_bp
from routes.admin.store import admin_store_bp
from routes.admin.groups import admin_groups_bp
from routes.admin.users import admin_users_bp
from routes.admin.maintenance import admin_maint_bp

# Register blueprints
app.register_blueprint(health_bp)
app.register_blueprint(user_profile_bp)
app.register_blueprint(user_social_bp)
app.register_blueprint(user_referral_bp)
app.register_blueprint(posts_bp)
app.register_blueprint(feed_bp)
app.register_blueprint(comments_bp)
app.register_blueprint(gorse_bp)
app.register_blueprint(wallet_bp)
app.register_blueprint(tipping_bp)
app.register_blueprint(store_bp)
app.register_blueprint(ai_voice_bp)
app.register_blueprint(ai_chat_bp)
app.register_blueprint(ai_users_bp)
app.register_blueprint(ai_social_bp)
app.register_blueprint(ai_content_bp)
app.register_blueprint(ai_engagement_bp)
app.register_blueprint(ai_scheduler_bp)
app.register_blueprint(groups_mgmt_bp)
app.register_blueprint(groups_access_bp)
app.register_blueprint(notif_events_bp)
app.register_blueprint(notif_prefs_bp)
app.register_blueprint(notif_push_bp)
app.register_blueprint(notif_debug_bp)
app.register_blueprint(admin_store_bp)
app.register_blueprint(admin_groups_bp)
app.register_blueprint(admin_users_bp)
app.register_blueprint(admin_maint_bp)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)
```

---

### Phase 7: Testing and Validation
**Goal:** Ensure everything works correctly.

**Estimated Time:** 4-6 hours

#### Step 7.1: Create Test Script

**Create `test_all_endpoints.sh`:**

```bash
#!/bin/bash

# Test script for all endpoints
BASE_URL="http://localhost:8080"

echo "Testing Core Endpoints..."
curl -s "$BASE_URL/" | grep "Backend is running"
curl -s "$BASE_URL/health" | grep "healthy"

echo "Testing User Endpoints..."
# Add test for each endpoint group...

echo "All tests completed!"
```

#### Step 7.2: Integration Testing

1. **Start the application**
   ```bash
   python app.py
   ```

2. **Run test script**
   ```bash
   chmod +x test_all_endpoints.sh
   ./test_all_endpoints.sh
   ```

3. **Manual testing**
   - Test critical user flows
   - Test payment flows
   - Test AI interactions
   - Test notifications

#### Step 7.3: Performance Testing

Compare before/after:
- Response times
- Memory usage
- Startup time

---

### Phase 8: Cleanup and Documentation
**Goal:** Clean up old code and update documentation.

**Estimated Time:** 2-3 hours

#### Step 8.1: Archive Old app.py

```bash
mv app.py archive/app_monolithic_backup.py
```

#### Step 8.2: Update Documentation

- ✅ Update ARCHITECTURE.md with any changes
- Update README.md with new structure
- Update deployment documentation if needed
- Add inline documentation to complex services

#### Step 8.3: Code Review Checklist

- [ ] All routes extracted to blueprints
- [ ] All business logic in services
- [ ] No duplicate code
- [ ] All imports correct
- [ ] Error handling consistent
- [ ] Logging in place
- [ ] Tests pass
- [ ] Documentation updated

---

## Common Issues and Solutions

### Issue: Import Errors

**Problem:** `ModuleNotFoundError` or circular imports

**Solution:**
```python
# Use absolute imports
from services.user.profile_service import ProfileService

# Not relative imports
from ..services.user.profile_service import ProfileService
```

### Issue: Database Connection Issues

**Problem:** Multiple Firebase initialization

**Solution:**
- Initialize Firebase once in `dependencies.py`
- Import `db` from dependencies everywhere else

### Issue: Blueprint Not Found

**Problem:** 404 errors for endpoints

**Solution:**
- Ensure blueprint is registered in app.py
- Check blueprint URL prefix
- Verify route decorators

### Issue: Service Dependencies

**Problem:** Services need other services

**Solution:**
```python
# In service, import from dependencies
from dependencies import db, openai_client, gorse_client

# Not from other services directly
```

---

## Rollback Plan

If something goes wrong:

1. **Keep git history clean**
   ```bash
   # Each phase should be a separate commit
   git commit -m "Phase 1: Create foundation"
   git commit -m "Phase 2: Extract utilities"
   ```

2. **Rollback to previous phase**
   ```bash
   git log  # Find commit hash
   git reset --hard <commit-hash>
   ```

3. **Emergency rollback**
   ```bash
   git checkout backup/pre-refactoring
   ```

---

## Post-Refactoring Benefits

After completing this refactoring:

1. **Maintainability:** Find and fix bugs faster
2. **Scalability:** Add features without touching existing code
3. **Testability:** Test components in isolation
4. **Team Collaboration:** Multiple developers can work simultaneously
5. **Onboarding:** New developers can understand the code structure quickly
6. **Microservices Ready:** Easy to extract domains into separate services later

---

## Timeline Estimate

| Phase | Time Estimate | Risk Level |
|-------|---------------|------------|
| Phase 1: Foundation | 2-3 hours | Low |
| Phase 2: Utilities | 2-3 hours | Low |
| Phase 3: Services | 4-6 hours | Medium |
| Phase 4: Routes | 6-8 hours | Medium |
| Phase 5: Business Logic | 10-15 hours | High Value |
| Phase 6: Integration | 2-3 hours | Medium |
| Phase 7: Testing | 4-6 hours | Critical |
| Phase 8: Cleanup | 2-3 hours | Low |
| **Total** | **32-47 hours** | |

**Recommendation:** Spread this over 1-2 weeks with thorough testing between phases.

---

## Questions or Issues?

If you encounter problems during refactoring:

1. Check this guide for common issues
2. Review ARCHITECTURE.md for structure clarification
3. Consult with the backend team lead
4. Document any new patterns or solutions for future reference

---

## Success Criteria

The refactoring is complete when:

- [ ] app.py is under 200 lines
- [ ] All endpoints work as before
- [ ] All tests pass
- [ ] Code is organized by domain
- [ ] Services contain business logic
- [ ] Routes are thin controllers
- [ ] Documentation is updated
- [ ] Team members understand new structure

Good luck with the refactoring! 🚀
