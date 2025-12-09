#!/usr/bin/env python3
"""
Clean Empty Video URLs from Posts

This script removes empty string entries from video_content arrays.
It does NOT delete posts or remove valid video URLs.

Found: 15 posts with empty video URL strings ("")
Action: Remove only the empty strings, keep everything else

Run ONLY after team approval.
"""

import os
import sys
from pathlib import Path

os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore

VIDEO_COLLECTIONS = ['aiPosts', 'humanPosts', 'youtubeVideos']

def clean_empty_urls(dry_run=True):
    """Remove empty string URLs from video_content arrays"""
    
    # Initialize Firebase
    key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
    cred = credentials.Certificate(key_path)
    
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    cleaned_count = 0
    mode = "DRY RUN" if dry_run else "LIVE RUN"
    
    print("="*70)
    print(f"EMPTY VIDEO URL CLEANUP - {mode}")
    print("="*70)
    
    for collection in VIDEO_COLLECTIONS:
        print(f"\nScanning {collection}...")
        posts = db.collection(collection).stream()
        
        for post in posts:
            post_data = post.to_dict()
            modified = False
            
            # Check video_content in nested post structure
            if 'post' in post_data and isinstance(post_data['post'], dict):
                if 'video_content' in post_data['post']:
                    content = post_data['post']['video_content']
                    
                    if isinstance(content, list) and '' in content:
                        # Remove empty strings
                        cleaned_content = [url for url in content if url != '']
                        
                        if dry_run:
                            print(f"\n  Would clean: {post.id}")
                            print(f"    Before: {content}")
                            print(f"    After:  {cleaned_content}")
                        else:
                            post.reference.update({
                                'post.video_content': cleaned_content
                            })
                            print(f"  ✅ Cleaned: {post.id}")
                        
                        cleaned_count += 1
                        modified = True
            
            # Check top-level video_content
            if 'video_content' in post_data and not modified:
                content = post_data['video_content']
                
                if isinstance(content, list) and '' in content:
                    cleaned_content = [url for url in content if url != '']
                    
                    if dry_run:
                        print(f"\n  Would clean: {post.id}")
                        print(f"    Before: {content}")
                        print(f"    After:  {cleaned_content}")
                    else:
                        post.reference.update({
                            'video_content': cleaned_content
                        })
                        print(f"  ✅ Cleaned: {post.id}")
                    
                    cleaned_count += 1
    
    print("\n" + "="*70)
    print("CLEANUP SUMMARY")
    print("="*70)
    
    if dry_run:
        print(f"\n📋 Would clean {cleaned_count} posts")
        print("\n⚠️  This was a DRY RUN - no changes made")
        print("    Run with --live flag to apply changes")
    else:
        print(f"\n✅ Cleaned {cleaned_count} posts")
        print("    Empty video URL strings removed")
        print("    All other data preserved")
    
    return cleaned_count

if __name__ == "__main__":
    # Default to dry run for safety
    dry_run = '--live' not in sys.argv
    
    if not dry_run:
        print("\n⚠️  WARNING: Running in LIVE mode!")
        print("This will modify your Firestore database.\n")
        response = input("Type 'CONFIRM' to proceed: ")
        
        if response != 'CONFIRM':
            print("❌ Cancelled")
            sys.exit(0)
    
    clean_empty_urls(dry_run=dry_run)
