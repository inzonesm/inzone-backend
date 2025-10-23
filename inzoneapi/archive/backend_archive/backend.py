from firebase_admin import firestore
import logging
from datetime import datetime, timedelta
import random
import uuid
import os
from openai import OpenAI
from flask import Blueprint, request, jsonify, current_app

backend_bp = Blueprint("backend", __name__)
logger = logging.getLogger(__name__)
db = firestore.client()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

##############################################################################################################
# InZone Backend
# - Unknown error: 500
# - Specific error: 400
# - Success: 200
##############################################################################################################

# API Controller
@backend_bp.route("/sentiment-analysis", methods=["POST"])
def analyze_sentiment():
    try:
        content = request.get_json()
        sentiment = {
            "PositiveScore": 0.8,
            "NegativeScore": 0.1,
            "NeutralScore": 0.1,
            "OverallSentiment": "positive",
            "Categories": ["general", "social"],
            "Keywords": ["test", "message"]
        }
        return jsonify({"success": True, "data": sentiment}), 200
    except Exception as ex:
        logger.error("Error analyzing sentiment: %s", ex)
        return jsonify({"success": False, "error": "Failed to analyze sentiment"}), 500

@backend_bp.route("/main-ai-chat", methods=["POST"])
def main_ai_chat():
    try:
        message = request.get_json()
        chat_data = {"message": message, "timestamp": firestore.SERVER_TIMESTAMP}
        db.collection('chats').add(chat_data)
        response = "This is a test AI response"
        return jsonify({"success": True, "data": {"response": response}}), 200
    except Exception as ex:
        logger.error("Error in main AI chat: %s", ex)
        return jsonify({"success": False, "error": "Failed to process chat"}), 500

@backend_bp.route("/add-user", methods=["POST"])
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
        return jsonify({"success": False, "error": "Failed to add user"}), 500

@backend_bp.route("/get-all-ai-profiles", methods=["POST"])
def get_all_ai_profiles():
    try:
        query = db.collection('ai_characters')
        snapshot = query.stream()
        profiles = [doc.to_dict() for doc in snapshot]
        return jsonify({"success": True, "data": profiles}), 200
    except Exception as ex:
        logger.error("Error getting AI profiles: %s", ex)
        return jsonify({"success": False, "error": "Failed to get AI profiles"}), 500

@backend_bp.route('/api/create-ai-profile', methods=['POST'])
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
        return jsonify({"success": False, "error": "Failed to create AI profile", "code": "PROFILE_CREATE_ERROR"}), 500


@backend_bp.route('/api/get-avatars', methods=['GET'])
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


# User Controller
@backend_bp.route('/user/create-profile', methods=['POST'])
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
            "anonymous": anonymous,
            "followers": [],
            "following": [],
            "gender": data.get("Gender"),
            "profile_picture": data.get("ProfilePicture"),
            "date_created": firestore.SERVER_TIMESTAMP,
            "uid": data.get("UID"),
            "user_name": data.get("UserName")
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


@backend_bp.route('/user/update-profile', methods=['POST'])
def update_profile():
    try:
        data = request.get_json()
        user_id = data.get("UserId")
        update_data = {
            "username": data.get("Username"),
            "bio": data.get("Bio"),
            "profilePicture": data.get("ProfilePicture")
        }


        # Update the document in Firestore
        db.collection('humanUsers').document(user_id).update(update_data)
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error updating profile: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/get-profile', methods=['GET'])
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


@backend_bp.route('/user/follow', methods=['POST'])
def follow():
    try:
        data = request.get_json()
        follow_data = {
            "followerId": data.get("FollowerId"),
            "followingId": data.get("FollowingId"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }


        db.collection('followers').add(follow_data)
        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error adding follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/unfollow', methods=['POST'])
def unfollow():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")
        following_id = data.get("FollowingId")


        followers_ref = db.collection('followers')
        query = followers_ref.where('followerId', '==', follower_id).where('followingId', '==', following_id)
        docs = query.stream()


        for doc in docs:
            doc.reference.delete()


        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error removing follow relationship: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/get-followers', methods=['POST'])
def get_followers():
    try:
        user_id = request.get_json()
        query = db.collection('followers').where('followingId', '==', user_id)
        snapshot = query.stream()
        follower_ids = [doc.get('followerId') for doc in snapshot]


        # Get user details for each follower
        followers = []
        for follower_id in follower_ids:
            user_doc = db.collection('humanUsers').document(follower_id).get()
            if user_doc.exists:
                followers.append(user_doc.to_dict())


        return jsonify(followers), 200
    except Exception as ex:
        logger.error("Error getting followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/get-following', methods=['POST'])
def get_following():
    try:
        user_id = request.get_json()
        query = db.collection('followers').where('followerId', '==', user_id)
        snapshot = query.stream()
        following_ids = [doc.get('followingId') for doc in snapshot]


        # Get user details for each following
        following = []
        for following_id in following_ids:
            user_doc = db.collection('humanUsers').document(following_id).get()
            if user_doc.exists:
                following.append(user_doc.to_dict())


        return jsonify(following), 200
    except Exception as ex:
        logger.error("Error getting following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/remove-from-following', methods=['POST'])
def remove_from_following():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to remove from A's following list)


        logger.info(f"User {follower_id} is managing their following list by removing {following_id}.")


        query = db.collection('followers').where('followerId', '==', follower_id).where('followingId', '==', following_id)
        snapshot = query.stream()
        for doc in snapshot:
            doc.reference.delete()
            logger.info(f"Removed {following_id} from {follower_id}'s following list.")


        return jsonify({"message": "User successfully removed from your following list."}), 200
    except Exception as ex:
        logger.error("Error removing from following: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/user/remove-from-followers', methods=['POST'])
def remove_from_followers():
    try:
        data = request.get_json()
        follower_id = data.get("FollowerId")  # A (authenticated user)
        following_id = data.get("FollowingId")  # B (user to remove as follower)


        # Remove B -> A following relationship (corrected logic)
        query = db.collection('followers').where('followerId', '==', following_id).where('followingId', '==', follower_id)
        snapshot = query.stream()
        for doc in snapshot:
            doc.reference.delete()


        return jsonify({"message": "User successfully removed from your followers list."}), 200
    except Exception as ex:
        logger.error("Error removing from followers: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500
       
@backend_bp.route('/user/like-post', methods=['POST'])
def like_post():
    try:
        data = request.get_json()
        like_data = {
            "user_id": data.get("UserId"),
            "post_id": data.get("PostId"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }


        # Add the like to the postLikes collection
        db.collection('postLikes').add(like_data)


        # Increment the like count in the posts collection
        post_ref = db.collection('posts').document(data.get("PostId"))
        post_ref.update({
            "likes": firestore.Increment(1)
        })


        return jsonify({"success": True}), 200
    except Exception as ex:
        logger.error("Error liking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to like post", "code": "LIKE_POST_ERROR"}), 500


@backend_bp.route('/user/unlike-post', methods=['POST'])
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
        post_ref = db.collection('posts').document(post_id)
        post_ref.update({
            "likes": firestore.Increment(-1)
        })


        return jsonify({"success": True, "message": "Post unliked successfully."}), 200
    except Exception as ex:
        logger.error("Error unliking post: %s", ex)
        return jsonify({"success": False, "error": "Failed to unlike post", "code": "UNLIKE_POST_ERROR"}), 500


@backend_bp.route('/user/get-liked-posts', methods=['POST'])
def get_liked_posts():
    try:
        user_id = request.get_json()


        # Query to find liked posts
        liked_query = db.collection('postLikes').where('user_id', '==', user_id)
        liked_snapshot = liked_query.stream()
        liked_post_ids = [doc.get('post_id') for doc in liked_snapshot]


        liked_posts = []
        for post_id in liked_post_ids:
            post_doc = db.collection('posts').document(post_id).get()
            if post_doc.exists:
                liked_posts.append(post_doc.to_dict())


        return jsonify(liked_posts), 200
    except Exception as ex:
        logger.error("Error retrieving liked posts: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


# Feed Controller
def generate_categories(post_text):
    """
    Uses OpenAI GPT to generate relevant categories for a given post text.
    """
    try:
        if not post_text:
            return []


        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an AI that classifies text into categories."},
                {"role": "user", "content": f"Classify this post into relevant categories: {post_text}"}
            ],
            max_tokens=20
        )


        categories = json.loads(response['choices'][0]['message']['content'])
        return categories[:5]
    except Exception as ex:
        logger.error("Error generating categories: %s", ex)
        return []


@backend_bp.route('/feed/create-human-post', methods=['POST'])
def create_human_post():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400
       
        username = data.get("UserName")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "INVALID_USERNAME"}), 400
       
        post_text = data.get("Post").get("TextContent", "")
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)
       
        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            },
            "user_document_id": data.get("UserDocumentId"),
            "user_name": data.get("UserName"),
        }


        doc_ref = db.collection('humanPosts').add(post_data)


        return jsonify({"postId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating human post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500


@backend_bp.route('/feed/create-ai-post', methods=['POST'])
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
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)


        post_data = {
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            },
            "user_name": username,
        }


        doc_ref = db.collection('aiPosts').add(post_data)


        ai_user_ref.update({"posts": firestore.ArrayUnion([doc_ref[1].id])})


        return jsonify({"postId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating AI post: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500


@backend_bp.route('/feed/create-repost', methods=['POST'])
def create_repost():
    try:
        data = request.get_json()
        if not data or not data.get("Post"):
            return jsonify({"success": False, "error": "Post content is required", "code": "INVALID_POST_CONTENT"}), 400


        username = data.get("UserName")
        if not username:
            return jsonify({"success": False, "error": "Username is required", "code": "INVALID_USERNAME"}), 400
       
        post_text = data.get("Post").get("TextContent", "")
        categories = data.get("category", []) if data.get("category", []) else generate_categories(post_text)
       
        post_data = {
            "ai_chat_content": data.get("AIChatContent"),
            "ai_name": data.get("AIName"),
            "ai_profile_image_url": data.get("AIProfileImageURL"),
            "category": categories,
            "comments": [],
            "date_posted": firestore.SERVER_TIMESTAMP,
            "likes": 0,
            "post": {
                "image_content": data.get("Post").get("ImageContent", []),
                "text_content": data.get("Post").get("TextContent"),
                "video_content": data.get("Post").get("VideoContent", [])
            },
            "user_document_id": data.get("UserDocumentId"),
            "user_name": data.get("UserName"),
            "ai_id": data.get("AiId"),
        }


        doc_ref = db.collection('reposts').add(post_data)


        return jsonify({"postId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating repost: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "POST_CREATE_ERROR"}), 500


@backend_bp.route('/feed/get-feed', methods=['POST'])
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
""" Old Version
@app.route('/feed/posts-flow', methods=['GET'])
def posts_flow(): # With pagination
    try:
        # Get page parameter (default to 1)
        page = request.args.get('page', default=1, type=int)
        posts_per_page = 30
        
        # Define distribution ratios
        ai_text_ratio = 0.21
        ai_video_ratio = 0.21
        human_text_ratio = 0.21
        human_video_ratio = 0.21
        reposts_ratio = 0.16

        # Calculate number of posts per category for one page
        num_ai_text_per_page = int(posts_per_page * ai_text_ratio)
        num_ai_video_per_page = int(posts_per_page * ai_video_ratio)
        num_human_text_per_page = int(posts_per_page * human_text_ratio)
        num_human_video_per_page = int(posts_per_page * human_video_ratio)
        num_reposts_per_page = int(posts_per_page * reposts_ratio)

        # Fetch posts from each collection
        ai_posts_query = db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page )  # increased limit for pagination
        human_posts_query = db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page )
        reposts_query = db.collection('reposts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page )
        
        ai_posts = [doc.to_dict() for doc in ai_posts_query.stream() if doc.exists]
        human_posts = [doc.to_dict() for doc in human_posts_query.stream() if doc.exists]
        reposts = [doc.to_dict() for doc in reposts_query.stream() if doc.exists]

        # Separate text and video posts based on 'video_content'
        ai_text_posts = [post for post in ai_posts if not post.get("post", {}).get("video_content")]
        ai_video_posts = [post for post in ai_posts if post.get("post", {}).get("video_content")]
        human_text_posts = [post for post in human_posts if not post.get("post", {}).get("video_content")]
        human_video_posts = [post for post in human_posts if post.get("post", {}).get("video_content")]

        # Sort each category by date_posted in descending order
        ai_text_sorted = sorted(ai_text_posts, key=lambda x: x['date_posted'], reverse=True)
        ai_video_sorted = sorted(ai_video_posts, key=lambda x: x['date_posted'], reverse=True)
        human_text_sorted = sorted(human_text_posts, key=lambda x: x['date_posted'], reverse=True)
        human_video_sorted = sorted(human_video_posts, key=lambda x: x['date_posted'], reverse=True)
        reposts_sorted = sorted(reposts, key=lambda x: x['date_posted'], reverse=True)

        # Calculate offset for each category based on page number
        offset_ai_text = (page - 1) * num_ai_text_per_page
        offset_ai_video = (page - 1) * num_ai_video_per_page
        offset_human_text = (page - 1) * num_human_text_per_page
        offset_human_video = (page - 1) * num_human_video_per_page
        offset_reposts = (page - 1) * num_reposts_per_page

        # Select posts for the current page using slicing and then merge and sort by date_posted
        selected_posts = {
            "aiPosts": sorted(
                ai_text_sorted[offset_ai_text: offset_ai_text + num_ai_text_per_page] +
                ai_video_sorted[offset_ai_video: offset_ai_video + num_ai_video_per_page],
                key=lambda x: x.get('date_posted', datetime.min), reverse=True
            ),
            "humanPosts": sorted(
                human_text_sorted[offset_human_text: offset_human_text + num_human_text_per_page] +
                human_video_sorted[offset_human_video: offset_human_video + num_human_video_per_page],
                key=lambda x: x.get('date_posted', datetime.min), reverse=True
            ),
            "reposts": sorted(
                reposts_sorted[offset_reposts: offset_reposts + num_reposts_per_page],
                key=lambda x: x.get('date_posted', datetime.min), reverse=True
            ),
        } 
        
        return jsonify(selected_posts), 200
    except Exception as ex:
        logger.error("Error getting posts flow: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500
"""

# @app.route('/feed/posts-flow', methods=['GET'])
# def posts_flow():
#     try:
#         page = request.args.get('page', default=1, type=int)
#         posts_per_page = 30
        
#         # Parse the comma-separated categories string from query parameters
#         topics = request.args.get('categories', '')
#         preferred = [cat.strip().lower() for cat in topics.split(',') if cat.strip()]
        
#         # Define distribution ratios
#         ai_text_ratio = 0.21
#         ai_video_ratio = 0.21
#         human_text_ratio = 0.21
#         human_video_ratio = 0.21
#         reposts_ratio = 0.16

#         # Calculate number of posts per category for one page
#         num_ai_text_per_page = int(posts_per_page * ai_text_ratio)
#         num_ai_video_per_page = int(posts_per_page * ai_video_ratio)
#         num_human_text_per_page = int(posts_per_page * human_text_ratio)
#         num_human_video_per_page = int(posts_per_page * human_video_ratio)
#         num_reposts_per_page = int(posts_per_page * reposts_ratio)

#         # Fetch posts from each collection (fetch extra to allow filtering)
#         ai_posts_query = db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page * 2)
#         human_posts_query = db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page * 2)
#         reposts_query = db.collection('reposts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(page * posts_per_page * 2)
        
#         # Convert Firestore documents to lists of dictionaries
#         ai_posts = [doc.to_dict() for doc in ai_posts_query.stream()]
#         human_posts = [doc.to_dict() for doc in human_posts_query.stream()]
#         reposts = [doc.to_dict() for doc in reposts_query.stream()]
        
#         # If preferred categories are provided, filter posts by matching the 'category' field.
#         if preferred:
#             ai_posts = [post for post in ai_posts if category_matches(post, preferred)]
#             human_posts = [post for post in human_posts if category_matches(post, preferred)]
#             reposts = [post for post in reposts if category_matches(post, preferred)]

#         # Separate text and video posts based on the presence of 'video_content' within the post sub-dictionary.
#         ai_text_posts = [post for post in ai_posts if not post.get("post", {}).get("video_content")]
#         ai_video_posts = [post for post in ai_posts if post.get("post", {}).get("video_content")]
#         human_text_posts = [post for post in human_posts if not post.get("post", {}).get("video_content")]
#         human_video_posts = [post for post in human_posts if post.get("post", {}).get("video_content")]

#         # Sort each category by date_posted in descending order
#         ai_text_sorted = sorted(ai_text_posts, key=lambda x: x.get('date_posted', datetime.min), reverse=True)
#         ai_video_sorted = sorted(ai_video_posts, key=lambda x: x.get('date_posted', datetime.min), reverse=True)
#         human_text_sorted = sorted(human_text_posts, key=lambda x: x.get('date_posted', datetime.min), reverse=True)
#         human_video_sorted = sorted(human_video_posts, key=lambda x: x.get('date_posted', datetime.min), reverse=True)
#         reposts_sorted = sorted(reposts, key=lambda x: x.get('date_posted', datetime.min), reverse=True)

#         # Calculate offsets for each category based on page number
#         offset_ai_text = (page - 1) * num_ai_text_per_page
#         offset_ai_video = (page - 1) * num_ai_video_per_page
#         offset_human_text = (page - 1) * num_human_text_per_page
#         offset_human_video = (page - 1) * num_human_video_per_page
#         offset_reposts = (page - 1) * num_reposts_per_page

#         # Select posts for the current page using slicing
#         selected_ai_text = ai_text_sorted[offset_ai_text: offset_ai_text + num_ai_text_per_page]
#         selected_ai_video = ai_video_sorted[offset_ai_video: offset_ai_video + num_ai_video_per_page]
#         selected_human_text = human_text_sorted[offset_human_text: offset_human_text + num_human_text_per_page]
#         selected_human_video = human_video_sorted[offset_human_video: offset_human_video + num_human_video_per_page]
#         selected_reposts = reposts_sorted[offset_reposts: offset_reposts + num_reposts_per_page]

#         # Add a field to each post indicating the post type
#         for post in selected_ai_text:
#             post['post_type'] = 'ai_post'
#         for post in selected_ai_video:
#             post['post_type'] = 'ai_post'
#         for post in selected_human_text:
#             post['post_type'] = 'human_post'
#         for post in selected_human_video:
#             post['post_type'] = 'human_post'
#         for post in selected_reposts:
#             post['post_type'] = 'repost'
        
#         # Merge the posts into one feed and sort by date_posted descending
#         merged_feed = selected_ai_text + selected_ai_video + selected_human_text + selected_human_video + selected_reposts
#         final_feed = sorted(merged_feed, key=lambda x: x.get('date_posted', datetime.min), reverse=True)
        
#         return jsonify({'posts': final_feed}), 200
#     except Exception as ex:
#         logger.error("Error getting posts flow: %s", ex)
#         return jsonify({"success": False, "error": str(ex)}), 500

# Without pagination
# def posts_flow():
    # try:
    #     # Fetch posts from each collection
    #     ai_posts_query = db.collection('aiPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(25)
    #     human_posts_query = db.collection('humanPosts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(25)
    #     reposts_query = db.collection('reposts').order_by('date_posted', direction=firestore.Query.DESCENDING).limit(25)
        
    #     ai_posts = [doc.to_dict() for doc in ai_posts_query.stream() if doc.exists]
    #     human_posts = [doc.to_dict() for doc in human_posts_query.stream() if doc.exists]
    #     reposts = [doc.to_dict() for doc in reposts_query.stream() if doc.exists]

    #     # Separate text and video posts based on 'video_content'
    #     ai_text_posts = [post for post in ai_posts if not post.get("post", {}).get("video_content")]
    #     ai_video_posts = [post for post in ai_posts if post.get("post", {}).get("video_content")]
    #     human_text_posts = [post for post in human_posts if not post.get("post", {}).get("video_content")]
    #     human_video_posts = [post for post in human_posts if post.get("post", {}).get("video_content")]

    #     # Calculate the total number of posts across all collections
    #     total_posts = len(ai_posts) + len(human_posts) + len(reposts)
    #     # Distribution ratios: 42% for AI (21% text, 21% video), 42% for human (21% text, 21% video), 16% for reposts
    #     num_ai_text_posts = int(total_posts * 0.21)
    #     num_ai_video_posts = int(total_posts * 0.21)
    #     num_human_text_posts = int(total_posts * 0.21)
    #     num_human_video_posts = int(total_posts * 0.21)
    #     num_reposts = int(total_posts * 0.16)

    #     # Sort each category by date_posted in descending order
    #     ai_text_sorted = sorted(ai_text_posts, key=lambda x: x['date_posted'], reverse=True)
    #     ai_video_sorted = sorted(ai_video_posts, key=lambda x: x['date_posted'], reverse=True)
    #     human_text_sorted = sorted(human_text_posts, key=lambda x: x['date_posted'], reverse=True)
    #     human_video_sorted = sorted(human_video_posts, key=lambda x: x['date_posted'], reverse=True)
    #     reposts_sorted = sorted(reposts, key=lambda x: x['date_posted'], reverse=True)

    #     selected_posts = {
    #         "aiPosts": sorted(
    #             ai_text_sorted[:num_ai_text_posts] + ai_video_sorted[:num_ai_video_posts],
    #             key=lambda x: x.get('date_posted', datetime.min), reverse=True
    #         ),
    #         "humanPosts": sorted(
    #             human_text_sorted[:num_human_text_posts] + human_video_sorted[:num_human_video_posts],
    #             key=lambda x: x.get('date_posted', datetime.min), reverse=True
    #         ),
    #         "reposts": sorted(
    #             reposts_sorted[:num_reposts],
    #             key=lambda x: x.get('date_posted', datetime.min), reverse=True
    #         ),
    #     }

    #     return jsonify(selected_posts), 200
    # except Exception as ex:
    #     logger.error("Error getting posts flow: %s", ex)
    #     return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/feed/posts-flow', methods=['GET'])
def posts_flow():
    try:
        collections = ['aiPosts', 'humanPosts', 'reposts']
        all_posts = []

        # Fetch all posts
        for collection in collections:
            posts_ref = db.collection(collection).order_by('date_posted', direction=firestore.Query.DESCENDING).limit(25)
            snapshot = posts_ref.stream()
            all_posts.extend([doc.to_dict() for doc in snapshot if doc.exists])


        # Fetch AI users
        ai_users_ref = db.collection('aiUsers')
        ai_users_snapshot = ai_users_ref.stream()
        ai_usernames = {doc.id for doc in ai_users_snapshot}

        # Fetch human users
        human_users_ref = db.collection('humanUsers')
        human_users_snapshot = human_users_ref.stream()
        human_user_uids = {doc.id for doc in human_users_snapshot}

        # Categorize posts
        ai_text_posts = [post for post in all_posts if post.get("user_name") in ai_usernames and not post.get("post", {}).get("video_content")]
        ai_video_posts = [post for post in all_posts if post.get("user_name") in ai_usernames and post.get("post", {}).get("video_content")]
        human_text_posts = [post for post in all_posts if post.get("user_document_id") in human_user_uids and not post.get("post", {}).get("video_content")]
        human_video_posts = [post for post in all_posts if post.get("user_document_id") in human_user_uids and post.get("post", {}).get("video_content")]
        reposts = [post for post in all_posts if post.get("aiChatContent") or post.get("aiName") or post.get("aiProfileImageURL")]


        # Distribution of posts
        # Human posts 42%: no videos 21%, videos 21%
        # AI posts 42%: no videos 21%,  videos 21%,
        # Reposts 16%
        total_posts = len(all_posts)
        num_human_text_posts = int(total_posts * 0.21)
        num_human_video_posts = int(total_posts * 0.21)
        num_ai_text_posts = int(total_posts * 0.21)
        num_ai_video_posts = int(total_posts * 0.21)
        num_reposts = int(total_posts * 0.16)


        human_text_posts_sorted = sorted(human_text_posts, key=lambda x: x['date_posted'], reverse=True)
        human_video_posts_sorted = sorted(human_video_posts, key=lambda x: x['date_posted'], reverse=True)
        ai_text_posts_sorted = sorted(ai_text_posts, key=lambda x: x['date_posted'], reverse=True)
        ai_video_posts_sorted = sorted(ai_video_posts, key=lambda x: x['date_posted'], reverse=True)
        reposts_sorted = sorted(reposts, key=lambda x: x['date_posted'], reverse=True)

        selected_posts = {
            "aiPosts": sorted(ai_text_posts_sorted[:num_ai_text_posts] + ai_video_posts_sorted[:num_ai_video_posts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
            "humanPosts": sorted(human_text_posts_sorted[:num_human_text_posts] + human_video_posts_sorted[:num_human_video_posts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
            "reposts": sorted(reposts_sorted[:num_reposts], key=lambda x: x.get('date_posted', datetime.min), reverse=True),
        }

        return jsonify(selected_posts), 200
    except Exception as ex:
        logger.error("Error getting posts flow: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500

@backend_bp.route('/feed/update-post', methods=['POST'])
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


@backend_bp.route('/feed/write-comment', methods=['POST'])
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


@backend_bp.route('/feed/get-user-posts', methods=['POST'])
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


# AI Controller
def generate_ai_response(message, ai_character_id):
    try:
        ai_character = None
        if ai_character_id:
            doc_ref = db.collection("aiCharacters").document(ai_character_id)
            snapshot = doc_ref.get()
            if not snapshot.exists:
                raise ApiException("AI character not found", "AI_CHARACTER_NOT_FOUND")
            ai_character = snapshot.to_dict()


        response = client.Completion.create(
            engine="text-davinci-003",
            prompt=f"{ai_character['Personality']} AI: {message}",
            max_tokens=150
        )


        return response.choices[0].text.strip()
    except Exception as ex:
        logger.error("Error generating AI response: %s", ex)
        raise ApiException("Failed to generate AI response", "AI_GENERATION_ERROR")


@backend_bp.route('/api/ai/chat', methods=['POST'])
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


@backend_bp.route('/api/ai/create-ai-user', methods=['POST'])
def create_ai_user():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "Character data is required", "code": "INVALID_CHARACTER_DATA"}), 400


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


        doc_ref = db.collection('aiUsers').add(character_data)


        return jsonify({"AiUserId": doc_ref[1].id}), 200
    except Exception as ex:
        logger.error("Error creating AI User: %s", ex)
        return jsonify({"success": False, "error": str(ex), "code": "CHARACTER_CREATE_ERROR"}), 500


@backend_bp.route('/api/ai/carousel/characters', methods=['GET'])
def get_carousel_characters():
    try:
        # Retrieve all AI characters
        characters_ref = db.collection('aiUsers')
        snapshot = characters_ref.stream()


        ai_characters = []


        for doc in snapshot:
            character = doc.to_dict()
            ai_characters.append(character)


        # Sort AI characters by likes for popularity
        # This will need to depend on the popularity field
        ai_characters.sort(key=lambda x: x.get('followers_count', 0), reverse=True)


        # Apply 10:1 ratio for popular to less popular characters
        num_ai_characters = len(ai_characters)
        num_user_characters = min(len(ai_characters), num_ai_characters // 10)


        selected_characters = ai_characters[:num_ai_characters] + ai_characters[:num_user_characters]


        random.shuffle(selected_characters)


        return jsonify(selected_characters), 200
    except Exception as ex:
        logger.error("Error retrieving carousel characters: %s", ex)
        return jsonify({"success": False, "error": str(ex)}), 500


@backend_bp.route('/api/ai/generate-image', methods=['POST'])
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


# AI Content Controller
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


@backend_bp.route('/ai-content/generate-post', methods=['POST'])
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
            "user_name": post["UserName"],
            "user_references": post["UserReferences"]
        }


        doc_ref = db.collection('posts').add(post_data)
        post_id = doc_ref[1].id


        return jsonify({"success": True, "data": {**post, "Id": post_id}}), 200
    except Exception as ex:
        logger.error("Error generating AI post: %s", ex)
        return jsonify({"success": False, "error": "Failed to generate post", "code": "POST_GENERATION_ERROR"}), 500