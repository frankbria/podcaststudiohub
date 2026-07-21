#!/usr/bin/env python3
"""
Credential Testing Script
Tests connectivity and validity of all external API credentials
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Results storage
results = []


def test_gemini_api():
    """Test Google Gemini API key"""
    service = "Google Gemini"
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "GEMINI_API_KEY environment variable not set",
            "working": False
        })
        return

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)

        # Test by listing available models
        models = genai.list_models()
        model_names = [m.name for m in models][:3]

        if model_names:
            results.append({
                "service": service,
                "status": "✅ Working",
                "message": f"Successfully authenticated. Available models: {', '.join(model_names)}",
                "working": True
            })
        else:
            results.append({
                "service": service,
                "status": "⚠️ Limited",
                "message": "API key accepted but no models available",
                "working": True
            })

    except Exception as e:
        error_msg = str(e)
        if "API key not valid" in error_msg or "401" in error_msg or "403" in error_msg:
            status = "❌ Invalid"
            message = f"Authentication failed: {error_msg[:100]}"
        elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
            status = "⚠️ Quota Exceeded"
            message = f"Quota/rate limit issue: {error_msg[:100]}"
        else:
            status = "❌ Network Error"
            message = f"Connection failed: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def test_openai_api():
    """Test OpenAI API key"""
    service = "OpenAI"
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "OPENAI_API_KEY environment variable not set",
            "working": False
        })
        return

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        # Test by listing models
        models = client.models.list()
        model_list = [m.id for m in models.data[:3]]

        results.append({
            "service": service,
            "status": "✅ Working",
            "message": f"Successfully authenticated. Available models: {', '.join(model_list)}",
            "working": True
        })

    except Exception as e:
        error_msg = str(e)
        if "Incorrect API key" in error_msg or "401" in error_msg or "authentication" in error_msg.lower():
            status = "❌ Invalid"
            message = f"Authentication failed: {error_msg[:100]}"
        elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
            status = "⚠️ Quota Exceeded"
            message = f"Quota/rate limit issue: {error_msg[:100]}"
        else:
            status = "❌ Network Error"
            message = f"Connection failed: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def test_elevenlabs_api():
    """Test ElevenLabs API key"""
    service = "ElevenLabs"
    api_key = os.getenv("ELEVENLABS_API_KEY")

    if not api_key:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "ELEVENLABS_API_KEY environment variable not set",
            "working": False
        })
        return

    try:
        import httpx

        # Test by getting voices
        headers = {"xi-api-key": api_key}
        response = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers=headers,
            timeout=10.0
        )

        if response.status_code == 200:
            voices = response.json().get("voices", [])
            voice_count = len(voices)
            results.append({
                "service": service,
                "status": "✅ Working",
                "message": f"Successfully authenticated. {voice_count} voices available",
                "working": True
            })
        elif response.status_code in [401, 403]:
            results.append({
                "service": service,
                "status": "❌ Invalid",
                "message": f"Authentication failed: {response.status_code} {response.text[:100]}",
                "working": False
            })
        else:
            results.append({
                "service": service,
                "status": "❌ Error",
                "message": f"Unexpected response: {response.status_code}",
                "working": False
            })

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg or "403" in error_msg:
            status = "❌ Invalid"
            message = f"Authentication failed: {error_msg[:100]}"
        else:
            status = "❌ Network Error"
            message = f"Connection failed: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def test_aws_s3():
    """Test AWS S3 credentials"""
    service = "AWS S3"
    access_key = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    bucket_name = os.getenv("AWS_S3_BUCKET")

    if not access_key or not secret_key:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY not set",
            "working": False
        })
        return

    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        # Create S3 client
        s3 = boto3.client(
            's3',
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=os.getenv("AWS_REGION", "us-east-1")
        )

        # Test by listing buckets
        response = s3.list_buckets()
        bucket_count = len(response.get('Buckets', []))

        # If specific bucket configured, test access
        if bucket_name:
            try:
                s3.head_bucket(Bucket=bucket_name)
                results.append({
                    "service": service,
                    "status": "✅ Working",
                    "message": f"Credentials valid. {bucket_count} buckets accessible. Bucket '{bucket_name}' accessible.",
                    "working": True
                })
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    results.append({
                        "service": service,
                        "status": "⚠️ Bucket Not Found",
                        "message": f"Credentials valid but bucket '{bucket_name}' not found or no permission",
                        "working": False
                    })
                else:
                    raise
        else:
            results.append({
                "service": service,
                "status": "✅ Working",
                "message": f"Credentials valid. {bucket_count} buckets accessible. (No specific bucket configured)",
                "working": True
            })

    except NoCredentialsError:
        results.append({
            "service": service,
            "status": "❌ Invalid",
            "message": "AWS credentials not found or invalid",
            "working": False
        })
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'InvalidAccessKeyId' or error_code == 'SignatureDoesNotMatch':
            status = "❌ Invalid"
            message = f"Invalid AWS credentials: {error_code}"
        else:
            status = "❌ Error"
            message = f"AWS error: {error_code} - {str(e)[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })
    except Exception as e:
        results.append({
            "service": service,
            "status": "❌ Network Error",
            "message": f"Connection failed: {str(e)[:100]}",
            "working": False
        })


def test_transistor_api():
    """Test Transistor.fm API key"""
    service = "Transistor.fm"
    api_key = os.getenv("TRANSISTOR_API_KEY")

    if not api_key:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "TRANSISTOR_API_KEY environment variable not set (expected - new scope)",
            "working": False
        })
        return

    try:
        import httpx

        # Test by getting account info
        headers = {"Authorization": f"Bearer {api_key}"}
        response = httpx.get(
            "https://api.transistor.fm/v1/shows",
            headers=headers,
            timeout=10.0
        )

        if response.status_code == 200:
            data = response.json()
            show_count = len(data.get("data", []))
            results.append({
                "service": service,
                "status": "✅ Working",
                "message": f"Successfully authenticated. {show_count} shows found",
                "working": True
            })
        elif response.status_code == 401:
            results.append({
                "service": service,
                "status": "❌ Invalid",
                "message": "Authentication failed: 401 Unauthorized - Invalid API key",
                "working": False
            })
        else:
            results.append({
                "service": service,
                "status": "❌ Error",
                "message": f"Unexpected response: {response.status_code}",
                "working": False
            })

    except Exception as e:
        error_msg = str(e)
        if "401" in error_msg:
            status = "❌ Invalid"
            message = f"Authentication failed: {error_msg[:100]}"
        else:
            status = "❌ Network Error"
            message = f"Connection failed: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def test_database():
    """Test database connectivity"""
    service = "PostgreSQL Database"
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "DATABASE_URL environment variable not set",
            "working": False
        })
        return

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.sql import text

        # Convert async URL to sync for testing
        sync_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

        # Create engine
        engine = create_engine(sync_url)

        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]

            results.append({
                "service": service,
                "status": "✅ Working",
                "message": f"Connection successful. {version[:50]}",
                "working": True
            })

    except Exception as e:
        error_msg = str(e)
        if "password authentication failed" in error_msg.lower():
            status = "❌ Invalid"
            message = "Invalid database credentials"
        elif "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
            status = "❌ Connection Failed"
            message = f"Cannot connect to database: {error_msg[:100]}"
        else:
            status = "❌ Error"
            message = f"Database error: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def test_redis():
    """Test Redis connectivity"""
    service = "Redis"
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        results.append({
            "service": service,
            "status": "⚠️ Missing",
            "message": "REDIS_URL environment variable not set",
            "working": False
        })
        return

    try:
        import redis

        # Parse URL and create client
        r = redis.from_url(redis_url)

        # Test connection with ping
        r.ping()

        # Get info
        info = r.info()
        version = info.get('redis_version', 'unknown')

        results.append({
            "service": service,
            "status": "✅ Working",
            "message": f"Connection successful. Redis version: {version}",
            "working": True
        })

    except Exception as e:
        error_msg = str(e)
        if "connection refused" in error_msg.lower():
            status = "❌ Connection Failed"
            message = "Cannot connect to Redis server"
        elif "authentication" in error_msg.lower():
            status = "❌ Invalid"
            message = "Redis authentication failed"
        else:
            status = "❌ Error"
            message = f"Redis error: {error_msg[:100]}"

        results.append({
            "service": service,
            "status": status,
            "message": message,
            "working": False
        })


def print_results():
    """Print formatted results"""
    print("\n" + "="*80)
    print("CREDENTIAL VALIDATION REPORT")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80 + "\n")

    working_count = sum(1 for r in results if r["working"])
    total_count = len(results)

    for result in results:
        print(f"\n{result['service']}")
        print(f"  Status: {result['status']}")
        print(f"  Details: {result['message']}")

    print("\n" + "="*80)
    print(f"SUMMARY: {working_count}/{total_count} services working")
    print("="*80 + "\n")

    return working_count, total_count


def main():
    """Run all credential tests"""
    print("Starting credential validation tests...\n")

    # Test all services
    test_database()
    test_redis()
    test_gemini_api()
    test_openai_api()
    test_elevenlabs_api()
    test_aws_s3()
    test_transistor_api()

    # Print results
    working, total = print_results()

    # Exit with appropriate code
    if working == total:
        sys.exit(0)  # All working
    elif working > 0:
        sys.exit(1)  # Some working, some not
    else:
        sys.exit(2)  # None working


if __name__ == "__main__":
    main()
