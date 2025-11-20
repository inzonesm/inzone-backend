import requests, pprint

# Simple test for the happy-path of create/popularCharacter

path = "/create/popularCharacter"
BASE_URL = "https://ai-apis-912424781531.us-east1.run.app/" 
URL = BASE_URL + path


payload = {
    "Greeting": "Hello",
    "Name": "SimpleTest",
    "Personality": "Friendly"
}

# payload = {
#     "keywords": "sports football skiing",
#     "k": 10
# }

# response = requests.post(URL, json=payload)
# # response = requests.get(URL, params=payload)

# print("Response:", response.text)
# print("Status:", response.status_code)
# print("Response:", response.json())


# Grab the character ID and the second image URL
character_id   = "EVYvHRBwAxaiEdnBTsyZ"
# second_img_url = "https://storage.googleapis.com/inzone-f93e4.appspot.com/character_profiles/SimpleTest_20250530_153852_b932195e91b346df9c89b89e1634f07f.png"     # index 1 == the 2nd image
second_img_url = "https://storage.googleapis.com/inzone-f93e4.appspot.com/character_profiles/SimpleTest_20250530_153851_b4805309ccf1488e9d7bfb5236ed6089.png"
# 2️⃣  Tell the API to swap the profile picture to that second image
update_payload = {
    "character_id": character_id,
    "new_image_url": second_img_url
}
update_resp = requests.patch(f"{BASE_URL}/update/popularCharacterImage", json=update_payload)
# update_resp.raise_for_status()           # raise if non-200 for quick debugging

print("\n--- Profile-picture update result ---")
pprint.pprint(update_resp.json())