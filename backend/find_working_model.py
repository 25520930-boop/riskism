import os
import sys
sys.path.append('/app')
from google import genai

key = os.getenv('GEMINI_API_KEY')
client = genai.Client(api_key=key)

test_models = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-flash-8b', 'gemini-2.0-flash-lite']

for model in test_models:
    print(f"Testing {model}...")
    try:
        res = client.models.generate_content(model=model, contents="Hi")
        print(f"  SUCCESS: {res.text[:30]}...")
        break
    except Exception as e:
        print(f"  FAILED: {str(e)[:100]}")
else:
    print("ALL MODELS FAILED QUOTA.")
