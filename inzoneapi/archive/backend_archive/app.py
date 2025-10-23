from firebase_admin import firestore, storage
import logging
import requests
import os
import base64
import time
import uuid
from openai import OpenAI
# https://docs.google.com/document/d/1mhQg_vOV0KVQi0J8nKVZaF-jd9teCdS3FkmykI0BZzc/edit?tab=t.0
# https://docs.google.com/spreadsheets/d/1Zt_y0gMstAXA2WKZCMp2qb3m62dcaKXVR5sTufXU8Nc/edit?gid=0#gid=0
from flask import Blueprint, request, jsonify, current_app
app_bp = Blueprint("app", __name__)
logger = logging.getLogger(__name__)
db = firestore.client()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)

@app_bp.route("/", methods=["GET"])
def test():
    return "Work in Progress!"


@app_bp.route('/get_post/<post_id>', methods=['GET'])
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

@app_bp.route('/api/image', methods=['POST'])
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
@app_bp.route('/api/3d', methods=['POST'])
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

@app_bp.route('/api/get_model/<task_id>', methods=['GET'])
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
