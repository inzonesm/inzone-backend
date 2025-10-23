#!/bin/bash

BASE_URL="https://inzoneapi-912424781531.us-central1.run.app"

declare -A endpoints=(
    ["/test/backend"]="GET"
    ["/api/sentiment-analysis"]="POST"
    ["/api/main-ai-chat"]="POST"
    ["/api/add-user"]="POST"
    ["/api/get-all-ai-profiles"]="POST"
    ["/api/create-ai-profile"]="POST"
    ["/api/get-avatars"]="GET"
    ["/user/create-profile"]="POST"
    ["/user/update-profile"]="POST"
    ["/user/get-profile"]="GET"
    ["/user/follow"]="POST"
    ["/user/unfollow"]="POST"
    ["/user/get-followers"]="POST"
    ["/user/get-following"]="POST"
    ["/user/remove-from-following"]="POST"
    ["/user/remove-from-followers"]="POST"
    ["/user/get-liked-posts"]="POST"
    ["/feed/create-human-post"]="POST"
    ["/feed/create-ai-post"]="POST"
    ["/feed/create-repost"]="POST"
    ["/feed/get-feed"]="POST"
    ["/feed/posts-flow"]="GET"
    ["/feed/update-post"]="POST"
    ["/feed/write-comment"]="POST"
    ["/feed/get-user-posts"]="POST"
    ["/api/ai/chat"]="POST"
    ["/api/ai/create-ai-user"]="POST"
    ["/api/ai/carousel/characters"]="GET"
    ["/api/ai/generate-image"]="POST"
    ["/ai-content/generate-post"]="POST"
)

echo "Testing all endpoints in $BASE_URL..."

for endpoint in "${!endpoints[@]}"; do
    method=${endpoints[$endpoint]}
    
    if [ "$method" == "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL$endpoint")
    else
        response=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL$endpoint" \
            -H "Content-Type: application/json" -d '{}')
    fi
    
    if [[ $response -ge 200 && $response -lt 300 ]]; then
        echo "✅ $method $endpoint - Success ($response)"
    else
        echo "❌ $method $endpoint - Failed ($response)"
    fi
done

# chmod +x test_endpoints.sh
# ./test_endpoints.sh