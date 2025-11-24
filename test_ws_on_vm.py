#!/usr/bin/env python3
"""
WebSocket test script to run on the Azure VM.
Tests the streaming answer endpoint.
"""
import asyncio
import websockets
import json
import uuid
import sys

async def test_websocket():
    # Get a valid question ID from the API
    import requests
    
    HOST = "localhost"
    PORT = "8000"
    BASE_URL = f"http://{HOST}:{PORT}"
    
    print("Fetching a valid question ID...")
    try:
        resp = requests.get(f"{BASE_URL}/api/v1/questions?page=1&page_size=1")
        if resp.status_code != 200:
            print(f"❌ Failed to fetch questions: {resp.status_code}")
            return False
        
        data = resp.json()
        if not data.get("questions"):
            print("❌ No questions found in database")
            return False
        
        question_id = data["questions"][0]["id"]
        print(f"✅ Found question ID: {question_id}")
        
    except Exception as e:
        print(f"❌ Failed to fetch question: {e}")
        return False
    
    # Test WebSocket connection
    attempt_id = str(uuid.uuid4())
    uri = f"ws://{HOST}:{PORT}/api/v1/ws/quiz-attempts/{attempt_id}/question/{question_id}/stream-answer"
    
    print(f"\nConnecting to WebSocket: {uri}")
    
    try:
        async with websockets.connect(uri, open_timeout=5) as websocket:
            print("✅ WebSocket Connected!")
            
            # Send test payload
            payload = {
                "parts": [{"text_response": "This is a test answer."}],
                "attempt_index": 1
            }
            
            print(f"Sending payload: {json.dumps(payload)}")
            await websocket.send(json.dumps(payload))
            print("✅ Payload sent")
            
            # Receive streaming responses
            print("\nReceiving responses:")
            message_count = 0
            
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    message_count += 1
                    data = json.loads(msg)
                    
                    msg_type = data.get("type", "unknown")
                    print(f"  [{message_count}] Type: {msg_type}")
                    
                    if msg_type == "chunk":
                        content = data.get("content", "")
                        print(f"      Content: {content[:50]}...")
                    elif msg_type == "result":
                        print(f"      Result: {data}")
                        print("\n✅ Received final result, test successful!")
                        break
                    elif msg_type == "error":
                        print(f"      Error: {data.get('error')}")
                        return False
                        
                except asyncio.TimeoutError:
                    print("❌ Timeout waiting for response")
                    return False
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"❌ Connection closed unexpectedly: {e}")
                    return False
            
            print(f"\n✅ WebSocket test PASSED ({message_count} messages received)")
            return True
            
    except Exception as e:
        print(f"❌ WebSocket test FAILED: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_websocket())
    sys.exit(0 if result else 1)
