# services/media/media_generation_service.py
from dependencies import db, openai_client, storage
from typing import Dict, Any, Optional, List, Tuple
import logging
from flask import jsonify
import requests
import time
import os
import uuid
import random
import base64
import json
from openai import OpenAI
from pydantic import ValidationError
from models.avatar_models import AvatarSpec, Item, Clothing
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
import pathlib
from threading import Thread

logger = logging.getLogger(__name__)

BASE_URL = "https://api.meshy.ai"

# Global cleanup scheduler state
_cleanup_scheduler_running = False
_cleanup_scheduler_thread = None

# OpenAI API configuration
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
OPENAI_HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json",
}

# Meshy API configuration
MESHY_API_KEY = os.getenv('MESHY_API_KEY', '')
HEADERS = {
    "Authorization": f"Bearer {MESHY_API_KEY}",
    "Content-Type": "application/json",
}

SCHEMA_TEXT = """
{
  "style": {"enum":["cartoon","anime","semi_realistic","realistic","low_poly","other"], "free_text": "string|null"},
  "species": {"enum":["human","non_humanoid"]},
  "body": {"skin_tone":"string|null","build":"string|null","height_hint":"string|null"},
  "hair": {"color":"string|null","style":"string|null","length":"string|null"},
  "clothing": {
    "top":{"category":"string|null","color":"string|null","notes":"string|null"},
    "bottom":{"category":"string|null","color":"string|null","notes":"string|null"},
    "shoes":{"category":"string|null","color":"string|null","notes":"string|null"},
    "outerwear":{"category":"string|null","color":"string|null","notes":"string|null"},
    "accessories":["string"]
  },
  "palette":["string"],
  "pose":{"enum":["t_pose","a_pose","neutral"]},
  "camera":{"enum":["full_body_orthographic","full_body_perspective"]},
  "notes":["string"],
  "confidence": {
    "style": "number", "clothing.top": "number", "clothing.bottom": "number",
    "hair.color": "number", "body.skin_tone": "number"
  }
}
""".strip()

SYSTEM_INSTRUCTIONS = f"""
You extract structured data for 3D avatar generation.

Return ONLY valid JSON matching this schema:
{SCHEMA_TEXT}

Rules:
- Prefer enums when possible (e.g., "cartoon" if user says "Animal Crossing").
- If an enum doesn't fit, set enum to "other" and use free_text/notes.
- Do NOT invent clothing or attributes not present in input.
- Species defaults to "human" unless clearly non-human.
- For humans, default pose to "t_pose".
- Default camera to "full_body_orthographic", neutral lighting.
- Provide confidence scores (0–1) for key fields listed in the schema.
- Output JSON only. No extra text.
- For species, pose, and camera, return a strong, not an object.
""".strip()

class MediaGenerationService:
    """Service for generating images and 3D avatars"""

    @staticmethod
    def _coerce_to_style_obj(val):
        # Accept {"enum": "...", "free_text": "..."} OR plain string -> object
        if isinstance(val, dict):
            enum_val = val.get("enum")
            ft = val.get("free_text")
            # ensure keys exist; default enum to "other" if missing
            return {"enum": enum_val or "other", "free_text": ft}
        elif isinstance(val, str):
            return {"enum": val, "free_text": None}
        else:
            return {"enum": "other", "free_text": None}

    @staticmethod
    def _unwrap_enum_dict(val):
        # Accept {"enum": "..."} OR string -> string
        if isinstance(val, dict) and "enum" in val:
            return val["enum"]
        if isinstance(val, str):
            return val
        return None

    @staticmethod
    def _normalize_llm_json(data: dict) -> dict:
        """
        Make the raw LLM JSON compatible with AvatarSpec:
        - style: object with enum/free_text
        - species/pose/camera: strings (unwrap {"enum": ...})
        - ensure nested dicts exist
        """
        data = dict(data)  # shallow copy

        # style
        data["style"] = MediaGenerationService._coerce_to_style_obj(data.get("style"))

        # strings that the model sometimes returns as {"enum": "..."}
        for k in ("species", "pose", "camera"):
            if k in data:
                data[k] = MediaGenerationService._unwrap_enum_dict(data[k]) or data.get(k) or ""

        # ensure dict containers exist
        data.setdefault("body", {})
        data.setdefault("hair", {})
        data.setdefault("clothing", {})
        data.setdefault("notes", [])
        data.setdefault("palette", [])
        data.setdefault("confidence", {})

        # clothing sub-objects
        c = data["clothing"]
        if c is None:
            c = {}
            data["clothing"] = c
        for part in ("top", "bottom", "shoes", "outerwear"):
            if part in c and isinstance(c[part], str):
                # If model returned just a string, wrap it as an Item
                c[part] = {"category": c[part], "color": None, "notes": None}
            elif part not in c:
                c[part] = None
        c.setdefault("accessories", [])

        # sane defaults
        if not data["species"]:
            data["species"] = "human"
        if not data["pose"]:
            data["pose"] = "t_pose" if data["species"] == "human" else "neutral"
        if not data["camera"]:
            data["camera"] = "full_body_orthographic"

        return data

    @staticmethod
    def _chat_extract_json(client: OpenAI, user_text: str, model: str = OPENAI_MODEL, temperature: float = 0.1) -> str:
        """Call OpenAI to extract JSON; request strict JSON output."""
        resp = client.chat.completions.create(
            model=model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {"role": "user", "content": f"Input text:\n{user_text}\n\nReturn JSON only."},
            ],
        )
        return resp.choices[0].message.content

    @staticmethod
    def extract_avatar_spec(user_text: str, api_key: Optional[str] = None, model: str = "gpt-4o", max_retries: int = 1) -> AvatarSpec:
        """
        LLM -> JSON -> validate -> (optional) retry with error feedback -> AvatarSpec
        """
        # Use openai_client from dependencies, or create new client if api_key provided
        client = openai_client if api_key is None else OpenAI(api_key=api_key)
        base_prompt = f"{SYSTEM_INSTRUCTIONS}\n\nInput text:\n{user_text}\n\nReturn JSON only."

        last_err = None
        for attempt in range(max_retries + 1):
            json_text = MediaGenerationService._chat_extract_json(client, user_text, model=model)
            try:
                data = json.loads(json_text)
                data = MediaGenerationService._normalize_llm_json(data)
                return AvatarSpec(**data)
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
                # retry with validator error feedback
                repair = client.chat.completions.create(
                    model=model,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": f"The previous output failed validation ({e})."
                                                    f"Re-output corrected JSON only for this input:\n{user_text}"},
                    ],
                )
                json_text = repair.choices[0].message.content
                try:
                    data = json.loads(json_text)
                    data = MediaGenerationService._normalize_llm_json(data)
                    return AvatarSpec(**data)
                except (json.JSONDecodeError, ValidationError) as e2:
                    last_err = e2

        raise RuntimeError(f"Failed to extract a valid AvatarSpec after retries. Last error: {last_err}")
        
    @staticmethod
    def _join(*parts: Optional[str]) -> str:
        return ", ".join([p for p in parts if p])

    @staticmethod
    def render_base_prompt(spec: AvatarSpec) -> str:
        """
        Backend/private base-body prompt: neutral bodysuit, T-pose, orthographic.
        Locks proportions for later clothing fitting.
        """
        style = (spec.style.get("enum") or "cartoon").replace("_", " ")
        notes = ", ".join(spec.notes) if spec.notes else ""
        style_bits = MediaGenerationService._join(f"{style} style", notes if notes else None)

        skin = spec.body.get("skin_tone") or "neutral"
        hair_color = spec.hair.get("color") or "neutral"
        hair_style = spec.hair.get("style")
        hair_len = spec.hair.get("length")

        hair_desc = " ".join([h for h in [hair_color.replace("_", " "), hair_len, hair_style] if h]) or "neutral hair"
        species = spec.species.replace("_", " ")

        return (
                f"{style_bits}, full-body {species}. "
                f"{skin} skin, {hair_desc}. "
                "Neutral bodysuit, T-pose, orthographic camera, neutral lighting, no accessories. "
                "Keep proportions consistent for clothing fitting and retargeting."
            ).strip()

    @staticmethod
    def _pretty_item(item: Optional[Item]) -> Optional[str]:
        if not item:
            return None
        cat = (item.category or "").replace("_", " ")
        col = (item.color or "").replace("_", " ")
        if cat and col:
            return f"{col} {cat}"
        return cat or col or None

    @staticmethod
    def render_clothed_prompt(spec: AvatarSpec) -> str:
        """
        User-facing clothed prompt: same character as base, with outfit and palette.
        """
        style = (spec.style.get("enum") or "cartoon").replace("_", " ")
        outfit_parts = [
            MediaGenerationService._pretty_item(spec.clothing.top),
            MediaGenerationService._pretty_item(spec.clothing.bottom),
            MediaGenerationService._pretty_item(spec.clothing.shoes),
            MediaGenerationService._pretty_item(spec.clothing.outerwear),
        ]
        outfit = ", ".join([p for p in outfit_parts if p]) or "neutral outfit"
        palette = ", ".join(list(dict.fromkeys(spec.palette))) if spec.palette else ""
        acc = ", ".join(spec.clothing.accessories) if spec.clothing.accessories else ""

        txt = f"Same character as base. {style} style, full-body render. Outfit: {outfit}."
        if palette:
            txt += f" Colors: {palette}."
        if acc:
            txt += f" Accessories: {acc}."
        txt += "Neutral lighting"
        return txt
    
    @staticmethod
    def build_prompts_from_text(user_text: str, api_key: Optional[str] = None, model: str = OPENAI_MODEL) -> Tuple[AvatarSpec, str, str]:
        spec = MediaGenerationService.extract_avatar_spec(user_text, api_key=api_key, model=model)
        base_p = MediaGenerationService.render_base_prompt(spec)
        clothed_p = MediaGenerationService.render_clothed_prompt(spec)
        return spec, base_p, clothed_p

    @staticmethod
    def _headers():
        return {"Authorization": f"Bearer {MESHY_API_KEY}", "Content-Type": "application/json"}

    @staticmethod
    def start_text_to_3d_preview(prompt: str, art_style: Optional[str] = None, ai_model: Optional[str] = None, should_remesh: bool = True) -> str:
        payload = {"mode": "preview", "prompt": prompt, "should_remesh": should_remesh}
        if art_style: payload["art_style"] = art_style
        if ai_model: payload["ai_model"] = ai_model
        payload["should_remesh"] = should_remesh

        r = requests.post(f"{BASE_URL}/openapi/v2/text-to-3d", headers=MediaGenerationService._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["result"]

    @staticmethod
    def start_text_to_3d_refine(preview_task_id: str, enable_pbr: bool = True) -> str:
        payload = {"mode": "refine", "preview_task_id": preview_task_id, "enable_pbr": enable_pbr}
        r = requests.post(f"{BASE_URL}/openapi/v2/text-to-3d", headers=MediaGenerationService._headers(), json=payload, timeout=30)
        r.raise_for_status()
        return r.json()["result"]

    @staticmethod
    def get_task(task_id: str) -> dict:
        url = f"{BASE_URL}/openapi/v2/text-to-3d/{task_id}"
        r = requests.get(url, headers=MediaGenerationService._headers(), timeout=30)
        if r.status_code != 200:
            print("GET task failed:", r.status_code, r.text)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def poll_until_done(task_id: str, poll_secs: int = 12, timeout_secs: int = 900) -> dict:
        """
        Polls Meshy task until SUCCEEDED or FAILED/TIMEOUT. Returns the final task object.
        """
        t0 = time.time()
        last_progress = None
        while True:
            task = MediaGenerationService.get_task(task_id)
            status = task.get("status")
            prog = task.get("progress")
            if prog != last_progress:
                logger.info(f"[{task_id}] status={status} progress={prog}")
                last_progress = prog

            if status == "SUCCEEDED":
                return task
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"Meshy task failed: {task.get('task_error', {}).get('message', 'unknown error')}")
            if time.time() - t0 > timeout_secs:
                raise TimeoutError("Timed out waiting for Meshy task.")
            time.sleep(poll_secs)

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
    def _generate_single_avatar(prompt: str, avatar_type: str, art_style: Optional[str] = None, 
                                ai_model: Optional[str] = None, avatar_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a single avatar (base or clothed) using Meshy API.
        
        Args:
            prompt: The prompt to use for generation
            avatar_type: "base" or "clothed"
            art_style: Optional art style
            ai_model: Optional AI model
            avatar_id: Optional avatar ID for progress tracking
            
        Returns:
            Dictionary with avatar URLs and task info
        """
        try:
            # Start preview task
            preview_id = MediaGenerationService.start_text_to_3d_preview(
                prompt=prompt,
                art_style=art_style,
                ai_model=ai_model or "meshy-5",
                should_remesh=True
            )
            logger.info(f"[{avatar_type}] Preview task started: {preview_id}")
            
            if avatar_id:
                stage = f"{avatar_type}_preview"
                MediaGenerationService._update_progress(avatar_id, stage, 
                   10, 
                   f"{avatar_type.capitalize()} avatar preview in progress...")
            
            # Wait for preview to complete (with progress updates)
            task_preview = MediaGenerationService.poll_until_done(preview_id)
            logger.info(f"[{avatar_type}] Preview completed")
            
            if avatar_id:
                stage = f"{avatar_type}_refine"
                MediaGenerationService._update_progress(avatar_id, stage,
                   20,
                   f"{avatar_type.capitalize()} avatar refinement in progress...")
            
            # Start refine task
            refine_id = MediaGenerationService.start_text_to_3d_refine(
                preview_task_id=preview_id, 
                enable_pbr=True
            )
            logger.info(f"[{avatar_type}] Refine task started: {refine_id}")
            
            # Wait for refine to complete
            task_refine = MediaGenerationService.poll_until_done(refine_id)
            logger.info(f"[{avatar_type}] Refine completed")
            
            # Extract URLs from refine task (for fallback and texture info)
            urls = task_refine.get("model_urls") or {}
            texture_urls = task_refine.get("texture_urls") or []
            texture_base_color_url = texture_urls[0].get("base_color") if texture_urls else None
            
            # Stage 3: Rigging (for humanoid avatars)
            if avatar_id:
                stage = f"{avatar_type}_rigging"
                MediaGenerationService._update_progress(avatar_id, stage,
                   30,
                   f"{avatar_type.capitalize()} avatar rigging in progress...")
            
            logger.info(f"[{avatar_type}] Starting rigging task for refine_id: {refine_id}")
            
            try:
                # Create rigging task using the refine task ID
                rigging_id = MediaGenerationService.create_rigging_task(
                    input_task_id=refine_id,
                    height_meters=1.7  # Default height, can be customized based on spec later
                )
                logger.info(f"[{avatar_type}] Rigging task started: {rigging_id}")
                
                # Wait for rigging to complete
                task_rigging = MediaGenerationService.wait_for_rigging(rigging_id, timeout_s=20*60, poll_s=5)
                logger.info(f"[{avatar_type}] Rigging completed")
                
                # Extract rigged model URL (prefer rigged GLB over unrigged)
                rigged_urls = task_rigging.get("model_urls") or {}
                rigged_glb = rigged_urls.get("glb") or urls.get("glb")  # Fallback to unrigged if rigged URL missing
                
                return {
                    "status": "SUCCEEDED",
                    "task_ids": {
                        "preview": preview_id,
                        "refine": refine_id,
                        "rigging": rigging_id
                    },
                    "model_glb": rigged_glb,  # Use rigged GLB
                    "model_obj": urls.get("obj"),  # Keep original OBJ
                    "texture_base_color": texture_base_color_url,
                    "thumbnail_url": task_refine.get("thumbnail_url"),
                    "progress": task_rigging.get("progress") or task_refine.get("progress"),
                    "rigged": True  # Flag to indicate this is rigged
                }
            except Exception as rigging_error:
                # If rigging fails, log warning but continue with unrigged model
                logger.warning(f"[{avatar_type}] Rigging failed, using unrigged model: {rigging_error}")
                
                return {
                    "status": "SUCCEEDED",
                    "task_ids": {
                        "preview": preview_id,
                        "refine": refine_id,
                        "rigging": None  # Rigging failed
                    },
                    "model_glb": urls.get("glb"),  # Use unrigged GLB as fallback
                    "model_obj": urls.get("obj"),
                    "texture_base_color": texture_base_color_url,
                    "thumbnail_url": task_refine.get("thumbnail_url"),
                    "progress": task_refine.get("progress"),
                    "rigged": False,  # Flag to indicate rigging failed
                    "rigging_error": str(rigging_error)
                }
        except Exception as e:
            logger.error(f"[{avatar_type}] Avatar generation failed: {e}")
            raise

    @staticmethod
    def _update_progress(avatar_id: str, stage: str, progress_percent: int, message: str = None, 
                        partial_data: Optional[Dict[str, Any]] = None):
        """
        Update avatar generation progress in Firestore.
        
        Args:
            avatar_id: Avatar ID
            stage: Current stage (e.g., "extracting_spec", "base_preview", "base_refine", etc.)
            progress_percent: Progress percentage (0-100)
            message: Optional status message
            partial_data: Optional partial data to save
        """
        try:
            progress_data = {
                "status": "processing",
                "stage": stage,
                "progress_percent": progress_percent,
                "updated_at": firestore.SERVER_TIMESTAMP
            }
            
            if message:
                progress_data["status_message"] = message
            
            if partial_data:
                progress_data.update(partial_data)
            
            db.collection('avatars').document(avatar_id).set(progress_data, merge=True)
            logger.info(f"[{avatar_id}] Progress: {stage} ({progress_percent}%) - {message or ''}")
        except Exception as e:
            logger.error(f"Error updating progress: {e}")

    @staticmethod
    def _generate_single_avatar_with_retry(prompt: str, avatar_type: str, avatar_id: str,
                                           art_style: Optional[str] = None, 
                                           ai_model: Optional[str] = None,
                                           max_retries: int = 3) -> Tuple[Optional[Dict[str, Any]], int]:
        """
        Generate a single avatar with automatic retry on failure.
        
        Args:
            prompt: The prompt to use for generation
            avatar_type: "base" or "clothed"
            avatar_id: Avatar ID for progress tracking
            art_style: Optional art style
            ai_model: Optional AI model
            max_retries: Maximum number of retry attempts
            
        Returns:
            Tuple of (result_dict or None, retry_count)
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    MediaGenerationService._update_progress(
                        avatar_id, f"{avatar_type}_retry_{attempt}", 
                        10,
                        f"Retrying {avatar_type} avatar generation (attempt {attempt + 1}/{max_retries})..."
                    )
                    logger.info(f"[{avatar_id}] Retrying {avatar_type} avatar generation (attempt {attempt + 1}/{max_retries})")
                    time.sleep(5 * attempt)  # Exponential backoff: 0s, 5s, 10s
                
                result = MediaGenerationService._generate_single_avatar(
                    prompt=prompt,
                    avatar_type=avatar_type,
                    art_style=art_style,
                    ai_model=ai_model,
                    avatar_id=avatar_id
                )
                
                # Success - return result with retry count
                logger.info(f"[{avatar_id}] {avatar_type.capitalize()} avatar generated successfully on attempt {attempt + 1}")
                return result, attempt  # Return result and number of retries needed
                
            except Exception as e:
                last_error = e
                logger.warning(f"[{avatar_id}] {avatar_type.capitalize()} avatar generation attempt {attempt + 1} failed: {e}")
                
                if attempt < max_retries - 1:
                    # Will retry
                    continue
                else:
                    # All retries exhausted
                    logger.error(f"[{avatar_id}] {avatar_type.capitalize()} avatar generation failed after {max_retries} attempts: {e}")
                    return None, max_retries  # Return None and retry count
        
        return None, max_retries

    @staticmethod
    def create_rigging_task(*,
                            input_task_id: Optional[str] = None,
                            model_url: Optional[str] = None,
                            height_meters: float = 1.7,
                            texture_image_url: Optional[str] = None) -> str:
        """
        Create a rigging task for a generated avatar.
        
        Args:
            input_task_id: The refine task ID from Meshy (preferred)
            model_url: Direct model URL (alternative to input_task_id)
            height_meters: Height of the avatar in meters (default 1.7)
            texture_image_url: Optional texture image URL
            
        Returns:
            Rigging task ID
        """
        if input_task_id is None and model_url is None:
            raise ValueError("Provide exactly one of: input_task_id OR model_url")

        payload: Dict[str, Any] = {
            "height_meters": height_meters,
        }
        if input_task_id:
            payload["input_task_id"] = input_task_id
        else:
            payload["model_url"] = model_url

        if texture_image_url:
            payload["texture_image_url"] = texture_image_url

        r = requests.post(f"{BASE_URL}/openapi/v1/rigging", headers=MediaGenerationService._headers(), json=payload, timeout=60)
        r.raise_for_status()
        task_id = r.json()["result"]
        return task_id

    @staticmethod
    def get_rigging_task(task_id: str) -> Dict[str, Any]:
        """
        Get the status of a rigging task.
        
        Args:
            task_id: The rigging task ID
            
        Returns:
            Task status dictionary
        """
        r = requests.get(f"{BASE_URL}/openapi/v1/rigging/{task_id}", headers=MediaGenerationService._headers(), timeout=60)
        r.raise_for_status()
        return r.json()

    @staticmethod
    def wait_for_rigging(task_id: str, *, timeout_s: int = 20 * 60, poll_s: int = 5) -> Dict[str, Any]:
        """
        Polls until SUCCEEDED/FAILED or timeout.
        
        Args:
            task_id: The rigging task ID
            timeout_s: Maximum time to wait in seconds (default 20 minutes)
            poll_s: Polling interval in seconds (default 5)
            
        Returns:
            Completed task dictionary with rigged model URL
        """
        start = time.time()
        while True:
            task = MediaGenerationService.get_rigging_task(task_id)
            status = task.get("status")
            progress = task.get("progress")
            logger.info(f"[rigging] Task {task_id}: status={status}, progress={progress}")

            if status == "SUCCEEDED":
                return task
            if status in ("FAILED", "CANCELED"):
                err = (task.get("task_error") or {}).get("message")
                raise RuntimeError(f"Rigging failed: {err or task}")
            
            if time.time() - start > timeout_s:
                raise TimeoutError(f"Rigging timed out after {timeout_s}s: {task_id}")

            time.sleep(poll_s)

    @staticmethod
    def _upload_avatar_to_storage_safe(glb_url: str, avatar_id: str, avatar_type: str, 
                                      avatar_result: Dict[str, Any]) -> bool:
        """
        Safely upload avatar GLB to Firebase Storage and update result.
        
        Returns:
            True if upload successful, False otherwise
        """
        try:
            if not glb_url:
                logger.warning(f"[{avatar_id}] No GLB URL for {avatar_type} avatar")
                return False
            
            storage_url = MediaGenerationService._save_avatar_to_storage(
                glb_url=glb_url,
                avatar_id=avatar_id,
                avatar_type=avatar_type
            )
            
            if storage_url:
                avatar_result["storage_glb_url"] = storage_url
                return True
            return False
        except Exception as e:
            logger.error(f"[{avatar_id}] Error uploading {avatar_type} GLB: {e}")
            return False

    @staticmethod
    def _generate_3d_avatar_sync(avatar_id: str, user_text: str, spec: AvatarSpec, 
                                 clothed_prompt: str, spec_dict: Dict[str, Any],
                                 art_style: Optional[str] = None, ai_model: Optional[str] = None,
                                 api_key: Optional[str] = None, user_id: Optional[str] = None):
        """
        Synchronous avatar generation (runs in background thread).
        Generates only the clothed avatar with retry logic.
        Updates progress in Firestore at each stage.
        """
        results = {
            "avatar_id": avatar_id,
            "user_id": user_id,
            "user_prompt": user_text,
            "clothed_prompt": clothed_prompt,
            "spec": spec_dict,
            "created_at": datetime.now().isoformat(),
            "clothed_avatar": None,
            "status": "processing",
            "retry_info": {
                "clothed_retries": 0,
                "clothed_failed": False
            }
        }

        clothed_result = None
        clothed_success = False

        try:
            # Generate clothed avatar with retry
            MediaGenerationService._update_progress(
                avatar_id, "clothed_preview", 10,
                "Starting avatar preview generation..."
            )
            logger.info(f"[{avatar_id}] Generating clothed avatar...")
            
            try:
                clothed_result, clothed_retry_count = MediaGenerationService._generate_single_avatar_with_retry(
                    prompt=clothed_prompt,
                    avatar_type="clothed",
                    avatar_id=avatar_id,
                    art_style=art_style,
                    ai_model=ai_model,
                    max_retries=3
                )
                
                if clothed_result:
                    clothed_success = True
                    results["clothed_avatar"] = clothed_result
                    results["retry_info"]["clothed_retries"] = clothed_retry_count
                    
                    # Save clothed avatar immediately
                    MediaGenerationService._update_progress(
                        avatar_id, "clothed_complete", 80,
                        "Avatar generated successfully",
                        {
                            "clothed_avatar": clothed_result,
                            "retry_info": results["retry_info"]
                        }
                    )
                    
                    # Upload clothed GLB immediately
                    clothed_glb_url = clothed_result.get("model_glb")
                    if clothed_glb_url:
                        MediaGenerationService._update_progress(
                            avatar_id, "uploading_clothed", 85,
                            "Uploading avatar GLB..."
                        )
                        MediaGenerationService._upload_avatar_to_storage_safe(
                            clothed_glb_url, avatar_id, "clothed", clothed_result
                        )
                        results["clothed_avatar"] = clothed_result
                    
                    # Save progress to database
                    MediaGenerationService._save_avatar_to_database(
                        avatar_spec=spec,
                        avatar_data=results,
                        user_id=user_id
                    )
                    logger.info(f"[{avatar_id}] Clothed avatar generated and saved successfully")
                else:
                    results["retry_info"]["clothed_failed"] = True
                    logger.error(f"[{avatar_id}] Clothed avatar generation failed after all retries")
                    
            except Exception as clothed_error:
                results["retry_info"]["clothed_failed"] = True
                logger.error(f"[{avatar_id}] Clothed avatar generation failed: {clothed_error}")

            # Handle final status
            if clothed_success:
                # Succeeded - finalize
                MediaGenerationService._update_progress(
                    avatar_id, "finalizing", 95,
                    "Finalizing avatar data..."
                )
                
                results["status"] = "SUCCEEDED"
                MediaGenerationService._save_avatar_to_database(
                    avatar_spec=spec,
                    avatar_data=results,
                    user_id=user_id
                )
                
                MediaGenerationService._update_progress(
                    avatar_id, "completed", 100,
                    "Avatar generation completed successfully",
                    {
                        "status": "SUCCEEDED",
                        "clothed_avatar": clothed_result
                    }
                )
                logger.info(f"[{avatar_id}] ✅ Avatar generation completed successfully")
            else:
                # Failed
                results["status"] = "FAILED"
                results["error"] = "Avatar generation failed after retries"
                results["retry_info"]["clothed_failed"] = True
                
                MediaGenerationService._save_avatar_to_database(
                    avatar_spec=spec,
                    avatar_data=results,
                    user_id=user_id
                )
                
                MediaGenerationService._update_progress(
                    avatar_id, "failed", 0,
                    "Avatar generation failed after retries",
                    {
                        "status": "FAILED",
                        "error": results["error"],
                        "retry_info": results["retry_info"]
                    }
                )
                logger.error(f"[{avatar_id}] ❌ Avatar generation failed after retries")

        except Exception as e:
            logger.error(f"[{avatar_id}] Avatar generation error: {e}")
            results["status"] = "FAILED"
            results["error"] = str(e)
            
            # Save whatever progress we have
            try:
                MediaGenerationService._save_avatar_to_database(
                    avatar_spec=spec,
                    avatar_data=results,
                    user_id=user_id
                )
            except Exception as db_error:
                logger.error(f"[{avatar_id}] Failed to save error state to database: {db_error}")
            
            MediaGenerationService._update_progress(
                avatar_id, "failed", 0,
                f"Generation failed: {str(e)}",
                {"status": "FAILED", "error": str(e)}
            )

    @staticmethod
    def generate_3d_avatar(user_text: str,
                        art_style: Optional[str] = None,
                        ai_model: Optional[str] = None,
                        api_key: Optional[str] = None,
                        user_id: Optional[str] = None,
                        async_mode: bool = True):
        """
        Generate clothed avatar from user text prompt.
        
        Args:
            user_text: User's text prompt
            art_style: Optional art style
            ai_model: Optional AI model
            api_key: Optional OpenAI API key
            user_id: Optional user ID to associate with avatars
            async_mode: If True, starts background thread and returns immediately
            
        Returns:
            Dictionary with avatar_id and status (if async) or full results (if sync)
        """
        # Extract avatar spec and build prompts
        spec, base_prompt, clothed_prompt = MediaGenerationService.build_prompts_from_text(
            user_text, api_key=api_key
        )

        # Convert spec to dict for storage
        try:
            spec_dict = spec.model_dump()
        except AttributeError:
            try:
                from dataclasses import asdict
                spec_dict = asdict(spec)
            except Exception:
                spec_dict = spec.dict() if hasattr(spec, 'dict') else dict(spec)

        timestamp = datetime.now()
        avatar_id = str(uuid.uuid4())
        
        # Update progress after avatar_id is created
        MediaGenerationService._update_progress(avatar_id, "extracting_spec", 5, "Extracted avatar specifications")
        
        # Create initial record in Firestore
        initial_data = {
            "avatar_id": avatar_id,
            "user_id": user_id,
            "user_prompt": user_text,
            "clothed_prompt": clothed_prompt,
            "spec": spec_dict,
            "created_at": firestore.SERVER_TIMESTAMP,
            "status": "processing",
            "stage": "initializing",
            "progress_percent": 0,
            "status_message": "Initializing avatar generation...",
            "clothed_avatar": None
        }
        
        db.collection('avatars').document(avatar_id).set(initial_data, merge=True)
        
        # If user_id provided, create reference in user's subcollection
        if user_id:
            user_avatar_ref = db.collection('users').document(user_id).collection('avatars').document(avatar_id)
            user_avatar_ref.set({
                "avatar_id": avatar_id,
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "processing"
            }, merge=True)

        if async_mode:
            # Start background thread for generation
            thread = Thread(
                target=MediaGenerationService._generate_3d_avatar_sync,
                args=(avatar_id, user_text, spec, clothed_prompt, spec_dict,
                      art_style, ai_model, api_key, user_id),
                daemon=True
            )
            thread.start()
            logger.info(f"[{avatar_id}] Started background avatar generation thread")
            
            # Return immediately with avatar_id
            return {
                "success": True,
                "avatar_id": avatar_id,
                "status": "processing",
                "message": "Avatar generation started. Poll /api/get-avatar/<avatar_id> for progress."
            }
        else:
            # Synchronous mode (for testing or direct calls)
            MediaGenerationService._generate_3d_avatar_sync(
                avatar_id, user_text, spec, clothed_prompt, spec_dict,
                art_style, ai_model, api_key, user_id
            )
            
            # Fetch final result
            final_data = db.collection('avatars').document(avatar_id).get()
            if final_data.exists:
                result = final_data.to_dict()
                clothed_avatar = result.get("clothed_avatar", {}) or {}
                return {
                    "success": result.get("status") == "SUCCEEDED",
                    "avatar_id": avatar_id,
                    "clothed_avatar": clothed_avatar,
                    "spec": spec_dict,
                    "clothed_glb_url": clothed_avatar.get("storage_glb_url") or clothed_avatar.get("model_glb")
                }
            else:
                return {
                    "success": False,
                    "error": "Avatar generation failed",
                    "avatar_id": avatar_id
                }

    @staticmethod
    def _save_avatar_to_database(avatar_spec: AvatarSpec, avatar_data: Dict[str, Any], 
                                 user_id: Optional[str] = None) -> str:
        """
        Save avatar information to Firebase Firestore.
        
        Args:
            avatar_spec: The AvatarSpec object with extracted information
            avatar_data: Dictionary containing avatar generation results
            user_id: Optional user ID to associate with the avatar
            
        Returns:
            Document ID of the saved avatar
        """
        try:
            # Convert spec to dict if needed
            try:
                spec_dict = avatar_spec.model_dump()
            except AttributeError:
                try:
                    from dataclasses import asdict
                    spec_dict = asdict(avatar_spec)
                except Exception:
                    spec_dict = avatar_spec.dict() if hasattr(avatar_spec, 'dict') else dict(avatar_spec)

            # Prepare document data
            avatar_doc = {
                "avatar_id": avatar_data.get("avatar_id"),
                "user_id": user_id,
                "user_prompt": avatar_data.get("user_prompt"),
                "clothed_prompt": avatar_data.get("clothed_prompt"),
                "spec": spec_dict,
                "clothed_avatar": avatar_data.get("clothed_avatar"),
                "status": avatar_data.get("status", "processing"),
                "created_at": firestore.SERVER_TIMESTAMP,
                "updated_at": firestore.SERVER_TIMESTAMP
            }

            # Add error if present
            if "error" in avatar_data:
                avatar_doc["error"] = avatar_data["error"]

            # Save to Firestore
            avatar_id = avatar_data.get("avatar_id")
            if not avatar_id:
                avatar_id = str(uuid.uuid4())
                avatar_doc["avatar_id"] = avatar_id

            # Save to 'avatars' collection
            db.collection('avatars').document(avatar_id).set(avatar_doc, merge=True)
            logger.info(f"✅ Saved avatar to Firestore: {avatar_id}")

            # If user_id provided, also create a reference in user's subcollection
            if user_id:
                user_avatar_ref = db.collection('users').document(user_id).collection('avatars').document(avatar_id)
                user_avatar_ref.set({
                    "avatar_id": avatar_id,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "status": avatar_data.get("status", "processing")
                }, merge=True)
                logger.info(f"✅ Saved avatar reference for user: {user_id}")

            return avatar_id

        except Exception as e:
            logger.error(f"❌ Error saving avatar to database: {e}")
            raise

    @staticmethod
    def _save_avatar_to_storage(glb_url: str, avatar_id: str, avatar_type: str) -> Optional[str]:
        """
        Download GLB file from Meshy URL and upload to Firebase Storage.
        
        Args:
            glb_url: URL of the GLB file from Meshy
            avatar_id: Unique avatar ID
            avatar_type: "clothed" (avatar type identifier)
            
        Returns:
            Public URL of the uploaded file, or None if upload fails
        """
        try:
            if not glb_url or not storage:
                logger.warning("GLB URL or storage not available, skipping storage upload")
                return None

            # Download GLB file from Meshy
            logger.info(f"Downloading {avatar_type} GLB from Meshy...")
            response = requests.get(glb_url, timeout=60)
            response.raise_for_status()

            # Upload to Firebase Storage
            blob_name = f"avatars/{avatar_id}/{avatar_type}_avatar.glb"
            bucket = storage.bucket()
            blob = bucket.blob(blob_name)
            blob.upload_from_string(response.content, content_type='model/gltf-binary')
            blob.make_public()
            
            public_url = blob.public_url
            logger.info(f"✅ Uploaded {avatar_type} GLB to Firebase Storage: {public_url}")
            return public_url

        except Exception as e:
            logger.error(f"❌ Error uploading {avatar_type} GLB to storage: {e}")
            # Don't fail the entire process if storage upload fails
            return None

    @staticmethod
    def get_avatar_by_id(avatar_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve avatar data from Firestore by avatar_id.
        Includes progress information if still processing.
        
        Args:
            avatar_id: The avatar ID to retrieve
            
        Returns:
            Avatar data dictionary with progress info or None if not found
        """
        try:
            avatar_doc = db.collection('avatars').document(avatar_id).get()
            if avatar_doc.exists:
                data = avatar_doc.to_dict()
                # Ensure progress fields exist for frontend
                if "progress_percent" not in data:
                    data["progress_percent"] = 0
                if "stage" not in data:
                    data["stage"] = data.get("status", "unknown")
                if "status_message" not in data:
                    data["status_message"] = data.get("status", "processing")
                return data
            return None
        except Exception as e:
            logger.error(f"Error retrieving avatar {avatar_id}: {e}")
            return None

    @staticmethod
    def get_user_avatars(user_id: str) -> List[Dict[str, Any]]:
        """
        Retrieve all avatars for a specific user.
        
        Args:
            user_id: The user ID
            
        Returns:
            List of avatar data dictionaries
        """
        try:
            avatars = []
            # Get from user's subcollection
            user_avatars_ref = db.collection('users').document(user_id).collection('avatars')
            for doc in user_avatars_ref.stream():
                avatar_id = doc.to_dict().get("avatar_id")
                if avatar_id:
                    avatar_data = MediaGenerationService.get_avatar_by_id(avatar_id)
                    if avatar_data:
                        avatars.append(avatar_data)
            return avatars
        except Exception as e:
            logger.error(f"Error retrieving avatars for user {user_id}: {e}")
            return []

    @staticmethod
    def find_stuck_generations(stuck_threshold_minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Find avatar generations that appear to be stuck (processing for too long).
        
        Args:
            stuck_threshold_minutes: Minutes after which a generation is considered stuck (default: 60)
            
        Returns:
            List of stuck avatar documents
        """
        try:
            stuck_avatars = []
            threshold_time = datetime.now(timezone.utc) - timedelta(minutes=stuck_threshold_minutes)
            
            # Query avatars with status "processing" that haven't been updated recently
            avatars_ref = db.collection('avatars')
            query = avatars_ref.where('status', '==', 'processing')
            
            for doc in query.stream():
                avatar_data = doc.to_dict()
                avatar_id = doc.id
                
                # Check updated_at timestamp
                updated_at = avatar_data.get('updated_at')
                if updated_at:
                    # Handle Firestore Timestamp
                    if hasattr(updated_at, 'timestamp'):
                        updated_datetime = datetime.fromtimestamp(updated_at.timestamp(), tz=timezone.utc)
                    elif isinstance(updated_at, datetime):
                        updated_datetime = updated_at
                        if updated_datetime.tzinfo is None:
                            updated_datetime = updated_datetime.replace(tzinfo=timezone.utc)
                    else:
                        # Fallback: check created_at
                        created_at = avatar_data.get('created_at')
                        if created_at:
                            if hasattr(created_at, 'timestamp'):
                                updated_datetime = datetime.fromtimestamp(created_at.timestamp(), tz=timezone.utc)
                            elif isinstance(created_at, datetime):
                                updated_datetime = created_at
                                if updated_datetime.tzinfo is None:
                                    updated_datetime = updated_datetime.replace(tzinfo=timezone.utc)
                            else:
                                continue
                        else:
                            continue
                    
                    # Check if stuck
                    if updated_datetime < threshold_time:
                        avatar_data['avatar_id'] = avatar_id
                        avatar_data['stuck_since'] = updated_datetime.isoformat()
                        stuck_avatars.append(avatar_data)
                else:
                    # No updated_at, check created_at
                    created_at = avatar_data.get('created_at')
                    if created_at:
                        if hasattr(created_at, 'timestamp'):
                            created_datetime = datetime.fromtimestamp(created_at.timestamp(), tz=timezone.utc)
                        elif isinstance(created_at, datetime):
                            created_datetime = created_at
                            if created_datetime.tzinfo is None:
                                created_datetime = created_datetime.replace(tzinfo=timezone.utc)
                        else:
                            continue
                        
                        if created_datetime < threshold_time:
                            avatar_data['avatar_id'] = avatar_id
                            avatar_data['stuck_since'] = created_datetime.isoformat()
                            stuck_avatars.append(avatar_data)
            
            logger.info(f"Found {len(stuck_avatars)} stuck avatar generations")
            return stuck_avatars
            
        except Exception as e:
            logger.error(f"Error finding stuck generations: {e}")
            return []

    @staticmethod
    def check_meshy_task_status(task_id: str) -> Optional[Dict[str, Any]]:
        """
        Check the status of a Meshy task to see if it's actually stuck or completed.
        
        Args:
            task_id: Meshy task ID
            
        Returns:
            Task status dictionary or None if task not found
        """
        try:
            task_data = MediaGenerationService.get_task(task_id)
            return task_data
        except Exception as e:
            logger.warning(f"Error checking Meshy task {task_id}: {e}")
            return None

    @staticmethod
    def cleanup_stuck_generation(avatar_id: str, force_retry: bool = False) -> Dict[str, Any]:
        """
        Clean up a stuck avatar generation by either retrying or marking as failed.
        
        Args:
            avatar_id: Avatar ID to clean up
            force_retry: If True, retry the generation. If False, mark as failed.
            
        Returns:
            Dictionary with cleanup result
        """
        try:
            avatar_data = MediaGenerationService.get_avatar_by_id(avatar_id)
            if not avatar_data:
                return {
                    "success": False,
                    "error": "Avatar not found",
                    "avatar_id": avatar_id
                }
            
            status = avatar_data.get("status")
            if status != "processing":
                return {
                    "success": False,
                    "error": f"Avatar is not in processing status (current: {status})",
                    "avatar_id": avatar_id,
                    "current_status": status
                }
            
            # Check if we have task IDs to verify
            clothed_avatar = avatar_data.get("clothed_avatar", {})
            
            clothed_task_ids = clothed_avatar.get("task_ids", {}) if clothed_avatar else {}
            
            # Check Meshy task statuses
            clothed_stuck = False
            
            if clothed_task_ids:
                refine_id = clothed_task_ids.get("refine")
                if refine_id:
                    task_status = MediaGenerationService.check_meshy_task_status(refine_id)
                    if task_status:
                        task_progress = task_status.get("progress", 0)
                        if task_progress < 100:
                            clothed_stuck = True
                            logger.info(f"[{avatar_id}] Avatar task {refine_id} appears stuck (progress: {task_progress}%)")
            
            if force_retry:
                # Retry the generation
                logger.info(f"[{avatar_id}] Retrying stuck avatar generation...")
                
                # Get original prompts
                user_text = avatar_data.get("user_prompt", "")
                clothed_prompt = avatar_data.get("clothed_prompt", "")
                spec_dict = avatar_data.get("spec", {})
                user_id = avatar_data.get("user_id")
                
                if not user_text or not clothed_prompt:
                    return {
                        "success": False,
                        "error": "Missing required data for retry",
                        "avatar_id": avatar_id
                    }
                
                # Reconstruct AvatarSpec from dict
                try:
                    spec = AvatarSpec(**spec_dict)
                except Exception as e:
                    logger.warning(f"[{avatar_id}] Could not reconstruct AvatarSpec, will extract from text: {e}")
                    # Fallback: extract from user text
                    spec, _, clothed_prompt = MediaGenerationService.build_prompts_from_text(user_text)
                    spec_dict = spec.model_dump() if hasattr(spec, 'model_dump') else spec.dict()
                
                # Update status to indicate retry
                MediaGenerationService._update_progress(
                    avatar_id, "retry_cleanup", 0,
                    "Retrying stuck avatar generation..."
                )
                
                # Start new generation thread
                thread = Thread(
                    target=MediaGenerationService._generate_3d_avatar_sync,
                    args=(avatar_id, user_text, spec, clothed_prompt, spec_dict,
                          None, None, None, user_id),
                    daemon=True
                )
                thread.start()
                
                return {
                    "success": True,
                    "action": "retry",
                    "avatar_id": avatar_id,
                    "message": "Avatar generation retry initiated"
                }
            else:
                # Mark as failed
                logger.info(f"[{avatar_id}] Marking stuck avatar generation as failed...")
                
                error_msg = "Avatar generation stuck and timed out"
                if clothed_stuck:
                    error_msg = "Avatar task stuck"
                
                # Update status
                cleanup_data = {
                    "status": "FAILED",
                    "error": error_msg,
                    "cleanup_reason": "stuck_generation",
                    "cleaned_up_at": datetime.now(timezone.utc).isoformat(),
                    "stage": "cleanup",
                    "progress_percent": 0,
                    "status_message": f"Generation stuck and marked as failed: {error_msg}"
                }
                
                db.collection('avatars').document(avatar_id).set(cleanup_data, merge=True)
                
                # Update user reference if exists
                if user_id:
                    user_avatar_ref = db.collection('users').document(user_id).collection('avatars').document(avatar_id)
                    user_avatar_ref.set({"status": "FAILED"}, merge=True)
                
                return {
                    "success": True,
                    "action": "failed",
                    "avatar_id": avatar_id,
                    "message": f"Avatar marked as failed: {error_msg}"
                }
                
        except Exception as e:
            logger.error(f"Error cleaning up stuck generation {avatar_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "avatar_id": avatar_id
            }

    @staticmethod
    def cleanup_all_stuck_generations(stuck_threshold_minutes: int = 60, 
                                     force_retry: bool = False,
                                     max_cleanup: int = 50) -> Dict[str, Any]:
        """
        Find and clean up all stuck avatar generations.
        
        Args:
            stuck_threshold_minutes: Minutes after which a generation is considered stuck
            force_retry: If True, retry stuck generations. If False, mark as failed.
            max_cleanup: Maximum number of avatars to clean up in one run
            
        Returns:
            Dictionary with cleanup summary
        """
        try:
            stuck_avatars = MediaGenerationService.find_stuck_generations(stuck_threshold_minutes)
            
            if not stuck_avatars:
                return {
                    "success": True,
                    "cleaned": 0,
                    "message": "No stuck generations found"
                }
            
            # Limit cleanup
            stuck_avatars = stuck_avatars[:max_cleanup]
            
            results = {
                "success": True,
                "found": len(stuck_avatars),
                "cleaned": 0,
                "retried": 0,
                "failed": 0,
                "errors": []
            }
            
            for avatar_data in stuck_avatars:
                avatar_id = avatar_data.get("avatar_id")
                if not avatar_id:
                    continue
                
                cleanup_result = MediaGenerationService.cleanup_stuck_generation(
                    avatar_id, force_retry=force_retry
                )
                
                if cleanup_result.get("success"):
                    results["cleaned"] += 1
                    if cleanup_result.get("action") == "retry":
                        results["retried"] += 1
                    else:
                        results["failed"] += 1
                else:
                    results["errors"].append({
                        "avatar_id": avatar_id,
                        "error": cleanup_result.get("error", "Unknown error")
                    })
            
            logger.info(f"Cleanup complete: {results['cleaned']} avatars cleaned ({results['retried']} retried, {results['failed']} marked as failed)")
            return results
            
        except Exception as e:
            logger.error(f"Error in cleanup_all_stuck_generations: {e}")
            return {
                "success": False,
                "error": str(e),
                "cleaned": 0
            }

    @staticmethod
    def start_cleanup_scheduler(interval_minutes: int = 30, 
                               stuck_threshold_minutes: int = 60,
                               force_retry: bool = False,
                               max_cleanup: int = 50):
        """
        Start a background thread that periodically cleans up stuck avatar generations.
        
        Args:
            interval_minutes: How often to run cleanup (default: 30 minutes)
            stuck_threshold_minutes: Minutes after which a generation is considered stuck
            force_retry: If True, retry stuck generations. If False, mark as failed.
            max_cleanup: Maximum number of avatars to clean up per run
        """
        global _cleanup_scheduler_running, _cleanup_scheduler_thread
        
        if _cleanup_scheduler_running:
            logger.warning("Cleanup scheduler is already running")
            return
        
        _cleanup_scheduler_running = True
        
        def cleanup_loop():
            """Background loop for periodic cleanup"""
            global _cleanup_scheduler_running
            logger.info(f"Started avatar cleanup scheduler (interval: {interval_minutes} minutes)")
            
            while _cleanup_scheduler_running:
                try:
                    logger.info("Running scheduled cleanup for stuck avatar generations...")
                    result = MediaGenerationService.cleanup_all_stuck_generations(
                        stuck_threshold_minutes=stuck_threshold_minutes,
                        force_retry=force_retry,
                        max_cleanup=max_cleanup
                    )
                    
                    if result.get("cleaned", 0) > 0:
                        logger.info(f"Cleanup completed: {result.get('cleaned')} avatars cleaned "
                                  f"({result.get('retried')} retried, {result.get('failed')} marked as failed)")
                    else:
                        logger.debug("No stuck avatars found")
                    
                    # Sleep until next run
                    sleep_seconds = interval_minutes * 60
                    for _ in range(sleep_seconds):
                        if not _cleanup_scheduler_running:
                            break
                        time.sleep(1)
                        
                except Exception as e:
                    logger.error(f"Error in cleanup scheduler loop: {e}")
                    # Wait 5 minutes before retrying on error
                    for _ in range(300):
                        if not _cleanup_scheduler_running:
                            break
                        time.sleep(1)
            
            logger.info("Avatar cleanup scheduler stopped")
        
        _cleanup_scheduler_thread = Thread(target=cleanup_loop, daemon=True)
        _cleanup_scheduler_thread.start()
        logger.info("Avatar cleanup scheduler started")

    @staticmethod
    def stop_cleanup_scheduler():
        """
        Stop the background cleanup scheduler.
        """
        global _cleanup_scheduler_running, _cleanup_scheduler_thread
        
        if not _cleanup_scheduler_running:
            logger.warning("Cleanup scheduler is not running")
            return
        
        _cleanup_scheduler_running = False
        
        if _cleanup_scheduler_thread:
            _cleanup_scheduler_thread.join(timeout=5)
        
        logger.info("Avatar cleanup scheduler stopped")

    @staticmethod
    def is_cleanup_scheduler_running() -> bool:
        """
        Check if the cleanup scheduler is currently running.
        
        Returns:
            True if scheduler is running, False otherwise
        """
        global _cleanup_scheduler_running
        return _cleanup_scheduler_running
