"""Check available Vertex AI models using the google-genai SDK."""

import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

project_id = os.getenv("VERTEXAI_PROJECT_ID")
location = os.getenv("VERTEXAI_LOCATION", "us-central1")
credentials_path = os.getenv("VERTEXAI_CREDENTIALS_PATH")

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

print(f"\n🔧 Configuration:")
print(f"   Project: {project_id}")
print(f"   Location: {location}")
print(f"   Credentials: {credentials_path}")
print("\n" + "="*80)

# Initialize the google-genai client for Vertex AI
print(f"\n⏳ Initializing Google Gen AI SDK (Vertex AI backend)...")
client = genai.Client(
    vertexai=True,
    project=project_id,
    location=location,
)
print("✅ Initialized successfully")

# List of Gemini models to test
models_to_test = [
    # Gemini 3.1 (newest)
    "gemini-3.1-pro",
    "gemini-3.1-flash",
    "gemini-3.1-flash-lite",
    
    # Gemini 3.0
    "gemini-3-pro",
    "gemini-3-flash",
    "gemini-3-flash-lite",
    "gemini-3.0-pro",
    "gemini-3.0-flash",
    "gemini-3.0-flash-lite",
    
    # Gemini 2.5
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    
    # Gemini 2.0
    "gemini-2.0-flash-exp",
    "gemini-2.0-flash",
    
    # Gemini 1.5 Pro
    "gemini-1.5-pro",
    "gemini-1.5-pro-001",
    "gemini-1.5-pro-002",
    "gemini-pro",
    
    # Gemini 1.5 Flash
    "gemini-1.5-flash",
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-flash",
    
    # Gemini 1.5 Flash-8B
    "gemini-1.5-flash-8b",
    
    # Gemini 1.0
    "gemini-1.0-pro",
    "gemini-1.0-pro-001",
    "gemini-1.0-pro-002",
]

print(f"\n🔍 Testing {len(models_to_test)} Gemini models in {location}...\n")

available_models = []
unavailable_models = []

for model_name in models_to_test:
    try:
        # Use the new google-genai SDK to generate content
        response = client.models.generate_content(
            model=model_name,
            contents="Say 'ok'",
        )
        
        if response and response.text:
            print(f"✅ {model_name:<35} AVAILABLE")
            available_models.append(model_name)
        else:
            print(f"⚠️  {model_name:<35} LOADED (no response)")
            available_models.append(model_name)
            
    except Exception as e:
        error_msg = str(e)
        if "404" in error_msg or "not found" in error_msg.lower():
            print(f"❌ {model_name:<35} NOT FOUND")
        elif "403" in error_msg or "permission" in error_msg.lower():
            print(f"🔒 {model_name:<35} PERMISSION DENIED")
        else:
            print(f"❌ {model_name:<35} ERROR: {str(e)[:50]}")
        unavailable_models.append(model_name)

print("\n" + "="*80)
print(f"\n📊 RESULTS: {len(available_models)}/{len(models_to_test)} models available\n")

if available_models:
    print("✅ AVAILABLE MODELS:")
    for model in available_models:
        print(f"   • {model}")
    print(f"\n💡 Update your .env file to use any of these models:")
    print(f"   VERTEXAI_MODEL={available_models[0]}")
else:
    print("❌ No models available!")
    print("\n🔧 Troubleshooting:")
    print("  1. Enable Vertex AI API:")
    print(f"     https://console.cloud.google.com/apis/library/aiplatform.googleapis.com?project={project_id}")
    print("\n  2. Grant service account permissions:")
    print("     - Vertex AI User")
    print("     - ML Developer")
    print(f"     https://console.cloud.google.com/iam-admin/iam?project={project_id}")
    print("\n  3. Enable billing:")
    print(f"     https://console.cloud.google.com/billing/linkedaccount?project={project_id}")
    print("\n  4. Try different regions:")
    print("     - us-east4")
    print("     - us-west1")
    print("     - europe-west1")

if unavailable_models:
    print(f"\n⚠️  UNAVAILABLE MODELS ({len(unavailable_models)}):")
    for model in unavailable_models[:5]:
        print(f"   • {model}")
    if len(unavailable_models) > 5:
        print(f"   ... and {len(unavailable_models) - 5} more")

print("\n" + "="*80)

# Also check other regions
print("\n🌍 Want to try other regions?")
other_regions = ["us-east4", "us-west1", "europe-west1", "asia-southeast1"]
print("   Alternative regions to try:")
for region in other_regions:
    if region != location:
        print(f"   • {region}")
print(f"\n   Update .env: VERTEXAI_LOCATION=<region>")
print()
