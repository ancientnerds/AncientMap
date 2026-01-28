"""
LLM Service - Ollama Integration for Lyra AI Agent.

Provides language model inference using Ollama's local API.
Supports any model available in Ollama (Qwen, Llama, Phi, Mistral, etc.)

Configuration:
    OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)
    OLLAMA_MODEL: Model to use (default: qwen2.5:3b)
    OLLAMA_TIMEOUT: Request timeout in seconds (default: 120)
"""

import os
import logging
import asyncio
import httpx
from typing import Optional, AsyncGenerator

from pipeline.config import get_ai_thread_limit

logger = logging.getLogger(__name__)

# Configuration from environment
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))


class LLMService:
    """
    Ollama LLM Service.

    Uses Ollama's REST API for text generation.
    Easily switch models by changing OLLAMA_MODEL environment variable.

    Supported models (examples):
        - qwen2.5:1.5b, qwen2.5:3b, qwen2.5:7b (recommended)
        - llama3.2:1b, llama3.2:3b
        - phi3:mini, phi3:medium
        - mistral:7b
        - gemma2:2b, gemma2:9b
    """

    def __init__(self, model: Optional[str] = None, host: Optional[str] = None):
        """
        Initialize LLM service.

        Args:
            model: Model name (defaults to OLLAMA_MODEL env var)
            host: Ollama host URL (defaults to OLLAMA_HOST env var)
        """
        self.host = host or OLLAMA_HOST
        self.model = model or OLLAMA_MODEL
        self.timeout = OLLAMA_TIMEOUT
        self._is_available: Optional[bool] = None

        logger.info(f"LLM Service initialized: model={self.model}, host={self.host}")

    @property
    def is_available(self) -> bool:
        """Check if LLM is available (cached)."""
        if self._is_available is None:
            self._is_available = self._check_availability()
        return self._is_available

    def _check_availability(self) -> bool:
        """Check if Ollama is running and model is available."""
        try:
            with httpx.Client(timeout=5) as client:
                # Check if Ollama is running
                response = client.get(f"{self.host}/api/tags")
                if response.status_code != 200:
                    logger.warning(f"Ollama not responding: {response.status_code}")
                    return False

                # Check if model is available
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check for exact match or partial match (model:tag)
                model_base = self.model.split(":")[0]
                available = any(
                    self.model == name or name.startswith(f"{model_base}:")
                    for name in model_names
                )

                if not available:
                    logger.warning(
                        f"Model '{self.model}' not found. "
                        f"Available: {model_names}. "
                        f"Run: ollama pull {self.model}"
                    )
                    return False

                logger.info(f"Ollama ready with model: {self.model}")
                return True

        except httpx.ConnectError:
            logger.warning(f"Cannot connect to Ollama at {self.host}. Is it running?")
            return False
        except Exception as e:
            logger.error(f"Error checking Ollama: {e}")
            return False

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 200,
        temperature: float = 0.3
    ) -> str:
        """
        Generate text response synchronously.

        Args:
            prompt: User prompt
            system_prompt: System/context prompt (defines persona)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            Generated text response
        """
        with httpx.Client(timeout=self.timeout) as client:
            return self._generate(client, prompt, system_prompt, max_tokens, temperature)

    def _generate(
        self,
        client: httpx.Client,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float
    ) -> str:
        """Internal generate method."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_gpu": 0,  # Force CPU-only for VPS compatibility
                "num_thread": get_ai_thread_limit(),  # Reserve 2 threads for web server
            }
        }

        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = client.post(
                f"{self.host}/api/generate",
                json=payload
            )
            response.raise_for_status()

            result = response.json()
            return result.get("response", "").strip()

        except httpx.TimeoutException:
            logger.error(f"LLM request timed out after {self.timeout}s")
            raise RuntimeError("LLM inference timed out")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama error: {e.response.status_code} - {e.response.text}")
            raise RuntimeError(f"LLM inference failed: {e.response.status_code}")
        except Exception as e:
            logger.error(f"LLM error: {e}")
            raise

    async def generate_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 200,
        temperature: float = 0.3
    ) -> str:
        """
        Generate text response asynchronously.

        Args:
            prompt: User prompt
            system_prompt: System/context prompt (defines persona)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0-1.0)

        Returns:
            Generated text response
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_gpu": 0,  # Force CPU-only for VPS compatibility
                "num_thread": get_ai_thread_limit(),  # Reserve 2 threads for web server
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json=payload
                )
                response.raise_for_status()

                result = response.json()
                return result.get("response", "").strip()

            except httpx.TimeoutException:
                logger.error(f"LLM request timed out after {self.timeout}s")
                raise RuntimeError("LLM inference timed out")
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama error: {e.response.status_code}")
                raise RuntimeError(f"LLM inference failed: {e.response.status_code}")
            except Exception as e:
                logger.error(f"LLM error: {e}")
                raise

    async def generate_stream_async(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 200,
        temperature: float = 0.3
    ) -> AsyncGenerator[str, None]:
        """
        Generate text with streaming output.

        Yields tokens as they are generated for real-time display.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
                "num_gpu": 0,  # Force CPU-only for VPS compatibility
                "num_thread": get_ai_thread_limit(),  # Reserve 2 threads for web server
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.host}/api/generate",
                    json=payload
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line:
                            import json
                            data = json.loads(line)
                            token = data.get("response", "")
                            if token:
                                yield token
                            if data.get("done", False):
                                break

            except httpx.TimeoutException:
                logger.error(f"LLM stream timed out after {self.timeout}s")
                raise RuntimeError("LLM inference timed out")
            except Exception as e:
                logger.error(f"LLM stream error: {e}")
                raise

    def list_models(self) -> list[dict]:
        """List all available models in Ollama."""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(f"{self.host}/api/tags")
                response.raise_for_status()
                return response.json().get("models", [])
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return []

    def pull_model(self, model_name: Optional[str] = None) -> bool:
        """
        Pull a model from Ollama registry.

        Args:
            model_name: Model to pull (defaults to configured model)

        Returns:
            True if successful
        """
        model = model_name or self.model
        logger.info(f"Pulling model: {model}")

        try:
            with httpx.Client(timeout=600) as client:  # 10 min timeout for download
                response = client.post(
                    f"{self.host}/api/pull",
                    json={"name": model, "stream": False}
                )
                response.raise_for_status()
                logger.info(f"Model {model} pulled successfully")
                self._is_available = None  # Reset cache
                return True
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
            return False

    def health_check(self) -> dict:
        """Check LLM service health."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.host}/api/tags")

                if response.status_code != 200:
                    return {
                        "status": "unhealthy",
                        "error": f"Ollama returned {response.status_code}",
                        "host": self.host
                    }

                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                model_available = self.model in model_names or any(
                    name.startswith(f"{self.model.split(':')[0]}:")
                    for name in model_names
                )

                return {
                    "status": "healthy" if model_available else "degraded",
                    "backend": "Ollama",
                    "host": self.host,
                    "model": self.model,
                    "model_available": model_available,
                    "available_models": model_names[:10],  # Limit for display
                }

        except httpx.ConnectError:
            return {
                "status": "unhealthy",
                "error": f"Cannot connect to Ollama at {self.host}",
                "host": self.host,
                "model": self.model,
                "hint": "Run: ollama serve"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "host": self.host
            }


# Singleton instance
_llm_service_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get singleton LLMService instance."""
    global _llm_service_instance
    if _llm_service_instance is None:
        _llm_service_instance = LLMService()
    return _llm_service_instance


def set_model(model: str) -> LLMService:
    """
    Change the active model.

    Args:
        model: New model name (e.g., "qwen2.5:7b", "llama3.2:3b")

    Returns:
        Updated LLMService instance
    """
    global _llm_service_instance
    _llm_service_instance = LLMService(model=model)
    return _llm_service_instance
