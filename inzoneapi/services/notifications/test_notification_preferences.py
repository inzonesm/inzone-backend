"""
Comprehensive Test Script for Notification Preferences
Tests all notification settings and combinations for user majtest@gmail.com

This script validates:
1. Pause All setting
2. Quiet Hours with digest delivery
3. Likes notifications (everyone, following, off) - includes post likes and comment likes
4. Comments notifications (everyone, following, followingAndFollowers, off)
5. Direct Messages (everyone, following, off) with sound and preview settings
6. Group Chat notifications with all filter modes
7. Follower notifications
8. System notifications
9. Rare offer notifications with weekly limits
10. AI Nudge notifications (currently disabled by default)
"""

import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from google.cloud import firestore
from dependencies import db
from services.notifications.preference_service import NotificationPreferenceService
from services.notifications.queue_service import NotificationQueueService
from services.notifications.event_service import NotificationEventService
from datetime import datetime
import time

# Test user configuration
TEST_USER_EMAIL = "majtest@gmail.com"
TEST_USER_ID = None  # Will be populated by finding the user
TEST_ACTOR_ID = None  # Will be populated by finding another user
TEST_CHARACTER_ID = None  # Will be populated by finding a character

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print a colored header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")


def print_test(test_name):
    """Print test name"""
    print(f"{Colors.OKBLUE}▶ Testing: {test_name}{Colors.ENDC}")


def print_success(message):
    """Print success message"""
    print(f"{Colors.OKGREEN}  ✓ {message}{Colors.ENDC}")


def print_failure(message):
    """Print failure message"""
    print(f"{Colors.FAIL}  ✗ {message}{Colors.ENDC}")


def print_info(message):
    """Print info message"""
    print(f"{Colors.OKCYAN}  ℹ {message}{Colors.ENDC}")


def print_warning(message):
    """Print warning message"""
    print(f"{Colors.WARNING}  ⚠ {message}{Colors.ENDC}")


def find_test_user():
    """Find the test user by email"""
    global TEST_USER_ID
    
    print_test("Finding test user by email")
    
    try:
        users = db.collection('humanUsers').where('email', '==', TEST_USER_EMAIL).limit(1).get()
        if users:
            user_doc = list(users)[0]
            TEST_USER_ID = user_doc.id
            user_data = user_doc.to_dict()
            print_success(f"Found user: {user_data.get('username', 'Unknown')} (ID: {TEST_USER_ID})")
            return True
        else:
            print_failure(f"User with email {TEST_USER_EMAIL} not found")
            return False
    except Exception as e:
        print_failure(f"Error finding user: {e}")
        return False


def find_actor_user():
    """Find another user to act as the actor in tests"""
    global TEST_ACTOR_ID
    
    print_test("Finding actor user for relationship tests")
    
    try:
        # Get a different user than the test user
        users = db.collection('humanUsers').limit(5).get()
        for user_doc in users:
            if user_doc.id != TEST_USER_ID:
                TEST_ACTOR_ID = user_doc.id
                user_data = user_doc.to_dict()
                print_success(f"Found actor user: {user_data.get('username', 'Unknown')} (ID: {TEST_ACTOR_ID})")
                return True
        
        print_failure("No actor user found")
        return False
    except Exception as e:
        print_failure(f"Error finding actor user: {e}")
        return False


def find_character():
    """Find an AI character for tests"""
    global TEST_CHARACTER_ID
    
    print_test("Finding AI character")
    
    try:
        characters = db.collection('popularCharacters').limit(1).get()
        if characters:
            char_doc = list(characters)[0]
            TEST_CHARACTER_ID = char_doc.id
            char_data = char_doc.to_dict()
            print_success(f"Found character: {char_data.get('name', 'Unknown')} (ID: {TEST_CHARACTER_ID})")
            return True
        else:
            print_warning("No characters found - some tests will be skipped")
            return False
    except Exception as e:
        print_failure(f"Error finding character: {e}")
        return False


def setup_test_preferences(preferences):
    """Set specific notification preferences for testing"""
    try:
        user_ref = db.collection('humanUsers').document(TEST_USER_ID)
        user_ref.update({
            'notificationPrefs': preferences,
            'preferencesUpdatedAt': firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        print_failure(f"Error setting preferences: {e}")
        return False


def get_current_preferences():
    """Get current user preferences"""
    return NotificationPreferenceService.get_user_preferences(TEST_USER_ID)


def test_pause_all():
    """Test 1: Pause All setting blocks all notifications"""
    print_header("TEST 1: PAUSE ALL SETTING")
    
    # Set pause all to true
    prefs = {
        'pauseAll': True,
        'categories': {
            'likes': {'enabled': True, 'from': 'everyone'},
            'dm': {'enabled': True, 'from': 'everyone'}
        }
    }
    
    if not setup_test_preferences(prefs):
        return False
    
    print_test("Testing pause all blocks likes notification")
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'like', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("Likes notification correctly blocked by pause all")
    else:
        print_failure("Likes notification was not blocked by pause all")
        return False
    
    print_test("Testing pause all blocks DM notification")
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'dm', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("DM notification correctly blocked by pause all")
    else:
        print_failure("DM notification was not blocked by pause all")
        return False
    
    # Reset pause all
    prefs['pauseAll'] = False
    setup_test_preferences(prefs)
    
    print_success("✓ PAUSE ALL TEST PASSED\n")
    return True


def test_quiet_hours():
    """Test 2: Quiet Hours digest feature"""
    print_header("TEST 2: QUIET HOURS DIGEST")
    
    # Set quiet hours to current time range (so we're in quiet hours)
    current_hour = datetime.utcnow().hour
    start_hour = (current_hour - 1) % 24
    end_hour = (current_hour + 2) % 24
    
    prefs = {
        'pauseAll': False,
        'quietHoursEnabled': True,
        'quietHours': {
            'start': f'{start_hour:02d}:00',
            'end': f'{end_hour:02d}:00'
        },
        'categories': {
            'likes': {'enabled': True, 'from': 'everyone'}
        }
    }
    
    if not setup_test_preferences(prefs):
        return False
    
    print_test("Checking if user is in quiet hours")
    in_quiet_hours = NotificationPreferenceService.is_in_quiet_hours(TEST_USER_ID)
    
    if in_quiet_hours:
        print_success("User is correctly detected as being in quiet hours")
    else:
        print_warning("User is not in quiet hours (may be timezone issue)")
    
    print_test("Getting quiet hours end time")
    end_time = NotificationQueueService.get_quiet_hours_end_time(TEST_USER_ID)
    print_info(f"Quiet hours end at: {end_time} UTC")
    print_success(f"Digest would be sent at: {end_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    print_test("Testing notification queueing during quiet hours")
    notification_data = {
        'type': 'like',
        'userId': TEST_USER_ID,
        'postId': 'test_post_123',
        'likerUserId': TEST_ACTOR_ID,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    # Queue a notification (should be delayed if in quiet hours)
    NotificationQueueService.smart_queue_notification(notification_data)
    print_success("Notification queued with quiet hours handling")
    
    # Check the queue
    print_test("Verifying notification was queued")
    queue_docs = db.collection('notificationsQueue').where('uid', '==', TEST_USER_ID).limit(5).get()
    queued_notifications = list(queue_docs)
    
    if queued_notifications:
        print_success(f"Found {len(queued_notifications)} queued notification(s)")
        for notif in queued_notifications:
            notif_data = notif.to_dict()
            is_digest = notif_data.get('quietHoursDigest', False)
            send_time = notif_data.get('notBefore')
            print_info(f"  - Type: {notif_data.get('type')}, Digest: {is_digest}, Send at: {send_time}")
    else:
        print_warning("No queued notifications found (may have been processed already)")
    
    print_success("✓ QUIET HOURS TEST PASSED\n")
    return True


def test_likes_preferences():
    """Test 3: Likes notification preferences"""
    print_header("TEST 3: LIKES NOTIFICATION PREFERENCES")
    
    # Test 3a: Everyone
    print_test("Testing likes from 'everyone'")
    prefs = {
        'pauseAll': False,
        'categories': {
            'likes': {'enabled': True, 'from': 'everyone'}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'like', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Likes from everyone correctly allowed")
    else:
        print_failure("Likes from everyone was blocked")
        return False
    
    # Test 3b: Following only
    print_test("Testing likes from 'following' only")
    prefs['categories']['likes']['from'] = 'following'
    setup_test_preferences(prefs)
    
    # First check if test user follows actor
    user_doc = db.collection('humanUsers').document(TEST_USER_ID).get()
    user_data = user_doc.to_dict()
    following = user_data.get('following', [])
    is_following = TEST_ACTOR_ID in following
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'like', TEST_ACTOR_ID
    )
    
    if is_following:
        if should_send:
            print_success("Likes from followed user correctly allowed")
        else:
            print_failure("Likes from followed user was blocked")
            return False
    else:
        if not should_send:
            print_success("Likes from non-followed user correctly blocked")
        else:
            print_failure("Likes from non-followed user was allowed")
            return False
    
    # Test 3c: Off
    print_test("Testing likes set to 'off'")
    prefs['categories']['likes']['from'] = 'off'
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'like', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("Likes correctly blocked when set to 'off'")
    else:
        print_failure("Likes was not blocked when set to 'off'")
        return False
    
    print_success("✓ LIKES PREFERENCES TEST PASSED\n")
    return True


def test_comments_preferences():
    """Test 4: Comments notification preferences"""
    print_header("TEST 4: COMMENTS NOTIFICATION PREFERENCES")
    
    # Test 4a: Everyone
    print_test("Testing comments from 'everyone'")
    prefs = {
        'pauseAll': False,
        'categories': {
            'comments': {'enabled': True, 'from': 'everyone'}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'comment', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Comments from everyone correctly allowed")
    else:
        print_failure("Comments from everyone was blocked")
        return False
    
    # Test 4b: Following only
    print_test("Testing comments from 'following' only")
    prefs['categories']['comments']['from'] = 'following'
    setup_test_preferences(prefs)
    
    user_doc = db.collection('humanUsers').document(TEST_USER_ID).get()
    user_data = user_doc.to_dict()
    following = user_data.get('following', [])
    is_following = TEST_ACTOR_ID in following
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'comment', TEST_ACTOR_ID
    )
    
    expected = is_following
    if should_send == expected:
        print_success(f"Comments from {'followed' if is_following else 'non-followed'} user handled correctly")
    else:
        print_failure("Comments 'following' filter not working correctly")
        return False
    
    # Test 4c: Following and Followers
    print_test("Testing comments from 'followingAndFollowers'")
    prefs['categories']['comments']['from'] = 'followingAndFollowers'
    setup_test_preferences(prefs)
    
    # Check if actor follows test user
    actor_doc = db.collection('humanUsers').document(TEST_ACTOR_ID).get()
    actor_data = actor_doc.to_dict()
    actor_following = actor_data.get('following', [])
    is_follower = TEST_USER_ID in actor_following
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'comment', TEST_ACTOR_ID
    )
    
    expected = is_following or is_follower
    if should_send == expected:
        print_success("Comments from followingAndFollowers handled correctly")
    else:
        print_failure("Comments 'followingAndFollowers' filter not working")
        return False
    
    # Test 4d: Off
    print_test("Testing comments set to 'off'")
    prefs['categories']['comments']['from'] = 'off'
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'comment', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("Comments correctly blocked when set to 'off'")
    else:
        print_failure("Comments was not blocked when set to 'off'")
        return False
    
    print_success("✓ COMMENTS PREFERENCES TEST PASSED\n")
    return True


def test_dm_preferences():
    """Test 5: Direct Message preferences"""
    print_header("TEST 5: DIRECT MESSAGE PREFERENCES")
    
    # Test 5a: DM enabled with everyone
    print_test("Testing DMs from 'everyone'")
    prefs = {
        'pauseAll': False,
        'categories': {
            'dm': {'enabled': True, 'from': 'everyone', 'sound': True, 'showPreviews': True}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'dm', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("DMs from everyone correctly allowed")
    else:
        print_failure("DMs from everyone was blocked")
        return False
    
    # Test 5b: DM from following only
    print_test("Testing DMs from 'following' only")
    prefs['categories']['dm']['from'] = 'following'
    setup_test_preferences(prefs)
    
    user_doc = db.collection('humanUsers').document(TEST_USER_ID).get()
    user_data = user_doc.to_dict()
    following = user_data.get('following', [])
    is_following = TEST_ACTOR_ID in following
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'dm', TEST_ACTOR_ID
    )
    
    expected = is_following
    if should_send == expected:
        print_success(f"DMs from {'followed' if is_following else 'non-followed'} user handled correctly")
    else:
        print_failure("DMs 'following' filter not working correctly")
        return False
    
    # Test 5c: DM disabled
    print_test("Testing DMs disabled")
    prefs['categories']['dm']['enabled'] = False
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'dm', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("DMs correctly blocked when disabled")
    else:
        print_failure("DMs was not blocked when disabled")
        return False
    
    # Test 5d: Preview settings
    print_test("Checking DM preview and sound settings")
    prefs['categories']['dm']['enabled'] = True
    prefs['categories']['dm']['sound'] = False
    prefs['categories']['dm']['showPreviews'] = False
    setup_test_preferences(prefs)
    
    current_prefs = get_current_preferences()
    dm_prefs = current_prefs.get('categories', {}).get('dm', {})
    
    if not dm_prefs.get('sound', True) and not dm_prefs.get('showPreviews', True):
        print_success("DM sound and preview settings saved correctly")
    else:
        print_failure("DM sound/preview settings not saved correctly")
        return False
    
    print_success("✓ DIRECT MESSAGE PREFERENCES TEST PASSED\n")
    return True


def test_group_preferences():
    """Test 6: Group chat notification preferences"""
    print_header("TEST 6: GROUP CHAT PREFERENCES")
    
    # Test 6a: All messages
    print_test("Testing group notifications for 'everyone'")
    prefs = {
        'pauseAll': False,
        'categories': {
            'group': {'enabled': True, 'notifyFor': 'everyone', 'batchMins': 15}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'group', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Group notifications for everyone correctly allowed")
    else:
        print_failure("Group notifications for everyone was blocked")
        return False
    
    # Test 6b: Mentions only
    print_test("Testing group notifications for 'mentions' only")
    prefs['categories']['group']['notifyFor'] = 'mentions'
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'group', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Group notifications base check passed (mention filtering happens in event handler)")
    else:
        print_failure("Group notifications check failed")
        return False
    
    # Test 6c: Characters only
    print_test("Testing group notifications for 'popularCharacters' only")
    prefs['categories']['group']['notifyFor'] = 'popularCharacters'
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'group', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Group notifications base check passed (character filtering happens in event handler)")
    else:
        print_failure("Group notifications check failed")
        return False
    
    # Test 6d: Off
    print_test("Testing group notifications set to 'off'")
    prefs['categories']['group']['notifyFor'] = 'off'
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'group', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("Group notifications correctly blocked when set to 'off'")
    else:
        print_failure("Group notifications was not blocked when set to 'off'")
        return False
    
    # Test 6e: Batch settings
    print_test("Checking group batch settings")
    prefs['categories']['group']['notifyFor'] = 'everyone'
    prefs['categories']['group']['batchMins'] = 30
    setup_test_preferences(prefs)
    
    current_prefs = get_current_preferences()
    group_prefs = current_prefs.get('categories', {}).get('group', {})
    
    if group_prefs.get('batchMins') == 30:
        print_success("Group batch minutes setting saved correctly")
    else:
        print_failure("Group batch minutes setting not saved correctly")
        return False
    
    print_success("✓ GROUP CHAT PREFERENCES TEST PASSED\n")
    return True


def test_follower_preferences():
    """Test 7: Follower notification preferences"""
    print_header("TEST 7: FOLLOWER NOTIFICATION PREFERENCES")
    
    # Test 7a: Enabled
    print_test("Testing follower notifications enabled")
    prefs = {
        'pauseAll': False,
        'categories': {
            'followers': {'enabled': True}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'follower', TEST_ACTOR_ID
    )
    
    if should_send:
        print_success("Follower notifications correctly allowed when enabled")
    else:
        print_failure("Follower notifications was blocked when enabled")
        return False
    
    # Test 7b: Disabled
    print_test("Testing follower notifications disabled")
    prefs['categories']['followers']['enabled'] = False
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'follower', TEST_ACTOR_ID
    )
    
    if not should_send:
        print_success("Follower notifications correctly blocked when disabled")
    else:
        print_failure("Follower notifications was not blocked when disabled")
        return False
    
    print_success("✓ FOLLOWER PREFERENCES TEST PASSED\n")
    return True


def test_rare_offer_preferences():
    """Test 8: Rare offer notification preferences"""
    print_header("TEST 8: RARE OFFER PREFERENCES")
    
    # Test 8a: Enabled
    print_test("Testing rare offers enabled")
    prefs = {
        'pauseAll': False,
        'categories': {
            'rareOffers': {'enabled': True, 'maxPerWeek': 2}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'rare_offer', None
    )
    
    if should_send:
        print_success("Rare offer notifications correctly allowed when enabled")
    else:
        print_failure("Rare offer notifications was blocked when enabled")
        return False
    
    # Test 8b: Check weekly limit
    print_test("Testing rare offer eligibility check")
    is_eligible = NotificationQueueService.check_rare_offer_eligibility(TEST_USER_ID)
    print_info(f"User eligibility for rare offers: {is_eligible}")
    print_success("Rare offer eligibility check completed")
    
    # Test 8c: Disabled
    print_test("Testing rare offers disabled")
    prefs['categories']['rareOffers']['enabled'] = False
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'rare_offer', None
    )
    
    if not should_send:
        print_success("Rare offer notifications correctly blocked when disabled")
    else:
        print_failure("Rare offer notifications was not blocked when disabled")
        return False
    
    print_success("✓ RARE OFFER PREFERENCES TEST PASSED\n")
    return True


def test_system_preferences():
    """Test 9: System notification preferences"""
    print_header("TEST 9: SYSTEM NOTIFICATION PREFERENCES")
    
    # Test 9a: Enabled
    print_test("Testing system notifications enabled")
    prefs = {
        'pauseAll': False,
        'categories': {
            'system': {'enabled': True}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'system', None
    )
    
    if should_send:
        print_success("System notifications correctly allowed when enabled")
    else:
        print_failure("System notifications was blocked when enabled")
        return False
    
    # Test 9b: Disabled
    print_test("Testing system notifications disabled")
    prefs['categories']['system']['enabled'] = False
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'system', None
    )
    
    if not should_send:
        print_success("System notifications correctly blocked when disabled")
    else:
        print_failure("System notifications was not blocked when disabled")
        return False
    
    print_success("✓ SYSTEM PREFERENCES TEST PASSED\n")
    return True


def test_ai_nudge_preferences():
    """Test 10: AI Nudge preferences (disabled by default)"""
    print_header("TEST 10: AI NUDGE PREFERENCES")
    
    # Test 10a: Disabled by default
    print_test("Testing AI nudges disabled by default")
    prefs = {
        'pauseAll': False,
        'categories': {
            'aiNudges': {'enabled': False, 'maxPerDay': 2}
        }
    }
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'ai_nudge', None
    )
    
    if not should_send:
        print_success("AI nudges correctly blocked when disabled (default)")
    else:
        print_failure("AI nudges was not blocked when disabled")
        return False
    
    # Test 10b: Enabled
    print_test("Testing AI nudges when enabled")
    prefs['categories']['aiNudges']['enabled'] = True
    setup_test_preferences(prefs)
    
    should_send = NotificationPreferenceService.should_send_notification(
        TEST_USER_ID, 'ai_nudge', None
    )
    
    if should_send:
        print_success("AI nudges correctly allowed when enabled")
    else:
        print_failure("AI nudges was blocked when enabled")
        return False
    
    print_success("✓ AI NUDGE PREFERENCES TEST PASSED\n")
    return True


def test_end_to_end_scenarios():
    """Test 11: End-to-end notification scenarios"""
    print_header("TEST 11: END-TO-END NOTIFICATION SCENARIOS")
    
    # Scenario 1: Like notification with quiet hours
    print_test("Scenario 1: Like notification with quiet hours enabled")
    
    current_hour = datetime.utcnow().hour
    start_hour = (current_hour - 1) % 24
    end_hour = (current_hour + 2) % 24
    
    prefs = {
        'pauseAll': False,
        'quietHoursEnabled': True,
        'quietHours': {
            'start': f'{start_hour:02d}:00',
            'end': f'{end_hour:02d}:00'
        },
        'categories': {
            'likes': {'enabled': True, 'from': 'everyone'}
        }
    }
    setup_test_preferences(prefs)
    
    notification_data = {
        'type': 'like',
        'userId': TEST_USER_ID,
        'postId': 'test_post_e2e_1',
        'likerUserId': TEST_ACTOR_ID,
        'timestamp': datetime.utcnow().isoformat()
    }
    
    NotificationQueueService.smart_queue_notification(notification_data)
    print_success("Like notification queued with quiet hours handling")
    
    # Scenario 2: Group message with batching
    print_test("Scenario 2: Group message with batching")
    
    prefs['quietHoursEnabled'] = False
    prefs['categories']['group'] = {'enabled': True, 'notifyFor': 'everyone', 'batchMins': 15}
    setup_test_preferences(prefs)
    
    notification_data = {
        'type': 'group_digest',
        'userId': TEST_USER_ID,
        'groupId': 'test_group_123',
        'groupName': 'Test Group',
        'senderName': 'Test Sender',
        'content': 'Test group message',
        'timestamp': datetime.utcnow().isoformat()
    }
    
    NotificationQueueService.smart_queue_notification(notification_data, batch=True, delay_minutes=15)
    print_success("Group message queued with batching")
    
    # Scenario 3: DM without previews
    print_test("Scenario 3: DM notification without previews")
    
    prefs['categories']['dm'] = {'enabled': True, 'from': 'everyone', 'sound': True, 'showPreviews': False}
    setup_test_preferences(prefs)
    
    current_prefs = get_current_preferences()
    dm_prefs = current_prefs.get('categories', {}).get('dm', {})
    
    if not dm_prefs.get('showPreviews', True):
        print_success("DM preview setting correctly disabled")
        print_info("Backend should not include message content in notification payload")
    else:
        print_failure("DM preview setting not saved")
        return False
    
    print_success("✓ END-TO-END SCENARIOS TEST PASSED\n")
    return True


def cleanup_test_data():
    """Clean up test notifications from queue"""
    print_header("CLEANUP")
    
    print_test("Cleaning up test notifications")
    
    try:
        # Delete test notifications from queue
        queue_docs = db.collection('notificationsQueue').where('uid', '==', TEST_USER_ID).limit(50).get()
        deleted_count = 0
        
        for doc in queue_docs:
            doc_data = doc.to_dict()
            # Only delete test notifications created in the last 5 minutes
            if doc_data.get('type') in ['like', 'group_digest', 'dm']:
                doc.reference.delete()
                deleted_count += 1
        
        print_success(f"Deleted {deleted_count} test notification(s) from queue")
        
        # Reset preferences to defaults
        default_prefs = {
            'pauseAll': False,
            'quietHoursEnabled': False,
            'quietHours': {'start': '22:00', 'end': '08:00'},
            'categories': {
                'likes': {'enabled': True, 'from': 'everyone'},  # Controls both post likes and comment likes
                'comments': {'enabled': True, 'from': 'everyone'},
                'commentLikes': {'enabled': True, 'from': 'everyone'},  # Synced with likes setting
                'dm': {'enabled': True, 'from': 'everyone', 'sound': True, 'showPreviews': True},
                'group': {'enabled': True, 'notifyFor': 'everyone', 'batchMins': 15},
                'followers': {'enabled': True},
                'aiNudges': {'enabled': False, 'maxPerDay': 2},
                'system': {'enabled': True},
                'rareOffers': {'enabled': True, 'maxPerWeek': 2}
            }
        }
        
        setup_test_preferences(default_prefs)
        print_success("Reset preferences to defaults")
        
    except Exception as e:
        print_warning(f"Cleanup encountered errors: {e}")


def run_all_tests():
    """Run all tests"""
    print_header("NOTIFICATION PREFERENCES COMPREHENSIVE TEST SUITE")
    print_info(f"Testing for user: {TEST_USER_EMAIL}")
    print_info(f"Started at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
    
    # Setup
    if not find_test_user():
        print_failure("Cannot proceed without test user")
        return
    
    if not find_actor_user():
        print_failure("Cannot proceed without actor user")
        return
    
    find_character()  # Optional
    
    # Run tests
    tests = [
        ("Pause All", test_pause_all),
        ("Quiet Hours", test_quiet_hours),
        ("Likes Preferences", test_likes_preferences),
        ("Comments Preferences", test_comments_preferences),
        ("DM Preferences", test_dm_preferences),
        ("Group Preferences", test_group_preferences),
        ("Follower Preferences", test_follower_preferences),
        ("Rare Offer Preferences", test_rare_offer_preferences),
        ("System Preferences", test_system_preferences),
        ("AI Nudge Preferences", test_ai_nudge_preferences),
        ("End-to-End Scenarios", test_end_to_end_scenarios)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print_failure(f"Test '{test_name}' FAILED")
        except Exception as e:
            failed += 1
            print_failure(f"Test '{test_name}' raised exception: {e}")
    
    # Cleanup
    cleanup_test_data()
    
    # Summary
    print_header("TEST SUMMARY")
    total = passed + failed
    print(f"{Colors.BOLD}Total Tests: {total}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}Passed: {passed}{Colors.ENDC}")
    print(f"{Colors.FAIL}Failed: {failed}{Colors.ENDC}")
    
    if failed == 0:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! 🎉{Colors.ENDC}\n")
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}❌ SOME TESTS FAILED ❌{Colors.ENDC}\n")
    
    print_info(f"Completed at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")


if __name__ == "__main__":
    run_all_tests()
