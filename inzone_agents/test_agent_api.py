import requests
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("BASE_URL", "http://10.88.0.4:8080")

def test_chat_endpoint():
    """Tests the /chat endpoint with a basic valid request."""

    url = f"{BASE_URL}/chat/popularCharacter"
    headers = {"Content-Type": "application/json"}
    data = {"message": "Hello there!", "ai_id": "Lionel Messi"}

    response = requests.post(url, headers=headers, json=data)

    print(response.json())

    assert response.status_code == 200, f"Expected status code 200, but got {response.status_code}"

    response_json = response.json()

    assert response_json["success"] is True, f"Expected success to be True, but got {response_json['success']}"
    assert "data" in response_json, "Expected 'data' key in response"
    assert "message" in response_json["data"], "Expected 'message' in data"


if __name__ == "__main__":
    test_chat_endpoint()
