import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

# Initialize Firebase Admin SDK
cred = credentials.Certificate("assets/key.json")
firebase_admin.initialize_app(cred)

def fetch_ai_users():
  """
  Fetches AI users from Firestore and stores detailed user information in live_agents.json
  using username as the key
  """
  db = firestore.client()
  ai_users = {}
  
  # Load existing data from live_agents.json if it exists and is not empty
  if os.path.exists('assets/live_agents.json') and os.path.getsize('assets/live_agents.json') > 0:
    with open('assets/live_agents.json', 'r') as f:
      ai_users = json.load(f)
  
  # Get all documents from the AI users collection
  docs = db.collection('aiUsers').limit(100).stream()
  
  added = 0
  
  # Process each document
  for doc in docs:
    user_data = doc.to_dict()
    username = user_data.get("username", "")
    if username and username not in ai_users:  # Only add users with a username and not already in the JSON
      ai_users[username] = {
        "name": user_data.get("name", ""),
        "age": user_data.get("age", None),
        "gender": user_data.get("gender", ""),
        "bio": user_data.get("bio", ""),
        "popularity": user_data.get("popularity", False),
        "personality": user_data.get("personality", "")
      }
      added += 1
      
  # Debugging: Print the ai_users dictionary
  # print("AI Users fetched:", ai_users)
  
  # Save to live_agents.json
  with open('assets/live_agents.json', 'w') as f:
    json.dump(ai_users, f, indent=2)
  
  return ai_users, added

if __name__ == "__main__":
  ai_users, added = fetch_ai_users()
  print(f"Found {len(ai_users)-added} duplicates. Skipping...")
  print(f"Successfully added {added} AI users to live_agents.json")