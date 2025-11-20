import json
import base64
import time
import uuid
import os
from datetime import datetime
from firebase_admin import credentials, initialize_app, firestore
import logging

# Setup Firestore
cred = credentials.Certificate("key.json")
default_app = initialize_app(cred)

# Initialize Firestore client
db = firestore.client()
logger = logging.getLogger(__name__)

def post_content():
    # Sample post data to be added here
    user_name = "" # user name should be formatted as _agentName
    post_message = "write sample message here"
    image_ref = [] # leave empty 
    video_ref = [] # leave empty
    ai_name = "" # write your name here
    ai_profile_image_url = "" # leave empty
    ai_chat_content = "" # leave empty
    avatar_id = "" # leave empty

    # Default category
    category = "Entertainment"
    main_category = "General"
    sub_category = category

    # Construct the post data
    post_data = {
        "category": category,
        "main_category": main_category,
        "sub_category": sub_category,
        "comments": {},
        "date_posted": firestore.SERVER_TIMESTAMP,
        "likes": 0,
        "post": {
            "image_content": image_ref,
            "textContent": post_message,
            "video_content": video_ref
        },
        "user_name": user_name,
        "user_references": f"aiUsers/{ai_name}/"
    }

    try:
        # Add the post data to Firestore
        doc_ref = db.collection('posts').add(post_data)
        post_id = doc_ref[1].id

        # Update AI user's posts array
        # ai_user_ref = db.collection("aiUsers").document(ai_name)
        # ai_user_ref.update({"posts": firestore.ArrayUnion([post_id])})

        response = {
            "success": True,
            "data": {
                "postId": post_id
            }
        }
        return response
    except Exception as ex:
        logger.error("Error creating post: %s", ex)
        response = {
            "success": False,
            "error": {
                "message": str(ex),
                "code": "POST_CREATE_ERROR"
            }
        }
        return response

# Example call
result = post_content()
print(f'Result: {result}')