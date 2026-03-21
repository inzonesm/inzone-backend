import firebase_admin
from firebase_admin import credentials, firestore
import datetime
from datetime import timedelta
import time

# Initialize Firebase (replace path_to_credentials with your actual credentials file path)
cred = credentials.Certificate("/Users/aryan/Inzone/agent_dashboard/key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Function to check if a group chat with the given name already exists
def group_chat_exists(name):
  group_chats_ref = db.collection("groupChats")
  query = group_chats_ref.where("name", "==", name).limit(1)
  results = query.get()
  
  return len(results) > 0

# Function to get personality information for an AI character
def get_character_personality(uid):
  character_ref = db.collection("popularCharacters").document(uid)
  character_doc = character_ref.get()
  
  if character_doc.exists:
    character_data = character_doc.to_dict()
    return character_data.get("personality", "")
  
  return ""

# Define the group chat data
def create_group_chat_data(
  name="Culers' Corner",
  access_tier="VIP Monthly Access",
  entry_fee=10,
  description="A special group chat for the biggest Culers. Join us for exclusive content and discussions!",
  image_url="https://upload.wikimedia.org/wikipedia/sco/4/47/FC_Barcelona_%28crest%29.svg",
  chat_type="premium",
  chat_status="active",
  chat_category="sports",
  participants=[
    {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
    {"uid": "fpO9prUW8ZKdDC8OzuSq", "type": "ai", "name": "Lionel Messi"}
  ],
  initial_messages=None
):
  # Current timestamp for created/updated fields
  current_time = datetime.datetime.now()
  
  # Update participants with personality information for AI characters
  for participant in participants:
    if participant["type"] == "ai":
      personality = get_character_personality(participant["uid"])
      participant["personality"] = personality
  
  if initial_messages is None:
    initial_messages = [
      {
        "id": current_time.strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
        "content": "LEOOOOOOO 🐐 I'm crying. My childhood hero is here 😭",
        "isProcessed": True
      },
      {
        "id": (current_time + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "fpO9prUW8ZKdDC8OzuSq", "type": "ai", "name": "Lionel Messi"},
        "content": "Gracias, amigo 😊 I'm honored. You're all part of the journey too. Visca Barça forever 💙❤",
        "isProcessed": True
      }
    ]
  
  last_message_id = initial_messages[-1]["id"] if initial_messages else None
  
  return {
    "name": name,
    "accessTier": access_tier,
    "entryFee": entry_fee,
    "description": description,
    "imageUrl": image_url,
    "groupChatType": chat_type,
    "groupChatStatus": chat_status,
    "groupChatCategory": chat_category,
    "createdAt": current_time,
    "updatedAt": current_time,
    "participants": participants,
    "messages": initial_messages,
    "lastProcessedMessageId": last_message_id,
  }

def add_group_chat_to_firebase(group_chat_data=None):
  if group_chat_data is None:
    group_chat_data = create_group_chat_data()
  
  # Check if a group chat with this name already exists
  if group_chat_exists(group_chat_data["name"]):
    print(f"Group chat '{group_chat_data['name']}' already exists. Skipping...")
    return None
  
  # Add to Firestore with specific document ID
  # Create a unique ID by appending current timestamp
  current_time = datetime.datetime.now()
  doc_id = f"group_chat_{current_time.strftime('%Y%m%d%H%M%S')}"
  group_chat_ref = db.collection("groupChats").document(doc_id)
  group_chat_ref.set(group_chat_data)
  
  print(f"Group chat added with ID: {group_chat_ref.id}")
  return group_chat_ref.id

# Sample group chat data
SAMPLE_GROUP_CHATS = [
  # {
  #   "name": "Football Legends",
  #   "access_tier": "Premium Monthly",
  #   "entry_fee": 15,
  #   "description": "Group chat for football enthusiasts with the greatest players of all time.",
  #   "image_url": "https://example.com/football.png",
  #   "chat_type": "premium",
  #   "chat_category": "sports",
  #   "participants": [
  #     {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #     {"uid": "fpO9prUW8ZKdDC8OzuSq", "type": "ai", "name": "Lionel Messi"},
  #     {"uid": "ElMuonJFB13BZtIuFYCD", "type": "ai", "name": "Cristiano Ronaldo"}
  #   ],
  #   "initial_messages": [
  #     {
  #       "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #       "content": "Welcome to the two greatest footballers of all time! Leo and CR7 in one chat!",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "fpO9prUW8ZKdDC8OzuSq", "type": "ai", "name": "Lionel Messi"},
  #       "content": "Gracias! Excited to be here with all of you fans and with Cristiano too!",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "ElMuonJFB13BZtIuFYCD", "type": "ai", "name": "Cristiano Ronaldo"},
  #       "content": "Siuuuu! Great to join this chat. Looking forward to discussing football with you all!",
  #       "isProcessed": True
  #     }
  #   ]
  # },
  # {
  #   "name": "Marvel Avengers HQ",
  #   "access_tier": "Premium Annual",
  #   "entry_fee": 99,
  #   "description": "Join your favorite superheroes in this exclusive Avengers chat",
  #   "image_url": "https://wallpapers.com/images/featured/avengers-vm16xv4a69smdauy.jpg",
  #   "chat_type": "premium",
  #   "chat_category": "entertainment",
  #   "participants": [
  #     {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #     {"uid": "EJ7AstPRxCOzSZpZsdTF", "type": "ai", "name": "Iron Man"},
  #     {"uid": "8ccw5SE2f3kI7e31e1fO", "type": "ai", "name": "Captain America"},
  #     {"uid": "ARbfqNOTKToC9QqMkWjy", "type": "ai", "name": "Spider-Man"}
  #   ],
  #   "initial_messages": [
  #     {
  #       "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #       "content": "Avengers Assemble! I can't believe I'm talking to the actual heroes!",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "EJ7AstPRxCOzSZpZsdTF", "type": "ai", "name": "Iron Man"},
  #       "content": "Well, believe it. Genius, billionaire, philanthropist at your service. How can we help?",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "ARbfqNOTKToC9QqMkWjy", "type": "ai", "name": "Spider-Man"},
  #       "content": "Hey everyone! Friendly neighborhood Spider-Man here! Mr. Stark, I had that question about the suit upgrades...",
  #       "isProcessed": True
  #     }
  #   ]
  # },
  {
    "name": "Hogwarts Common Room",
    "access_tier": "Premium Monthly",
    "entry_fee": 20,
    "description": "Chat with your favorite wizards from the Harry Potter universe!",
    "image_url": "https://storage.googleapis.com/pod_public/1300/105088.jpg",
    "chat_type": "premium",
    "chat_category": "entertainment",
    "participants": [
      {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
      {"uid": "dnnlAYEhSsA706TL0pu4", "type": "ai", "name": "Harry Potter"},
      {"uid": "bXqiQSDwdDzbByb1aC2C", "type": "ai", "name": "Hermione Granger"}
    ],
    "initial_messages": [
      {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
        "content": "Expecto Patronum! Is this spell correct? I'm so excited to learn magic from the best!",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "bXqiQSDwdDzbByb1aC2C", "type": "ai", "name": "Hermione Granger"},
        "content": "That's the correct incantation, but remember it's not just about the words! You need to focus on your happiest memory to produce a Patronus.",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "dnnlAYEhSsA706TL0pu4", "type": "ai", "name": "Harry Potter"},
        "content": "Hermione's right, as usual! The Patronus Charm is one of the most difficult defensive spells. It took me a while to master it too.",
        "isProcessed": True
      }
    ]
  },
  {
    "name": "Pop Stars Central",
    "access_tier": "Premium Monthly",
    "entry_fee": 25,
    "description": "Connect with your favorite music stars in this exclusive chat",
    "image_url": "https://www.rollingstone.com/wp-content/uploads/2022/12/RollingStone_-200-Greatest-Singers_Collage.gif",
    "chat_type": "premium",
    "chat_category": "entertainment",
    "participants": [
      {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
      {"uid": "V0KD4pP4doWJG9y3eWdn", "type": "ai", "name": "Taylor Swift"},
      {"uid": "WVNtY7lPqySiSSyJy1Ro", "type": "ai", "name": "Ariana Grande"},
      {"uid": "uFixAO7uYzuEXGB3Fzgm", "type": "ai", "name": "Beyoncé"}
    ],
    "initial_messages": [
      {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
        "content": "OMG! All my favorite artists in one place! I'm definitely in my fan era right now!",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "V0KD4pP4doWJG9y3eWdn", "type": "ai", "name": "Taylor Swift"},
        "content": "Hey everyone! So glad to be here with you all. Who's excited for the next album? 💫",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "WVNtY7lPqySiSSyJy1Ro", "type": "ai", "name": "Ariana Grande"},
        "content": "yuh! this is so fun ☁️✨ love connecting with y'all like this!",
        "isProcessed": True
      }
    ]
  },
  {
    "name": "Anime Universe",
    "access_tier": "Free",
    "entry_fee": 0,
    "description": "Join your favorite anime characters in this exciting chat group!",
    "image_url": "https://uchi.imgix.net/properties/anime2.png?crop=focalpoint&domain=uchi.imgix.net&fit=crop&fm=pjpg&fp-x=0.5&fp-y=0.5&h=558&ixlib=php-3.3.1&q=82&usm=20&w=992",
    "chat_type": "free",
    "chat_category": "entertainment",
    "participants": [
      {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
      {"uid": "o1gcfwZX4Hw6tUwzSFT5", "type": "ai", "name": "Naruto Uzumaki"},
      {"uid": "h4iCOXgwjsQzp1nJtTms", "type": "ai", "name": "Goku"},
      {"uid": "CrXU55pUHxcTbq90Upfg", "type": "ai", "name": "Deku"}
    ],
    "initial_messages": [
      {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
        "content": "I can't believe I'm chatting with the best anime protagonists ever! What's your favorite jutsu/technique?",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "o1gcfwZX4Hw6tUwzSFT5", "type": "ai", "name": "Naruto Uzumaki"},
        "content": "Believe it! I love my Shadow Clone Jutsu dattebayo! It was the first technique I mastered and it's gotten me out of so many tough situations!",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "h4iCOXgwjsQzp1nJtTms", "type": "ai", "name": "Goku"},
        "content": "Hey there! The Kamehameha is my signature move, but I'm always training to get stronger! Anyone want to spar?",
        "isProcessed": True
      }
    ]
  },
  {
    "name": "Hollywood Stars",
    "access_tier": "Premium Monthly",
    "entry_fee": 30,
    "description": "Connect with your favorite actresses and actors",
    "image_url": "https://sylvi.in/cdn/shop/articles/Popular_Hollywood_Stars_and_Their_Stylish.webp?v=1663322566",
    "chat_type": "premium",
    "chat_category": "entertainment",
    "participants": [
      {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
      {"uid": "29zVzxnwZCq7yCHrHiyY", "type": "ai", "name": "Emma Watson"},
      {"uid": "5iSRFy5A1jEDCcTZeYOe", "type": "ai", "name": "Zendaya"},
      {"uid": "Ma2qQEfOBYj4KTTUBxjH", "type": "ai", "name": "Sydney Sweeney"}
    ],
    "initial_messages": [
      {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
        "content": "What's it like on a Hollywood movie set? I've always been curious!",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "5iSRFy5A1jEDCcTZeYOe", "type": "ai", "name": "Zendaya"},
        "content": "Film sets are like little communities! Long days, lots of waiting, but when the cameras roll it's magical. Euphoria was particularly intense but rewarding.",
        "isProcessed": True
      },
      {
        "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
        "sender": {"uid": "29zVzxnwZCq7yCHrHiyY", "type": "ai", "name": "Emma Watson"},
        "content": "I grew up on film sets with Harry Potter, which was like a second home. Each project has its own unique atmosphere. The best part is the collaborative creativity!",
        "isProcessed": True
      }
    ]
  },
  # {
  #   "name": "Sports Champions",
  #   "access_tier": "Premium Annual",
  #   "entry_fee": 85,
  #   "description": "Elite discussions with the greatest athletes of our time",
  #   "image_url": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT48YOzC9rs2MCpc5NnKUrLBCZtTRN3mpPdZA&s",
  #   "chat_type": "premium",
  #   "chat_category": "sports",
  #   "participants": [
  #     {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #     {"uid": "HEp66NLHofX9mFl8gRRh", "type": "ai", "name": "LeBron James"},
  #     {"uid": "4rLI6qT6PeNncV8wFnIJ", "type": "ai", "name": "Serena Williams"},
  #     {"uid": "2gFNxmlrtvjoZJI1OG6E", "type": "ai", "name": "Naomi Osaka"}
  #   ],
  #   "initial_messages": [
  #     {
  #       "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "qL73zIfq9OQP5WIHz6oxSRSesgx1", "type": "user", "name": "aryan527"},
  #       "content": "What's your best advice for young athletes trying to reach the professional level?",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "HEp66NLHofX9mFl8gRRh", "type": "ai", "name": "LeBron James"},
  #       "content": "Consistency is key. Put in the work every single day, even when nobody's watching. And take care of your body and mind - it's a marathon, not a sprint. #StriveForGreatness",
  #       "isProcessed": True
  #     },
  #     {
  #       "id": (datetime.datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S"),
  #       "sender": {"uid": "4rLI6qT6PeNncV8wFnIJ", "type": "ai", "name": "Serena Williams"},
  #       "content": "Never let anyone tell you what you can't achieve. I faced so many doubters throughout my career. Your determination has to be stronger than any obstacle.",
  #       "isProcessed": True
  #     }
  #   ]
  # }
]

if __name__ == "__main__":
  # Add default group chat
  # add_group_chat_to_firebase()
  
  # Add sample group chats
  for sample_data in SAMPLE_GROUP_CHATS:
    time.sleep(1)
    group_chat_data = create_group_chat_data(
      name=sample_data["name"],
      access_tier=sample_data["access_tier"],
      entry_fee=sample_data["entry_fee"],
      description=sample_data["description"],
      image_url=sample_data["image_url"],
      chat_type=sample_data["chat_type"],
      chat_category=sample_data["chat_category"],
      participants=sample_data["participants"],
      initial_messages=sample_data.get("initial_messages")
    )
    add_group_chat_to_firebase(group_chat_data)