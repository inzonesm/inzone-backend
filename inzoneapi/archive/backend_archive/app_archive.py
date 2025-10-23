from flask import Flask, request, jsonify
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from flask_cors import CORS
from openai import OpenAI
import requests
import json
import logging
import random
import base64
import time
import uuid
import os
import subprocess
import sys
import math
from firebase_admin import credentials, initialize_app, firestore

"""
Commands
gcloud builds submit --tag gcr.io/inzone-f93e4/inzoneapi
gcloud run deploy --image gcr.io/inzone-f93e4/inzoneapi --set-env-vars OPENAI_API_KEY='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'

"""
# try:
#     from rapidfuzz import fuzz
# except ImportError:
#     print("rapidfuzz not found. Installing...")
#     subprocess.check_call([sys.executable, "-m", "pip", "install", "rapidfuzz"])
#     from rapidfuzz import fuzz

# subprocess.check_call([sys.executable, "-m", "pip", "install", "flask-jwt-extended"])
# from flask_jwt_extended import jwt_required, get_jwt_identity

# subprocess.check_call([sys.executable, "-m", "pip", "install", "twilio"])

load_dotenv()


OPENAI_API_KEY=os.environ.get("OPENAI_API_KEY")
if OPENAI_API_KEY is None:
        raise ValueError("OPENAI_API_KEY environment variable is not set")


client = OpenAI(api_key=OPENAI_API_KEY)


# Create Flask app
# Initialize Firebase Admin
cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
default_app = initialize_app(cred)


# Initialize Firestore client
db = firestore.client()
logger = logging.getLogger(__name__)
app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'INZONE1234'

@app.route("/", methods=["GET"])
def test():
    return "Work in Progress!"

@app.route('/get_post/<post_id>', methods=['GET'])
def get_post(post_id):
    try:
        # Fetch the post from Firestore
        post_ref = db.collection('posts').document(post_id)
        post_doc = post_ref.get()

        if post_doc.exists:
            return jsonify(post_doc.to_dict()), 200
        else:
            return jsonify({"error": "Post not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
    return encoded_string

@app.route('/api/image', methods=['POST'])
def image_generate():
    data = request.get_json()

    if not data or 'prompt' not in data:
        return jsonify({"error": "Missing 'prompt' in request"}), 400

    prompt = data['prompt']

    try:
       
        response = client.images.generate(
            model="dall-e-3",
            prompt=f"${prompt}",
            size="1024x1024",
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        time.sleep(5)
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            return jsonify({"error": "Failed to download image"}), 500

        # Save the image locally
        local_file_path = 'prompt_image.png'
        with open(local_file_path, 'wb') as file:
            file.write(image_response.content)

        # Generate a unique ID for the file
        unique_id = str(uuid.uuid4())
        blob_name = f"3d/{unique_id}.png"

        # Upload the file to Firebase Storage
        bucket = storage.bucket()
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(local_file_path)

        # Make the file publicly accessible
        blob.make_public()
        public_url = blob.public_url

        # Clean up the local file
        os.remove(local_file_path)

        return jsonify({"image_url": public_url}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Define a route to accept data via POST
@app.route('/api/3d', methods=['POST'])
def threed_generate():
    data = request.get_json()

    if not data or 'image_url' not in data:
        return jsonify({"error": "Missing 'image_url' in request"}), 400

    image_url = data['image_url']

    try:
        # Step 1: Download the image
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            return jsonify({"error": "Failed to download image"}), 500

        # Step 2: Save the image locally
        local_file_path = 'downloaded_image.png'
        with open(local_file_path, 'wb') as file:
            file.write(image_response.content)

        # Step 3: Convert the image to Base64
        base64_image = image_to_base64(local_file_path)

        # Step 4: Prepare payload and send to Meshy API
        payload = {
            "image_url": f"data:image/png;base64,{base64_image}",
            "enable_pbr": True
        }
        headers = {
            "Authorization": f"Bearer {MESH_API_KEY}"
        }

        response = requests.post(
            "https://api.meshy.ai/v1/image-to-3d",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()

        # Step 5: Extract and return the task ID
        task_id = response.json()
        return jsonify(task_id), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/get_model/<task_id>', methods=['GET'])
def get_model(task_id):
    headers = {
        'Authorization': f'Bearer {MESH_API_KEY}'
    }

    try:
        # Fetch task details from Meshy API
        response = requests.get(
            f'https://api.meshy.ai/v1/image-to-3d/{task_id}',
            headers=headers
        )
        response.raise_for_status()
        object_json = response.json()

        # Get model and texture URLs
        model_url = object_json['model_urls']['obj']
        texture_url = object_json['texture_urls'][0]['base_color']

        return jsonify({
            "model_url": model_url,
            "texture_url": texture_url
        }), 200

        # return jsonify(object_json), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

##############################################################################################################
# InZone Backend
# - Unknown error: 500
# - Specific error: 400
# - Success: 200
##############################################################################################################

# ---------------------------
# API Controller
# ---------------------------

@app.route('/api/sentiment-analysis', methods=['POST'])
def analyze_sentiment():
    try:
        # Extract JSON content from the request
        content = request.get_json()
        if not content or 'text' not in content:
            return jsonify({"success": False, "error": "Missing 'text' in request body", "code": "INVALID_REQUEST"}), 400
        # Prepare the prompt for sentiment analysis
        prompt = f'Analyze the sentiment of the following text and provide scores in the exact JSON format: {content['text']}. do not add anything else to the response, not even ```json. just give me a json starting and ending in curly braces. repeat all the fields exactly like "PositiveScore", "NegativeScore", "NeutralScore", "OverallSentiment", "Categories", "Keywords".'
        # Call OpenAI API for sentiment analysis
        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a sentiment analysis model."},
                {"role": "user", "content": prompt}
            ]
        )
        # Extract the assistant's response
        chat_response = completion.choices[0].message.content
        # Parse the response into JSON format
        try:
            sentiment = json.loads(chat_response)
        except json.JSONDecodeError:
            logger.error("Invalid JSON response from OpenAI: %s", chat_response)
            return jsonify({"success": False, "error": "Invalid response format from OpenAI", "code": "SENTIMENT_FORMAT_ERROR"}), 500
        # Validate the response format
        required_keys = {"PositiveScore", "NegativeScore", "NeutralScore", "OverallSentiment", "Categories", "Keywords"}
        if not all(key in sentiment for key in required_keys):
            logger.error("Missing keys in OpenAI response: %s", sentiment)
            return jsonify({"success": False, "error": "Invalid response format from OpenAI", "code": "SENTIMENT_FORMAT_ERROR"}), 500
        # Return the sentiment analysis result
        return jsonify({"success": True, "data": sentiment}), 200
    except Exception as ex:
        logger.error("Error analyzing sentiment: %s", ex)
        return jsonify({"success": False, "error": "Failed to analyze sentiment", "code": "SENTIMENT_ERROR"}), 500
        
@app.route('/api/main-ai-chat', methods=['POST'])
def main_ai_chat():
    try:
        message = request.get_json()
        chat_data = {
            "message": message,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('chats').add(chat_data)

        response = "This is a test AI response"

        return jsonify({"success": True, "data": {"response": response}}), 200
    except Exception as ex:
        logger.error("Error in main AI chat: %s", ex)
        return jsonify({"success": False, "error": "Failed to process chat", "code": "CHAT_ERROR"}), 500

@app.route('/api/add-user', methods=['POST'])
def add_user():
    try:
        data = request.get_json()
        user_data = {
            "name": data.get("Name"),
            "born": data.get("Born"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('humanUsers').add(user_data)
        return jsonify({"success": True, "data": {"userId": doc_ref[1].id}}), 200
    except Exception as ex:
        logger.error("Error adding user: %s", ex)
        return jsonify({"success": False, "error": "Failed to add user", "code": "USER_ADD_ERROR"}), 500

@app.route('/api/get-all-ai-profiles', methods=['POST'])
def get_all_ai_profiles():
    try:
        query = db.collection('ai_characters')
        snapshot = query.stream()
        profiles = [doc.to_dict() for doc in snapshot]

        return jsonify({"success": True, "data": profiles}), 200
    except Exception as ex:
        logger.error("Error getting AI profiles: %s", ex)
        return jsonify({"success": False, "error": "Failed to get AI profiles", "code": "PROFILE_GET_ERROR"}), 500

@app.route('/api/create-ai-profile', methods=['POST'])
def create_ai_profile():
    try:
        data = request.get_json()
        profile_data = {
            "userName": data.get("UserName"),
            "description": data.get("Description"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('ai_characters').add(profile_data)
        return jsonify({"success": True, "data": {"profileId": doc_ref[1].id}}), 200
    except Exception as ex:
        logger.error("Error creating AI profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to create AI profile", "code": "AI_PROFILE_CREATE_ERROR"}), 500

@app.route('/api/get-avatars', methods=['GET'])
def get_avatars():
    try:
        # Retrieve all avatars
        avatars_ref = db.collection('avatars')
        snapshot = avatars_ref.stream()

        # Separate predefined avatars based on the image URL
        predefined_avatars = []
        user_created_avatars = []

        for doc in snapshot:
            avatar = doc.to_dict()
            if "predefined" in avatar.get("imgPath", ""):
                predefined_avatars.append(avatar)
            else:
                user_created_avatars.append(avatar)

        # Combine lists, prioritizing predefined avatars
        prioritized_avatars = predefined_avatars + user_created_avatars

        return jsonify(prioritized_avatars), 200
    except Exception as ex:
        return jsonify({"success": False, "error": str(ex)}), 500

# ---------------------------
# User Controller
# ---------------------------

@app.route('/user/create-profile', methods=['POST'])
def create_profile():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

        anonymous = data.get("Email") if data.get("Email") else False
       
        user_data = {
            "name": data.get("Name"),
            "age": data.get("Age"),
            "bio": data.get("Bio"),
            "blockout": [],
            "user_interests": data.get("UserInterests", []),
            "email": data.get("Email"),
            "liked_posts": [],
            "anonymous": anonymous,
            "balance": 0,
            "followers": [],
            "following": [],
            "gender": data.get("Gender"),
            "profile_picture": data.get("ProfilePicture"),
            "date_created": firestore.SERVER_TIMESTAMP,
            "uid": data.get("UID"),
            "username": data.get("UserName")
        }

        doc_ref = db.collection('humanUsers').document(data.get("UID")).set(user_data)

        response = {
            "success": True,
            "data": {
                "UserId": data.get("UID")
            }
        }
        return jsonify(response), 200
    except Exception as ex:
        logger.error("Error creating user profile: %s", ex)
        response = {
            "success": False,
            "error": {
                "message": "Failed to create user profile",
                "code": "PROFILE_CREATE_ERROR"
            }
        }
        return jsonify(response), 500

@app.route('/user/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        update_data = {
            "name": data.get("Name"),
            "username": data.get("Username"),
            "bio": data.get("Bio"),
        }

        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update(update_data)
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/get-profile', methods=['GET'])
def get_profile():
    try:
        uid = request.args.get('uid')
        if not uid:
            return jsonify({"success": False, "error": "UID is required"}), 400

        user_doc = db.collection('humanUsers').document(uid).get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"success": True, "data": user_data}), 200
    except Exception as ex:
        logger.error("Error retrieving profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve profile", "code": "PROFILE_RETRIEVE_ERROR"}), 500

@app.route('/user/follow', methods=['POST'])
def follow():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to follow)
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"
        follower_username = data.get("FollowerUserName")
        following_type = data.get("FollowingType", "human")  # "human" or "ai"
        following_username = data.get("FollowingUserName")

        # Determine the correct collections based on user types
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'

        # For AI users, the document ID is the username
        follower_doc_id = follower_id
        following_doc_id = following_id

        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Update the follower's following list
        follower_data = follower_doc.to_dict()
        following_entry = {
            "id": following_id,
            "username": following_username,
            "type": following_type
        }
        
        # Check if already following
        current_following = follower_data.get("following", [])
        already_following = False
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                already_following = True
                break
            elif entry == following_id:  # Handle legacy format
                already_following = True
                break
                
        if not already_following:
            # Convert any legacy format to new format
            new_following = []
            for entry in current_following:
                if isinstance(entry, str):
                    new_following.append({"id": entry, "username": following_username, "type": "human" if follower_collection == "humanUsers" else "ai"})
                else:
                    new_following.append(entry)
            
            new_following.append(following_entry)
            follower_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(1) if follower_collection == 'aiUsers' else len(new_following)
            })

        # Update the following user's followers list
        following_data = following_doc.to_dict()
        follower_entry = {
            "id": follower_id,
            "username": follower_username,
            "type": follower_type
        }
        
        # Check if already in followers
        current_followers = following_data.get("followers", [])
        already_follower = False
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                already_follower = True
                break
            elif entry == follower_id:  # Handle legacy format
                already_follower = True
                break
                
        if not already_follower:
            # Convert any legacy format to new format
            new_followers = []
            for entry in current_followers:
                if isinstance(entry, str):
                    new_followers.append({"id": entry, "type": "human" if following_collection == "humanUsers" else "ai"})
                else:
                    new_followers.append(entry)
            
            new_followers.append(follower_entry)
            following_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(1) if following_collection == 'aiUsers' else len(new_followers)
            })

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error adding follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/unfollow', methods=['POST'])
def unfollow():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to follow)
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"
        follower_username = data.get("FollowerUserName")
        following_type = data.get("FollowingType", "human")  # "human" or "ai"
        follower_username = data.get("FollowingUserName")

        # Determine the correct collections based on user types
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'

        # For AI users, the document ID is the username
        follower_doc_id = follower_id
        following_doc_id = following_id

        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        # Update the follower's following list
        follower_data = follower_doc.to_dict()
        current_following = follower_data.get("following", [])
        new_following = []
        removed = False
        
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                removed = True
                continue
            elif entry == following_id:  # Handle legacy format
                removed = True
                continue
            new_following.append(entry)
            
        if removed:
            follower_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(-1) if follower_collection == 'aiUsers' else len(new_following)
            })

        # Update the following user's followers list
        following_data = following_doc.to_dict()
        current_followers = following_data.get("followers", [])
        new_followers = []
        removed = False
        
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                removed = True
                continue
            elif entry == follower_id:  # Handle legacy format
                removed = True
                continue
            new_followers.append(entry)
            
        if removed:
            following_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(-1) if following_collection == 'aiUsers' else len(new_followers)
            })

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/user/get-followers', methods=['POST'])
# def get_followers():
#     try:
#         data = request.get_json()
#         user_id = data.get("UserId")
#         user_type = data.get("UserType", "human")  # "human" or "ai"

#         # Determine the correct collection based on user type
#         collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        
#         # For AI users, the document ID is the username
#         doc_id = user_id

#         user_doc = db.collection(collection).document(doc_id).get()
#         if not user_doc.exists:
#             return jsonify({"success": False, "error": "User not found"}), 404

#         user_data = user_doc.to_dict()
#         followers = user_data.get("followers", [])
        
#         # Format response to include type information if not already present
#         formatted_followers = []
#         for follower in followers:
#             if isinstance(follower, dict):
#                 formatted_followers.append(follower)
#             else:
#                 # Legacy format - assume type based on collection
#                 formatted_followers.append({
#                     "id": follower,
#                     "type": "human" if collection == "humanUsers" else "ai"
#                 })
        
#         return jsonify({"success": True, "followers": formatted_followers}), 200
#     except Exception as ex:
#         logger.error("Error getting followers: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/user/get-following', methods=['POST'])
# def get_following():
#     try:
#         data = request.get_json()
#         user_id = data.get("UserId")
#         user_type = data.get("UserType", "human")  # "human" or "ai"

#         # Determine the correct collection based on user type
#         collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        
#         # For AI users, the document ID is the username
#         doc_id = user_id

#         user_doc = db.collection(collection).document(doc_id).get()
#         if not user_doc.exists:
#             return jsonify({"success": False, "error": "User not found"}), 404

#         user_data = user_doc.to_dict()
#         following = user_data.get("following", [])
        
#         # Format response to include type information if not already present
#         formatted_following = []
#         for follow in following:
#             if isinstance(follow, dict):
#                 formatted_following.append(follow)
#             else:
#                 # Legacy format - assume type based on collection
#                 formatted_following.append({
#                     "id": follow,
#                     "type": "human" if collection == "humanUsers" else "ai"
#                 })
        
#         return jsonify({"success": True, "following": formatted_following}), 200
#     except Exception as ex:
#         logger.error("Error getting following: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/remove-from-following', methods=['POST'])
def remove_from_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to remove from A's following list)
        user_type = data.get("UserType", "human")  # "human" or "ai"
        following_type = data.get("FollowingType", "human")  # "human" or "ai"

        logger.info(f"User {user_id} ({user_type}) is managing their following list by removing {following_id} ({following_type}).")

        # Determine the correct collections based on user types
        user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        following_collection = 'aiUsers' if following_type == 'ai' else 'humanUsers'
        
        # For AI users, the document ID is the username
        user_doc_id = user_id
        following_doc_id = following_id

        user_ref = db.collection(user_collection).document(user_doc_id)
        following_ref = db.collection(following_collection).document(following_doc_id)
        
        # Get current following list
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        user_data = user_doc.to_dict()
        current_following = user_data.get("following", [])
        new_following = []
        removed = False
        
        for entry in current_following:
            if isinstance(entry, dict) and entry.get("id") == following_id and entry.get("type") == following_type:
                removed = True
                continue
            elif entry == following_id:  # Handle legacy format
                removed = True
                continue
            new_following.append(entry)
            
        if removed:
            user_ref.update({
                "following": new_following,
                "following_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_following)
            })
            
            # Also update the followers list of the followed user
            following_doc = following_ref.get()
            if following_doc.exists:
                following_data = following_doc.to_dict()
                current_followers = following_data.get("followers", [])
                new_followers = []
                
                for entry in current_followers:
                    if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                        continue
                    elif entry == user_id:  # Handle legacy format
                        continue
                    new_followers.append(entry)
                    
                following_ref.update({
                    "followers": new_followers,
                    "followers_count": firestore.Increment(-1) if following_collection == 'aiUsers' else len(new_followers)
                })
        
        return jsonify({"success": True, "message": "User successfully removed from your following list."}), 200
    except Exception as ex:
        logger.error("Error removing from following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/remove-from-followers', methods=['POST'])
def remove_from_followers():
    try:
        data = request.get_json()
        user_id = data.get("UserId")  # A (authenticated user)
        follower_id = data.get("FollowerId")  # B (user to remove as follower)
        user_type = data.get("UserType", "human")  # "human" or "ai"
        follower_type = data.get("FollowerType", "human")  # "human" or "ai"

        logger.info(f"User {user_id} ({user_type}) is removing follower {follower_id} ({follower_type}).")

        # Determine the correct collections based on user types
        user_collection = 'aiUsers' if user_type == 'ai' else 'humanUsers'
        follower_collection = 'aiUsers' if follower_type == 'ai' else 'humanUsers'
        
        # For AI users, the document ID is the username
        user_doc_id = user_id
        follower_doc_id = follower_id

        user_ref = db.collection(user_collection).document(user_doc_id)
        follower_ref = db.collection(follower_collection).document(follower_doc_id)
        
        # Get current followers list
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        user_data = user_doc.to_dict()
        current_followers = user_data.get("followers", [])
        new_followers = []
        removed = False
        
        for entry in current_followers:
            if isinstance(entry, dict) and entry.get("id") == follower_id and entry.get("type") == follower_type:
                removed = True
                continue
            elif entry == follower_id:  # Handle legacy format
                removed = True
                continue
            new_followers.append(entry)
            
        if removed:
            user_ref.update({
                "followers": new_followers,
                "followers_count": firestore.Increment(-1) if user_collection == 'aiUsers' else len(new_followers)
            })
            
            # Also update the following list of the follower
            follower_doc = follower_ref.get()
            if follower_doc.exists:
                follower_data = follower_doc.to_dict()
                current_following = follower_data.get("following", [])
                new_following = []
                
                for entry in current_following:
                    if isinstance(entry, dict) and entry.get("id") == user_id and entry.get("type") == user_type:
                        continue
                    elif entry == user_id:  # Handle legacy format
                        continue
                    new_following.append(entry)
                    
                follower_ref.update({
                    "following": new_following,
                    "following_count": firestore.Increment(-1) if follower_collection == 'aiUsers' else len(new_following)
                })
        
        return jsonify({"success": True, "message": "User successfully removed from your followers list."}), 200
    except Exception as ex:
        logger.error("Error removing from followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/user/like-post', methods=['POST'])
def like_post():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        post_id = data.get("PostId")

        like_data = {
            "user_id": user_id,
            "post_id": post_id,
            "timestamp": firestore.SERVER_TIMESTAMP
        }

        # Increment the like count in the posts collection
        post_ref = db.collection('humanPosts').document(post_id)
        post_ref.update({
            "likes": firestore.Increment(1)
        })

        # Update the liked_posts field in humanUsers collection
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "liked_posts": firestore.ArrayUnion([post_id])
        })

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error liking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to like post", "code": "LIKE_POST_ERROR"}), 500

@app.route('/user/unlike-post', methods=['POST'])
def unlike_post():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        post_id = data.get("PostId")

        # Query to find the like relationship
        query = db.collection('postLikes').where('user_id', '==', user_id).where('post_id', '==', post_id)
        snapshot = query.stream()

        # Remove the like relationship
        for doc in snapshot:
            doc.reference.delete()

        # Decrement the like count in the posts collection
        post_ref = db.collection('humanPosts').document(post_id)
        post_ref.update({
            "likes": firestore.Increment(-1)
        })

        # Update the liked_posts field in humanUsers collection
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "liked_posts": firestore.ArrayRemove([post_id])
        })

        return jsonify({"success": True, "message": "Post unliked successfully."}), 200
    except Exception as ex:
        logger.error("Error unliking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to unlike post", "code": "UNLIKE_POST_ERROR"}), 500

@app.route('/user/get-liked-posts', methods=['POST'])
def get_liked_posts():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        # Retrieve the liked posts from the user's profile
        user_ref = db.collection('humanUsers').document(user_id).get()
        if user_ref.exists:
            liked_posts = user_ref.to_dict().get("liked_posts", [])
        else:
            liked_posts = []

        # Fetch the post details for each liked post ID
        liked_posts_details = []
        for post_id in liked_posts:
            post_ref = db.collection('humanPosts').document(post_id).get()
            if post_ref.exists:
                liked_posts_details.append(post_ref.to_dict())

        return jsonify({"success": True, "liked_posts": liked_posts_details}), 200
    except Exception as ex:
        logger.error("Error retrieving liked posts: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve liked posts", "code": "GET_LIKED_POSTS_ERROR"}), 500

@app.route('/user/generate-referral-code', methods=['POST'])
def generate_referral_code():
    try:
        data = request.get_json()
        user_id = data.get("UserDocumentId")
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        referral_code = f"INZONE-{uuid.uuid4().hex[:6].upper()}"

        # Update user profile with referral code
        user_ref = db.collection('humanUsers').document(user_id)
        user_ref.update({
            "referral_code": referral_code,
            "referral_count": 0,
            "total_referral_earnings": 0
        })

        return jsonify({
            "success": True,
            "data": {
                "referral_code": referral_code,
                "referral_link": f"https://inzone.ai/referral?code={referral_code}"
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/user/apply-referral', methods=['POST'])
def apply_referral():
    try:
        data = request.get_json()
        referral_code = data.get("ReferralCode")
        new_user_id = data.get("UserDocumentId")

        if not referral_code or not new_user_id:
            return jsonify({"success": False, "error": "Referral code and user ID are required"}), 400

        # Find referrer by referral code
        referrer_query = db.collection('humanUsers').where("referral_code", "==", referral_code).limit(1).get()
        if not referrer_query:
            return jsonify({"success": False, "error": "Invalid referral code"}), 404

        referrer_doc = referrer_query[0]
        referrer_id = referrer_doc.id

        # Check if user has already used a referral code
        new_user_ref = db.collection('humanUsers').document(new_user_id)
        new_user_doc = new_user_ref.get()
        if new_user_doc.exists and new_user_doc.to_dict().get("used_referral_code"):
            return jsonify({"success": False, "error": "User has already used a referral code"}), 400

        # Create referral record
        referral_data = {
            "referrer_id": referrer_id,
            "referee_id": new_user_id,
            "referral_code": referral_code,
            "status": "completed",
            "date_created": firestore.SERVER_TIMESTAMP,
            "rewards_granted": False
        }
        db.collection('referrals').add(referral_data)

        # Update new user's profile
        new_user_ref.update({
            "used_referral_code": referral_code,
            "referrer_id": referrer_id
        })

        # Update referrer's stats
        db.collection('humanUsers').document(referrer_id).update({
            "referral_count": firestore.Increment(1)
        })

        # Grant InCash rewards
        grant_referral_rewards(referrer_id, new_user_id)

        return jsonify({"success": True, "message": "Referral applied successfully"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

from twilio.rest import Client

twilio_client = Client(os.environ.get("TWILIO_ACCOUNT_SID"), os.environ.get("TWILIO_AUTH_TOKEN"))

def send_referral_sms(referral_code, phone_numbers, user_id):
    try:
        # Get user's current SMS history
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        user_data = user_doc.to_dict()
        
        # Initialize SMS history if it doesn't exist
        sms_history = user_data.get('sms', [])
        
        # Add new messages to history
        for number in phone_numbers:
            message = twilio_client.messages.create(
                body=f"Get 1000 InCash when you join InZone! Use my referral code: {referral_code}",
                from_=os.environ.get("TWILIO_PHONE_NUMBER"),
                to=number
            )
            
            sms_history.append({
                "account_sid": message.account_sid,
                "api_version": message.api_version,
                "body": message.body,
                "date_created": message.date_created,
                "date_sent": message.date_sent,
                "date_updated": message.date_updated,
                "direction": message.direction,
                "error_code": message.error_code,
                "error_message": message.error_message,
                "from": message.from_,
                "messaging_service_sid": message.messaging_service_sid,
                "num_media": message.num_media,
                "num_segments": message.num_segments,
                "price": message.price,
                "price_unit": message.price_unit,
                "sid": message.sid,
                "status": message.status,
                "subresource_uris": message.subresource_uris,
                "tags": message.tags,
                "to": message.to,
                "uri": message.uri,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        
        # Update user's document with the complete SMS history
        user_ref.update({
            "sms": sms_history
        })

        return sms_history
    except Exception as e:
        raise Exception(f"Failed to send SMS: {str(e)}")

@app.route('/user/send-referral-sms', methods=['POST'])
def send_referral_sms_endpoint():
    try:
        data = request.get_json()
        user_id = data.get("userId")
        phone_numbers = data.get("phoneNumbers")

        if not user_id or not phone_numbers:
            return jsonify({"success": False, "error": "User ID and phone numbers are required"}), 400

        # Get user's referral code
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        referral_code = user_doc.to_dict().get("referral_code")
        if not referral_code:
            return jsonify({"success": False, "error": "User does not have a referral code"}), 400

        # Send SMS to all phone numbers
        messages = send_referral_sms(referral_code, phone_numbers, user_id)

        return jsonify({
            "success": True,
            "message": "SMS sent successfully",
            "sms": messages
        }), 200

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def grant_referral_rewards(referrer_id, referee_id):
    """Grant InCash rewards to both referrer and referee"""
    try:
        referrer_reward = 1500  # 10$ worth of InCash
        referee_reward = 1500   # 10$ worth of InCash

        # Grant reward to referrer
        db.collection('humanUsers').document(referrer_id).update({
            "balance": firestore.Increment(referrer_reward),
            "total_referral_earnings": firestore.Increment(referrer_reward)
        })

        # Grant reward to new user
        db.collection('humanUsers').document(referee_id).update({
            "balance": firestore.Increment(referee_reward)
        })

        # Record rewards
        reward_data = {
            "referrer_id": referrer_id,
            "referee_id": referee_id,
            "referrer_reward": referrer_reward,
            "referee_reward": referee_reward,
            "date_granted": firestore.SERVER_TIMESTAMP
        }
        db.collection('referral_rewards').add(reward_data)
    except Exception as e:
        logger.error(f"Error granting referral rewards: {e}")
        raise e

@app.route('/user/referral-stats', methods=['GET'])
def get_referral_stats():
    try:
        user_id = request.args.get('UserDocumentId')
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        user_doc = db.collection('humanUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()

        # Get referral history
        referrals = db.collection('referrals').where("referrer_id", "==", user_id).get()
        referral_history = [{
            "referee_id": ref.get("referee_id"),
            "date": ref.get("date_created"),
            "status": ref.get("status")
        } for ref in referrals]

        return jsonify({
            "success": True,
            "data": {
                "referral_code": user_data.get("referral_code"),
                "referral_link": f"https://inzone.ai/referral?code={user_data.get('referral_code')}",
                "referral_count": user_data.get("referral_count", 0),
                "total_earnings": user_data.get("total_referral_earnings", 0),
                "referral_history": referral_history
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ---------------------------
# Monetization System Endpoints
# ---------------------------

@app.route('/wallet/balance', methods=['GET'])
def get_balance():
    try:
        user_id = request.args.get('UserDocumentId')
        if not user_id:
            return jsonify({"success": False, "error": "User ID is required"}), 400

        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        balance = user_data.get('balance')

        # If balance field does not exist, set it to 0 in Firestore
        if balance is None:
            user_ref.update({'balance': 0})
            balance = 0

        return jsonify({
            "success": True,
            "data": {
                "balance": balance,
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/wallet/purchase-incash', methods=['POST'])
def purchase_incash():
    try:
        data = request.get_json()
        user_id = data.get('UserDocumentId')
        package_id = data.get('PackageId')
        platform = data.get('Platform')  # "ios" or "android"
        receipt_data = data.get('ReceiptData')

        if not all([user_id, package_id, platform, receipt_data]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        packages = {
            # iOS packages
            'InCashGold': 2500,      # Monthly subscription
            'InCashElite2025': 1500, # One-time purchase
            'InCashAdvanced2025': 500,
            'InCashBasic2025': 100,
            
            # Android packages
            '2025incashgold': 2500,  # Monthly subscription
            '2025incashelite': 1500, # One-time purchase
            '2025incashadvanced': 500,
            '2025incashbasic': 100,
        }
        if package_id not in packages:
            return jsonify({"success": False, "error": "Invalid package"}), 400

        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
            
        # Get current balance
        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 0)
        
        # Update balance
        new_balance = current_balance + amount
        
        # Record purchase history
        purchase_history = user_data.get('purchaseHistory', [])
        purchase_history.append({
            'packageId': package_id,
            'platform': platform,
            'amount': amount,
            'date': datetime.now().isoformat(),
            'receiptData': receipt_data
        })
        
        # Check if this is a subscription purchase
        is_subscription = package_id in ['InCashGold', '2025incashgold']
        
        # If it's a subscription, update subscription status
        if is_subscription:
            subscription_data = {
                'isSubscribed': True,
                'subscriptionType': 'gold',
                'subscriptionId': package_id,
                'startDate': datetime.now().isoformat(),
                'nextRenewalDate': (datetime.now() + timedelta(days=30)).isoformat()
            }
            user_ref.update({
                'balance': new_balance,
                'purchaseHistory': purchase_history,
                'subscription': subscription_data
            })
        else:
            # For one-time purchases
            user_ref.update({
                'balance': new_balance,
                'purchaseHistory': purchase_history
            })
            
        return jsonify({
            'success': True,
            'data': {
                'balance': new_balance,
                'packageId': package_id,
                'amountAdded': amount
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def verify_ios_subscription(receipt_data, user_id):
    try:
        function_path = functions_client.function_path('inzone-project', 'us-central1', 'verifyIosSubscription')
        
        request_data = {
            'receiptData': receipt_data,
            'userId': user_id
        }
        
        response = functions_client.call_function(
            name=function_path,
            data=json.dumps(request_data).encode()
        )
        
        result = json.loads(response.result)
        
        if result.get('success'):
            subscription_info = result.get('data', {})
            return {
                'is_valid': True,
                'expiry_date': subscription_info.get('expiryDate'),
                'product_id': subscription_info.get('productId'),
                'is_trial_period': subscription_info.get('isTrialPeriod', False),
                'original_transaction_id': subscription_info.get('originalTransactionId')
            }
        else:
            print(f"iOS subscription verification failed: {result.get('error')}")
            return {'is_valid': False}
    except Exception as e:
        print(f"Error verifying iOS subscription: {e}")
        return {'is_valid': False}

# Verify Android subscription using Google Play Developer API
def verify_android_subscription(subscription_id, purchase_token):
    try:
        # Get the Android Publisher API client
        android_publisher = get_android_publisher_api()
        if not android_publisher:
            return {'is_valid': False}
        
        # Call the API to verify the subscription
        purchases_service = android_publisher.purchases().subscriptions()
        result = purchases_service.get(
            packageName=PACKAGE_NAME,
            subscriptionId=subscription_id,
            token=purchase_token
        ).execute()
        
        # Check if the subscription is active
        if result.get('paymentState') == 1:  # 1 means payment received
            expiry_time_millis = int(result.get('expiryTimeMillis', 0))
            expiry_date = datetime.fromtimestamp(expiry_time_millis / 1000).isoformat()
            
            return {
                'is_valid': True,
                'expiry_date': expiry_date,
                'auto_renewing': result.get('autoRenewing', False),
                'purchase_token': purchase_token,
                'order_id': result.get('orderId')
            }
        else:
            return {'is_valid': False}
    except Exception as e:
        print(f"Error verifying Android subscription: {e}")
        return {'is_valid': False}

@app.route('/wallet/spend-incash', methods=['POST'])
def spend_incash():
    try:
        data = request.get_json()
        user_id = data.get('UserDocumentId')
        amount = data.get('Amount')
        purpose = data.get('Purpose')  # 'group_access' or other future purposes
        group_id = data.get('GroupId')  # Only required for group_access purpose
        
        if not all([user_id, amount, purpose]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
            
        if purpose == 'group_access' and not group_id:
            return jsonify({"success": False, "error": "GroupId is required for group access"}), 400
        
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404
            
        # Get current balance
        user_data = user_doc.to_dict()
        current_balance = user_data.get('balance', 0)
        
        # Check if user has enough balance
        if current_balance < amount:
            return jsonify({
                "success": False, 
                "error": f"Insufficient balance. You have {current_balance} InCash, but {amount} is required."
            }), 400
        
        # Update balance
        new_balance = current_balance - amount
        
        # Record transaction history
        transaction_history = user_data.get('transactionHistory', [])
        transaction_history.append({
            'type': 'spend',
            'amount': amount,
            'purpose': purpose,
            'groupId': group_id if purpose == 'group_access' else None,
            'date': datetime.now().isoformat()
        })
        
        # Update user document
        user_ref.update({
            'balance': new_balance,
            'transactionHistory': transaction_history
        })
        
        # If purpose is group_access, add user to group participants if not already there
        if purpose == 'group_access':
            # Check if group exists in conversations collection
            group_ref = db.collection('conversations').document(group_id)
            group_doc = group_ref.get()
            
            if group_doc.exists:
                group_data = group_doc.to_dict()
                participants = group_data.get('participants', [])
                
                # Add user to participants if not already there
                if user_id not in participants:
                    participants.append(user_id)
                    group_ref.update({
                        'participants': participants,
                        'lastMessageTime': firestore.SERVER_TIMESTAMP,
                        'lastMessage': 'A new user joined the group'
                    })
            else:
                # Create group document if it doesn't exist
                group_ref.set({
                    'isGroupChat': True,
                    'participants': [user_id],
                    'lastMessageTime': firestore.SERVER_TIMESTAMP,
                    'lastMessage': 'A new user joined the group'
                })
        
        return jsonify({
            "success": True,
            "data": {
                "balance": new_balance,
                "amountSpent": amount,
                "purpose": purpose
            }
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint to update subscription status
@app.route('/wallet/update-subscription', methods=['POST'])
def update_subscription():
    try:
        data = request.json
        user_id = data.get('UserDocumentId')
        platform = data.get('Platform', '').lower()  # 'ios' or 'android'
        subscription_id = data.get('SubscriptionId')
        receipt_data = data.get('ReceiptData')  # For iOS: receipt data, For Android: purchase token
        
        if not user_id or not platform or not subscription_id or not receipt_data:
            return jsonify({
                'success': False,
                'error': 'Missing required fields'
            }), 400
            
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
        
        # Verify subscription based on platform
        if platform == 'ios':
            verification_result = verify_ios_subscription(receipt_data, user_id)
        elif platform == 'android':
            verification_result = verify_android_subscription(subscription_id, receipt_data)
        else:
            return jsonify({
                'success': False,
                'error': 'Invalid platform'
            }), 400
        
        # Update subscription status based on verification result
        if verification_result.get('is_valid'):
            expiry_date = verification_result.get('expiry_date')
            expiry_datetime = datetime.fromisoformat(expiry_date) if expiry_date else (datetime.now() + timedelta(days=30))
            
            subscription_data = {
                'isSubscribed': True,
                'subscriptionType': 'gold',
                'subscriptionId': subscription_id,
                'platform': platform,
                'startDate': datetime.now().isoformat(),
                'expiryDate': expiry_date,
                'nextRenewalDate': expiry_date,
                'verificationDetails': verification_result
            }
            
            user_ref.update({
                'subscription': subscription_data
            })
            
            return jsonify({
                'success': True,
                'data': {
                    'isSubscribed': True,
                    'subscriptionType': 'gold',
                    'expiryDate': expiry_date
                }
            })
        else:
            # Subscription is not valid
            subscription_data = {
                'isSubscribed': False,
                'cancelDate': datetime.now().isoformat(),
                'verificationDetails': verification_result
            }
            
            user_ref.update({
                'subscription': subscription_data
            })
            
            return jsonify({
                'success': False,
                'error': 'Subscription verification failed',
                'data': {
                    'isSubscribed': False
                }
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Endpoint to check subscription status
@app.route('/wallet/subscription-status', methods=['GET'])
def subscription_status():
    try:
        user_id = request.args.get('UserDocumentId')
        verify = request.args.get('verify', 'false').lower() == 'true'
        
        if not user_id:
            return jsonify({
                'success': False,
                'error': 'Missing user ID'
            }), 400
            
        # Get user document
        user_ref = db.collection('humanUsers').document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return jsonify({
                'success': False,
                'error': 'User not found'
            }), 404
            
        # Get subscription data
        user_data = user_doc.to_dict()
        subscription_data = user_data.get('subscription', {})
        is_subscribed = subscription_data.get('isSubscribed', False)
        
        # If verify flag is true, verify the subscription with the platform
        if verify and is_subscribed:
            platform = subscription_data.get('platform')
            subscription_id = subscription_data.get('subscriptionId')
            
            # For iOS, we need the original receipt data which should be stored
            if platform == 'ios':
                receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                if receipt_data:
                    verification_result = verify_ios_subscription(receipt_data, user_id)
                    is_subscribed = verification_result.get('is_valid', False)
            
            # For Android, we need the purchase token
            elif platform == 'android':
                purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                if purchase_token and subscription_id:
                    verification_result = verify_android_subscription(subscription_id, purchase_token)
                    is_subscribed = verification_result.get('is_valid', False)
            
            # Update subscription status if verification failed
            if not is_subscribed:
                subscription_data['isSubscribed'] = False
                subscription_data['cancelDate'] = datetime.now().isoformat()
                user_ref.update({
                    'subscription': subscription_data
                })
        
        return jsonify({
            'success': True,
            'data': {
                'isSubscribed': is_subscribed,
                'subscriptionData': subscription_data
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Endpoint to process monthly subscription rewards
@app.route('/wallet/process-subscription-rewards', methods=['POST'])
def process_subscription_rewards():
    try:
        # This endpoint should be called by a scheduled job/cron job at the start of each month
        # It will add 2500 InCash to all subscribed users
        
        # Get all subscribed users
        subscribed_users = db.collection('humanUsers').where('subscription.isSubscribed', '==', True).stream()
        
        processed_count = 0
        verified_count = 0
        failed_count = 0
        
        for user_doc in subscribed_users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            # Check if subscription is still active
            subscription_data = user_data.get('subscription', {})
            next_renewal_date = subscription_data.get('nextRenewalDate')
            platform = subscription_data.get('platform')
            subscription_id = subscription_data.get('subscriptionId')
            
            # Verify subscription with the platform
            is_valid = False
            
            if platform == 'ios':
                # For iOS, verify with Apple through Firebase Functions
                receipt_data = subscription_data.get('verificationDetails', {}).get('original_transaction_id')
                if receipt_data:
                    verification_result = verify_ios_subscription(receipt_data, user_id)
                    is_valid = verification_result.get('is_valid', False)
                    verified_count += 1
            
            elif platform == 'android':
                # For Android, verify with Google Play Developer API
                purchase_token = subscription_data.get('verificationDetails', {}).get('purchase_token')
                if purchase_token and subscription_id:
                    verification_result = verify_android_subscription(subscription_id, purchase_token)
                    is_valid = verification_result.get('is_valid', False)
                    verified_count += 1
            
            # If subscription is not valid, update status and skip reward
            if not is_valid:
                user_ref = db.collection('humanUsers').document(user_id)
                user_ref.update({
                    'subscription.isSubscribed': False,
                    'subscription.cancelDate': datetime.now().isoformat()
                })
                failed_count += 1
                continue
            
            # If subscription is valid and renewal date has passed, add the monthly reward
            if next_renewal_date and is_valid:
                next_renewal = datetime.fromisoformat(next_renewal_date)
                
                # If the renewal date has passed, add the monthly reward
                if datetime.now() >= next_renewal:
                    # Get current balance
                    current_balance = user_data.get('balance', 0)
                    
                    # Add 2500 InCash
                    new_balance = current_balance + 2500
                    
                    # Update next renewal date (30 days from now)
                    new_next_renewal = (datetime.now() + timedelta(days=30)).isoformat()
                    
                    # Record subscription reward
                    reward_history = user_data.get('subscriptionRewards', [])
                    reward_history.append({
                        'amount': 2500,
                        'date': datetime.now().isoformat(),
                        'type': 'monthly_subscription'
                    })
                    
                    # Update user document
                    user_ref = db.collection('humanUsers').document(user_id)
                    user_ref.update({
                        'balance': new_balance,
                        'subscriptionRewards': reward_history,
                        'subscription.nextRenewalDate': new_next_renewal
                    })
                    
                    processed_count += 1
        
        return jsonify({
            'success': True,
            'data': {
                'processedCount': processed_count,
                'verifiedCount': verified_count,
                'failedCount': failed_count
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# def verify_apple_purchase(receipt_data):
#     """Verify iOS purchase receipt with Apple servers"""
#     try:
#         APPLE_VERIFY_URL = "https://buy.itunes.apple.com/verifyReceipt"
#         payload = {
#             "receipt-data": receipt_data,
#             "password": os.getenv("APPLE_SHARED_SECRET")
#         }
#         response = requests.post(APPLE_VERIFY_URL, json=payload)
#         result = response.json()
#         return {
#             "success": result.get("status") == 0,
#             "new_balance": result.get("latest_receipt_info", [{}])[0].get("balance", 0)
#         }
#     except Exception as e:
#         logger.error(f"Error verifying Apple purchase: {e}")
#         return {"success": False, "error": str(e)}
        
# def verify_google_purchase(purchase_token, product_id):
#     """Verify Android purchase with Google Play"""
#     try:
#         PACKAGE = os.getenv("PACKAGE_NAME")
#         GOOGLE_VERIFY_URL = f"https://androidpublisher.googleapis.com/androidpublisher/v3/applications/{PACKAGE}/purchases/products/{product_id}/tokens/{purchase_token}"
#         headers = {"Authorization": f"Bearer {os.getenv('GOOGLE_ACCESS_TOKEN')}"}
#         response = requests.get(GOOGLE_VERIFY_URL, headers=headers)
#         result = response.json()
#         return {
#             "success": result.get("purchaseState") == 0,
#             "new_balance": result.get("balance", 0)
#         }
#     except Exception as e:
#         logger.error(f"Error verifying Google purchase: {e}")
#         return {"success": False, "error": str(e)}

# ---------------------------
# Asset Store Endpoints
# ---------------------------

@app.route('/store/items', methods=['GET'])
def get_items():
    items = [doc.to_dict() for doc in db.collection('store_items').stream()]
    return jsonify({'items': items})

@app.route('/store/purchase', methods=['POST'])
def purchase_item():
    data = request.json
    user_id = data['user_id']
    item_id = data['item_id']

    item_ref = db.collection('store_items').document(item_id)
    item = item_ref.get().to_dict()
    user_ref = db.collection('humanUsers').document(user_id)
    user_data = user_ref.get().to_dict()

    if not item:
        return jsonify({'error': 'Item not found'}), 404
    if user_data.get('balance', 0) < item.get('price', 0):
        return jsonify({'error': 'Insufficient funds'}), 400

    # Deduct funds and record purchase in the humanUsers document
    user_ref.update({
        'balance': firestore.Increment(-item.get('price', 0)),
        'purchases': firestore.ArrayUnion([item_id])
    })
    # Save purchased item to the user's inventory (subcollection)
    db.collection('humanUsers').document(user_id).collection('inventory').document(item_id).set(item)
    return jsonify({'message': 'Purchase successful'})

@app.route('/store/inventory', methods=['GET'])
def get_inventory():
    user_id = request.args.get('user_id')
    inventory = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('inventory').stream()]
    return jsonify({'inventory': inventory})

# ---------------------------
# Feed Controller
# ---------------------------
def generate_categories(post_text):
    try:
        if not post_text:
            return []
        
        prompt = (
            f"Classify the following post into relevant categories and return a JSON array. "
            f"Do not add anything else—just give me a JSON array starting and ending with brackets. "
            f"Post: {post_text}"
        )
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a text classification model."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = response.choices[0].message.content.strip()

        # Ensure we only get valid JSON output
        try:
            categories = json.loads(content)
            if isinstance(categories, list):
                return categories[:5]
        except json.JSONDecodeError:
            print(f"Invalid JSON response: {content}")
        
        return []
    
    except Exception as ex:
        print(f"Error generating categories: {ex}")
        return []

@app.route('/feed/create-human-post', methods=['POST'])
def create_human_post():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400
       
        username = data.get("UserName")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "INVALID_USERNAME"}), 400
       
        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)

        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": data.get("UserDocumentId"),
            "user_name": username,
            "id": data.get("Id")
        }

        db.collection('humanPosts').document(data.get("Id")).set(post_data)

        return jsonify({"postId": data.get("Id")}), 200
    except Exception as ex:
        logger.error("Error creating human post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

@app.route('/feed/create-ai-post', methods=['POST'])
def create_ai_post():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400

        username = data.get("username")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "MISSING_USERNAME"}), 400

        ai_user_ref = db.collection('aiUsers').document(username)
        ai_user_doc = ai_user_ref.get()
        if not ai_user_doc.exists:
            return jsonify({"success": False, "error": "Invalid username", "code": "USER_NOT_FOUND"}), 400

        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)

        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_name": username,
        }

        doc_ref = db.collection('aiPosts').document()
        post_id = doc_ref.id
        post_data["id"] = post_id
        doc_ref.set(post_data)

        ai_user_ref.update({"posts": firestore.ArrayUnion([post_id])})

        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error creating AI post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

# create a repost endpoint for reposting normal posts not just ai chats
@app.route('/feed/repost', methods=['POST'])
def repost_post():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Request data missing", "code": "NO_DATA"}), 400

        original_post_id = data.get("OriginalPostId")
        reposting_user_id = data.get("RepostingUserId")

        if not original_post_id or not reposting_user_id:
            return jsonify({"success": False, "error": "OriginalPostId and RepostingUserId are required", "code": "MISSING_PARAMS"}), 400

        original_doc = db.collection("humanPosts").document(original_post_id).get()
        original_post_type = "human"

        if not original_doc.exists:
            original_doc = db.collection("aiPosts").document(original_post_id).get()
            original_post_type = "ai"

        if not original_doc.exists:
            return jsonify({"success": False, "error": "Original post not found", "code": "ORIGINAL_POST_NOT_FOUND"}), 404

        original_data = original_doc.to_dict()
        post = original_data.get("post", {})
        post_text = post.get("text_content", "")
        image_content = post.get("image_content", [])
        video_content = post.get("video_content", [])
        categories = original_data.get("category", [])
        original_user_name = original_data.get("user_name")

        reposting_user_doc = db.collection("humanUsers").document(reposting_user_id).get()
        user_type = "human"

        if not reposting_user_doc.exists:
            reposting_user_doc = db.collection("aiUsers").document(reposting_user_id).get()
            user_type = "ai"

        if not reposting_user_doc.exists:
            return jsonify({"success": False, "error": "Reposting user not found", "code": "REPOSTING_USER_NOT_FOUND"}), 404

        reposting_user_data = reposting_user_doc.to_dict()

        repost_id = str(uuid.uuid4())
        repost_data = {
            "original_post_id": original_post_id,
            "original_post_type": original_post_type,
            "original_post_author": original_user_name,
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": reposting_user_id,
            "user_name": reposting_user_data.get("username"),
            "id": repost_id,
            "user_type": user_type
        }

        db.collection("reposts").document(repost_id).set(repost_data)

        return jsonify({"postId": repost_id}), 200

    except Exception as ex:
        logger.error("Error creating repost: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "REPOST_ERROR"}), 500

@app.route('/feed/create-repost', methods=['POST'])
def create_repost():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400
       
        post_text = data.get("Post").get("TextContent", "")
        image_content = data.get("Post").get("ImageContent", [])
        video_content = data.get("Post").get("VideoContent", [])

        post_data = {
            "ai_chat_content": data.get("AIChatContent"),
            "ai_name": data.get("AIName"),
            "ai_profile_image_url": data.get("AIProfileImageURL"),
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "has_image": bool(image_content),
            "has_video": bool(video_content),
            "post": {
                "image_content": image_content,
                "text_content": post_text,
                "video_content": video_content
            },
            "user_document_id": data.get("UserDocumentId"),
            "user_name": data.get("UserName"),
            "ai_id": data.get("AiId"),
            "id": data.get("Id")
        }

        db.collection('reposts').document(data.get("Id")).set(post_data)

        return jsonify({"postId": data.get("Id")}), 200
    except Exception as ex:
        logger.error("Error creating repost: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500

@app.route('/feed/update-human-post', methods=['POST'])
def update_human_post():
    try:
        data = request.get_json()
        post_id = data.get("Id")
        doc_ref = db.collection('humanPosts').document(post_id)
        
        if not doc_ref.get().exists:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404
        
        update_data = {
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            }
        }
        
        doc_ref.update(update_data)
        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error updating human post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

@app.route('/feed/update-ai-post', methods=['POST'])
def update_ai_post():
    try:
        data = request.get_json()
        post_id = data.get("Id")
        doc_ref = db.collection('aiPosts').document(post_id)
        
        if not doc_ref.get().exists:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404
        
        update_data = {
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            }
        }
        
        doc_ref.update(update_data)
        return jsonify({"postId": post_id}), 200
    except Exception as ex:
        logger.error("Error updating AI post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

@app.route('/feed/get-feed', methods=['POST'])
def get_feed():
    try:
        data = request.get_json()

        collections = ['aiPosts', 'humanPosts', 'reposts']
        posts = []

        for collection in collections:
            query = db.collection(collection).order_by("date_posted", direction=firestore.Query.DESCENDING).limit(15)
            snapshot = query.stream()
            posts.extend([doc.to_dict() for doc in snapshot])

        posts.sort(key=lambda x: x['date_posted'], reverse=True)

        return jsonify(posts[:limit]), 200
    except Exception as ex:
        logger.error("Error getting feed: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# @app.route('/feed/posts-flow', methods=['GET'])
# def posts_flow():
#     try:
#         collections = ['aiPosts', 'humanPosts', 'reposts']
#         all_posts = []

#         # Fetch all posts
#         for collection in collections:
#             posts_ref = db.collection(collection).order_by('date_posted', direction=firestore.Query.DESCENDING).limit(25)
#             snapshot = posts_ref.stream()
#             all_posts.extend([doc.to_dict() for doc in snapshot if doc.exists])

#         # Fetch AI users
#         ai_users_ref = db.collection('aiUsers')
#         ai_users_snapshot = ai_users_ref.stream()
#         ai_usernames = {doc.id for doc in ai_users_snapshot}

#         # Fetch human users
#         human_users_ref = db.collection('humanUsers')
#         human_users_snapshot = human_users_ref.stream()
#         human_user_uids = {doc.id for doc in human_users_snapshot}

#         # Categorize posts
#         ai_text_posts = [post for post in all_posts if post.get("username") in ai_usernames and not post.get("post", {}).get("video_content")]
#         ai_video_posts = [post for post in all_posts if post.get("username") in ai_usernames and post.get("post", {}).get("video_content")]
#         human_text_posts = [post for post in all_posts if post.get("user_document_id") in human_user_uids and not post.get("post", {}).get("video_content")]
#         human_video_posts = [post for post in all_posts if post.get("user_document_id") in human_user_uids and post.get("post", {}).get("video_content")]
#         reposts = [post for post in all_posts if post.get("aiChatContent") or post.get("aiName") or post.get("aiProfileImageURL")]

#         # Distribution of posts
#         # Human posts 42%: no videos 21%, videos 21%
#         # AI posts 42%: no videos 21%,  videos 21%,
#         # Reposts 16%
#         total_posts = len(all_posts)
#         num_human_text_posts = int(total_posts * 0.21)
#         num_human_video_posts = int(total_posts * 0.21)
#         num_ai_text_posts = int(total_posts * 0.21)
#         num_ai_video_posts = int(total_posts * 0.21)
#         num_reposts = int(total_posts * 0.16)

#         human_text_posts_sorted = sorted(human_text_posts, key=lambda x: x['date_posted'], reverse=True)
#         human_video_posts_sorted = sorted(human_video_posts, key=lambda x: x['date_posted'], reverse=True)
#         ai_text_posts_sorted = sorted(ai_text_posts, key=lambda x: x['date_posted'], reverse=True)
#         ai_video_posts_sorted = sorted(ai_video_posts, key=lambda x: x['date_posted'], reverse=True)
#         reposts_sorted = sorted(reposts, key=lambda x: x['date_posted'], reverse=True)

#         selected_posts = {
#             "aiPosts": sorted(ai_text_posts_sorted[:num_ai_text_posts] + ai_video_posts_sorted[:num_ai_video_posts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
#             "humanPosts": sorted(human_text_posts_sorted[:num_human_text_posts] + human_video_posts_sorted[:num_human_video_posts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
#             "reposts": sorted(reposts_sorted[:num_reposts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
#         }

#         return jsonify(selected_posts), 200
#     except Exception as ex:
#         logger.error("Error getting posts flow: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# Helper function to check if a post's category matches any category in a given list.
def category_matches(post, categories):
    category_field = post.get("category", "")
    if isinstance(category_field, str):
        return category_field.lower() in categories
    elif isinstance(category_field, list):
        return any(isinstance(cat, str) and cat.lower() in categories for cat in category_field)
    return False

# Compute similarity between two category strings using rapidfuzz.
def similarity_score(cat1, cat2):
    return fuzz.ratio(cat1.lower(), cat2.lower())

# Given preferred categories and a set of all distinct categories, find similar ones.
def compute_similar_categories(preferred, all_categories, threshold=60):
    similar = set()
    for pref in preferred:
        for candidate in all_categories:
            if candidate not in preferred:
                score = similarity_score(pref, candidate)
                if score >= threshold:
                    similar.add(candidate)
    return similar

# Also track when user log in and log out/delete app in humanUsers collection

# Add to recommendation system add posts to feed based on user's actions like 
# - liking a post
# - liking a certain number of posts from the same user


# @app.route('/feed/posts-flow', methods=['GET'])
# def posts_flow():
#     try:
#         user_id = request.args.get('user_id')
#         page = request.args.get('page', default=1, type=int)
#         posts_per_page = 30

#         user_doc = db.collection('humanUsers').document(user_id).get()
#         if user_doc.exists:
#             preferred = [cat.strip().lower() for cat in user_doc.to_dict().get('user_interests', []) if cat.strip()]
#         else:
#             preferred = []
#         print(f"User {user_id} preferred interests: {preferred}")

#         ratios = {
#             "ai_text": 0.21,
#             "ai_video": 0.21,
#             "human_text": 0.21,
#             "human_video": 0.21,
#             "reposts": 0.16
#         }
#         num_posts = {key: int(posts_per_page * ratio) for key, ratio in ratios.items()}
#         total_calculated = sum(num_posts.values())
#         if total_calculated < posts_per_page:
#             num_posts["ai_text"] += (posts_per_page - total_calculated)
#         print(f"Posts per type distribution (for logging): {num_posts}")

#         # Fetch all posts from each collection
#         ai_posts_all = [doc.to_dict() for doc in db.collection('aiPosts').stream()]
#         human_posts_all = [doc.to_dict() for doc in db.collection('humanPosts').stream()]
#         reposts_all = [doc.to_dict() for doc in db.collection('reposts').stream()]

#         all_categories = set()
#         for posts in [ai_posts_all, human_posts_all, reposts_all]:
#             for post in posts:
#                 cats = post.get("category", [])
#                 if isinstance(cats, str) and cats:
#                     all_categories.add(cats.lower())
#                 elif isinstance(cats, list):
#                     all_categories.update(cat.lower() for cat in cats if isinstance(cat, str))
#         print(f"All categories from posts: {list(all_categories)}")

#         # If user has no interests, use all categories
#         if not preferred or page >= 2:
#             preferred = list(all_categories)
#             print("No user interests found; using all categories.")

#         # filter posts by preferred categories
#         def filter_posts(posts, categories):
#             return [post for post in posts if category_matches(post, categories)]

#         ai_filtered = filter_posts(ai_posts_all, preferred)
#         human_filtered = filter_posts(human_posts_all, preferred)
#         reposts_filtered = filter_posts(reposts_all, preferred)

#         # Log counts per category
#         def log_posts_by_category(posts, label):
#             cat_dict = {}
#             for post in posts:
#                 cats = post.get("category", [])
#                 if isinstance(cats, str):
#                     cats = [cats.lower()]
#                 elif isinstance(cats, list):
#                     cats = [cat.lower() for cat in cats if isinstance(cat, str)]
#                 else:
#                     cats = []
#                 for cat in cats:
#                     cat_dict.setdefault(cat, 0)
#                     cat_dict[cat] += 1
#             for cat, count in cat_dict.items():
#                 print(f"{label} - Category '{cat}': {count} posts.")
#         log_posts_by_category(ai_filtered, "AI posts (filtered)")
#         log_posts_by_category(human_filtered, "Human posts (filtered)")
#         log_posts_by_category(reposts_filtered, "Reposts (filtered)")

#         def separate_text_video(posts):
#             text_posts = [p for p in posts if not p.get("post", {}).get("video_content")]
#             video_posts = [p for p in posts if p.get("post", {}).get("video_content")]
#             return text_posts, video_posts

#         ai_text, ai_video = separate_text_video(ai_filtered)
#         human_text, human_video = separate_text_video(human_filtered)

#         def parse_date(date_str):
#             try:
#                 return datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
#             except Exception:
#                 return datetime.min

#         def sort_posts(posts):
#             return sorted(posts, key=lambda x: parse_date(x.get('date_posted', '')), reverse=True)

#         ai_text = sort_posts(ai_text)
#         ai_video = sort_posts(ai_video)
#         human_text = sort_posts(human_text)
#         human_video = sort_posts(human_video)
#         reposts_filtered = sort_posts(reposts_filtered)

#         for post in ai_text:
#             post['post_type'] = 'ai_post'
#         for post in ai_video:
#             post['post_type'] = 'ai_post'
#         for post in human_text:
#             post['post_type'] = 'human_post'
#         for post in human_video:
#             post['post_type'] = 'human_post'
#         for post in reposts_filtered:
#             post['post_type'] = 'repost'

#         combined_posts = ai_text + ai_video + human_text + human_video + reposts_filtered

#         unique_posts = []
#         seen_ids = set()
#         for post in combined_posts:
#             post_id = post.get('id')
#             if post_id and post_id not in seen_ids:
#                 unique_posts.append(post)
#                 seen_ids.add(post_id)
#         print(f"After deduplication, found {len(unique_posts)} unique posts.")

#         # If we don't have enough posts, try to fetch additional posts using similar categories
#         if len(unique_posts) < posts_per_page:
#             missing = posts_per_page - len(unique_posts)
#             print(f"Final feed has {len(unique_posts)} unique posts; need {missing} more.")
#             additional_cats = compute_similar_categories(preferred, all_categories)
#             print(f"Additional similar categories computed: {additional_cats}")
#             similar_categories = list(set(preferred).union(additional_cats))

#             additional_ai = filter_posts(ai_posts_all, similar_categories)
#             additional_human = filter_posts(human_posts_all, similar_categories)
#             additional_reposts = filter_posts(reposts_all, similar_categories)

#             additional_ai = sort_posts(additional_ai)
#             additional_human = sort_posts(additional_human)
#             additional_reposts = sort_posts(additional_reposts)

#             for post in additional_ai:
#                 post['post_type'] = 'ai_post'
#             for post in additional_human:
#                 post['post_type'] = 'human_post'
#             for post in additional_reposts:
#                 post['post_type'] = 'repost'

#             additional_posts = additional_ai + additional_human + additional_reposts
#             for post in additional_posts:
#                 post_id = post.get('id')
#                 if post_id and post_id not in seen_ids:
#                     unique_posts.append(post)
#                     seen_ids.add(post_id)
#                     if len(unique_posts) >= posts_per_page:
#                         break

#         unique_posts = sort_posts(unique_posts)
#         print(f"Total unique posts after filling: {len(unique_posts)}")

#         # Global pagination: slice the deduplicated, sorted list
#         random.shuffle(unique_posts)
#         offset = (page - 1) * posts_per_page
#         final_feed = unique_posts[offset:offset + posts_per_page]
#         print(f"Final feed has {len(final_feed)} posts for page {page}.")
        
#         def log_final_counts(posts):
#             cat_dict = {}
#             for post in posts:
#                 cats = post.get("category", [])
#                 if isinstance(cats, str):
#                     cats = [cats.lower()]
#                 elif isinstance(cats, list):
#                     cats = [cat.lower() for cat in cats if isinstance(cat, str)]
#                 for cat in cats:
#                     cat_dict[cat] = cat_dict.get(cat, 0) + 1
#             for cat, count in cat_dict.items():
#                 print(f"Final feed - Category '{cat}': {count} posts.")
#         log_final_counts(final_feed)

#         return jsonify({'posts': final_feed}), 200
#     except Exception as ex:
#         logger.error("Error getting posts flow: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/posts-flow', methods=['GET'])
def posts_flow():
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        posts_per_page = 30

        print(f"Processing posts flow for user {user_id}, page {page}")

        user_doc = db.collection('humanUsers').document(user_id).get()

        # Helper Functions
        def parse_date(date_str):
            try:
                naive_dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
                return naive_dt.replace(tzinfo=timezone.utc)
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)

        def compute_freshness_score(post_date):
            now = datetime.now(timezone.utc)
            seconds_since = (now - post_date).total_seconds()
            return 1 / math.log(seconds_since + 2)

        def compute_engagement_score(post):
            return float(post.get("engagement_score", 0.5))

        def compute_media_score(post):
            if post.get("has_video"):
                return 1.0 if post.get("post_type") == "human_post" else 0.9
            elif post.get("has_image"):
                return 0.8 if post.get("post_type") == "human_post" else 0.7
            else:
                return 0.6 if post.get("post_type") == "human_post" else 0.5

        def compute_human_score(post):
            return 1.0 if post.get("post_type") in ["human_post", "repost"] else 0.8

        def compute_repost_adjustment(post):
            if post.get("post_type") == "repost":
                return 0.8
            return 0.0

        def compute_final_score(post):
            date_str = post.get('date_posted', '')
            post_date = parse_date(date_str)
            freshness = compute_freshness_score(post_date)
            engagement = compute_engagement_score(post)
            media = compute_media_score(post)
            human = compute_human_score(post)
            repost_adj = compute_repost_adjustment(post)

            # Base score calculation
            if post.get("has_video"):
                base_score = (0.35 * freshness +
                         0.30 * engagement +
                         0.15 * media +
                         0.10 * human +
                         0.10 * repost_adj)
            else:
                base_score = (0.20 * freshness +
                         0.20 * engagement +
                         0.10 * media +
                         0.15 * human +
                         0.35 * repost_adj)

            # Apply penalties and boosts
            human_boost = 0.07 if post.get("post_type") == "human_post" else 0.0
            repost_boost = 0.2 if post.get("post_type") == "repost" else 0.0
            text_boost = 0.19 if not post.get("has_video") and not post.get("has_image") else 0.0

            final_score = base_score + human_boost + repost_boost + text_boost
            return final_score

        # Fetch and Filter Posts
        def fetch_posts(collection_name, filters=None):
            query = db.collection(collection_name)
            
            if filters:
                for field, value in filters.items():
                    query = query.where(field, '==', value)

            return [doc.to_dict() for doc in query.stream()]

        ai_posts_all = fetch_posts('aiPosts')
        human_posts_all = fetch_posts('humanPosts')
        reposts_all = fetch_posts('reposts')

        print(f"Total posts fetched - AI: {len(ai_posts_all)}, Human: {len(human_posts_all)}, Reposts: {len(reposts_all)}")

        # Separate Posts by Type
        def separate_posts(posts):
            text_posts = [p for p in posts if not p.get("has_video") and not p.get("has_image")]
            video_posts = [p for p in posts if p.get("has_video")]
            image_posts = [p for p in posts if p.get("has_image")]
            return text_posts, video_posts, image_posts

        ai_text, ai_video, ai_image = separate_posts(ai_posts_all)
        human_text, human_video, human_image = separate_posts(human_posts_all)

        print(f"Separated posts - AI: Text={len(ai_text)}, Video={len(ai_video)}, Image={len(ai_image)}")
        print(f"Separated posts - Human: Text={len(human_text)}, Video={len(human_video)}, Image={len(human_image)}")

        # Assign Post Types
        for post in ai_text + ai_video + ai_image:
            post['post_type'] = 'ai_post'
        for post in human_text + human_video + human_image:
            post['post_type'] = 'human_post'
        for post in reposts_all:
            post['post_type'] = 'repost'

        # Combine all posts
        all_posts = human_posts_all + reposts_all + ai_posts_all

        # Compute scores for all posts
        for post in all_posts:
            post['final_score'] = compute_final_score(post)

        # Sort Posts by Final Score
        sorted_posts = sorted(all_posts, key=lambda x: x['final_score'], reverse=True)
        print(f"Posts after sorting: {len(sorted_posts)}")

        # Deduplication
        seen_ids = set()
        unique_posts = []
        for post in sorted_posts:
            post_id = post.get('id')
            if post_id and post_id not in seen_ids:
                unique_posts.append(post)
                seen_ids.add(post_id)
        print(f"Unique posts after deduplication: {len(unique_posts)}")

        # Pagination - no random shuffle to maintain consistent ordering
        offset = (page - 1) * posts_per_page
        final_feed = unique_posts[offset:offset + posts_per_page]
        
        # Count post types in final feed
        post_types = {'ai_post': 0, 'human_post': 0, 'repost': 0}
        media_types = {'text': 0, 'video': 0, 'image': 0}
        for post in final_feed:
            post_types[post.get('post_type', 'unknown')] += 1
            if post.get('has_video'):
                media_types['video'] += 1
            elif post.get('has_image'):
                media_types['image'] += 1
            else:
                media_types['text'] += 1
        
        print(f"Final feed composition:")
        print(f"Post types: {post_types}")
        print(f"Media types: {media_types}")
        print(f"Total posts in feed: {len(final_feed)}")
        print(f"Showing posts {offset + 1} to {offset + len(final_feed)} of {len(unique_posts)} total unique posts")

        return jsonify({'posts': final_feed}), 200

    except Exception as ex:
        print(f"Error generating posts flow: {ex}")
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/test-feed-quality', methods=['GET'])
def test_feed_quality():
    try:
        user_id = request.args.get('user_id')
        page = request.args.get('page', default=1, type=int)
        pages_to_test = request.args.get('pages', default=10, type=int)
        
        all_posts = []
        issues = {
            "repeating_posts": [],
            "consecutive_user_posts": [],
            "cross_page_duplicates": []
        }
        
        # Collect posts from multiple pages
        for p in range(page, page + pages_to_test):
            response = requests.get(f"http://127.0.0.1:8080/feed/posts-flow?user_id={user_id}&page={p}")
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    print(f"Response data type: {type(response_data)}")
                    print(f"Response data: {response_data}")
                    
                    if isinstance(response_data, list):
                        return jsonify({
                            "error": "Unexpected list response from posts-flow endpoint",
                            "details": response_data
                        }), 500
                    
                    page_posts = response_data.get('posts', [])
                    if not isinstance(page_posts, list):
                        return jsonify({
                            "error": "Posts data is not a list",
                            "details": page_posts
                        }), 500
                    
                    print(f"Collected {len(page_posts)} posts from page {p}")
                    all_posts.extend(page_posts)
                except ValueError as e:
                    return jsonify({"error": f"Invalid JSON response: {str(e)}"}), 500
            else:
                return jsonify({"error": f"Failed to fetch page {p}"}), 500
        
        # Test for repeating posts
        seen_ids = set()
        seen_videos = set()
        
        for post in all_posts:
            if not isinstance(post, dict):
                continue
            
            post_id = post.get('id')
            username = post.get('user_name', 'unknown')
            
            # Check for repeating posts by ID
            if post_id:
                if post_id in seen_ids:
                    issues["repeating_posts"].append({
                        "type": "repeating_post_id",
                        "post_id": post_id,
                        "username": username
                    })
                seen_ids.add(post_id)
            
            video_content = post.get('post', {}).get('video_content', [])
            video_url = None
            if isinstance(video_content, list):
                # Use the first URL in the list if available
                video_url = video_content[0] if video_content else None
            elif isinstance(video_content, dict):
                video_url = video_content.get('url')
            
            if video_url:
                if video_url in seen_videos:
                    issues["repeating_posts"].append({
                        "type": "repeating_video",
                        "video_url": video_url,
                        "username": username
                    })
                seen_videos.add(video_url)
        
        # Test for consecutive posts by the same user
        for i in range(1, len(all_posts)):
            if not isinstance(all_posts[i], dict) or not isinstance(all_posts[i - 1], dict):
                continue
            current_username = all_posts[i].get('user_name')
            prev_username = all_posts[i - 1].get('user_name')
            
            if current_username and current_username == prev_username:
                issues["consecutive_user_posts"].append({
                    "username": current_username,
                    "post_ids": [all_posts[i - 1].get('id'), all_posts[i].get('id')]
                })

        # Test for cross-page duplicates
        posts_by_page = {}
        for p in range(page, page + pages_to_test):
            page_posts = all_posts[(p-page)*30:(p-page+1)*30]  # Get posts for this page
            posts_by_page[p] = page_posts

        # Compare each page with all other pages
        for page1 in range(page, page + pages_to_test):
            for page2 in range(page1 + 1, page + pages_to_test):
                page1_posts = posts_by_page[page1]
                page2_posts = posts_by_page[page2]
                
                for post1 in page1_posts:
                    if not isinstance(post1, dict):
                        continue
                    post1_id = post1.get('id')
                    if not post1_id:
                        continue
                        
                    for post2 in page2_posts:
                        if not isinstance(post2, dict):
                            continue
                        post2_id = post2.get('id')
                        if not post2_id:
                            continue
                            
                        if post1_id == post2_id:
                            issues["cross_page_duplicates"].append({
                                "post_id": post1_id,
                                "username": post1.get('user_name', 'unknown'),
                                "duplicate_pages": [page1, page2]
                            })
        
        # Collect statistics about the feed quality
        stats = {
            "total_posts_analyzed": len(all_posts),
            "unique_posts": len(seen_ids),
            "unique_videos": len(seen_videos),
            "unique_users": len(set(post.get('user_name') for post in all_posts if isinstance(post, dict) and post.get('user_name'))),
            "pages_analyzed": pages_to_test,
            "repeating_posts_count": len(issues["repeating_posts"]),
            "consecutive_user_posts_count": len(issues["consecutive_user_posts"]),
            "cross_page_duplicates_count": len(issues["cross_page_duplicates"])
        }
        
        print(f"Feed quality test results: {stats}")
        if issues["repeating_posts"]:
            print(f"Found {len(issues['repeating_posts'])} repeating posts")
        if issues["consecutive_user_posts"]:
            print(f"Found {len(issues['consecutive_user_posts'])} instances of consecutive posts by the same user")
        if issues["cross_page_duplicates"]:
            print(f"Found {len(issues['cross_page_duplicates'])} posts that appear on multiple pages")
            for dup in issues["cross_page_duplicates"]:
                print(f"Post {dup['post_id']} by {dup['username']} appears on pages {dup['duplicate_pages']}")
        
        return jsonify({
            "stats": stats,
            "issues": issues
        }), 200
    except Exception as ex:
        logger.error("Error testing feed quality: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/update-post', methods=['POST'])
def update_post():
    try:
        data = request.get_json()
        post_id = data.get("PostId")

        if not post_id:
            return jsonify({"success": False, "error": "PostId is required", "code": "INVALID_POST_ID"}), 400

        update_data = {
            "content": data.get("Content"),
            "imageUrl": data.get("ImageUrl"),
            "updatedAt": firestore.SERVER_TIMESTAMP
        }

        collections = ['aiPosts', 'humanPosts', 'reposts']
        post_found = False

        for collection in collections:
            post_ref = db.collection(collection).document(post_id)
            post_doc = post_ref.get()

            if post_doc.exists:
                post_ref.update(update_data)
                post_found = True
                break

        if not post_found:
            return jsonify({"success": False, "error": "Post not found", "code": "POST_NOT_FOUND"}), 404

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_UPDATE_ERROR"}), 500

@app.route('/feed/write-comment', methods=['POST'])
def write_comment():
    try:
        data = request.get_json()
        comment_data = {
            "postId": data.get("PostId"),
            "userId": data.get("UserId"),
            "content": data.get("Content"),
            "createdAt": firestore.SERVER_TIMESTAMP
        }

        doc_ref = db.collection('postComments').add(comment_data)
        return jsonify({"commentId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error writing comment: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/get-user-posts', methods=['POST'])
def get_user_posts():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        # Retrieve user posts from all collections
        collections = ['humanPosts', 'reposts']
        posts = []

        for collection in collections:
            query = db.collection(collection).where("user_document_id", "==", user_id).limit(25)
            snapshot = query.stream()
            posts.extend([doc.to_dict() for doc in snapshot])


        posts.sort(key=lambda x: x['date_posted'], reverse=True)

        return jsonify(posts[:25]), 200
    except Exception as ex:
        logger.error("Error getting user posts: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/feed/get-ai-posts', methods=['POST'])
def get_ai_posts():
    try:
        data = request.get_json()
        username = data.get("UserName")

        # Retrieve user posts from all collections
        collection = 'aiPosts'
        posts = []

        query = db.collection(collection).where("user_name", "==", username).limit(25)
        snapshot = query.stream()
        posts.extend([doc.to_dict() for doc in snapshot])

        posts.sort(key=lambda x: x['date_posted'], reverse=True)

        return jsonify(posts[:25]), 200
    except Exception as ex:
        logger.error("Error getting user posts: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

# --------------------------
# AI Controller
# --------------------------

def generate_ai_response(message, ai_character_id):
    try:
        ai_character = None
        if ai_character_id:
            doc_ref = db.collection("aiCharacters").document(ai_character_id)
            snapshot = doc_ref.get()
            if not snapshot.exists:
                raise ApiException("AI character not found", "AI_CHARACTER_NOT_FOUND")
            ai_character = snapshot.to_dict()

        response = client.completions.create(
            engine="text-davinci-003",
            prompt=f"{ai_character['Personality']} AI: {message}",
            max_tokens=150
        )

        return response.choices[0].text.strip()
    except Exception as ex:
        logger.error("Error generating AI response: %s", ex)
        raise ApiException("Failed to generate AI response", "AI_GENERATION_ERROR")

@app.route('/api/ai/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        response = generate_ai_response(data.get("Message"), data.get("AICharacterId"))

        chat_response = {
            "Message": response,
            "ConversationId": str(uuid.uuid4())
        }

        return jsonify({"success": True, "data": chat_response}), 200
    except ApiException as ex:
        return jsonify({"success": False, "error": ex.args[0], "code": ex.error_code}), ex.status_code
    except Exception as ex:
        logger.error("Error in chat: %s", ex)
        return jsonify({"success": False, "error": "Failed to process chat", "code": "CHAT_ERROR"}), 500

@app.route('/api/ai/upvote', methods=['POST'])
def upvote():
    try:
        name = request.json.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        if 'upvotes' in data:
            character_ref.update({'upvotes': firestore.Increment(1)})
        else:
            character_ref.update({'upvotes': 1})

        return jsonify({"success": True, "message": "Upvote successful."}), 200
    except Exception as ex:
        logger.error("Error upvoting: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/downvote', methods=['POST'])
def downvote():
    try:
        name = request.json.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        if 'downvotes' in data:
            character_ref.update({'downvotes': firestore.Increment(1)})
        else:
            character_ref.update({'downvotes': 1})

        return jsonify({"success": True, "message": "Downvote successful."}), 200
    except Exception as ex:
        logger.error("Error downvoting: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/chat-counter', methods=['GET'])
def chat_counter():
    try:
        name = request.args.get('Name')
        if not name:
            return jsonify({"success": False, "error": "Popular character's name is required"}), 400

        character_ref = db.collection('popularCharacters').document(name)
        character_doc = character_ref.get()

        if not character_doc.exists:
            return jsonify({"success": False, "error": "Character not found"}), 404

        data = character_doc.to_dict()
        return jsonify({"success": True, "numberOfChats": data.get('numberOfChats', 0)}), 200
    except Exception as ex:
        logger.error("Error retrieving numberOfChats: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/create-ai-user', methods=['POST'])
def create_ai_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "AI User data is required", "code": "INVALID_AI_USER_DATA"}), 400

        username = data.get("Username")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "MISSING_USERNAME"}), 400

        # Check if a user with the same username already exists
        existing_users = db.collection('aiUsers').where("username", "==", username).stream()
        if any(existing_users):
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

        doc_ref = db.collection('aiUsers').document(username).set(character_data)

        return jsonify({"AiUserId": username}), 200
        # return jsonify({"AiUserId": data.get("username")}), 200
        # return jsonify({"AiUserId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating AI User: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "CHARACTER_CREATE_ERROR"}), 500

@app.route('/api/ai/update-ai-user', methods=['POST'])
def update_ai_profile():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        update_data = {
            "name": data.get("Name"),
            "bio": data.get("Bio"),
            "username": data.get("UserName")
        }

        # Update the document in Firestore
        db.collection('aiUsers').document(data.get("username")).update(update_data)
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-ai-user', methods=['GET'])
def get_ai_profile():
    try:
        username = request.args.get('username')
        if not username:
            return jsonify({"success": False, "error": "Username is required"}), 400

        user_doc = db.collection('aiUsers').document(username).get()

        if not user_doc.exists:
            return jsonify({"success": False, "error": "User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"success": True, "data": user_data}), 200
    except Exception as ex:
        logger.error("Error retrieving profile: %s", ex)
        return jsonify({"success": False, "error": "Failed to retrieve profile", "code": "PROFILE_RETRIEVE_ERROR"}), 500

@app.route('/api/ai/carousel/characters', methods=['GET'])
def get_carousel_characters():
    try:
        # Retrieve all characters from the 'popularCharacters' collection
        characters_ref = db.collection('popularCharacters')
        snapshot = characters_ref.stream()

        # Convert all documents to dictionaries
        all_characters = []
        for doc in snapshot:
            character = doc.to_dict()
            all_characters.append(character)

        # Get 20 random characters
        num_characters_to_show = 20
        
        # If we have fewer than 20 characters, return all of them
        if len(all_characters) <= num_characters_to_show:
            selected_characters = all_characters
        else:
            # Shuffle the characters and select 20 random ones
            random.shuffle(all_characters)
            selected_characters = all_characters[:num_characters_to_show]

        return jsonify(selected_characters), 200

    except Exception as ex:
        logger.error("Error retrieving carousel characters: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/follow', methods=['POST'])
def follow_ai_user():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated AI user)
        following_id = data.get("FollowingId")  # B (AI user to follow)

        follower_ref = db.collection('aiUsers').document(follower_id)
        following_ref = db.collection('aiUsers').document(following_id)

        follower_doc = follower_ref.get()
        following_doc = following_ref.get()

        if not follower_doc.exists or not following_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        follower_data = follower_doc.to_dict()
        if following_id not in follower_data.get("following", []):
            follower_data["following"].append(following_id)
            follower_ref.update({"following": follower_data["following"], "following_count": firestore.Increment(1)})

        following_data = following_doc.to_dict()
        if follower_id not in following_data.get("followers", []):
            following_data["followers"].append(follower_id)
            following_ref.update({"followers": following_data["followers"], "followers_count": firestore.Increment(1)})

        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error adding AI follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/unfollow', methods=['POST'])
def unfollow_ai_user():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")
        following_id = data.get("FollowingId")

        follower_ref = db.collection('aiUsers').document(follower_id)
        following_ref = db.collection('aiUsers').document(following_id)

        follower_ref.update({"following": firestore.ArrayRemove([following_id]), "following_count": firestore.Increment(-1)})
        following_ref.update({"followers": firestore.ArrayRemove([follower_id]), "followers_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-followers', methods=['POST'])
def get_ai_followers():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        user_doc = db.collection('aiUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"followers": user_data.get("followers", [])}), 200
    except Exception as ex:
        logger.error("Error getting AI followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/get-following', methods=['POST'])
def get_ai_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")

        user_doc = db.collection('aiUsers').document(user_id).get()
        if not user_doc.exists:
            return jsonify({"success": False, "error": "AI User not found"}), 404

        user_data = user_doc.to_dict()
        return jsonify({"following": user_data.get("following", [])}), 200
    except Exception as ex:
        logger.error("Error getting AI following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/remove-from-followers', methods=['POST'])
def remove_ai_follower():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        follower_id = data.get("FollowerId")

        user_ref = db.collection('aiUsers').document(user_id)
        follower_ref = db.collection('aiUsers').document(follower_id)

        user_ref.update({"followers": firestore.ArrayRemove([follower_id]), "followers_count": firestore.Increment(-1)})
        follower_ref.update({"following": firestore.ArrayRemove([user_id]), "following_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI follower: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/remove-from-following', methods=['POST'])
def remove_ai_following():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        following_id = data.get("FollowingId")

        user_ref = db.collection('aiUsers').document(user_id)
        following_ref = db.collection('aiUsers').document(following_id)

        user_ref.update({"following": firestore.ArrayRemove([following_id]), "following_count": firestore.Increment(-1)})
        following_ref.update({"followers": firestore.ArrayRemove([user_id]), "followers_count": firestore.Increment(-1)})
        
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing AI following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@app.route('/api/ai/generate-image', methods=['POST'])
def generate_image():
    try:
        # Add image generation logic here
        image_url = f"https://storage.googleapis.com/inzonebackend.appspot.com/generated-images/{uuid.uuid4().hex}.png"


        return jsonify({"success": True, "data": {"ImageUrl": image_url}}), 200
    except ApiException as ex:
        return jsonify({"success": False, "error": ex.args[0], "code": ex.error_code}), ex.status_code
    except Exception as ex:
        logger.error("Error generating image: %s", ex)
        return jsonify({"success": False, "error": "Failed to generate image", "code": "IMAGE_GENERATION_ERROR"}), 500


# ---------------------------
# AI Content Controller
# ---------------------------

class AIContentGenerationService:
    def generate_ai_post(self, ai_user_id):
        # Mock implementation of AI post generation
        return {
            "Category": "Tech",
            "MainCategory": "AI",
            "SubCategory": "Machine Learning",
            "Comments": [],
            "DatePosted": firestore.SERVER_TIMESTAMP,
            "Likes": 0,
            "Post": {
                "ImageContent": [],
                "TextContent": "This is a generated AI post.",
                "VideoContent": []
            },
            "UserName": ai_user_id,
            "UserReferences": f"aiUsers/{ai_user_id}/"
        }

content_service = AIContentGenerationService()

@app.route('/ai-content/generate-post', methods=['POST'])
def generate_post():
    try:
        ai_user_id = request.get_json()
        post = content_service.generate_ai_post(ai_user_id)

        # Save the generated post
        post_data = {
            "category": post["Category"],
            "main_category": post["MainCategory"],
            "sub_category": post["SubCategory"],
            "comments": post["Comments"],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": post["Likes"],
            "post": {
                "image_content": post["Post"]["ImageContent"],
                "textContent": post["Post"]["TextContent"],
                "video_content": post["Post"]["VideoContent"]
            },
            "username": post["UserName"],
            "user_references": post["UserReferences"]
        }

        doc_ref = db.collection('posts').add(post_data)
        post_id = doc_ref[1].id


        return jsonify({"success": True, "data": {**post, "Id": post_id}}), 200
    except Exception as ex:
        logger.error("Error generating AI post: %s", ex)
        return jsonify({"success": False, "error": "Failed to generate post", "code": "POST_GENERATION_ERROR"}), 500

# ---------------------------
# Group Chat
# ---------------------------
# modifying profile picture
# modifying groupchat name
# return number people in groupchat

@app.route('/group/add-participant', methods=['POST'])
def add_participant():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    user_id = data.get('user_id')
    username = data.get('username')
    
    if not all([groupchat_id, user_id, username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupchats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if user_id in groupchat_data['user_ids']:
        return jsonify({"error": "User already in the group chat"}), 400
    
    groupchat_ref.update({
        'user_ids': firestore.ArrayUnion([user_id]),
        'usernames': firestore.ArrayUnion([username])
    })
    
    return jsonify({"message": "Participant added successfully"}), 200

@app.route('/group/delete-participant', methods=['POST'])
def delete_participant():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    user_id = data.get('user_id')
    username = data.get('username')
    
    if not all([groupchat_id, user_id, username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupchats').document(groupchat_id)
    groupchat = gsroupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if user_id not in groupchat_data['user_ids']:
        return jsonify({"error": "User not in the group chat"}), 400
    
    groupchat_ref.update({
        'user_ids': firestore.ArrayRemove([user_id]),
        'usernames': firestore.ArrayRemove([username])
    })
    
    return jsonify({"message": "Participant removed successfully"}), 200

@app.route('/group/create-groupchat', methods=['POST'])
def create_group_chat():
    data = request.json
    groupchat_name = data.get('groupchat_name')
    bio = data.get('bio')
    creator_id = data.get('creator_id')
    creator_username = data.get('creator_username')
    
    if not all([groupchat_name, creator_id, creator_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    new_groupchat = {
        'groupchat_name': groupchat_name,
        'bio': bio,
        'user_ids': [creator_id],
        'usernames': [creator_username],
        'ai_usernames': [],
        'messages': [],
        'date_created': firestore.SERVER_TIMESTAMP,
        'groupchat_doc_id': data.get("GroupchatDocId")
    }
    
    doc_ref = db.collection('groupchats').document(data.get("GroupchatDocId")).set(post_data)    
    return jsonify({
        "message": "Group chat created successfully",
        "groupchat_id": doc_ref[1].id
    }), 201

@app.route('/group/add-ai-character', methods=['POST'])
def add_ai_character():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    ai_username = data.get('ai_username')
    
    if not all([groupchat_id, ai_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupchats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_ref.update({
        'ai_usernames': firestore.ArrayUnion([ai_username])
    })
    
    return jsonify({"message": "AI character added successfully"}), 200

@app.route('/group/delete-ai-character', methods=['POST'])
def delete_ai_character():
    data = request.json
    groupchat_id = data.get('groupchat_id')
    ai_username = data.get('ai_username')
    
    if not all([groupchat_id, ai_username]):
        return jsonify({"error": "Missing required fields"}), 400
    
    groupchat_ref = db.collection('groupchats').document(groupchat_id)
    groupchat = groupchat_ref.get()
    
    if not groupchat.exists:
        return jsonify({"error": "Group chat not found"}), 404
    
    groupchat_data = groupchat.to_dict()
    if ai_username not in groupchat_data['ai_usernames']:
        return jsonify({"error": "AI character not in the group chat"}), 400
    
    groupchat_ref.update({
        'ai_usernames': firestore.ArrayRemove([ai_username])
    })
    
    return jsonify({"message": "AI character removed successfully"}), 200

# ---------------------------
# Premium Group Chat Access Endpoints (Subscription Model using InCash)
# ---------------------------
@app.route('/groups/available', methods=['GET'])
def available_groups():
    groups = [doc.to_dict() for doc in db.collection('groups').stream()]
    return jsonify({'groups': groups})

@app.route('/groups/join', methods=['POST'])
def join_group():
    data = request.json
    user_id = data['user_id']
    group_id = data['group_id']
    # The subscription tier: expected values are "free", "pass", or "vip"
    tier = data.get('tier', 'free').lower()

    group_ref = db.collection('groups').document(group_id)
    group = group_ref.get().to_dict()
    user_ref = db.collection('humanUsers').document(user_id)
    user_data = user_ref.get().to_dict()

    if not group:
        return jsonify({'error': 'Group not found'}), 404

    # Determine pricing and duration based on the tier.
    # The group document should contain pricing and duration info for each tier.
    if tier == 'free':
        price = 0
        duration = group.get('free_duration')  # For example, could be None (or indefinite) or set to a default period
    elif tier == 'pass':
        price = group.get('pass_price', 0)
        duration = group.get('pass_duration', 1)  # Default to 1 day if not provided
    elif tier == 'vip':
        price = group.get('vip_price', 0)
        duration = group.get('vip_duration', 30)  # Default to 30 days if not provided
    else:
        return jsonify({'error': 'Invalid tier specified'}), 400
    
    # For tiers with a price, ensure the user has sufficient funds.
    if price > 0 and user_data.get('balance', 0) < price:
        return jsonify({'error': 'Insufficient funds'}), 400

    # Deduct funds if necessary.
    if price > 0:
        user_ref.update({'balance': firestore.Increment(-price)})
    
    # Add the group to the user's groups array in the humanUsers document.
    user_ref.update({'groups': firestore.ArrayUnion([group_id])})
    
    # Calculate the subscription end time if a duration is provided.
    if duration:
        subscription_end = datetime.utcnow() + timedelta(days=duration)
        subscription_end_iso = subscription_end.isoformat()
    else:
        subscription_end_iso = None

    membership_data = {
        'group_id': group_id,
        'tier': tier,
        'subscription_end': subscription_end_iso,
        'joined_at': datetime.utcnow().isoformat()
    }
    
    # Save the group subscription in a subcollection under humanUsers.
    db.collection('humanUsers').document(user_id).collection('groups').document(group_id).set(membership_data)
    
    return jsonify({
        'message': 'Group joined successfully',
        'tier': tier,
        'subscription_end': subscription_end_iso
    })

@app.route('/groups/user-access', methods=['GET'])
def user_access():
    user_id = request.args.get('user_id')
    groups = [doc.to_dict() for doc in db.collection('humanUsers').document(user_id).collection('groups').stream()]
    return jsonify({'groups': groups})

# ---------------------------
# Admin Endpoints
# ---------------------------

@app.route('/admin/store/add-item', methods=['POST'])
def add_item():
    data = request.json
    db.collection('store_items').document(data['id']).set(data)
    return jsonify({'message': 'Item added successfully'})

@app.route('/admin/groups/create', methods=['POST'])
def create_group():
    data = request.json
    db.collection('groups').document(data['id']).set(data)
    return jsonify({'message': 'Group created successfully'})

if __name__ == '__main__':
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/key.json"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
