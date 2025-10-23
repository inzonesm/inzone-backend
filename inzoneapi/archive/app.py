# from flask import Flask, request, jsonify
# from firebase_admin import credentials, initialize_app, firestore
# from flask_cors import CORS
# import uuid
# import os

# # Initialize Firebase Admin
# cred = credentials.Certificate(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
# default_app = initialize_app(cred)

# # Initialize Firestore client
# db = firestore.client()
# user_ref = db.collection("users")

# # Create Flask app
# app = Flask(__name__)
# CORS(app)
# app.config['SECRET_KEY'] = 'INZONE1234'

# # Helper function to get user document reference and snapshot
# def get_user_document(user_email):
#     user_doc_ref = user_ref.document(user_email)
#     return user_doc_ref, user_doc_ref.get()


# # Route to get a specific user by email
# @app.route("/users/<user_email>", methods=["GET"])
# def get_user(user_email):
#     try:
#         user_doc_ref, user_doc = get_user_document(user_email)
#         if user_doc.exists:
#             return jsonify(user_doc.to_dict()), 200
#         return jsonify({"error": "User not found"}), 404
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# # Route to update user information
# @app.route("/users/<user_email>", methods=["PUT"])
# def update_user(user_email):
#     try:
#         data = request.json
#         user_doc_ref, user_doc = get_user_document(user_email)

#         # Check if the user exists
#         if not user_doc.exists:
#             return jsonify({"error": "User not found"}), 404

#         user_data = user_doc.to_dict()

#         # Update user fields
#         user_data.update(
#             {
#                 "age": data.get("age", user_data.get("age")),
#                 "ai": data.get("ai", user_data.get("ai")),
#                 "bio": data.get("bio", user_data.get("bio")),
#                 "categories": data.get("categories", user_data.get("categories")),
#                 "chats": data.get("chats", user_data.get("chats")),
#                 "email": data.get("email", user_data.get("email")),
#                 "family": data.get("family", user_data.get("family")),
#                 "firstName": data.get("firstName", user_data.get("firstName")),
#                 "followers": data.get("followers", user_data.get("followers")),
#                 "following": data.get("following", user_data.get("following")),
#                 "gender": data.get("gender", user_data.get("gender")),
#                 "lastName": data.get("lastName", user_data.get("lastName")),
#                 "parent": data.get("parent", user_data.get("parent")),
#                 "user_name": data.get("user_name", user_data.get("user_name")),
#             }
#         )

#         # Save updated user data to Firestore
#         user_doc_ref.set(user_data)
#         return jsonify({"success": True}), 200
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# # Route to add a follower or following
# @app.route("/users/<user_email>/followers_following", methods=["POST"])
# def add_follower_or_following(user_email):
#     try:
#         data = request.json
#         addition_type = data.get("type")
#         new_entry = {
#             "email": data.get("email"),
#             "name": data.get("name"),
#             "profileImage": data.get("profileImage"),
#             "verified": data.get("verified"),
#         }

#         user_doc_ref, user_doc = get_user_document(user_email)
#         if user_doc.exists():
#             user_data = user_doc.to_dict()
#             if addition_type == "followers":
#                 user_data.setdefault("followers", []).append(new_entry)
#             elif addition_type == "following":
#                 user_data.setdefault("following", []).append(new_entry)
#             else:
#                 return jsonify({"error": "Invalid addition type"}), 400

#             user_doc_ref.set(user_data)
#             return jsonify({"success": True}), 200
#         return jsonify({"error": "User not found"}), 404
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# # Route to remove a follower or following
# @app.route("/users/remove/<user_email>", methods=["DELETE"])
# def remove_follower_or_following(user_email):
#     try:
#         data = request.json
#         other_email = data.get("other_email")
#         removal_type = data.get("type")

#         user_doc_ref, user_doc = get_user_document(user_email)
#         if user_doc.exists:
#             user_data = user_doc.to_dict()
#             if removal_type == "followers":
#                 user_data["followers"] = [
#                     f
#                     for f in user_data.get("followers", [])
#                     if f["email"] != other_email
#                 ]
#             elif removal_type == "following":
#                 user_data["following"] = [
#                     f
#                     for f in user_data.get("following", [])
#                     if f["email"] != other_email
#                 ]
#             else:
#                 return jsonify({"error": "Invalid removal type"}), 400

#             user_doc_ref.set(user_data)
#             return jsonify({"success": True}), 200
#         return jsonify({"error": "User not found"}), 404
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# # Route to update user profile picture    
# @app.route("/users/profile_picture/<user_email>", methods=["POST"])
# def set_profile_picture(user_email):
#     try:
#         data = request.json
#         profile_image_url = data.get("profileImage")

#         if not profile_image_url:
#             return jsonify({"error": "Profile image URL not provided"}), 400

#         user_doc_ref, user_doc = get_user_document(user_email)
#         if not user_doc.exists:
#             return jsonify({"error": "User not found"}), 404

#         # Update the profileImage field
#         user_doc_ref.update({"profileImage": profile_image_url})

#         return jsonify({"success": True}), 200
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# # Endpoint to update specific fields
# @app.route("/update/<field_type>/<user_email>", methods=["PUT"])
# def update_field(field_type, user_email):
#     try:
#         data = request.json
#         user_doc_ref, user_doc = get_user_document(user_email)

#         if not user_doc.exists:
#             return jsonify({"error": "User not found"}), 404

#         if field_type not in ["categories", "screentime", "chats", "blockout", "notifications"]:
#             return jsonify({"error": "Invalid field type"}), 400

#         user_data = user_doc.to_dict()
#         user_data[field_type] = data

#         user_doc_ref.set(user_data)
#         return jsonify({"success": True}), 200
#     except Exception as e:
#         return f"An exception occurred: {e}", 500

# def generate_prompt(prompt):
#     final = ""
    
# @app.route("/avatars/<prompt>", methods=["POST"])
# def avatar_create(prompt):
#     try:
#         prompt_final = generate_prompt(prompt)
#         pass
#     except Exception as e:
#         pass

# if __name__ == '__main__':
#     os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/app/key.json"
#     app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))