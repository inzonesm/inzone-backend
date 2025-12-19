# routes/media/generation.py
from flask import Blueprint, request, jsonify
from services.media.media_generation_service import MediaGenerationService
import logging

logger = logging.getLogger(__name__)

media_generation_bp = Blueprint('media_generation', __name__)

@media_generation_bp.route('/api/image', methods=['POST'])
def image_generate():
    try:
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({"error": "Missing 'prompt' in request"}), 400

        prompt = data['prompt']
        return MediaGenerationService.generate_image(prompt)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': 'Internal server error'}), 500

@media_generation_bp.route("/api/generate_3d_avatar", methods=["POST"])
def generate_3d_avatar():
    """
    Generate 3D avatar from user text prompt.
    
    Flow:
    1. Extract user text from request
    2. Use GPT-4 to extract structured avatar information and build prompts
    3. Generate 3D avatar using Meshy API with enhanced prompt
    4. Save avatar information to database
    5. Return avatar URLs and metadata
    """
    try:
        # Step 1: Extract and validate user text from request
        data = request.get_json()
        if not data or 'prompt' not in data:
            return jsonify({
                "error": "Missing 'prompt' in request",
                "code": "INVALID_REQUEST"
            }), 400
        
        user_text = data.get("prompt")
        if not user_text or not isinstance(user_text, str) or not user_text.strip():
            return jsonify({
                "error": "Invalid 'prompt'. Must be a non-empty string.",
                "code": "INVALID_PROMPT"
            }), 400
        
        # Extract user_id if provided
        user_id = data.get("user_id")
        
        # Optional: Extract art_style and ai_model if provided
        art_style = data.get("art_style")
        ai_model = data.get("ai_model")
        
        # Step 2: Start avatar generation (async mode - returns immediately)
        # This method:
        # - Extracts avatar spec with GPT-4
        # - Creates initial Firestore record
        # - Starts background thread for generation
        # - Returns avatar_id immediately
        result = MediaGenerationService.generate_3d_avatar(
            user_text=user_text,
            art_style=art_style,
            ai_model=ai_model,
            user_id=user_id,
            async_mode=True  # Async mode - returns immediately
        )
        
        # Step 3: Return immediately with avatar_id for polling
        return jsonify({
            "success": True,
            "avatar_id": result.get("avatar_id"),
            "status": "processing",
            "message": "Avatar generation started. Use GET /api/get-avatar/<avatar_id> to check progress.",
            "poll_url": f"/api/get-avatar/{result.get('avatar_id')}"
        }), 202  # 202 Accepted - request accepted for processing
        
    except ValueError as e:
        return jsonify({
            "error": str(e),
            "code": "VALIDATION_ERROR"
        }), 400
    except TimeoutError as e:
        return jsonify({
            "error": f"Avatar generation timed out: {str(e)}",
            "code": "TIMEOUT_ERROR"
        }), 504
    except Exception as e:
        import traceback
        logger.error(f"Error generating 3D avatar: {e}\n{traceback.format_exc()}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/get-avatar/<avatar_id>", methods=["GET"])
def get_avatar(avatar_id: str):
    """
    Retrieve avatar data by ID for Unity to use.
    
    Returns:
        Avatar data including GLB URLs and metadata
    """
    try:
        if not avatar_id:
            return jsonify({
                "error": "Missing avatar_id",
                "code": "INVALID_REQUEST"
            }), 400
        
        avatar_data = MediaGenerationService.get_avatar_by_id(avatar_id)
        
        if not avatar_data:
            return jsonify({
                "error": "Avatar not found",
                "code": "NOT_FOUND"
            }), 404
        
        # Extract GLB URLs (prefer storage URLs)
        clothed_avatar = avatar_data.get("clothed_avatar", {}) or {}
        status = avatar_data.get("status", "processing")
        retry_info = avatar_data.get("retry_info", {})
        
        response_data = {
            "success": status == "SUCCEEDED",
            "avatar_id": avatar_id,
            "status": status,
            "stage": avatar_data.get("stage", "unknown"),
            "progress_percent": avatar_data.get("progress_percent", 0),
            "status_message": avatar_data.get("status_message", "Processing..."),
            "data": {
                "spec": avatar_data.get("spec"),
                "user_prompt": avatar_data.get("user_prompt"),
                "created_at": avatar_data.get("created_at")
            }
        }
        
        # Add retry information if available
        if retry_info:
            response_data["retry_info"] = retry_info
        
        # Add avatar data if available
        if clothed_avatar:
            response_data["data"]["clothed_avatar"] = clothed_avatar
            response_data["data"]["clothed_glb_url"] = clothed_avatar.get("storage_glb_url") or clothed_avatar.get("model_glb")
        
        # Handle different statuses
        if status == "SUCCEEDED":
            # Avatar ready - can proceed
            response_data["ready"] = True
            response_data["message"] = "Avatar generated successfully"
        elif status == "FAILED":
            # Failed
            response_data["ready"] = False
            response_data["error"] = avatar_data.get("error", "Unknown error")
            response_data["message"] = "Avatar generation failed"
        else:
            # Still processing
            response_data["ready"] = False
            response_data["message"] = "Avatar generation in progress..."
        
        # Return appropriate status code
        if status == "SUCCEEDED":
            status_code = 200
        elif status == "processing" or status == "partial_success":
            status_code = 202  # Still processing or retrying
        else:
            status_code = 500  # Failed
        
        return jsonify(response_data), status_code
        
    except Exception as e:
        logger.error(f"Error retrieving avatar: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/get-user-avatars", methods=["GET"])
def get_user_avatars():
    """
    Retrieve all avatars for a specific user.
    
    Query params:
        user_id: The user ID
    """
    try:
        user_id = request.args.get("user_id")
        if not user_id:
            return jsonify({
                "error": "Missing user_id parameter",
                "code": "INVALID_REQUEST"
            }), 400
        
        avatars = MediaGenerationService.get_user_avatars(user_id)
        
        return jsonify({
            "success": True,
            "count": len(avatars),
            "avatars": avatars
        }), 200
        
    except Exception as e:
        logger.error(f"Error retrieving user avatars: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/cleanup-stuck-avatars", methods=["POST"])
def cleanup_stuck_avatars():
    """
    Clean up stuck avatar generations.
    
    Request body (optional):
        {
            "stuck_threshold_minutes": 60,  # Minutes after which generation is considered stuck
            "force_retry": false,  # If true, retry stuck generations. If false, mark as failed.
            "max_cleanup": 50,  # Maximum number of avatars to clean up
            "avatar_id": null  # If provided, only clean up this specific avatar
        }
    """
    try:
        data = request.get_json() or {}
        
        stuck_threshold_minutes = data.get("stuck_threshold_minutes", 60)
        force_retry = data.get("force_retry", False)
        max_cleanup = data.get("max_cleanup", 50)
        avatar_id = data.get("avatar_id")
        
        if avatar_id:
            # Clean up specific avatar
            result = MediaGenerationService.cleanup_stuck_generation(
                avatar_id=avatar_id,
                force_retry=force_retry
            )
            
            if result.get("success"):
                return jsonify({
                    "success": True,
                    "message": result.get("message", "Avatar cleaned up"),
                    "action": result.get("action"),
                    "avatar_id": avatar_id
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": result.get("error", "Cleanup failed"),
                    "avatar_id": avatar_id
                }), 400
        else:
            # Clean up all stuck avatars
            result = MediaGenerationService.cleanup_all_stuck_generations(
                stuck_threshold_minutes=stuck_threshold_minutes,
                force_retry=force_retry,
                max_cleanup=max_cleanup
            )
            
            return jsonify({
                "success": result.get("success", True),
                "found": result.get("found", 0),
                "cleaned": result.get("cleaned", 0),
                "retried": result.get("retried", 0),
                "failed": result.get("failed", 0),
                "errors": result.get("errors", []),
                "message": result.get("message", "Cleanup completed")
            }), 200
            
    except Exception as e:
        logger.error(f"Error cleaning up stuck avatars: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/find-stuck-avatars", methods=["GET"])
def find_stuck_avatars():
    """
    Find avatar generations that appear to be stuck.
    
    Query params:
        stuck_threshold_minutes: Minutes after which a generation is considered stuck (default: 60)
    """
    try:
        stuck_threshold_minutes = int(request.args.get("stuck_threshold_minutes", 60))
        
        stuck_avatars = MediaGenerationService.find_stuck_generations(
            stuck_threshold_minutes=stuck_threshold_minutes
        )
        
        # Return summary info (not full data to avoid large responses)
        summary = []
        for avatar in stuck_avatars:
            summary.append({
                "avatar_id": avatar.get("avatar_id"),
                "user_id": avatar.get("user_id"),
                "stage": avatar.get("stage"),
                "progress_percent": avatar.get("progress_percent", 0),
                "stuck_since": avatar.get("stuck_since"),
                "status_message": avatar.get("status_message", "Processing...")
            })
        
        return jsonify({
            "success": True,
            "count": len(stuck_avatars),
            "stuck_avatars": summary
        }), 200
        
    except Exception as e:
        logger.error(f"Error finding stuck avatars: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/cleanup-scheduler/start", methods=["POST"])
def start_cleanup_scheduler():
    """
    Start the background cleanup scheduler for stuck avatar generations.
    
    Request body (optional):
        {
            "interval_minutes": 30,  # How often to run cleanup
            "stuck_threshold_minutes": 60,  # Minutes after which generation is considered stuck
            "force_retry": false,  # If true, retry stuck generations. If false, mark as failed.
            "max_cleanup": 50  # Maximum number of avatars to clean up per run
        }
    """
    try:
        data = request.get_json() or {}
        
        interval_minutes = data.get("interval_minutes", 30)
        stuck_threshold_minutes = data.get("stuck_threshold_minutes", 60)
        force_retry = data.get("force_retry", False)
        max_cleanup = data.get("max_cleanup", 50)
        
        MediaGenerationService.start_cleanup_scheduler(
            interval_minutes=interval_minutes,
            stuck_threshold_minutes=stuck_threshold_minutes,
            force_retry=force_retry,
            max_cleanup=max_cleanup
        )
        
        return jsonify({
            "success": True,
            "message": "Cleanup scheduler started",
            "interval_minutes": interval_minutes,
            "stuck_threshold_minutes": stuck_threshold_minutes
        }), 200
        
    except Exception as e:
        logger.error(f"Error starting cleanup scheduler: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/cleanup-scheduler/stop", methods=["POST"])
def stop_cleanup_scheduler():
    """
    Stop the background cleanup scheduler.
    """
    try:
        MediaGenerationService.stop_cleanup_scheduler()
        
        return jsonify({
            "success": True,
            "message": "Cleanup scheduler stopped"
        }), 200
        
    except Exception as e:
        logger.error(f"Error stopping cleanup scheduler: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500

@media_generation_bp.route("/api/cleanup-scheduler/status", methods=["GET"])
def get_cleanup_scheduler_status():
    """
    Get the status of the cleanup scheduler.
    """
    try:
        is_running = MediaGenerationService.is_cleanup_scheduler_running()
        
        return jsonify({
            "success": True,
            "running": is_running,
            "message": "Cleanup scheduler is running" if is_running else "Cleanup scheduler is not running"
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting cleanup scheduler status: {e}")
        return jsonify({
            "error": "Internal server error",
            "code": "INTERNAL_ERROR"
        }), 500