"""Script to check available Gemini AI models (Google AI API via google-genai SDK)."""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Gemini API key
api_key = os.getenv("GEMINI_API_KEY")

print(f"🔑 API Key: {api_key[:20]}..." if api_key else "❌ No API Key found")
print("\n" + "="*80)

if not api_key:
    print("\n❌ GEMINI_API_KEY not found in .env file!")
    sys.exit(1)

try:
    from google import genai
    
    # Configure client with API key
    print(f"\n⏳ Configuring Google Gen AI SDK...")
    client = genai.Client(api_key=api_key)
    print(f"✅ Google Gen AI SDK configured successfully\n")
    
    print("🔍 Testing Gemini models...\n")
    
    # List of Gemini model names to test
    model_names = [
        # Gemini 2.5 models (newest)
        "gemini-2.5-flash",
        "gemini-2.5-flash-latest",
        "flash-2.5",
        "gemini-flash-2.5",
        
        # Gemini 2.0 models
        "gemini-2.0-flash-exp",
        "gemini-2.0-flash",
        
        # Gemini 1.5 models
        "gemini-1.5-pro",
        "gemini-1.5-pro-latest",
        "gemini-1.5-flash",
        "gemini-1.5-flash-latest",
        "gemini-1.5-flash-8b",
        "gemini-1.5-flash-8b-latest",
        
        # Gemini 1.0 models
        "gemini-1.0-pro",
        "gemini-pro",
        
        # Generic names
        "gemini-flash",
        "gemini-pro-latest",
    ]
    
    available_models = []
    
    for model_name in model_names:
        try:
            print(f"Testing {model_name:35} ", end="", flush=True)
            
            # Use the new google-genai SDK to generate content
            response = client.models.generate_content(
                model=model_name,
                contents="Say 'OK'",
                config={
                    "max_output_tokens": 10,
                    "temperature": 0.0,
                },
            )
            
            # Check if we got a valid response
            if response and response.text:
                print(f"✅ WORKS")
                available_models.append(model_name)
            else:
                print(f"⚠️  NO RESPONSE")
            
        except Exception as e:
            error_msg = str(e)
            if "404" in error_msg or "not found" in error_msg.lower():
                print(f"❌ NOT FOUND")
            elif "403" in error_msg or "permission" in error_msg.lower():
                print(f"🚫 NO ACCESS")
            elif "quota" in error_msg.lower() or "resource_exhausted" in error_msg.lower():
                print(f"⚠️  QUOTA EXCEEDED")
            elif "invalid" in error_msg.lower() and "api" in error_msg.lower():
                print(f"🔑 INVALID API KEY")
            else:
                print(f"❌ ERROR: {error_msg[:50]}")
    
    print("\n" + "="*80)
    print(f"\n📊 RESULTS: {len(available_models)}/{len(model_names)} models available\n")
    
    if available_models:
        print("✅ Working models:")
        for model in available_models:
            print(f"   • {model}")
        
        print(f"\n💡 Update your .env with one of these:")
        for model in available_models[:3]:  # Show top 3
            print(f"   GEMINI_MODEL={model}")
        
        # Suggest best models
        if "gemini-1.5-flash" in available_models:
            print(f"\n⚡ Fastest & Most Cost-Effective: gemini-1.5-flash")
        if "gemini-1.5-pro" in available_models:
            print(f"🧠 Most Capable: gemini-1.5-pro")
        if "gemini-2.0-flash-exp" in available_models:
            print(f"🆕 Latest Experimental: gemini-2.0-flash-exp")
            
        # Test current configured model
        current_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        print(f"\n🎯 Current .env setting: GEMINI_MODEL={current_model}")
        if current_model in available_models:
            print(f"   ✅ This model is working!")
        else:
            print(f"   ⚠️  This model may not be available")
            
    else:
        print("❌ No models available!")
        print("\n🔧 Troubleshooting steps:")
        print("  1. Verify API key is correct:")
        print("     https://makersuite.google.com/app/apikey")
        print("\n  2. Check API key restrictions:")
        print("     - Ensure no IP restrictions are blocking you")
        print("     - Ensure API key has 'Generative Language API' enabled")
        print("\n  3. Enable Generative Language API:")
        print("     https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com")
        print("\n  4. Check quota/billing:")
        print("     https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas")
        
        sys.exit(1)
        
except ImportError as e:
    print(f"\n❌ Missing package: {e}")
    print("Run: pip install google-genai")
    sys.exit(1)
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    print("\nPossible issues:")
    print("  1. Invalid API key")
    print("  2. API not enabled")
    print("  3. Network connectivity issue")
    sys.exit(1)
