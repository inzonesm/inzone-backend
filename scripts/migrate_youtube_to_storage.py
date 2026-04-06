#!/usr/bin/env python3
"""
Migrate YouTube Shorts Videos to Firebase Storage

This script:
1. Fetches all YouTube video URLs from Firestore (youtubeVideos, aiPosts, humanPosts)
2. Downloads videos using yt-dlp
3. Uploads them to Firebase Storage
4. Updates Firestore documents with new Firebase Storage URLs

Requirements:
    pip install yt-dlp firebase-admin google-cloud-storage

Usage:
    python migrate_youtube_to_storage.py [--dry-run] [--limit N] [--collection COLLECTION]

Options:
    --dry-run       Preview what would be migrated without making changes
    --limit N       Limit the number of videos to process (default: all)
    --collection    Process only a specific collection (youtubeVideos, aiPosts, humanPosts)
    --reset         Clear progress tracking and start fresh
"""

import os
import sys
import argparse
import tempfile
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

# Set environment before imports
os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore, storage
import yt_dlp
import json

# Progress tracking file
PROGRESS_FILE = 'migration_progress.json'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('migration_log.txt', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Collections containing YouTube videos
VIDEO_COLLECTIONS = ['youtubeVideos', 'aiPosts', 'humanPosts']

# Firebase Storage bucket path for migrated videos
STORAGE_VIDEO_PATH = 'migrated_videos'

# Track migration statistics
stats = {
    'total_found': 0,
    'already_migrated': 0,
    'successfully_migrated': 0,
    'failed': 0,
    'skipped': 0,
    'deleted_failed': 0,
    'deleted_duplicates': 0
}


class YouTubeToStorageMigrator:
    """Handles migration of YouTube videos to Firebase Storage"""
    
    def __init__(self, dry_run: bool = False, reset_progress: bool = False, redownload: bool = False, skip: int = 0):
        """Initialize the migrator with Firebase connections"""
        self.dry_run = dry_run
        self.redownload = redownload
        self.skip = skip
        self._init_firebase()
        self._load_progress(reset_progress)
        
        # yt-dlp options for downloading - best quality MP4
        self.ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best',
            'outtmpl': '%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'merge_output_format': 'mp4',  # Ensure output is MP4
        }
    
    def _init_firebase(self):
        """Initialize Firebase Admin SDK"""
        key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
        
        if not os.path.exists(key_path):
            # Try alternative path
            key_path = os.path.join(os.path.dirname(__file__), '..', 'agent_dashboard', 'Inzone_agents', 'assets', 'key.json')
        
        if not os.path.exists(key_path):
            raise FileNotFoundError(f"Firebase credentials not found. Tried: {key_path}")
        
        logger.info(f"Using Firebase credentials from: {key_path}")
        
        cred = credentials.Certificate(key_path)
        
        try:
            firebase_admin.get_app()
        except ValueError:
            # Get storage bucket name from the service account file
            import json
            with open(key_path, 'r') as f:
                sa_info = json.load(f)
                project_id = sa_info.get('project_id', 'inzone-d4b94')
            
            firebase_admin.initialize_app(cred, {
                'storageBucket': f'{project_id}.appspot.com'
            })
        
        self.db = firestore.client()
        self.bucket = storage.bucket()
        
        logger.info(f"Firebase initialized. Storage bucket: {self.bucket.name}")
    
    def _load_progress(self, reset: bool = False):
        """Load or initialize progress tracking"""
        self.progress = {
            'migrated_docs': {},  # doc_id -> {video_id, storage_url, timestamp}
            'failed_docs': {},    # doc_id -> {video_id, error, timestamp}
            'last_processed': None,
            'started_at': None,
            'total_migrated': 0,
            'total_failed': 0
        }
        
        if reset:
            logger.info("🔄 Resetting progress tracking...")
            self._save_progress()
            return
        
        if os.path.exists(PROGRESS_FILE):
            try:
                with open(PROGRESS_FILE, 'r') as f:
                    self.progress = json.load(f)
                logger.info(f"📂 Loaded progress: {self.progress['total_migrated']} already migrated, {self.progress['total_failed']} failed")
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        else:
            self.progress['started_at'] = datetime.now().isoformat()
    
    def _save_progress(self):
        """Save progress to file"""
        try:
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(self.progress, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save progress: {e}")
    
    def _is_doc_already_processed(self, doc_id: str, video_id: str) -> bool:
        """Check if a document has already been successfully processed"""
        if doc_id in self.progress['migrated_docs']:
            migrated = self.progress['migrated_docs'][doc_id]
            if migrated.get('video_id') == video_id:
                return True
        return False
    
    def _mark_doc_migrated(self, doc_id: str, video_id: str, storage_url: str):
        """Mark a document as successfully migrated"""
        self.progress['migrated_docs'][doc_id] = {
            'video_id': video_id,
            'storage_url': storage_url,
            'timestamp': datetime.now().isoformat()
        }
        self.progress['total_migrated'] += 1
        self.progress['last_processed'] = doc_id
        self._save_progress()
    
    def _delete_failed_doc(self, doc, video_id: str, reason: str):
        """Delete a document from Firestore after migration failure"""
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would delete document {doc.id} (video {video_id}, reason: {reason})")
            return
        try:
            doc.reference.delete()
            logger.info(f"   Deleted document {doc.id} (video {video_id}, reason: {reason})")
            stats['deleted_failed'] += 1
        except Exception as e:
            logger.error(f"   Failed to delete document {doc.id}: {e}")

    def _mark_doc_failed(self, doc_id: str, video_id: str, error: str):
        """Mark a document as failed"""
        self.progress['failed_docs'][doc_id] = {
            'video_id': video_id,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.progress['total_failed'] += 1
        self._save_progress()
    
    def extract_youtube_video_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats"""
        if not url:
            return None
        
        import re
        
        # Various YouTube URL patterns
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
            r'(?:youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        return None
    
    def is_youtube_url(self, url: str) -> bool:
        """Check if URL is a YouTube URL"""
        if not url or not isinstance(url, str):
            return False
        return 'youtube.com' in url or 'youtu.be' in url
    
    def is_already_migrated(self, url: str) -> bool:
        """Check if URL is already on Firebase Storage"""
        if not url or not isinstance(url, str):
            return False
        return 'firebasestorage' in url or 'storage.googleapis.com' in url
    
    def download_video(self, url: str, output_dir: str) -> Optional[str]:
        """Download YouTube video using yt-dlp"""
        video_id = self.extract_youtube_video_id(url)
        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None
        
        try:
            opts = self.ydl_opts.copy()
            opts['outtmpl'] = os.path.join(output_dir, '%(id)s.%(ext)s')
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"Downloading: {url}")
                info = ydl.extract_info(url, download=True)
                
                # Find the downloaded file
                ext = info.get('ext', 'mp4')
                video_path = os.path.join(output_dir, f"{video_id}.{ext}")
                
                if os.path.exists(video_path):
                    file_size = os.path.getsize(video_path)
                    logger.info(f"Downloaded: {video_path} ({file_size / 1024 / 1024:.2f} MB)")
                    return video_path
                
                # Try to find any matching file
                for file in os.listdir(output_dir):
                    if file.startswith(video_id):
                        return os.path.join(output_dir, file)
                
                logger.error(f"Downloaded file not found for video: {video_id}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to download {url}: {str(e)}")
            return None
    
    def upload_to_storage(self, local_path: str, video_id: str) -> Optional[str]:
        """Upload video to Firebase Storage and return the public URL"""
        try:
            # Determine file extension
            ext = Path(local_path).suffix or '.mp4'
            
            # Create a unique storage path
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            storage_path = f"{STORAGE_VIDEO_PATH}/{video_id}_{timestamp}{ext}"
            
            logger.info(f"Uploading to Firebase Storage: {storage_path}")
            
            blob = self.bucket.blob(storage_path)
            
            # Set content type
            content_type = 'video/mp4' if ext == '.mp4' else f'video/{ext[1:]}'
            blob.upload_from_filename(local_path, content_type=content_type)
            
            # Make publicly accessible
            blob.make_public()
            
            public_url = blob.public_url
            logger.info(f"Uploaded successfully: {public_url}")
            
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {str(e)}")
            return None
    
    def find_migrated_videos_for_redownload(self, doc_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Find videos that were already migrated and need to be re-downloaded.
        Uses the original_youtube_url field to get the source URL.
        Returns list of (field_path, original_youtube_url) tuples.
        """
        results = []
        
        # Check if this document was previously migrated
        original_url = doc_data.get('original_youtube_url')
        if not original_url:
            return results
        
        # Find the field that has a Firebase Storage URL
        if 'post' in doc_data and isinstance(doc_data['post'], dict):
            post = doc_data['post']
            if 'video_content' in post:
                content = post['video_content']
                if isinstance(content, list) and len(content) > 0:
                    if self.is_already_migrated(content[0]):
                        results.append(('post.video_content.0', original_url))
                elif isinstance(content, str) and self.is_already_migrated(content):
                    results.append(('post.video_content', original_url))
        
        # Check root level video_content
        if 'video_content' in doc_data:
            content = doc_data['video_content']
            if isinstance(content, list) and len(content) > 0:
                if self.is_already_migrated(content[0]):
                    results.append(('video_content.0', original_url))
            elif isinstance(content, str) and self.is_already_migrated(content):
                results.append(('video_content', original_url))
        
        return results
    
    def find_youtube_videos_in_document(self, doc_data: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        Find all YouTube video URLs in a document.
        Returns list of (field_path, url) tuples.
        """
        results = []
        
        # Check direct fields
        url_fields = ['youtube_shorts_links', 'video_url', 'videoUrl']
        for field in url_fields:
            if field in doc_data:
                url = doc_data[field]
                if self.is_youtube_url(url):
                    results.append((field, url))
        
        # Check video_content field (can be string or list)
        if 'video_content' in doc_data:
            content = doc_data['video_content']
            if isinstance(content, str) and self.is_youtube_url(content):
                results.append(('video_content', content))
            elif isinstance(content, list):
                for i, url in enumerate(content):
                    if self.is_youtube_url(url):
                        results.append((f'video_content.{i}', url))
        
        # Check nested post object (used in aiPosts and humanPosts)
        if 'post' in doc_data and isinstance(doc_data['post'], dict):
            post = doc_data['post']
            if 'video_content' in post:
                content = post['video_content']
                if isinstance(content, str) and self.is_youtube_url(content):
                    results.append(('post.video_content', content))
                elif isinstance(content, list):
                    for i, url in enumerate(content):
                        if self.is_youtube_url(url):
                            results.append((f'post.video_content.{i}', url))
        
        return results
    
    def update_document_with_new_url(self, doc_ref, field_path: str, new_url: str) -> bool:
        """Update a document field with the new Firebase Storage URL"""
        try:
            if self.dry_run:
                logger.info(f"[DRY RUN] Would update {doc_ref.id}: {field_path} -> {new_url[:80]}...")
                return True
            
            # Handle nested paths like 'post.video_content.0'
            parts = field_path.split('.')
            
            if len(parts) == 1:
                # Simple field update
                doc_ref.update({field_path: new_url})
            elif len(parts) == 2 and parts[0] == 'post':
                # Nested in post object
                doc_data = doc_ref.get().to_dict()
                post = doc_data.get('post', {})
                post[parts[1]] = new_url
                doc_ref.update({'post': post})
            elif len(parts) == 3 and parts[1] == 'video_content':
                # Array element in video_content
                doc_data = doc_ref.get().to_dict()
                index = int(parts[2])
                
                if parts[0] == 'post':
                    post = doc_data.get('post', {})
                    content = post.get('video_content', [])
                    if isinstance(content, list) and index < len(content):
                        content[index] = new_url
                        post['video_content'] = content
                        doc_ref.update({'post': post})
                else:
                    content = doc_data.get('video_content', [])
                    if isinstance(content, list) and index < len(content):
                        content[index] = new_url
                        doc_ref.update({'video_content': content})
            elif len(parts) == 2 and parts[0] == 'video_content':
                # Array element in root video_content
                doc_data = doc_ref.get().to_dict()
                index = int(parts[1])
                content = doc_data.get('video_content', [])
                if isinstance(content, list) and index < len(content):
                    content[index] = new_url
                    doc_ref.update({'video_content': content})
            
            logger.info(f"Updated document {doc_ref.id}: {field_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update document {doc_ref.id}: {str(e)}")
            return False
    
    def migrate_collection(self, collection_name: str, limit: Optional[int] = None) -> Dict[str, int]:
        """Migrate all YouTube videos in a collection"""
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing collection: {collection_name}")
        logger.info(f"{'='*60}")
        
        collection_stats = {
            'found': 0,
            'already_migrated': 0,
            'successfully_migrated': 0,
            'failed': 0,
            'skipped': 0
        }
        
        query = self.db.collection(collection_name)
        if limit:
            query = query.limit(limit)
        
        # Stream documents one at a time to avoid loading all into memory
        logger.info(f"Scanning documents...")

        # First pass: count videos to migrate and detect duplicates
        videos_to_migrate = []
        seen_video_ids = {}  # video_id -> first doc reference
        duplicates_to_delete = []
        doc_count = 0
        for doc in query.stream():
            doc_count += 1
            try:
                doc_data = doc.to_dict()
            except (MemoryError, Exception) as e:
                logger.warning(f"Skipping document {doc.id}: failed to read ({type(e).__name__}: {e})")
                collection_stats['skipped'] += 1
                stats['skipped'] += 1
                continue

            if self.redownload:
                # Redownload mode: find already migrated videos
                migrated_videos = self.find_migrated_videos_for_redownload(doc_data)
                for field_path, url in migrated_videos:
                    video_id = self.extract_youtube_video_id(url)
                    if video_id:
                        if video_id in seen_video_ids:
                            duplicates_to_delete.append((doc, video_id))
                        else:
                            seen_video_ids[video_id] = doc.id
                            videos_to_migrate.append((doc, field_path, url, video_id))
            else:
                # Normal mode: find YouTube videos not yet migrated
                youtube_urls = self.find_youtube_videos_in_document(doc_data)
                for field_path, url in youtube_urls:
                    video_id = self.extract_youtube_video_id(url)
                    if video_id and not self._is_doc_already_processed(doc.id, video_id):
                        if video_id in seen_video_ids:
                            duplicates_to_delete.append((doc, video_id))
                        else:
                            seen_video_ids[video_id] = doc.id
                            videos_to_migrate.append((doc, field_path, url, video_id))

        logger.info(f"Scanned {doc_count} documents")

        # Delete duplicate documents
        if duplicates_to_delete:
            logger.info(f"Found {len(duplicates_to_delete)} duplicate videos, deleting...")
            for dup_doc, dup_video_id in duplicates_to_delete:
                kept_doc_id = seen_video_ids[dup_video_id]
                if self.dry_run:
                    logger.info(f"   [DRY RUN] Would delete duplicate {dup_doc.id} (video {dup_video_id}, keeping {kept_doc_id})")
                else:
                    try:
                        dup_doc.reference.delete()
                        logger.info(f"   Deleted duplicate {dup_doc.id} (video {dup_video_id}, keeping {kept_doc_id})")
                    except Exception as e:
                        logger.error(f"   Failed to delete duplicate {dup_doc.id}: {e}")
                collection_stats['skipped'] += 1
                stats['deleted_duplicates'] += 1
        
        total_videos = len(videos_to_migrate)
        mode_str = "to redownload in best quality" if self.redownload else "to migrate"
        logger.info(f"Found {total_videos} videos {mode_str}")
        
        if self.skip > 0:
            logger.info(f"⏭️  Skipping first {self.skip} videos (resuming from {self.skip + 1})")
        
        for idx, (doc, field_path, url, video_id) in enumerate(videos_to_migrate, 1):
            # Skip videos if resume position is set
            if idx <= self.skip:
                continue
            
            collection_stats['found'] += 1
            stats['total_found'] += 1
            
            logger.info(f"[{idx}/{total_videos}] Processing: {video_id}")
            
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would migrate this video")
                collection_stats['successfully_migrated'] += 1
                stats['successfully_migrated'] += 1
                continue
            
            # Create temporary directory for download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the video
                local_path = self.download_video(url, temp_dir)
                
                if not local_path:
                    self._mark_doc_failed(doc.id, video_id, "Download failed")
                    collection_stats['failed'] += 1
                    stats['failed'] += 1
                    # Delete the document from collection on failure
                    self._delete_failed_doc(doc, video_id, "Download failed")
                    continue

                # Upload to Firebase Storage
                storage_url = self.upload_to_storage(local_path, video_id)

                if not storage_url:
                    self._mark_doc_failed(doc.id, video_id, "Upload failed")
                    collection_stats['failed'] += 1
                    stats['failed'] += 1
                    # Delete the document from collection on failure
                    self._delete_failed_doc(doc, video_id, "Upload failed")
                    continue
                
                # Update Firestore document
                if self.update_document_with_new_url(doc.reference, field_path, storage_url):
                    self._mark_doc_migrated(doc.id, video_id, storage_url)
                    collection_stats['successfully_migrated'] += 1
                    stats['successfully_migrated'] += 1
                    
                    # Also store the original YouTube URL for reference
                    try:
                        doc.reference.update({
                            'original_youtube_url': url,
                            'migrated_at': firestore.SERVER_TIMESTAMP,
                            'migrated_from': 'youtube'
                        })
                    except Exception:
                        pass
                else:
                    self._mark_doc_failed(doc.id, video_id, "Database update failed")
                    collection_stats['failed'] += 1
                    stats['failed'] += 1
                    self._delete_failed_doc(doc, video_id, "Database update failed")
        
        return collection_stats
    
    def run(self, collections: Optional[List[str]] = None, limit: Optional[int] = None):
        """Run the migration process"""
        logger.info("\n" + "="*70)
        if self.redownload:
            logger.info("YouTube to Firebase Storage - REDOWNLOAD (Best Quality)")
        else:
            logger.info("YouTube to Firebase Storage Migration")
        logger.info("="*70)
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE - No changes will be made")
        if self.redownload:
            logger.info("🔄 REDOWNLOAD MODE - Re-downloading migrated videos in best quality")
        
        target_collections = collections or VIDEO_COLLECTIONS
        
        for collection in target_collections:
            if collection not in VIDEO_COLLECTIONS:
                logger.warning(f"Unknown collection: {collection}")
                continue
            
            self.migrate_collection(collection, limit)
        
        # Print summary
        self._print_summary()
    
    def _print_summary(self):
        """Print migration summary"""
        logger.info("\n" + "="*70)
        logger.info("MIGRATION SUMMARY")
        logger.info("="*70)
        
        logger.info(f"\n📊 Statistics:")
        logger.info(f"   Total YouTube videos found:    {stats['total_found']}")
        logger.info(f"   Already migrated (skipped):    {stats['already_migrated']}")
        logger.info(f"   Successfully migrated (new):   {stats['successfully_migrated']}")
        logger.info(f"   Failed:                        {stats['failed']}")
        logger.info(f"   Deleted (failed migration):    {stats['deleted_failed']}")
        logger.info(f"   Deleted (duplicates):          {stats['deleted_duplicates']}")
        logger.info(f"   Skipped (other reasons):       {stats['skipped']}")
        logger.info(f"\n📁 Progress tracking:")
        logger.info(f"   Total migrated (all runs):     {self.progress['total_migrated']}")
        logger.info(f"   Total failed (all runs):       {self.progress['total_failed']}")
        logger.info(f"   Progress saved to:             {PROGRESS_FILE}")
        
        if self.dry_run:
            logger.info("\n⚠️  This was a DRY RUN. No actual changes were made.")
            logger.info("   Run without --dry-run to perform the actual migration.")
        else:
            logger.info("\n✅ Migration complete!")
            logger.info("   Migrated videos are stored in Firebase Storage at:")
            logger.info(f"   gs://{self.bucket.name}/{STORAGE_VIDEO_PATH}/")


def main():
    parser = argparse.ArgumentParser(
        description='Migrate YouTube videos to Firebase Storage',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be migrated (recommended first step)
  python migrate_youtube_to_storage.py --dry-run
  
  # Migrate only 5 videos for testing
  python migrate_youtube_to_storage.py --limit 5
  
  # Migrate only youtubeVideos collection
  python migrate_youtube_to_storage.py --collection youtubeVideos
  
  # Full migration
  python migrate_youtube_to_storage.py
  
  # Reset progress and start fresh
  python migrate_youtube_to_storage.py --reset
  
  # Re-download already migrated videos in best quality
  python migrate_youtube_to_storage.py --collection aiPosts --redownload
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be migrated without making changes'
    )
    
    parser.add_argument(
        '--redownload',
        action='store_true',
        help='Re-download already migrated videos in best quality (uses original_youtube_url)'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit the number of documents to process per collection'
    )
    
    parser.add_argument(
        '--collection',
        type=str,
        choices=VIDEO_COLLECTIONS,
        default=None,
        help='Process only a specific collection'
    )
    
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Clear progress tracking and start fresh'
    )
    
    parser.add_argument(
        '--skip',
        type=int,
        default=0,
        help='Skip the first N videos (for resuming interrupted runs)'
    )
    
    args = parser.parse_args()
    
    collections = [args.collection] if args.collection else None
    
    try:
        migrator = YouTubeToStorageMigrator(dry_run=args.dry_run, reset_progress=args.reset, redownload=args.redownload, skip=args.skip)
        migrator.run(collections=collections, limit=args.limit)
    except KeyboardInterrupt:
        logger.info("\n\nMigration interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\nMigration failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
