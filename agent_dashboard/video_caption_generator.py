import os
from openai import OpenAI
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter


# Load environment variables
load_dotenv("Inzone_agents/assets/.env")

# Set up API keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# GLOBAL VARIABLES
GPT_MODEL = "gpt-4o-mini"
MAX_TOKENS = 200
TEMPERATURE = 0.5

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    cred = credentials.Certificate("Inzone_agents/assets/key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()
openai_client = OpenAI(api_key=OPENAI_API_KEY)

def generate_caption(video_details, category, subcategory):
    """Generates a social media caption using OpenAI GPT-4o-mini."""
    prompt = f"""
    Generate an engaging, authentic-sounding social media caption for a YouTube Short.

    Video Title: {video_details['title']}
    Channel: {video_details['channelTitle']}
    Video Description: {video_details['description']}
    Views: {video_details['view_count']}
    Likes: {video_details['like_count']}
    Comments: {video_details['comment_count']}
    Sample Comments: {video_details['comments'][:3]}
    Category: {category}
    Subcategory: {subcategory}

    The caption should:
    - Sound like it was written by a real person who watched the video
    - Include relevant emojis (2-3 max)
    - Be concise (under 150 characters)
    - Include 1-2 relevant hashtags
    - Have a conversational, excited tone
    - Include a hook or question to encourage engagement
    - NOT sound like AI-generated content
    """

    try:
        response = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating caption: {e}")
        return f"Check out this amazing {subcategory} video from {video_details['channelTitle']}! #shorts #{category.lower().replace(' ', '')}"

def process_videos():
    """Process videos from Firestore that don't have captions yet."""
    videos_ref = db.collection('youtubeVideos')
    
    try:
        # Get documents where generated_caption is null
        docs = videos_ref.where(filter=FieldFilter('generated_caption', '==', None)).get()
        
        if not docs:
            print("No videos found that need captions.")
            return
        
        print(f"Found {len(docs)} videos that need captions.")
        
        for doc in docs:
            try:
                video_data = doc.to_dict()
                
                # Validate required fields exist
                required_fields = ['title', 'description', 'channel_title', 'view_count', 
                                 'like_count', 'comment_count', 'main_category', 
                                 'subcategory', 'youtube_shorts_links']
                
                if not all(field in video_data for field in required_fields):
                    print(f"Skipping document {doc.id} - missing required fields")
                    continue
                
                video_details = {
                    'title': video_data['title'],
                    'description': video_data['description'],
                    'channelTitle': video_data['channel_title'],
                    'view_count': video_data['view_count'],
                    'like_count': video_data['like_count'],
                    'comment_count': video_data['comment_count'],
                    'comments': video_data['sample_comments'].split('; ') if video_data.get('sample_comments') else []
                }
                
                print(f"Processing video: {video_data['youtube_shorts_links']}")
                
                caption = generate_caption(
                    video_details, 
                    video_data['main_category'], 
                    video_data['subcategory']
                )
                
                # Only update if caption was successfully generated
                if caption:
                    doc.reference.update({
                        'generated_caption': caption,
                        'caption_timestamp': firestore.SERVER_TIMESTAMP
                    })
                    print(f"✓ Caption generated and stored for: {video_data['youtube_shorts_links']}")
                else:
                    print(f"✗ Failed to generate caption for: {video_data['youtube_shorts_links']}")
                    
            except Exception as e:
                print(f"Error processing document {doc.id}: {str(e)}")
                continue
                
    except Exception as e:
        print(f"Error accessing Firestore: {str(e)}")
        raise

if __name__ == "__main__":
    process_videos()

