import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
import random
import firebase_admin
from firebase_admin import credentials, firestore

load_dotenv("Inzone_agents/assets/.env")

# Retrieve API key from GitHub secrets
api_key = os.getenv('YOUTUBE_API_KEY')

# Define all categories and subcategories
categories = {
  "Funny Memes and Jokes": ["Trends & Memes", "Stand-up Comedy", "Dad Jokes", "Parody & Satire"],
  "DIY and Craft Projects": ["Home Decor Crafts", "Upcycling Projects", "Handmade Jewelry Making", "Seasonal Crafts and Decorations"],
  "Video Game Reviews and Tips": ["Latest Game Releases Reviews", "Strategy & Walkthrough Guides", "eSports Highlights", "Retro Gaming"],
  "Animated Movies and Cartoons": ["Classic Cartoon Series", "Modern Animated Films", "Anime & Manga", "Animation Behind-the-Scenes"],
  "Challenge Videos": ["Fitness Challenges", "Food Challenges", "Viral Internet Challenges", "Creative Skill Challenges"],
  "Cooking and Baking": ["Gourmet Recipes", "Quick & Easy Meals", "Baking Desserts & Pastries", "International Cuisine Tutorials"],
  "Pets and Animals": ["Funny Pet Videos", "Wildlife Documentaries", "Pet Care Tips", "Animal Rescues & Adoption Stories"],
  "Science & Exploration": ["Space & Astronomy", "Nature & Ecology", "Scientific Experiments", "Discovering New Technologies"],
}

# Initialize YouTube API client
youtube = build('youtube', 'v3', developerKey=api_key)
CREDENTIALS_PATH = "Inzone_agents/assets/bigquery_key.json"

# Initialize Firebase
if not firebase_admin._apps:
  cred = credentials.Certificate("Inzone_agents/assets/key.json")
  firebase_admin.initialize_app(cred)

db = firestore.client()

def fetch_youtube_shorts(num_shorts, category=None):
    results = []
    
    if category is None or category not in categories:
        category = random.choice(list(categories.keys()))
    
    subcategory = random.choice(categories[category])
    query = f"{subcategory} YouTube Shorts"
    
    search_results = search_youtube(query, num_shorts)
    
    for item in search_results:
        video_id = item['id']['videoId']
        video_details = get_video_details(video_id)
        video_details.update({
            'main_category': category,
            'subcategory': subcategory,
            'youtube_shorts_links': f"https://www.youtube.com/watch?v={video_id}",
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        results.append(video_details)
    
    store_in_firestore(results)
    return results

def search_youtube(query, max_results):
    request = youtube.search().list(
      part='snippet',
      q=query,
      type='video',
      videoDuration='short',
      maxResults=max_results
    )
    response = request.execute()
    return response.get('items', [])

def get_video_details(video_id):
    video_response = youtube.videos().list(
        part="snippet,statistics",
        id=video_id
    ).execute()
    
    if 'items' in video_response and len(video_response['items']) > 0:
        video = video_response['items'][0]
        comments = get_comments(video_id, max_comments=5)
        
        return {
            'title': video['snippet']['title'],
            'description': video['snippet']['description'],
            'channel_title': video['snippet']['channelTitle'],
            'view_count': video['statistics']['viewCount'],
            'like_count': video['statistics'].get('likeCount', 'N/A'),
            'comment_count': video['statistics'].get('commentCount', 'N/A'),
            'sample_comments': '; '.join(comments)
        }
    else:
        return {}

def get_comments(video_id, max_comments=5):
    try:
        comments_response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=max_comments
        ).execute()
        
        comments = []
        if 'items' in comments_response:
            for item in comments_response['items']:
                comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
                comments.append(comment)
        return comments
    except HttpError as e:
        print(f"Could not retrieve comments for video {video_id}: {e}")
        return []

def store_in_firestore(data):
  videos_collection = db.collection('youtubeVideos')
  for video in data:
    # Use video ID as document ID for easy reference
    video_id = video['youtube_shorts_links'].split('=')[1]
    video['generated_caption'] = None
    video['posted'] = False
    video["post_id"] = None
    videos_collection.document(video_id).set(video, merge=True)

# Example usage
if __name__ == "__main__":
  num_shorts = 1  # Number of shorts to search for
  shorts_links = fetch_youtube_shorts(num_shorts)
  for link in shorts_links:
    print(link)