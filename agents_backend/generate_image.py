from openai import OpenAI
import urllib.request
import os
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime

def generate_image(
  prompt: str, 
  user_name: str
  ) -> str:
  """
  Generates an image based on the given prompt using OpenAI's DALL-E model, downloads the image,
  and uploads it to Firebase Storage.
  Args:
    prompt (str): The text prompt to generate the image.
    user_name (str): The name of the user, used to create a unique filename for the image.
  Returns:
    str: The public URL of the uploaded image if successful, None otherwise.
  Raises:
    FileNotFoundError: If the API key file is not found.
    Exception: If there is an error generating the image, downloading the image, or uploading the image to Firebase Storage.
  """
  # Read API key from file
  try:
    with open('openai_key.txt', 'r') as file:
      openai_api_key = file.read().strip()
  except FileNotFoundError:
    print("API key file not found.")
    return None

  # Initialize OpenAI client
  client = OpenAI(api_key=openai_api_key)

  # Generate image
  try:
    response = client.images.generate(
      model="dall-e-3",
      prompt=prompt,
      size="1024x1024",
      quality="standard",
      n=1,
    )
    imgURL = response.data[0].url
  except Exception as e:
    print(f"Error generating image: {e}")
    return None

  # Create output path with user_name and timestamp
  timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
  output_path = f"agent_images/ai-image-{user_name}-{timestamp}.png"

  # Download image
  try:
    urllib.request.urlretrieve(imgURL, output_path)
    print("Image downloaded successfully.")
  except Exception as e:
    print(f"Error downloading image: {e}")
    return None
  
  # Store image in Firebase Storage - gs://inzone-f93e4.appspot.com/ai_images

  # Initialize Firebase app
  cred = credentials.Certificate("key.json")
  named_app_2 = firebase_admin.initialize_app(cred, {
    'storageBucket': 'inzone-f93e4.appspot.com'
  }, name='inzone-app-image-store')

  # Upload image to Firebase Storage
  try:
    bucket = storage.bucket(app=named_app_2)
    blob = bucket.blob(f"ai_images/{os.path.basename(output_path)}")
    blob.upload_from_filename(output_path)
    blob.make_public()
    print(f"Image uploaded to Firebase Storage successfully. URL: {blob.public_url}")
    return blob.public_url
  except Exception as e:
    print(f"Error uploading image to Firebase Storage: {e}")
    return None
  
# Test
# generate_image("test", user_name="aryan")
