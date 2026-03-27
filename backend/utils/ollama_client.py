"""
Async Ollama client for LLM inference.
Handles connection, retries, and error handling.
"""

import httpx
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_MAX_RETRIES, OLLAMA_TIMEOUT

RETRY_DELAY = 2  # seconds


class OllamaClient:
    """Async HTTP client for Ollama API."""

    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = OLLAMA_MODEL,
        timeout: int = OLLAMA_TIMEOUT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def health_check(self) -> bool:
        """Check if Ollama server is alive."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False

    async def list_models(self) -> list:
        """List all available models on Ollama."""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [m["name"] for m in data.get("models", [])]
            return models
        except Exception as e:
            print(f"❌ Failed to list models: {e}")
            return []

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        top_p: float = 0.9,
        retries: int = OLLAMA_MAX_RETRIES,
    ) -> str:
        """
        Generate text from Ollama model with retry logic.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system instruction
            temperature: Sampling temperature (0.0-1.0)
            top_p: Nucleus sampling parameter
            retries: Number of retry attempts
            
        Returns:
            Generated text response
        """
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        for attempt in range(retries):
            try:
                print(f"[Attempt {attempt + 1}/{retries}] Calling Ollama...")
                
                response = await self.client.post(
                    f"{self.base_url}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": full_prompt,
                        "stream": False,
                        "temperature": temperature,
                        "top_p": top_p,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip()

            except httpx.ConnectError:
                print(f"❌ Connection refused. Is Ollama running? (http://{self.base_url})")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)
            except httpx.TimeoutException:
                print(f"❌ Request timeout after {self.timeout}s")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)
            except Exception as e:
                print(f"❌ Error: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(RETRY_DELAY)

        raise RuntimeError(
            f"Failed to generate response after {retries} attempts. "
            f"Is Ollama running at {self.base_url}?"
        )

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ============================================================================
# TEST UTILITIES
# ============================================================================


async def test_ollama_connection():
    """Test basic Ollama connectivity and model availability."""
    print("=" * 60)
    print("🔍 Testing Ollama Connection")
    print("=" * 60)
    
    async with OllamaClient() as client:
        # Check health
        print(f"\n1. Health check ({OLLAMA_BASE_URL})...")
        is_healthy = await client.health_check()
        if is_healthy:
            print("   ✅ Ollama server is reachable")
        else:
            print("   ❌ Ollama server is not reachable")
            return False

        # List models
        print(f"\n2. Available models:")
        models = await client.list_models()
        if not models:
            print("   ❌ No models found. Run: ollama pull qwen2.5:3b")
            return False
        
        for model in models:
            marker = "✅" if model == OLLAMA_MODEL else "  "
            print(f"   {marker} {model}")

        if OLLAMA_MODEL not in models:
            print(f"\n   ⚠️  {OLLAMA_MODEL} not found. Run:")
            print(f"      ollama pull {OLLAMA_MODEL}")
            return False

        # Test inference
        print(f"\n3. Testing inference with {OLLAMA_MODEL}...")
        try:
            response = await client.generate(
                prompt="Say 'Hello from Ollama!' and count to 3.",
                temperature=0.5,
            )
            print(f"   ✅ Model responded:")
            print(f"   → {response}")
        except Exception as e:
            print(f"   ❌ Inference failed: {e}")
            return False

    print("\n" + "=" * 60)
    print("✅ All checks passed! Ollama is ready.")
    print("=" * 60)
    return True


async def test_json_extraction():
    """Test entity extraction (JSON parsing from SLM)."""
    print("\n" + "=" * 60)
    print("🧪 Testing Entity Extraction")
    print("=" * 60)
    
    async with OllamaClient() as client:
        system_prompt = """You are a bank loan assistant. Extract entities from customer input.
Return ONLY valid JSON, no extra text. Use this format:
{
    "customer_name": "string or null",
    "income": "number or null",
    "co_applicant": "string or null",
    "loan_amount": "number or null",
    "entities_mentioned": ["list of topics"]
}"""

        user_input = "My name is Rajesh, I earn ₹45,000 per year. My wife Sunita will be co-applicant."
        
        print(f"\nInput: {user_input}")
        print("\nExtracting entities...")
        
        try:
            response = await client.generate(
                prompt=user_input,
                system_prompt=system_prompt,
                temperature=0.2,  # Lower temp for consistent JSON
            )
            print(f"\nRaw response:\n{response}")
            
            # Try to parse JSON
            try:
                entities = json.loads(response)
                print(f"\n✅ Successfully parsed JSON:")
                print(json.dumps(entities, indent=2, ensure_ascii=False))
            except json.JSONDecodeError:
                print(f"\n⚠️  Could not parse response as JSON. Response was:")
                print(response)
        except Exception as e:
            print(f"❌ Generation failed: {e}")

    print("=" * 60)


async def main():
    """Run all tests."""
    success = await test_ollama_connection()
    
    if success:
        await test_json_extraction()


if __name__ == "__main__":
    asyncio.run(main())
