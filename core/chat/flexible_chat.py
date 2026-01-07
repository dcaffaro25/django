"""
Simple flexible chat endpoint using OpenAI/ChatGPT.
Supports model selection and conversation history.
"""
import logging
import time
from typing import List, Dict, Any, Optional

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

log = logging.getLogger("chat.flexible")

# Available models for selection
AVAILABLE_MODELS = {
    # OpenAI models
    "gpt-4o": {"provider": "openai", "description": "Most capable GPT-4 model"},
    "gpt-4o-mini": {"provider": "openai", "description": "Fast and affordable GPT-4"},
    "gpt-4-turbo": {"provider": "openai", "description": "GPT-4 Turbo with vision"},
    "gpt-3.5-turbo": {"provider": "openai", "description": "Fast GPT-3.5"},
    # Anthropic models (if configured)
    "claude-3-5-sonnet-20241022": {"provider": "anthropic", "description": "Claude 3.5 Sonnet"},
    "claude-3-opus-20240229": {"provider": "anthropic", "description": "Claude 3 Opus"},
}

DEFAULT_MODEL = "gpt-4o-mini"


class FlexibleChatView(APIView):
    """
    POST /api/chat/flexible/
    
    Simple chat endpoint with model selection and customizable system prompt.
    Uses OpenAI/ChatGPT (or Anthropic if configured).
    
    Body:
    {
      "message": "Hello, how are you?",
      "system_prompt": "You are a helpful assistant.",  # optional
      "messages": [  # optional - conversation history
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"}
      ],
      "model": "gpt-4o-mini",  # optional - see GET for available models
      "temperature": 0.7,  # optional (0-2)
      "max_tokens": 1024  # optional
    }
    
    Response:
    {
      "success": true,
      "response": "I'm doing great, thanks for asking!",
      "model": "gpt-4o-mini",
      "latency_ms": 523
    }
    
    GET /api/chat/flexible/
    Returns available models.
    """
    permission_classes = []  # Open access - adjust as needed

    def get(self, request):
        """Return available models for selection."""
        models = []
        for model_id, info in AVAILABLE_MODELS.items():
            models.append({
                "id": model_id,
                "provider": info["provider"],
                "description": info["description"],
            })
        return Response({
            "available_models": models,
            "default_model": DEFAULT_MODEL,
        })

    def post(self, request):
        body = request.data or {}
        
        # Get message (required)
        message = body.get("message", "").strip()
        if not message:
            return Response(
                {"success": False, "error": "message is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Optional parameters
        system_prompt = body.get("system_prompt", "You are a helpful assistant.")
        messages = body.get("messages", [])  # conversation history
        model = body.get("model", DEFAULT_MODEL)
        temperature = float(body.get("temperature", 0.7))
        max_tokens = int(body.get("max_tokens", 1024))
        
        # Determine provider from model
        model_info = AVAILABLE_MODELS.get(model, {"provider": "openai"})
        provider = model_info["provider"]
        
        log.info(
            "[flexible_chat] provider=%s model=%s temp=%.2f max_tokens=%d msg_len=%d history=%d",
            provider, model, temperature, max_tokens, len(message), len(messages)
        )
        
        t0 = time.perf_counter()
        
        try:
            if provider == "openai":
                response_text = self._call_openai(
                    message, system_prompt, messages, model, temperature, max_tokens
                )
            elif provider == "anthropic":
                response_text = self._call_anthropic(
                    message, system_prompt, messages, model, temperature, max_tokens
                )
            else:
                return Response(
                    {"success": False, "error": f"Unknown provider: {provider}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            ms = int((time.perf_counter() - t0) * 1000)
            
            return Response({
                "success": True,
                "response": response_text,
                "model": model,
                "provider": provider,
                "latency_ms": ms,
            })
            
        except Exception as e:
            log.exception("[flexible_chat] AI error")
            return Response({
                "success": False,
                "error": str(e),
                "model": model,
                "provider": provider,
            }, status=status.HTTP_502_BAD_GATEWAY)

    def _call_openai(
        self,
        message: str,
        system_prompt: str,
        history: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call OpenAI API and return response text."""
        try:
            from openai import OpenAI
        except ImportError:
            raise Exception("openai package not installed. Run: pip install openai")
        
        import os
        import configparser
        from pathlib import Path
        
        # Try multiple ways to get the API key
        api_key = (
            getattr(settings, 'OPEN_AI_API_KEY', None) or
            getattr(settings, 'OPENAI_API_KEY', None) or
            os.getenv("OPEN_AI_API_KEY") or 
            os.getenv("OPENAI_API_KEY")
        )
        
        # Fallback: try reading from local_credentials.ini
        if not api_key:
            try:
                # Try multiple possible locations for local_credentials.ini
                base_dir = getattr(settings, 'BASE_DIR', None)
                possible_paths = []
                if base_dir:
                    possible_paths.append(Path(base_dir) / "local_credentials.ini")
                # Also try current working directory
                possible_paths.append(Path.cwd() / "local_credentials.ini")
                
                for config_path in possible_paths:
                    if config_path.exists():
                        config = configparser.ConfigParser()
                        config.read(config_path)
                        if config.has_section("ai_services") and config.has_option("ai_services", "openai_api_key"):
                            api_key = config.get("ai_services", "openai_api_key")
                            if api_key and not api_key.startswith("sk-your-"):  # Skip placeholder
                                log.info("[flexible_chat] Loaded OpenAI API key from %s", config_path)
                                break
            except Exception as e:
                log.debug("[flexible_chat] Could not read local_credentials.ini: %s", e)
        
        if not api_key:
            # Debug: log what we found
            log.error(
                "[flexible_chat] OpenAI API key not found. "
                "Checked: settings.OPEN_AI_API_KEY=%s, settings.OPENAI_API_KEY=%s, "
                "env.OPEN_AI_API_KEY=%s, env.OPENAI_API_KEY=%s",
                getattr(settings, 'OPEN_AI_API_KEY', 'NOT_SET'),
                getattr(settings, 'OPENAI_API_KEY', 'NOT_SET'),
                os.getenv("OPEN_AI_API_KEY", 'NOT_SET'),
                os.getenv("OPENAI_API_KEY", 'NOT_SET')
            )
            raise Exception("OpenAI API key not configured. Please set OPEN_AI_API_KEY in settings, environment, or local_credentials.ini")
        
        client = OpenAI(api_key=api_key, timeout=120.0)
        
        # Build messages array
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant", "system") and content:
                messages.append({"role": role, "content": content})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content or ""

    def _call_anthropic(
        self,
        message: str,
        system_prompt: str,
        history: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Call Anthropic API and return response text."""
        try:
            import anthropic
        except ImportError:
            raise Exception("anthropic package not installed. Run: pip install anthropic")
        
        import os
        import configparser
        from pathlib import Path
        
        # Try multiple ways to get the API key
        api_key = (
            getattr(settings, 'ANTHROPIC_API_KEY', None) or
            os.getenv("ANTHROPIC_API_KEY")
        )
        
        # Fallback: try reading from local_credentials.ini
        if not api_key:
            try:
                # Try multiple possible locations for local_credentials.ini
                base_dir = getattr(settings, 'BASE_DIR', None)
                possible_paths = []
                if base_dir:
                    possible_paths.append(Path(base_dir) / "local_credentials.ini")
                # Also try current working directory
                possible_paths.append(Path.cwd() / "local_credentials.ini")
                
                for config_path in possible_paths:
                    if config_path.exists():
                        config = configparser.ConfigParser()
                        config.read(config_path)
                        if config.has_section("ai_services") and config.has_option("ai_services", "anthropic_api_key"):
                            api_key = config.get("ai_services", "anthropic_api_key")
                            if api_key and not api_key.startswith("sk-ant-your-"):  # Skip placeholder
                                log.info("[flexible_chat] Loaded Anthropic API key from %s", config_path)
                                break
            except Exception as e:
                log.debug("[flexible_chat] Could not read local_credentials.ini: %s", e)
        
        if not api_key:
            raise Exception("Anthropic API key not configured. Please set ANTHROPIC_API_KEY in settings, environment, or local_credentials.ini")
        
        client = anthropic.Anthropic(api_key=api_key, timeout=120.0)
        
        # Build messages array for Anthropic
        messages = []
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        
        # Add current message
        messages.append({"role": "user", "content": message})
        
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt or "",
            messages=messages,
        )
        
        return response.content[0].text if response.content else ""
