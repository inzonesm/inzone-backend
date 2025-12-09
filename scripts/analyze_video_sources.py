#!/usr/bin/env python3
"""
Analyze Video Sources and Identify Potential Issues

This script analyzes videos in Firestore to understand:
1. Distribution of video sources (YouTube vs Firebase Storage)
2. Video URL patterns
3. Potential issues based on Flutter video player limitations

Key Finding: Flutter's video_player package CANNOT play YouTube URLs directly.
This is likely the source of "Could not open codec" errors.
"""

import os
import sys
from pathlib import Path
from collections import defaultdict

os.environ['GRPC_DNS_RESOLVER'] = 'native'
sys.path.insert(0, str(Path(__file__).parent.parent))

import firebase_admin
from firebase_admin import credentials, firestore

# Collections to scan
VIDEO_COLLECTIONS = ['aiPosts', 'humanPosts', 'youtubeVideos']

def analyze_video_sources():
    """Analyze video sources to identify potential Flutter compatibility issues"""
    
    # Initialize Firebase
    key_path = os.path.join(os.path.dirname(__file__), '..', 'inzoneapi', 'key.json')
    cred = credentials.Certificate(key_path)
    
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    # Statistics
    stats = {
        'youtube_videos': 0,
        'firebase_storage_videos': 0,
        'gcs_videos': 0,
        'empty_urls': 0,
        'other_videos': 0,
        'total_posts': 0,
        'posts_with_videos': 0
    }
    
    youtube_samples = []
    firebase_samples = []
    
    print("="*70)
    print("VIDEO SOURCE ANALYSIS - Flutter Compatibility Check")
    print("="*70)
    
    for collection in VIDEO_COLLECTIONS:
        print(f"\nScanning {collection}...")
        posts = db.collection(collection).limit(100).stream()
        
        for post in posts:
            stats['total_posts'] += 1
            post_data = post.to_dict()
            
            # Extract video URLs
            video_urls = []
            
            if 'post' in post_data and isinstance(post_data['post'], dict):
                if 'video_content' in post_data['post']:
                    content = post_data['post']['video_content']
                    if isinstance(content, list):
                        video_urls.extend([u for u in content if isinstance(u, str)])
                    elif isinstance(content, str):
                        video_urls.append(content)
            
            for field in ['video_content', 'videoUrl', 'video_url', 'youtube_shorts_links']:
                if field in post_data:
                    value = post_data[field]
                    if isinstance(value, list):
                        video_urls.extend([u for u in value if isinstance(u, str)])
                    elif isinstance(value, str):
                        video_urls.append(value)
            
            if video_urls:
                stats['posts_with_videos'] += 1
            
            for url in video_urls:
                if not url or url == '':
                    stats['empty_urls'] += 1
                elif 'youtube.com' in url or 'youtu.be' in url:
                    stats['youtube_videos'] += 1
                    if len(youtube_samples) < 3:
                        youtube_samples.append(url)
                elif 'firebasestorage' in url:
                    stats['firebase_storage_videos'] += 1
                    if len(firebase_samples) < 3:
                        firebase_samples.append(url)
                elif 'storage.googleapis.com' in url:
                    stats['gcs_videos'] += 1
                else:
                    stats['other_videos'] += 1
    
    # Print results
    print("\n" + "="*70)
    print("ANALYSIS RESULTS")
    print("="*70)
    
    print(f"\nTotal posts scanned: {stats['total_posts']}")
    print(f"Posts with videos: {stats['posts_with_videos']}")
    
    print(f"\n📊 Video Source Breakdown:")
    print(f"  YouTube videos:        {stats['youtube_videos']}")
    print(f"  Firebase Storage:      {stats['firebase_storage_videos']}")
    print(f"  Google Cloud Storage:  {stats['gcs_videos']}")
    print(f"  Empty URLs:            {stats['empty_urls']}")
    print(f"  Other sources:         {stats['other_videos']}")
    
    total_videos = (stats['youtube_videos'] + stats['firebase_storage_videos'] + 
                   stats['gcs_videos'] + stats['other_videos'])
    
    if total_videos > 0:
        youtube_pct = (stats['youtube_videos'] / total_videos) * 100
        print(f"\n📈 YouTube videos: {youtube_pct:.1f}% of all videos")
    
    # Flutter compatibility analysis
    print("\n" + "="*70)
    print("🔍 FLUTTER VIDEO PLAYER COMPATIBILITY ANALYSIS")
    print("="*70)
    
    print("\n⚠️  CRITICAL FINDING:")
    print(f"   {stats['youtube_videos']} YouTube videos detected")
    print("\n   Flutter's video_player package CANNOT play YouTube URLs directly!")
    print("   Attempting to use VideoPlayerController.network() with YouTube URLs")
    print("   will result in 'Could not open codec' errors.")
    
    print(f"\n✅ COMPATIBLE VIDEOS:")
    print(f"   {stats['firebase_storage_videos'] + stats['gcs_videos']} Firebase/GCS videos")
    print("   These should work fine with video_player (likely H.264 codec)")
    
    if stats['empty_urls'] > 0:
        print(f"\n🧹 CLEANUP NEEDED:")
        print(f"   {stats['empty_urls']} posts have empty video URLs")
        print("   These should be removed from posts")
    
    # Show samples
    if youtube_samples:
        print(f"\n📺 YouTube URL Samples:")
        for i, url in enumerate(youtube_samples, 1):
            print(f"   {i}. {url[:80]}...")
    
    if firebase_samples:
        print(f"\n🔥 Firebase Storage URL Samples:")
        for i, url in enumerate(firebase_samples, 1):
            print(f"   {i}. {url[:80]}...")
    
    # Recommendations
    print("\n" + "="*70)
    print("💡 RECOMMENDED SOLUTION")
    print("="*70)
    
    if stats['youtube_videos'] > 0:
        print("\n1. FOR YOUTUBE VIDEOS:")
        print("   ├─ Use youtube_player_flutter package")
        print("   ├─ Extract video ID from URL")
        print("   └─ Use YoutubePlayer widget")
        
        print("\n   Code example:")
        print("   ```dart")
        print("   if (url.contains('youtube.com')) {")
        print("     String? videoId = YoutubePlayer.convertUrlToId(url);")
        print("     return YoutubePlayer(controller: ...);"  )
        print("   }")
        print("   ```")
    
    if stats['firebase_storage_videos'] > 0:
        print("\n2. FOR FIREBASE STORAGE VIDEOS:")
        print("   ├─ Continue using video_player package")
        print("   ├─ Use VideoPlayerController.network(url)")
        print("   └─ These should work without issues")
    
    if stats['empty_urls'] > 0:
        print("\n3. FOR EMPTY VIDEO URLS:")
        print("   └─ Create cleanup script to remove empty video_content arrays")
    
    print("\n✅ Analysis complete!")
    
    return stats

if __name__ == "__main__":
    analyze_video_sources()
