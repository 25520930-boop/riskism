import os
import sys

# Add backend to path to import config
sys.path.append('/app')

try:
    from google import genai
    from google.genai import types
    key = os.getenv('GEMINI_API_KEY')
    print(f"Testing Key: [{key[:10]}...]")
    client = genai.Client(api_key=key)
    print("Calling Gemini...")
    response = client.models.generate_content(
        model='gemini-1.5-flash', 
        contents='Say hello world'
    )
    print(f"SUCCESS: {response.text}")
except Exception as e:
    print(f"FAILURE: {type(e).__name__}: {str(e)}")
