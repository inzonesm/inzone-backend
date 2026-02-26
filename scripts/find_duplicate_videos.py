#!/usr/bin/env python3
"""
Find and Clean Duplicate YouTube Shorts Videos in aiPosts Collection

This script:
1. Scans all documents in the 'aiPosts' collection
2. Identifies duplicate video URLs (YouTube shorts that appear in multiple posts)
3. Reports duplicate counts
4. Optionally removes duplicate posts (keeps the earliest one)
"""

import os
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore

def init_firebase():
    """Initialize Firebase Admin SDK"""
    key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
    cred = credentials.Certificate(key_path)
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)
    return firestore.client()

def extract_video_urls(post_data):
    """Extract all video URLs from a post document"""
    urls = []
    
    # Check nested post.video_content
    if 'post' in post_data and isinstance(post_data['post'], dict):
        content = post_data['post'].get('video_content', [])
        if isinstance(content, list):
            urls.extend([u for u in content if isinstance(u, str) and u.strip()])
        elif isinstance(content, str) and content.strip():
            urls.append(content)
    
    # Check top-level video_content
    if 'video_content' in post_data:
        content = post_data['video_content']
        if isinstance(content, list):
            urls.extend([u for u in content if isinstance(u, str) and u.strip()])
        elif isinstance(content, str) and content.strip():
            urls.append(content)
    
    # Check youtube_shorts_links
    if 'youtube_shorts_links' in post_data:
        val = post_data['youtube_shorts_links']
        if isinstance(val, str) and val.strip():
            urls.append(val)
    
    return urls

def normalize_youtube_url(url):
    """Normalize a YouTube URL to extract consistent video ID"""
    url = url.strip()
    
    # Extract video ID from various YouTube URL formats
    import re
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # For non-YouTube URLs (firebase storage etc.), use the full URL
    return url

def analyze_duplicates(db):
    """Analyze aiPosts collection for duplicate videos"""
    print("=" * 70)
    print("DUPLICATE VIDEO ANALYSIS - aiPosts Collection")
    print("=" * 70)
    
    # video_id -> list of (doc_id, post_data, date_posted)
    video_map = defaultdict(list)
    total_posts = 0
    posts_with_videos = 0
    
    print("\nFetching all documents from aiPosts...")
    posts = db.collection('aiPosts').stream()
    
    for post in posts:
        total_posts += 1
        post_data = post.to_dict()
        video_urls = extract_video_urls(post_data)
        
        if video_urls:
            posts_with_videos += 1
            for url in video_urls:
                video_id = normalize_youtube_url(url)
                date_posted = post_data.get('date_posted', None)
                video_map[video_id].append({
                    'doc_id': post.id,
                    'url': url,
                    'date_posted': date_posted,
                    'username': post_data.get('user_name', post_data.get('username', 'unknown'))
                })
    
    # Find duplicates
    duplicates = {vid: posts for vid, posts in video_map.items() if len(posts) > 1}
    
    # Stats
    total_duplicate_entries = sum(len(posts) - 1 for posts in duplicates.values())
    
    print(f"\nTotal posts scanned: {total_posts}")
    print(f"Posts with videos: {posts_with_videos}")
    print(f"Unique videos: {len(video_map)}")
    print(f"Videos with duplicates: {len(duplicates)}")
    print(f"Total duplicate entries (to remove): {total_duplicate_entries}")
    
    if duplicates:
        print(f"\n{'=' * 70}")
        print("DUPLICATE DETAILS (showing first 20)")
        print(f"{'=' * 70}")
        
        for i, (video_id, posts) in enumerate(sorted(duplicates.items(), key=lambda x: -len(x[1]))):
            if i >= 20:
                print(f"\n... and {len(duplicates) - 20} more duplicate groups")
                break
            print(f"\n  Video ID: {video_id}")
            print(f"  Copies: {len(posts)}")
            for p in posts:
                date_str = str(p['date_posted'])[:19] if p['date_posted'] else 'N/A'
                print(f"    - Doc: {p['doc_id']}  User: {p['username']}  Date: {date_str}")
    
    return video_map, duplicates

def clean_duplicates(db, duplicates, dry_run=True):
    """Remove duplicate posts, keeping the earliest one for each video"""
    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\n{'=' * 70}")
    print(f"CLEANING DUPLICATES - {mode}")
    print(f"{'=' * 70}")
    
    docs_to_delete = []
    
    for video_id, posts in duplicates.items():
        # Sort by date_posted, keep the earliest
        sorted_posts = sorted(posts, key=lambda p: (
            p['date_posted'] if p['date_posted'] is not None else datetime.max
        ))
        
        # Keep the first, mark rest for deletion
        keeper = sorted_posts[0]
        to_remove = sorted_posts[1:]
        
        for p in to_remove:
            docs_to_delete.append(p['doc_id'])
    
    print(f"\nTotal documents to delete: {len(docs_to_delete)}")
    
    if not dry_run:
        deleted = 0
        batch_size = 400  # Firestore batch limit is 500
        
        for i in range(0, len(docs_to_delete), batch_size):
            batch = db.batch()
            chunk = docs_to_delete[i:i + batch_size]
            
            for doc_id in chunk:
                ref = db.collection('aiPosts').document(doc_id)
                batch.delete(ref)
            
            batch.commit()
            deleted += len(chunk)
            print(f"  Deleted {deleted}/{len(docs_to_delete)} documents...")
        
        print(f"\nSuccessfully deleted {deleted} duplicate posts.")
    else:
        print("\nDry run complete. No documents were deleted.")
        print("Run with --live flag to actually delete duplicates.")
    
    return docs_to_delete

if __name__ == "__main__":
    db = init_firebase()
    
    # Phase 1: Analyze
    video_map, duplicates = analyze_duplicates(db)
    
    if duplicates:
        # Phase 2: Clean (dry run by default)
        dry_run = '--live' not in sys.argv
        
        if not dry_run:
            print("\n⚠️  WARNING: Running in LIVE mode!")
            print("This will permanently delete duplicate documents from Firestore.\n")
            confirm = input("Type 'yes' to confirm: ")
            if confirm.lower() != 'yes':
                print("Aborted.")
                sys.exit(0)
        
        clean_duplicates(db, duplicates, dry_run=dry_run)
    else:
        print("\nNo duplicates found!")
