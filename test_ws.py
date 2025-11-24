import asyncio
import websockets
import json
import uuid

async def test_websocket():
    # Use the question ID found in the DB earlier
    question_id = "8dadedf9-d846-4836-ae90-ab89c028840e"
    attempt_id = str(uuid.uuid4())
    
    uri = f"ws://web:8000/api/v1/ws/quiz-attempts/{attempt_id}/question/{question_id}/stream-answer"
    
    print(f"Connecting to {uri}")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            # Payload matching AnswerSubmissionService
            payload = {
                "parts": [
                    {
                        "text_response": "This is a test answer from the reproduction script."
                    }
                ],
                "attempt_index": 1
            }
            
            print(f"Sending payload: {json.dumps(payload)}")
            await websocket.send(json.dumps(payload))
            
            print("Waiting for response...")
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    print(f"Received: {response}")
                    
                    data = json.loads(response)
                    if data.get("type") == "result":
                        print("Received result, closing.")
                        break
                    if data.get("error"):
                        print(f"Error received: {data['error']}")
                        break
                        
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Connection closed: {e}")
                    break
                    
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
