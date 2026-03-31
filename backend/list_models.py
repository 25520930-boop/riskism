import os
import sys

# Add backend to path to import config
sys.path.append('/app')

try:
    from google import genai
    key = os.getenv('GEMINI_API_KEY')
    client = genai.Client(api_key=key)
    print("Listing models...")
    for model in client.models.list():
        print(f"- {model.name}: {model.supported_methods}")
except Exception as e:
    print(f"FAILURE: {type(e).__name__}: {str(e)}")
