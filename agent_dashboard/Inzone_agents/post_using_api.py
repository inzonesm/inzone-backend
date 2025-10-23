from typing import Optional, List, Dict, Union
import requests

def create_social_post(
    post_message: str,
    username: str,
    category: list = ["Entertainment"],
    image_ref: Optional[List[str]] = None,
    video_ref: Optional[List[str]] = None
) -> Dict[str, Union[bool, Dict]]:
    """
    Creates a social media post via an API endpoint.
    
    Args:
        post_message (str): The post content.
        username (str): Username of the poster. Defaults to "ByteBanter".
        category (list, optional): List of post categories. Defaults to ["Entertainment"].
        image_ref (list, optional): List of image references. Defaults to None.
        video_ref (list, optional): List of video references. Defaults to None.
    
    Returns:
        dict: Response containing success status and data/error.
    """
    try:
        # Set default values for optional lists
        image_ref = image_ref if image_ref is not None else []
        video_ref = video_ref if video_ref is not None else []

        # Construct the post data
        post_data = {
            "category": category,
            "Comments": [],
            "Likes": 0,
            "Post": {
                    "ImageContent": image_ref,
                    "TextContent": post_message,
                    "VideoContent": video_ref
            },
            "username": username,
        }

        # Send the post data to the API endpoint
        api_url = "https://inzoneapi-912424781531.us-central1.run.app/feed/create-ai-post"
        response = requests.post(api_url, json=post_data)

        # Check if the request was successful
        if response.status_code == 200:
            response_data = response.json()
            return {
                    "success": True,
                    "data": response_data
            }
        else:
            return {
                "success": False,
                "error": {
                    "message": response.text,
                    "code": "POST_CREATE_ERROR"
                }
            }

    except Exception as ex:
        return {
            "success": False,
            "error": {
                "message": str(ex),
                "code": "POST_CREATE_ERROR"
            }
        }


if __name__ == "__main__":
    # Sample data for the function call
    post_message = "Check out our latest AI-generated content!"
    ai_name = "Test_Posting"
    username = "Byte.Banter"
    category = ["Entertainment"]
    image_ref = ["image reference example"]
    video_ref = ["video reference example"]

    # Call the function with sample data
    print(create_social_post(
    post_message,
    username=username,
    category=category,
    image_ref=image_ref,
    video_ref=video_ref,
    ))