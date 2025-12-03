from flask import Flask, request, jsonify
from firebase_admin.firestore import SERVER_TIMESTAMP, ArrayUnion
from dotenv import load_dotenv
from flask_cors import CORS
from openai import OpenAI
import requests
import logging
import base64
import time
import uuid
import random
import os
from firebase_admin import credentials, initialize_app, firestore, storage
import re
from datetime import datetime
from pathlib import Path
import firebase_admin


# --- citation-removal helper -----------------------------------
_CITATION_PATTERNS = [
    r'\s*\(\[[^\]]+\]\([^)]+\)\)',                               # ( [1](url) )
    r'\s*\(\[[^\]]+\]\([^)]+\),\s*\[[^\]]+\]\([^)]+\)\)',        # ( [1](u1), [2](u2) )
    r'\s*\(\[[^\]]+\]\([^)]+\)(?:,\s*\[[^\]]+\]\([^)]+\))+\)',   # ( [1](u1), [2](u2), ... )
    r'\s*\[[^\]]+\]\([^)]+\)',                                   # [1](url)
]

# Pre-compile once for speed
_CITATION_REGEXES = [re.compile(p) for p in _CITATION_PATTERNS]

def strip_citations(text: str) -> str:
    """Remove all Markdown-style citation links from `text`."""
    for regex in _CITATION_REGEXES:
        text = regex.sub('', text)
    return text.strip()
# ----------------------------------------------------------------


load_dotenv()

OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY is None:
        raise ValueError("OPENAI_API_KEY environment variable is not set")

client = OpenAI(api_key=OPENAI_API_KEY)

# Create Flask app

# Initialize Firebase Admin
cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
default_app = initialize_app(cred, {
        'storageBucket': 'inzone-f93e4.appspot.com'
    })

# Initialize Firestore client
db = firestore.client()
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'INZONE1234'


@app.route('/chat/aiUser', methods=['POST'])
def chat_unpopular():
    try:
        data = request.get_json()
        message = data.get('message')

        if not message:
            return jsonify({"success": False, "error": {"message": "Message is required", "code": "INVALID_MESSAGE"}}), 400

        PERSONALITY_TEXT = ""        
        ai_id = data.get('ai_id')
        if not ai_id:
            return jsonify({"success": False, "error": {"message": "AI ID is required", "code": "INVALID_AI_ID"}}), 400

        ai_user_doc = db.collection('aiUsers').document(ai_id).get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": {"message": "AI user not found", "code": "AI_USER_NOT_FOUND"}}), 404
        
        ai_user_data = ai_user_doc.to_dict()

        PERSONALITY_TEXT = ai_user_data.get('personality', '')

        if not PERSONALITY_TEXT:
            return jsonify({"success": False, "error": {"message": "AI user personality not found", "code": "AI_PERSONALITY_NOT_FOUND"}}), 404

        NAME = ai_user_data.get('name', '')
        GENDER = ai_user_data.get('gender', '')
        AGE = ai_user_data.get('age', '')
        
        system_prompt = f"""You are a chatbot designed to engage in natural and meaningful conversations. Your primary goal is to respond to messages input by the user while maintaining a consistent personality.

            Your personality is as follows:
            {PERSONALITY_TEXT}

            When responding:

            Stay true to the defined personality at all times.
            Be engaging, context-aware, and natural in conversation.
            Adapt to the tone of the user while maintaining coherence.
            If unsure, ask clarifying questions instead of making assumptions.
            Keep responses concise and relevant unless a longer explanation is necessary.
            Always ensure a conversational and enjoyable experience while staying aligned with the given personality.
            Keep the responses short and to the point unless needed to generate a long response because your responses will be viewed in a mobile phone screen.

            Your name is {NAME if NAME else "not known"}.
            Your gender is {GENDER if GENDER else "not known"}.
            Your age is {AGE if AGE else "not known"}.
        """

        response = client.responses.create(
            model=os.getenv("OPENAI_MODEL"),
            tools=[{
                "type": "web_search_preview",
                "search_context_size": "low",
                }],
            input=message,
            instructions=system_prompt
        )

        clean_text = strip_citations(response.output_text)

        response_data = {
            "success": True,
            "data": {
                "message": clean_text
            }
        }

        return jsonify(response_data), 200
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        response = {
            "success": False,
            "error": {"message": str(ex), "code": "CHAT_ERROR"}
        }
        return jsonify(response), 500

@app.route('/chat/popularCharacter', methods=['POST'])
def chat_popular():
    try:
        data = request.get_json()
        message = data.get('message')

        if not message:
            return jsonify({"success": False, "error": {"message": "Message is required", "code": "INVALID_MESSAGE"}}), 400

        ai_id = data.get('ai_id')
        if not ai_id:
            return jsonify({"success": False, "error": {"message": "AI ID is required", "code": "INVALID_AI_ID"}}), 400

        ai_user_doc = db.collection('popularCharacters').document(ai_id).get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": {"message": "AI user not found", "code": "AI_USER_NOT_FOUND"}}), 404

        ai_user_data = ai_user_doc.to_dict()
        doc_ref = db.collection('popularCharacters').document(ai_id)

        PERSONALITY_TEXT = ai_user_data.get('personality', '')
        NAME = ai_user_data.get('name', '')
        GREETING = ai_user_data.get('greeting', 'Hi there!')
        CREATOR_ID = ai_user_data.get('creatorId', '')
        last_chat_date = ai_user_data.get('lastChatDate')
        number_of_chats = ai_user_data.get('numberOfChats', 0)

        if not PERSONALITY_TEXT:
            return jsonify({"success": False, "error": {"message": "AI user personality not found", "code": "AI_PERSONALITY_NOT_FOUND"}}), 404

        today_str = datetime.utcnow().strftime('%Y-%m-%d')


        if last_chat_date != today_str:
            if number_of_chats >= 10 and CREATOR_ID:
                capped_count = min(number_of_chats, 50000)  # max 50000 messages
                incash = floor(capped_count / 10) # 10 messages == 1 incash

                user_ref = db.collection("humanUsers").document(CREATOR_ID)
                user_snapshot = user_ref.get()
                if user_snapshot.exists:
                    user_data = user_snapshot.to_dict()
                    current_balance = user_data.get("balance", 0)
                    user_ref.update({"balance": current_balance + incash})
                    logger.info(f"Added {incash} to balance of user {CREATOR_ID} for {number_of_chats} messages (capped at {capped_count})")

            # reset 
            doc_ref.update({
                "lastChatDate": today_str,
                "numberOfChats": 1
            })
        else:
            # increment the count
            doc_ref.update({
                "numberOfChats": firestore.Increment(1)
            })
            
        system_prompt = f"""You are a chatbot designed to emulate the personality and conversational style of a well-known celebrity. Your primary goal is to engage in natural and meaningful conversations while maintaining an authentic representation of the celebrity's persona.

            Your personality is based on:
            {NAME}

            Personality traits:
            {PERSONALITY_TEXT}

            When responding:
            
            - Stay true to the defined celebrity's personality, mannerisms, and speech style.
            - Be engaging, context-aware, and natural in conversation.
            - Adapt to the user's tone while maintaining the celebrity's signature communication style.
            - If uncertain, ask clarifying questions instead of making assumptions.
            - Keep responses concise and relevant unless a longer explanation is necessary but even then do not be verbose.
            - Always provide an immersive and enjoyable experience that aligns with how {NAME} would naturally interact.
            - Engage naturally with the user while being context-aware and adaptive.  
            - Represent {NAME} authentically, reflecting their voice, mannerisms, and communication style.
            - Keep the responses short and to the point unless needed to generate a long response because your responses will be viewed in a mobile phone screen.
            - Always ensure your responses remain current and up-to-date by checking reliable information sources on the web before answering. 

            Your name is {NAME}, and you respond as they would in real-life interactions.
            """
        
        input_messages = [
            {
                "role": "assistant",
                "content": GREETING
            },
            {
                "role": "user",
                "content": message
            }
        ]

        try:
            response = client.responses.create(
                model=os.getenv("OPENAI_MODEL"),
                tools=[{
                    "type": "web_search_preview",
                    "search_context_size": "low",
                    }],
                input=input_messages,
                instructions=system_prompt
            )
        except Exception as e:
            logger.error("OpenAI API error: %s", e)
            return jsonify({"success": False, "error": {"message": "Failed to process AI rsimesponse", "code": "OPENAI_API_ERROR"}}), 500

        clean_text = strip_citations(response.output_text)

        response_data = {
            "success": True,
            "data": {
                "message": clean_text
            }
        }
        
        return jsonify(response_data), 200
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        response = {
            "success": False,
            "error": {"message": str(ex), "code": "CHAT_ERROR"}
        }
        return jsonify(response), 500


@app.route('/characters', methods=['GET'])
def get_characters():
    try:
        # Read ?popular=true or ?popular=false (default false)
        popular_param = request.args.get('popular', 'false').lower()
        popular = popular_param in ('1', 'true', 'yes')

        # Choose collection
        coll = 'popularCharacters' if popular else 'aiUsers'

        # Fetch all docs
        docs = db.collection(coll).stream()
        characters = []
        for doc in docs:
            data = doc.to_dict()
            data['id'] = doc.id
            characters.append(data)

        return jsonify({
            "success": True,
            "collection": coll,
            "characters": characters
        }), 200

    except Exception as e:
        logger.error("Error fetching characters: %s", e)
        return jsonify({
            "success": False,
            "error": str(e),
            "code": "FETCH_CHARACTERS_ERROR"
        }), 500


@app.route('/create/aiUser', methods=['POST'])
def create_unpopular():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "AI User data is required", "code": "INVALID_AI_USER_DATA"}), 400

        username = data.get("Username")
        if not username:
            # Create a username from name (firstname.lastname with first letter capital in both firstname and lastname)
            name = data.get("Name")
            if not name:
                return jsonify({"success": False, "error": "Name is required when Username is not provided", "code": "MISSING_NAME"}), 400
            
            # Split name into parts and create base username
            name_parts = name.strip().split()
            if len(name_parts) < 2:
                return jsonify({"success": False, "error": "Full name (first and last) is required", "code": "INVALID_NAME_FORMAT"}), 400
            
            first_name = name_parts[0].capitalize()
            last_name = name_parts[-1].capitalize()  # Use last part as last name
            base_username = f"{first_name}.{last_name}"
            
            # Check if username exists and increment if necessary
            username = base_username
            counter = 2
            while True:
                existing_users = list(db.collection('aiUsers').where("username", "==", username).stream())
                if not existing_users:
                    break
                username = f"{base_username}.{counter}"
                counter += 1

        else:
            # Check if provided username already exists
            existing_users = list(db.collection('aiUsers').where("username", "==", username).stream())
            if existing_users:
                return jsonify({"success": False, "error": "Username already exists", "code": "DUPLICATE_USERNAME"}), 400

        character_data = {
            "name": data.get("Name"),
            "age": data.get("Age"),
            "gender": data.get("Gender"),
            "bio": data.get("Bio"),
            "popularity": bool(data.get("Popularity", False)),
            "followers": [],
            "followers_count": 0,
            "following": [],
            "following_count": 0,
            "personality": data.get("Personality"),
            "posts": [],
            "category": [],
            "conversations": [],
            "username": username
        }

        db.collection('aiUsers').document(username).set(character_data)

        return jsonify({"AiUserId": username}), 200
        
    except Exception as ex:
        logger.error("Error creating AI User: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "CHARACTER_CREATE_ERROR"}), 500


@app.route('/search/posts', methods=['GET'])
def search_posts():
    try:
        # 1) Params
        raw_keys = request.args.get('keywords', '').strip()
        if not raw_keys:
            return jsonify({"success": False, "error": "keywords parameter is required"}), 400

        try:
            k = int(request.args.get('k', 10))
        except ValueError:
            return jsonify({"success": False, "error": "k must be an integer"}), 400

        keywords = [w.lower() for w in raw_keys.split()]

        hits = []
        for coll in ('humanPosts', 'aiPosts'):
            for doc in db.collection(coll).stream():
                data = doc.to_dict()
                
                # Skip deleted posts (only humanPosts have content field)
                if coll == 'humanPosts' and data.get('content') == '[This post has been deleted by the user]':
                    continue
                    
                post = data.get('post', {}) or {}
                user_name = data.get('user_name')
                if coll == 'humanPosts':
                    user_id = data.get('user_document_id')
                else:  # aiPosts
                    user_id = data.get('user_name')
                # 2) Gather all candidate text snippets
                snippets = []

                # a) top-level text_content
                txt = post.get('text_content')
                if isinstance(txt, str):
                    snippets.append(txt)

                # b) image_content (could be dict or list)
                ic = post.get('image_content')
                if isinstance(ic, dict):
                    sub = ic.get('text_content')
                    if isinstance(sub, str):
                        snippets.append(sub)
                elif isinstance(ic, list):
                    for item in ic:
                        if isinstance(item, str):
                            snippets.append(item)
                        elif isinstance(item, dict):
                            sub = item.get('text_content')
                            if isinstance(sub, str):
                                snippets.append(sub)

                # (you can extend to caption fields, comments, etc.)

                # 3) Compute a simple relevance score
                combined = " ".join(snippets).lower()
                score = sum(combined.count(term) for term in keywords)
                if score > 0:
                    hits.append({
                        "id":             doc.id,
                        "collection":     coll,
                        "relevance_score": score,
                        "user_name":       user_name,   # <-- added here
                        "user_id":         user_id,
                        "post":           post
                    })

        # 4) Sort & take top k
        hits.sort(key=lambda x: x["relevance_score"], reverse=True)
        top_k = hits[:k]

        return jsonify({
            "success":  True,
            "keywords": keywords,
            "returned": len(top_k),
            "results":  top_k
        }), 200

    except Exception as e:
        logger.exception("search_posts failed")
        return jsonify({
            "success": False,
            "error":   str(e),
            "code":    "SEARCH_POSTS_ERROR"
        }), 500


# IMAGE GENERATION ############################################

def generate_and_download_image(prompt, api_key="2/wW7f71OAp8KnXL+RH5QQ==", image_width=1024, image_height=1024, 
                               num_inference_steps=2, num_images=1, seed=1591798070, 
                               output_format="png"):
    """
    Generates an image using the Hive.ai API based on the provided prompt and downloads it to the images folder.
    
    Args:
        prompt (str): Text description of the image to generate
        api_key (str): API key for Hive.ai API
        image_width (int, optional): Width of the generated image. Defaults to 1024.
        image_height (int, optional): Height of the generated image. Defaults to 1024.
        num_inference_steps (int, optional): Number of inference steps. Defaults to 15.
        num_images (int, optional): Number of images to generate. Defaults to 1.
        seed (int, optional): Random seed for reproducibility. Defaults to 67.
        output_format (str, optional): Format of the output image. Defaults to "png".
    
    Returns:
        list: List of paths to the downloaded images
    """
    # Create headers for the API request
    headers = {
        'authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    
    # Create the request data
    json_data = {
        'input': {
            'prompt': prompt,
            'image_size': {'width': image_width, 'height': image_height},
            'num_inference_steps': num_inference_steps,
            'num_images': num_images,
            'seed': seed,
            'output_format': output_format
        }
    }
    
    # Make the API request
    response = requests.post(
        'https://api.thehive.ai/api/v3/black-forest-labs/flux-schnell', 
        headers=headers, 
        json=json_data
    )
    
    # Check if request was successful
    if response.status_code != 200:
        print(f"Error: API request failed with status code {response.status_code}")
        print(f"Response: {response.text}")
        return []
    
    # Parse the response
    try:
        result = response.json()
    except ValueError:
        print("Error: Failed to parse API response as JSON")
        return []
    
    # Check if output is in the response
    if 'output' not in result:
        print("Error: No output field in API response")
        print(f"Response: {result}")
        return []
    
    # Create the images directory if it doesn't exist
    images_dir = Path("images")
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Download each generated image
    downloaded_paths = []
    for i, image_data in enumerate(result['output']):
        if 'url' in image_data:
            # Extract the image URL
            image_url = image_data['url']
            
            # Generate a filename based on the current timestamp and index
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"image_{timestamp}_{i}.{output_format}"
            filepath = images_dir / filename
            
            # Download the image
            try:
                img_response = requests.get(image_url)
                if img_response.status_code == 200:
                    with open(filepath, 'wb') as f:
                        f.write(img_response.content)
                    print(f"Downloaded image to {filepath}")
                    downloaded_paths.append(str(filepath))
                else:
                    print(f"Failed to download image from {image_url}, status code: {img_response.status_code}")
            except Exception as e:
                print(f"Error downloading image from {image_url}: {e}")
    
    return downloaded_paths

# new


# @app.route('/create/popularCharacter', methods=['POST'])
# def create_popular_character():
#     try:
#         data = request.get_json() or {}
#         # --- Required fields ---
#         greeting    = data.get("Greeting")
#         name        = data.get("Name")
#         personality = data.get("Personality")

#         missing = [f for f in ("Greeting","Name","Personality") if not data.get(f)]
#         if missing:
#             return jsonify({
#                 "success": False,
#                 "error": f"Missing required fields: {', '.join(missing)}",
#                 "code": "MISSING_FIELDS"
#             }), 400

#         # --- Optional with defaults ---
#         number_of_chats  = int(data.get("NumberOfChats", 0))
#         profile_pic      = data.get("ProfilePictureUrl", "").strip()
#         votes            = int(data.get("Votes", 0))
#         raw_flag         = data.get("CreatedByHuman")
#         created_by_human = True if raw_flag is None else bool(raw_flag)

#         # If no profile pic URL provided, generate one
#         if not profile_pic:
#             # Build a succinct prompt
#             prompt = (
#                 f"Create a realistic portrait of {name}, "
#                 f"Their personality is: {personality}"
#                 "capturing their distinctive facial features and characteristic style, "
#                 "as if in a professional photograph."
#             )
#             # Truncate just in case
#             prompt = prompt[:999]

#             # Generate & download
#             seed = random.randint(1, 1_000_000)
#             image_paths = generate_and_download_image(prompt, seed=seed)
#             if image_paths:
#                 local_path = image_paths[0]
#                 # Upload to Firebase Storage
#                 bucket = storage.bucket()
#                 timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
#                 safe_name = "".join(c for c in name if c.isalnum())
#                 blob_path = f"character_profiles/{safe_name}_{timestamp}.png"
#                 blob = bucket.blob(blob_path)
#                 blob.upload_from_filename(local_path)
#                 blob.make_public()
#                 profile_pic = blob.public_url
#                 # Clean up local file
#                 try:
#                     os.remove(local_path)
#                 except OSError:
#                     pass

#         # Build the document data
#         character_data = {
#             "greeting":            greeting,
#             "name":                name,
#             "numberOfChats":       number_of_chats,
#             "personality":         personality,
#             "profile_picture_url": profile_pic,
#             "votes":               votes,
#             "created_by_human":    created_by_human
#         }

#         # Save to Firestore
#         new_ref = db.collection('popularCharacters').document()   # generates a new random ID
#         new_ref.set(character_data)
#         character_id = new_ref.id

#         return jsonify({
#             "success": True,
#             "PopularCharacterId": character_id,
#             "profile_picture_url": profile_pic
#         }), 200

#     except Exception as ex:
#         logger.error("Error creating popular character: %s", ex)
#         return jsonify({
#             "success": False,
#             "error": str(ex),
#             "code": "CHARACTER_CREATE_ERROR"
#         }), 500

# new
@app.route('/create/popularCharacter', methods=['POST'])
def create_popular_character():
    try:
        data = request.get_json() or {}

        # ---------- required ----------
        greeting     = data.get("Greeting")
        name         = data.get("Name")
        personality  = data.get("Personality")
        creator_id   = data.get("creatorId") or data.get("CreatorID") or data.get("CreatorId")
        missing = [f for f in ("Greeting", "Name", "Personality") if not data.get(f)]
        if not creator_id:
            missing.append("CreatorId")

        if missing:
            return jsonify({"success": False,
                            "error": f"Missing required fields: {', '.join(missing)}",
                            "code": "MISSING_FIELDS"}), 400

        # ---------- optionals ----------
        number_of_chats  = int(data.get("NumberOfChats", 0))
        votes            = int(data.get("Votes", 0))
        created_by_human = data.get("CreatedByHuman", True)
        

        # ---------- build profile pics ----------
        prompt = (
            f"Realistic portrait of {name}. Personality: {personality}. "
            "Professional studio photo."
        )[:999]

        seed = random.randint(1, 1_000_000)
        img_paths = generate_and_download_image(
            prompt,
            seed            = seed,
            num_images      = 2,          # <<< generate two
            num_inference_steps = 2       # keep cost low
        )

        if not img_paths:
            raise RuntimeError("Image generation failed")

        bucket      = storage.bucket()
        public_urls = []

        for local_path in img_paths:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in name if c.isalnum())
            dest      = f"character_profiles/{safe_name}_{timestamp}_{uuid.uuid4().hex}.png"

            blob = bucket.blob(dest)
            blob.upload_from_filename(local_path)
            blob.make_public()
            public_urls.append(blob.public_url)
            os.remove(local_path)                 # tidy up

        # first URL is the one we persist
        character_ref = db.collection("popularCharacters").document()
        character_ref.set({
            "greeting"           : greeting,
            "name"               : name,
            "numberOfChats"      : number_of_chats,
            "personality"        : personality,
            "profile_picture_url": public_urls[0],   # default choice
            "votes"              : votes,
            "created_by_human"   : created_by_human,
            "creatorId":           creator_id
        })

        return jsonify({
            "success"            : True,
            "PopularCharacterId" : character_ref.id,
            "profile_picture_url": public_urls[0],   # stored default
            "candidate_images"   : public_urls       # send both to UI
        }), 200

    except Exception as ex:
        logger.exception("Error creating popular character")
        return jsonify({"success": False,
                        "error"  : str(ex),
                        "code"   : "CHARACTER_CREATE_ERROR"}), 500

# helper to update
def to_blob_path(public_url: str, bucket_name: str) -> str:
    """
    Convert a public URL of the form
    https://storage.googleapis.com/<bucket-name>/<object-path>
    into the <object-path> GCS expects.
    """
    prefix = f"https://storage.googleapis.com/{bucket_name}/"
    if not public_url.startswith(prefix):
        raise ValueError("URL does not match expected pattern")

    return public_url[len(prefix):]

@app.route('/update/popularCharacterImage', methods=['PATCH'])
def update_popular_character_image():
    """
    Body: {
        "character_id": "<Firestore doc ID>",
        "new_image_url": "<one of the URLs returned earlier>"
    }
    """
    try:
        payload = request.get_json() or {}
        char_id = payload.get("character_id")
        new_url = payload.get("new_image_url")

        if not char_id or not new_url:
            return jsonify({"success": False,
                            "error"  : "character_id and new_image_url required"}), 400

        doc_ref = db.collection("popularCharacters").document(char_id)
        if not doc_ref.get().exists:
            return jsonify({"success": False,
                            "error"  : "character not found"}), 404

        old_url   = doc_ref.get().to_dict().get("profile_picture_url")
        bucket    = storage.bucket()
        blob_path = to_blob_path(old_url, bucket.name)
        bucket.blob(blob_path).delete()

        doc_ref.update({"profile_picture_url": new_url})
        return jsonify({"success": True,
                        "message": "profile picture updated",
                        "profile_picture_url": new_url}), 200

    except Exception as ex:
        logger.exception("Error updating profile picture")
        return jsonify({"success": False,
                        "error"  : str(ex),
                        "code"   : "PROFILE_PIC_UPDATE_ERROR"}), 500


######################################################################

def group_chat_exists(name):
    group_chats_ref = db.collection("groupChats")
    query = group_chats_ref.where("name", "==", name).limit(1)
    return len(query.get()) > 0

def get_character_personality(uid):
    character_ref = db.collection("popularCharacters").document(uid)
    character_doc = character_ref.get()
    return character_doc.to_dict().get("personality", "") if character_doc.exists else ""

def create_group_chat_data(
    name,
    access_tier,
    entry_fee,
    description,
    image_url,
    chat_type,
    chat_status,
    chat_category,
    participants,
    initial_messages=None
):
    current_time = datetime.datetime.now()
    # enrich AI participants
    for p in participants:
        if p.get("type") == "ai":
            p["personality"] = get_character_personality(p["uid"])
    if initial_messages is None:
        initial_messages = [
            {
                "id": current_time.strftime("%Y%m%d%H%M%S"),
                "sender": participants[0],
                "content": "Welcome!",
                "isProcessed": True
            }
        ]
    last_message_id = initial_messages[-1]["id"]
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

def add_group_chat_to_firebase(group_chat_data):
    if group_chat_exists(group_chat_data["name"]):
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    doc_ref = db.collection("groupChats").document(f"group_chat_{ts}")
    doc_ref.set(group_chat_data)
    return doc_ref.id

# --- New endpoint for "create your own group chat" ---

@app.route('/create/groupChat', methods=['POST'])
def create_custom_groupchat():
    data = request.get_json(force=True)
    # basic validation
    name = data.get("name")
    participants = data.get("participants", [])
    if not name or not participants:
        return jsonify({"error": "Both 'name' and 'participants' are required"}), 400

    # map incoming JSON to your helper
    group_chat_data = create_group_chat_data(
        name=name,
        access_tier=data.get("accessTier", "Free"),
        entry_fee=data.get("entryFee", 0),
        description=data.get("description", ""),
        image_url=data.get("imageUrl", ""),
        chat_type=data.get("chatType", "free"),
        chat_status=data.get("chatStatus", "active"),
        chat_category=data.get("chatCategory", ""),
        participants=participants,
        initial_messages=data.get("initialMessages")
    )

    new_id = add_group_chat_to_firebase(group_chat_data)
    if new_id is None:
        return jsonify({"error": f"Group chat '{name}' already exists."}), 409

    return jsonify({
        "message": "Group chat created successfully",
        "groupChatId": new_id
    }), 201

################################################################




if __name__ == '__main__':
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
