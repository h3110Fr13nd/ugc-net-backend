import asyncio
import websockets
import json
import uuid
import sys
import requests

HOST = "20.244.35.24"
PORT = "8000"
BASE_URL = f"http://{HOST}:{PORT}"
WS_URL = f"ws://{HOST}:{PORT}"

def check_http():
    print(f"Checking HTTP connectivity to {BASE_URL}...")
    try:
        resp = requests.get(f"{BASE_URL}/docs", timeout=5)
        if resp.status_code == 200:
            print("✅ HTTP /docs is accessible.")
            return True
        else:
            print(f"❌ HTTP /docs returned {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP Connection failed: {e}")
        return False

async def check_ws():
    # We need a valid question ID. For a generic connectivity test, we might fail if the ID doesn't exist,
    # but we should at least connect.
    # Let's try to list questions first to get a valid ID if possible, or use a dummy one.
    
    question_id = "dummy-id"
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/questions?page=1&page_size=1")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("questions"):
                question_id = data["questions"][0]["id"]
                print(f"Found valid question ID: {question_id}")
    except:
        pass

    attempt_id = str(uuid.uuid4())
    uri = f"{WS_URL}/api/v1/ws/quiz-attempts/{attempt_id}/question/{question_id}/stream-answer"
    
    print(f"Checking WebSocket connectivity to {uri}...")
    
    try:
        async with websockets.connect(uri, open_timeout=5) as websocket:
            print("✅ WebSocket Connected!")
            
            # Send a ping/dummy payload
            payload = {
                "parts": [{"text_response": "Ping"}],
                "attempt_index": 1
            }
            await websocket.send(json.dumps(payload))
            print("✅ Sent test payload")
            
            # Wait briefly for any response or just to confirm connection stays open
            try:
                msg = await asyncio.wait_for(websocket.recv())
                print(f"Received: {msg}")
            except asyncio.TimeoutError:
                print("No immediate response (expected if dummy ID), but connection stayed open.")
            
            return True
            
    except Exception as e:
        print(f"❌ WebSocket Connection failed: {e}")
        return False

async def main():
    http_ok = check_http()
    ws_ok = await check_ws()
    
    if http_ok and ws_ok:
        print("\n🎉 Deployment Verification PASSED")
        sys.exit(0)
    else:
        print("\n⚠️ Deployment Verification FAILED")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
