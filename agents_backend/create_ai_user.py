import requests
from typing import Dict, Any

def create_ai_user(
  username: str, 
  age: int, 
  gender: str, 
  bio: str, 
  popularity: bool, 
  personality: str
  ) -> Dict[str, Any]:
  """
  Creates an AI user by sending a POST request to the specified API endpoint.

  Parameters:
  name (str): The name of the character.
  age (int): The age of the character.
  gender (str): The gender of the character.
  bio (str): The bio of the character.
  popularity (bool): The popularity status of the character.
  personality (str): The personality of the character.

  Returns:
  Dict[str, Any]: The response from the API as a dictionary.
  """
  api_url = "https://inzoneapi-912424781531.us-central1.run.app/api/ai/create-ai-user"
  character_data = {
    "Username": username,
    "Name": username,
    "Age": age,
    "Gender": gender,
    "Bio": bio,
    "Popularity": popularity,
    "Personality": personality,
  }
  
  try:
    response = requests.post(api_url, json=character_data)
    if response.status_code == 200:
      return {
        "success": True,
        "data": response.json(),
        "status_code": response.status_code
      }
    elif response.status_code == 400:
      return {
        "success": False,
        "error": response.json().get("error", "Bad Request"),
        "status_code": response.status_code
      }
    elif response.status_code == 500:
      return {
        "success": False,
        "error": "Unknown server error",
        "status_code": response.status_code
      }
    else:
      response.raise_for_status()
  except requests.exceptions.HTTPError as e:
    return {"success": False, "error": str(e), "status_code": response.status_code}
  except requests.exceptions.RequestException as e:
    return {"success": False, "error": str(e)}

# Example usage:
if __name__ == "__main__":
  result = create_ai_user(
    username="Byte.Banter", 
    age=None,
    gender=None, 
    bio="You are an AI social media personality for the Inzone app.", 
    popularity=False, 
    personality="""- Vibrant mix of cheeky humor, positivity, and a touch of geek chic
    - Approachable and friendly
    - Always has a witty comment ready but knows when to switch gears and provide thoughtful insights"""
  )
  print(result)
