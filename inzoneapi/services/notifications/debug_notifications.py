from google.cloud import firestore
from dependencies import db

user_id = 'LWiwzqmG0TNXxXyMAxifkVe1wXc2'

print(f"Checking notifications for user: {user_id}")

# Check recent notifications (without ordering to avoid index requirement)
notifs = db.collection('notifications').where('userId', '==', user_id).limit(10).get()

notif_list = list(notifs)
print(f"\nRecent notifications ({len(notif_list)} found):")
for n in notif_list:
    data = n.to_dict()
    print(f"  - Type: {data.get('type')}, Read: {data.get('isRead')}, Title: {data.get('title')}, Created: {data.get('createdAt')}")

# Check FCM tokens
user_doc = db.collection('humanUsers').document(user_id).get()
if user_doc.exists:
    user_data = user_doc.to_dict()
    fcm_tokens = user_data.get('fcmTokens', [])
    print(f"\nFCM Tokens ({len(fcm_tokens)} found):")
    for token in fcm_tokens:
        print(f"  - {token[:50]}...")
    
    # Check notification preferences
    prefs = user_data.get('notificationPrefs', {})
    print(f"\nNotification Preferences:")
    print(f"  pauseAll: {prefs.get('pauseAll')}")
    print(f"  quietHoursEnabled: {prefs.get('quietHoursEnabled')}")
    dm_prefs = prefs.get('categories', {}).get('dm', {})
    print(f"  DM enabled: {dm_prefs.get('enabled')}")
    print(f"  DM from: {dm_prefs.get('from')}")
