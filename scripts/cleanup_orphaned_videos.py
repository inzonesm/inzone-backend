#!/usr/bin/env python3
"""
Cleanup Orphaned Videos from Firebase Storage

This script:
1. Lists all video files in the migrated_videos/ folder in Firebase Storage
2. Checks which URLs are actually referenced in Firestore
3. Deletes orphaned files that are no longer used

Usage:
    python cleanup_orphaned_videos.py [--dry-run]

Options:
    --dry-run    Preview what would be deleted without actually deleting
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import Set

# Set environment before imports
os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore, storage
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Storage path for migrated videos
STORAGE_VIDEO_PATH = 'migrated_videos'

# Collections to check for video references
VIDEO_COLLECTIONS = ['youtubeVideos', 'aiPosts', 'humanPosts']


def init_firebase():
    """Initialize Firebase Admin SDK"""
    key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
    
    if not os.path.exists(key_path):
        key_path = os.path.join(os.path.dirname(__file__), '..', 'agent_dashboard', 'Inzone_agents', 'assets', 'key.json')
    
    if not os.path.exists(key_path):
        raise FileNotFoundError(f"Firebase credentials not found")
    
    cred = credentials.Certificate(key_path)
    
    try:
        firebase_admin.get_app()
    except ValueError:
        with open(key_path, 'r') as f:
            sa_info = json.load(f)
            project_id = sa_info.get('project_id', 'inzone-d4b94')
        
        firebase_admin.initialize_app(cred, {
            'storageBucket': f'{project_id}.appspot.com'
        })
    
    return firestore.client(), storage.bucket()


def get_referenced_urls(db) -> Set[str]:
    """Get all video URLs that are referenced in Firestore"""
    referenced_urls = set()
    
    for collection_name in VIDEO_COLLECTIONS:
        logger.info(f"Scanning {collection_name} for video references...")
        docs = db.collection(collection_name).stream()
        
        for doc in docs:
            data = doc.to_dict()
            
            # Check various fields for video URLs
            url_fields = ['video_url', 'videoUrl', 'youtube_shorts_links']
            for field in url_fields:
                if field in data and data[field]:
                    url = data[field]
                    if 'storage.googleapis.com' in str(url) or 'firebasestorage' in str(url):
                        referenced_urls.add(url)
            
            # Check video_content field
            if 'video_content' in data:
                content = data['video_content']
                if isinstance(content, list):
                    for url in content:
                        if 'storage.googleapis.com' in str(url) or 'firebasestorage' in str(url):
                            referenced_urls.add(url)
                elif isinstance(content, str):
                    if 'storage.googleapis.com' in content or 'firebasestorage' in content:
                        referenced_urls.add(content)
            
            # Check nested post.video_content
            if 'post' in data and isinstance(data['post'], dict):
                post = data['post']
                if 'video_content' in post:
                    content = post['video_content']
                    if isinstance(content, list):
                        for url in content:
                            if 'storage.googleapis.com' in str(url) or 'firebasestorage' in str(url):
                                referenced_urls.add(url)
                    elif isinstance(content, str):
                        if 'storage.googleapis.com' in content or 'firebasestorage' in content:
                            referenced_urls.add(content)
    
    return referenced_urls


def get_storage_files(bucket) -> dict:
    """Get all files in the migrated_videos folder"""
    files = {}
    
    logger.info(f"Listing files in {STORAGE_VIDEO_PATH}/...")
    blobs = bucket.list_blobs(prefix=f"{STORAGE_VIDEO_PATH}/")
    
    for blob in blobs:
        # Get the public URL for this blob
        public_url = f"https://storage.googleapis.com/{bucket.name}/{blob.name}"
        files[public_url] = blob
    
    return files


def cleanup_orphaned_videos(dry_run: bool = False):
    """Main cleanup function"""
    logger.info("="*60)
    logger.info("Orphaned Video Cleanup")
    logger.info("="*60)
    
    if dry_run:
        logger.info("🔍 DRY RUN MODE - No files will be deleted")
    
    # Initialize Firebase
    db, bucket = init_firebase()
    logger.info(f"Connected to bucket: {bucket.name}")
    
    # Get all referenced URLs from Firestore
    logger.info("\n📊 Step 1: Scanning Firestore for video references...")
    referenced_urls = get_referenced_urls(db)
    logger.info(f"Found {len(referenced_urls)} video URLs referenced in Firestore")
    
    # Get all files in storage
    logger.info("\n📁 Step 2: Listing files in Firebase Storage...")
    storage_files = get_storage_files(bucket)
    logger.info(f"Found {len(storage_files)} files in {STORAGE_VIDEO_PATH}/")
    
    # Find orphaned files
    logger.info("\n🔍 Step 3: Identifying orphaned files...")
    orphaned_files = []
    referenced_files = []
    
    for url, blob in storage_files.items():
        if url in referenced_urls:
            referenced_files.append(blob)
        else:
            orphaned_files.append(blob)
    
    logger.info(f"   Referenced files: {len(referenced_files)}")
    logger.info(f"   Orphaned files:   {len(orphaned_files)}")
    
    if not orphaned_files:
        logger.info("\n✅ No orphaned files found. Storage is clean!")
        return
    
    # Calculate storage savings
    total_size = sum(blob.size or 0 for blob in orphaned_files)
    size_mb = total_size / (1024 * 1024)
    
    logger.info(f"\n💾 Potential storage savings: {size_mb:.2f} MB")
    
    # Delete orphaned files
    logger.info(f"\n🗑️  Step 4: {'Would delete' if dry_run else 'Deleting'} orphaned files...")
    
    deleted_count = 0
    failed_count = 0
    
    for idx, blob in enumerate(orphaned_files, 1):
        try:
            if dry_run:
                logger.info(f"   [{idx}/{len(orphaned_files)}] Would delete: {blob.name}")
            else:
                logger.info(f"   [{idx}/{len(orphaned_files)}] Deleting: {blob.name}")
                blob.delete()
            deleted_count += 1
        except Exception as e:
            logger.error(f"   Failed to delete {blob.name}: {e}")
            failed_count += 1
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("CLEANUP SUMMARY")
    logger.info("="*60)
    logger.info(f"   Files scanned:    {len(storage_files)}")
    logger.info(f"   Files referenced: {len(referenced_files)}")
    logger.info(f"   Files orphaned:   {len(orphaned_files)}")
    logger.info(f"   {'Would delete' if dry_run else 'Deleted'}:      {deleted_count}")
    logger.info(f"   Failed:           {failed_count}")
    logger.info(f"   Storage freed:    {size_mb:.2f} MB")
    
    if dry_run:
        logger.info("\n⚠️  This was a DRY RUN. No files were actually deleted.")
        logger.info("   Run without --dry-run to perform the actual cleanup.")
    else:
        logger.info("\n✅ Cleanup complete!")


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup orphaned videos from Firebase Storage'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be deleted without actually deleting'
    )
    
    args = parser.parse_args()
    
    try:
        cleanup_orphaned_videos(dry_run=args.dry_run)
    except KeyboardInterrupt:
        logger.info("\n\nCleanup interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\nCleanup failed: {str(e)}")
        raise


if __name__ == "__main__":
    main()
