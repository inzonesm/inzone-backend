# 3D Avatar Generation System Documentation

## Overview

The 3D Avatar Generation System is an asynchronous pipeline that generates two 3D avatars (base/nude and clothed) from user text prompts using GPT-4 for prompt enhancement and Meshy API for 3D model generation. The system includes progress tracking, automatic retry logic, partial success handling, and stuck generation cleanup.

## Architecture

### Components

1. **Data Models** (`models/avatar_models.py`)
   - `AvatarSpec`: Structured representation of avatar characteristics
   - `Clothing`: Clothing items (top, bottom, shoes, outerwear, accessories)
   - `Item`: Individual clothing item with category, color, and notes

2. **Service Layer** (`services/media/media_generation_service.py`)
   - Core generation logic
   - Meshy API integration
   - OpenAI GPT-4 integration
   - Firebase Storage and Firestore operations
   - Progress tracking and cleanup

3. **API Routes** (`routes/media/generation.py`)
   - REST endpoints for avatar generation and retrieval
   - Cleanup and scheduler management endpoints

## Data Models

### AvatarSpec
Structured representation extracted from user text prompts:
- `style`: Art style (cartoon, anime, semi_realistic, realistic, low_poly, other)
- `species`: "human" or "non_humanoid"
- `body`: Skin tone, build, height hints
- `hair`: Color, style, length
- `clothing`: Clothing object with top, bottom, shoes, outerwear, accessories
- `palette`: Color palette list
- `pose`: Pose description
- `camera`: Camera angle description
- `notes`: Additional notes
- `confidence`: Confidence scores for extracted fields

### Clothing & Item
- `Clothing`: Container for clothing items
  - `top`, `bottom`, `shoes`, `outerwear`: Optional `Item` objects
  - `accessories`: List of accessory strings
- `Item`: Individual clothing item
  - `category`: Item type (e.g., "hoodie", "jeans", "sneakers")
  - `color`: Color description
  - `notes`: Additional details

## Generation Workflow

### 1. Prompt Processing
- User submits text prompt via API
- GPT-4 extracts structured `AvatarSpec` from text
- System generates two detailed prompts:
  - **Base prompt**: Neutral/nude avatar (for Unity customization)
  - **Clothed prompt**: Fully clothed avatar (for display)

### 2. Asynchronous Generation
- Generation runs in background thread (non-blocking)
- API returns immediately with `avatar_id` and `poll_url`
- Frontend polls for status updates

### 3. Dual Avatar Generation
- **Base Avatar**: Generated first (nude/neutral)
  - Saved immediately upon success
  - Uploaded to Firebase Storage
- **Clothed Avatar**: Generated second
  - Saved immediately upon success
  - Uploaded to Firebase Storage

### 4. Progress Tracking
Real-time progress updates stored in Firestore:
- `status`: "processing", "SUCCEEDED", "partial_success", "FAILED"
- `stage`: Current stage (e.g., "base_preview", "clothed_refine", "uploading_storage")
- `progress_percent`: 0-100
- `status_message`: Human-readable status message
- `retry_info`: Retry attempt counts and failure flags

### 5. Partial Success Handling
If one avatar succeeds and one fails:
- Successful avatar is saved immediately (prevents credit waste)
- Failed avatar is automatically retried (up to 3 attempts)
- Status set to "partial_success" during retry
- If retry succeeds → status becomes "SUCCEEDED"
- If retry fails → status remains "partial_success" with error details

### 6. Storage
- GLB files downloaded from Meshy
- Uploaded to Firebase Storage with public URLs
- URLs stored in Firestore for Unity access
- Format: `avatars/{avatar_id}/{type}_avatar.glb`

## Key Features

### Asynchronous Processing
- Non-blocking generation using background threads
- Immediate API response (HTTP 202 Accepted)
- Frontend polls for completion

### Progress Tracking
- Real-time status updates in Firestore
- Progress percentage (0-100)
- Stage information for debugging
- Status messages for user feedback

### Automatic Retry Logic
- Failed avatars retry automatically (up to 3 attempts)
- Exponential backoff between retries (0s, 5s, 10s)
- Retry counts tracked in `retry_info`
- Only failed avatars are retried (successful ones preserved)

### Partial Success Handling
- Saves successful avatars immediately
- Prevents regenerating successful avatars (saves credits)
- Automatically retries failed avatars
- Clear status indicators for frontend

### Stuck Generation Cleanup
- Detects avatars stuck in "processing" status
- Configurable threshold (default: 60 minutes)
- Two cleanup modes:
  - **Retry**: Restart generation for stuck avatar
  - **Mark as Failed**: Mark as failed with reason
- Bulk cleanup for multiple stuck avatars
- Optional background scheduler for automatic cleanup

## API Endpoints

### Avatar Generation

#### `POST /api/generate_3d_avatar`
Generate 3D avatars from text prompt.

**Request Body:**
```json
{
  "prompt": "A tall anime character with blue hair wearing a red hoodie",
  "user_id": "user123",
  "art_style": "anime",  // optional
  "ai_model": "gpt-4o"   // optional
}
```

**Response (202 Accepted):**
```json
{
  "success": true,
  "avatar_id": "uuid-here",
  "status": "processing",
  "message": "Avatar generation started...",
  "poll_url": "/api/get-avatar/uuid-here"
}
```

#### `GET /api/get-avatar/<avatar_id>`
Retrieve avatar status and data (for polling).

**Response (200 OK - Completed):**
```json
{
  "success": true,
  "avatar_id": "uuid-here",
  "status": "SUCCEEDED",
  "stage": "completed",
  "progress_percent": 100,
  "status_message": "Avatar generation completed successfully",
  "ready": true,
  "data": {
    "spec": { /* AvatarSpec */ },
    "user_prompt": "...",
    "base_avatar": {
      "model_glb": "https://...",
      "storage_glb_url": "https://...",
      "task_ids": { "preview": "...", "refine": "..." }
    },
    "clothed_avatar": { /* same structure */ },
    "base_glb_url": "https://...",
    "clothed_glb_url": "https://..."
  }
}
```

**Response (202 Accepted - Processing):**
```json
{
  "success": false,
  "avatar_id": "uuid-here",
  "status": "processing",
  "stage": "base_refine",
  "progress_percent": 30,
  "status_message": "Base avatar refinement in progress...",
  "ready": false
}
```

**Response (202 Accepted - Partial Success):**
```json
{
  "success": false,
  "avatar_id": "uuid-here",
  "status": "partial_success",
  "ready": false,
  "missing": "clothed",
  "message": "One avatar succeeded, but the other failed. Retrying failed avatar...",
  "retry_info": {
    "base_retries": 0,
    "clothed_retries": 1,
    "base_failed": false,
    "clothed_failed": false
  }
}
```

#### `GET /api/get-user-avatars?user_id=<user_id>`
Retrieve all avatars for a user.

**Response:**
```json
{
  "success": true,
  "count": 2,
  "avatars": [ /* array of avatar objects */ ]
}
```

### Cleanup Endpoints

#### `POST /api/cleanup-stuck-avatars`
Clean up stuck avatar generations.

**Request Body:**
```json
{
  "avatar_id": "uuid-here",  // optional: clean specific avatar
  "stuck_threshold_minutes": 60,
  "force_retry": false,  // true = retry, false = mark as failed
  "max_cleanup": 50
}
```

**Response:**
```json
{
  "success": true,
  "found": 5,
  "cleaned": 5,
  "retried": 2,
  "failed": 3,
  "errors": []
}
```

#### `GET /api/find-stuck-avatars?stuck_threshold_minutes=60`
Find stuck avatars without cleaning.

**Response:**
```json
{
  "success": true,
  "count": 3,
  "stuck_avatars": [
    {
      "avatar_id": "uuid-here",
      "user_id": "user123",
      "stage": "base_refine",
      "progress_percent": 45,
      "stuck_since": "2024-01-01T12:00:00Z"
    }
  ]
}
```

### Scheduler Endpoints

#### `POST /api/cleanup-scheduler/start`
Start background cleanup scheduler.

**Request Body:**
```json
{
  "interval_minutes": 30,
  "stuck_threshold_minutes": 60,
  "force_retry": false,
  "max_cleanup": 50
}
```

#### `POST /api/cleanup-scheduler/stop`
Stop the background scheduler.

#### `GET /api/cleanup-scheduler/status`
Check scheduler status.

**Response:**
```json
{
  "success": true,
  "running": true,
  "message": "Cleanup scheduler is running"
}
```

## Service Methods

### Core Generation Methods

#### `generate_3d_avatar(user_text, user_id, art_style, ai_model, async_mode=True)`
Main entry point for avatar generation.
- Extracts `AvatarSpec` using GPT-4
- Creates initial Firestore record
- Starts background thread if `async_mode=True`
- Returns `avatar_id` immediately

#### `build_prompts_from_text(user_text)`
Extracts structured data and generates prompts.
- Returns: `(AvatarSpec, base_prompt, clothed_prompt)`

#### `extract_avatar_spec(user_text, max_retries=1)`
Uses GPT-4 to extract structured `AvatarSpec` from text.
- Includes retry logic for validation errors
- Returns validated `AvatarSpec` object

#### `_generate_3d_avatar_sync(avatar_id, user_text, spec, base_prompt, clothed_prompt, ...)`
Synchronous generation logic (runs in background thread).
- Generates base avatar
- Generates clothed avatar
- Handles partial success
- Uploads to Firebase Storage
- Updates Firestore with final status

#### `_generate_single_avatar(prompt, avatar_type, ...)`
Generates one avatar (base or clothed).
- Calls Meshy preview API
- Calls Meshy refine API
- Returns task data with GLB URLs

#### `_generate_single_avatar_with_retry(prompt, avatar_type, avatar_id, max_retries=3)`
Generates avatar with automatic retry on failure.
- Returns: `(result_dict or None, retry_count)`

### Storage Methods

#### `_save_avatar_to_database(avatar_spec, avatar_data, user_id)`
Saves avatar data to Firestore.
- Saves to `avatars` collection
- Creates reference in user's `avatars` subcollection

#### `_save_avatar_to_storage(glb_url, avatar_id, avatar_type)`
Downloads GLB from Meshy and uploads to Firebase Storage.
- Returns public URL for Unity access

#### `_upload_avatar_to_storage_safe(glb_url, avatar_id, avatar_type, avatar_result)`
Safe wrapper for storage upload with error handling.

### Progress Tracking

#### `_update_progress(avatar_id, stage, progress_percent, message, partial_data)`
Updates progress in Firestore.
- Updates `status`, `stage`, `progress_percent`, `status_message`
- Optionally merges `partial_data`

### Retrieval Methods

#### `get_avatar_by_id(avatar_id)`
Retrieves avatar data from Firestore.
- Includes progress information if still processing

#### `get_user_avatars(user_id)`
Retrieves all avatars for a user.

### Cleanup Methods

#### `find_stuck_generations(stuck_threshold_minutes=60)`
Finds avatars stuck in "processing" status.
- Checks `updated_at` timestamp
- Returns list of stuck avatars

#### `check_meshy_task_status(task_id)`
Verifies Meshy task status to confirm if stuck.

#### `cleanup_stuck_generation(avatar_id, force_retry=False)`
Cleans up a single stuck avatar.
- `force_retry=True`: Restart generation
- `force_retry=False`: Mark as failed

#### `cleanup_all_stuck_generations(stuck_threshold_minutes, force_retry, max_cleanup)`
Bulk cleanup of all stuck avatars.

#### `start_cleanup_scheduler(interval_minutes, stuck_threshold_minutes, force_retry, max_cleanup)`
Starts background thread for periodic cleanup.

#### `stop_cleanup_scheduler()`
Stops the background scheduler.

#### `is_cleanup_scheduler_running()`
Checks if scheduler is running.

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for GPT-4
- `OPENAI_MODEL`: Model to use (default: "gpt-4o")
- `MESHY_API_KEY`: Meshy API key for 3D generation

### Default Settings
- **Stuck Threshold**: 60 minutes
- **Max Retries**: 3 attempts per avatar
- **Retry Backoff**: Exponential (0s, 5s, 10s)
- **Cleanup Interval**: 30 minutes (if scheduler enabled)
- **Max Cleanup**: 50 avatars per cleanup run

## Status Values

- `"processing"`: Generation in progress
- `"SUCCEEDED"`: Both avatars generated successfully
- `"partial_success"`: One avatar succeeded, one failed (retrying)
- `"FAILED"`: Both avatars failed or generation error

## Error Handling

### Generation Errors
- Validation errors: Returned as HTTP 400
- Timeout errors: Returned as HTTP 504
- Internal errors: Returned as HTTP 500 with error details

### Partial Failures
- Successful avatars are saved immediately
- Failed avatars are automatically retried
- Status clearly indicates which avatar is missing

### Stuck Generations
- Detected by timestamp threshold
- Can be retried or marked as failed
- Automatic cleanup via scheduler

## Database Schema

### Firestore Collections

#### `avatars/{avatar_id}`
Main avatar document:
```json
{
  "avatar_id": "uuid",
  "user_id": "user123",
  "user_prompt": "text prompt",
  "base_prompt": "detailed base prompt",
  "clothed_prompt": "detailed clothed prompt",
  "spec": { /* AvatarSpec dict */ },
  "status": "SUCCEEDED",
  "stage": "completed",
  "progress_percent": 100,
  "status_message": "...",
  "base_avatar": {
    "status": "SUCCEEDED",
    "task_ids": { "preview": "...", "refine": "..." },
    "model_glb": "https://meshy-url",
    "storage_glb_url": "https://firebase-storage-url",
    "texture_base_color": "https://...",
    "thumbnail_url": "https://..."
  },
  "clothed_avatar": { /* same structure */ },
  "retry_info": {
    "base_retries": 0,
    "clothed_retries": 0,
    "base_failed": false,
    "clothed_failed": false
  },
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

#### `users/{user_id}/avatars/{avatar_id}`
User avatar reference:
```json
{
  "avatar_id": "uuid",
  "created_at": "timestamp",
  "status": "SUCCEEDED"
}
```

## Integration with Unity

The system provides GLB files compatible with Unity:
1. Frontend polls `/api/get-avatar/<avatar_id>` until `ready: true`
2. Retrieves `base_glb_url` and `clothed_glb_url` from response
3. Downloads GLB files from Firebase Storage URLs
4. Loads into Unity for 3D rendering

## Best Practices

1. **Polling**: Poll every 5-10 seconds during generation
2. **Timeout**: Set client-side timeout (e.g., 30 minutes)
3. **Error Handling**: Check `status` and `ready` fields
4. **Cleanup**: Enable scheduler for production environments
5. **Monitoring**: Monitor stuck generations via cleanup endpoints

## Future Enhancements

- WebSocket support for real-time progress updates
- Batch generation for multiple avatars
- Avatar customization endpoints
- Generation queue management
- Cost tracking and analytics





