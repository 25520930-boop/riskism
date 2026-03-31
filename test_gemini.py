import os
import json
try:
    from google import genai
    from google.genai import types
    key = os.getenv('GEMINI_API_KEY')
    print(f"Testing Key: {key[:10]}...")
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model='gemini-2.0-flash', 
        contents='Say hello world in JSON: {"reply": "..."}'
    )
    print(f"SUCCESS: {response.text}")
except Exception as e:
    print(f"FAILURE: {e}")
