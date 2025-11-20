# services/media/media_generation_service.py
from dependencies import db, openai_client, storage
from typing import Dict, Any
import logging
from flask import jsonify
import requests
import time
import os
import uuid
import random
import base64

logger = logging.getLogger(__name__)

# Meshy API configuration
MESHY_API_KEY = os.getenv('MESHY_API_KEY', '')
HEADERS = {
    "Authorization": f"Bearer {MESHY_API_KEY}",
    "Content-Type": "application/json",
}

class MediaGenerationService:
    """Service for generating images and 3D avatars"""

    @staticmethod
    def image_to_base64(image_path: str) -> str:
        """Convert image file to base64 string"""
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return encoded_string

    @staticmethod
    def generate_image(prompt: str) -> Dict[str, Any]:
        """Generate image using DALL-E 3"""
        try:
            if not prompt:
                return jsonify({"error": "Missing 'prompt' in request"}), 400

            # Generate image using DALL-E 3
            response = openai_client.images.generate(
                model="dall-e-3",
                prompt=f"${prompt}",
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url

            # Wait for image to be ready
            time.sleep(5)

            # Download the image
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
            logger.error(f"Error generating image: {e}")
            return jsonify({"error": str(e)}), 500

    @staticmethod
    def _create_preview_task(prompt: str, seed: int) -> str:
        """Create a preview task for 3D avatar generation"""
        payload = {
            "mode": "preview",
            "prompt": prompt,
            "art_style": "realistic",
            "should_remesh": True,
            "ai_model": "meshy-5",
            "seed": seed,
            "topology": "triangle",
            "target_polycount": 30000,
        }
        resp = requests.post(
            "https://api.meshy.ai/openapi/v2/text-to-3d",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["result"]

    @staticmethod
    def _create_refine_task(preview_task_id: str) -> str:
        """Create a refine task for 3D avatar generation"""
        payload = {
            "mode": "refine",
            "preview_task_id": preview_task_id,
            "enable_pbr": False,
        }
        resp = requests.post(
            "https://api.meshy.ai/openapi/v2/text-to-3d",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["result"]

    @staticmethod
    def _poll_task(task_id: str, label: str, retries: int = 60, delay: int = 5) -> dict:
        """Poll a Meshy API task until completion"""
        for _ in range(retries):
            time.sleep(delay)
            resp = requests.get(
                f"https://api.meshy.ai/openapi/v2/text-to-3d/{task_id}",
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") == "SUCCEEDED":
                return data
            if data.get("status") == "FAILED":
                raise RuntimeError(f"{label} task failed")
        raise TimeoutError(f"{label} task timed out")

    @staticmethod
    def generate_3d_avatar(prompt: str) -> Dict[str, Any]:
        """Generate 3D avatar using Meshy API"""
        try:
            if not prompt:
                return jsonify({"error": "Missing prompt"}), 400

            seed = random.randint(0, 2**31 - 1)

            # Create preview task
            preview_id = MediaGenerationService._create_preview_task(prompt, seed)
            _ = MediaGenerationService._poll_task(preview_id, "Preview")

            # Create refine task
            refine_id = MediaGenerationService._create_refine_task(preview_id)
            refine_data = MediaGenerationService._poll_task(refine_id, "Refine")

            return jsonify(
                {
                    "model_glb": refine_data["model_urls"]["glb"],
                    "model_obj": refine_data["model_urls"]["obj"],
                    "texture": refine_data["texture_urls"][0]["base_color"],
                    "thumbnail": refine_data.get("thumbnail_url"),
                    "seed": seed,
                }
            ), 200

        except TimeoutError as e:
            logger.error(f"3D avatar generation timeout: {e}")
            return jsonify({"error": str(e)}), 504
        except Exception as e:
            logger.error(f"Error generating 3D avatar: {e}")
            return jsonify({"error": str(e)}), 500
