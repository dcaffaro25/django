"""
External AI Client

A pluggable abstraction for calling external AI providers (OpenAI, Anthropic, etc.)
to generate financial statement template suggestions.

This client:
- Reads API key from settings/environment
- Sends structured prompts
- Parses JSON responses
- Handles errors and timeouts gracefully
"""

import json
import logging
import os
from typing import Any, Dict, Optional

from django.conf import settings

log = logging.getLogger(__name__)


class ExternalAIClient:
    """
    External AI client for generating financial statement template suggestions.
    
    Supports OpenAI-compatible APIs by default. Can be extended for Anthropic, etc.
    
    Usage:
        client = ExternalAIClient()
        response = client.generate_json(prompt, json_schema)
    """
    
    # Supported providers
    PROVIDER_OPENAI = "openai"
    PROVIDER_ANTHROPIC = "anthropic"
    
    def __init__(
        self,
        provider: str = PROVIDER_OPENAI,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
        max_tokens: int = 16000,
        temperature: float = 0.1,
    ):
        """
        Initialize the external AI client.
        
        Parameters
        ----------
        provider : str
            AI provider to use ("openai" or "anthropic")
        api_key : Optional[str]
            API key. If not provided, reads from settings.OPEN_AI_API_KEY or environment.
        model : Optional[str]
            Model to use. Defaults vary by provider.
        timeout : float
            Request timeout in seconds.
        max_tokens : int
            Maximum tokens in response.
        temperature : float
            Temperature for generation (lower = more deterministic).
        """
        self.provider = provider.lower()
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        # Resolve API key based on provider
        if api_key:
            self.api_key = api_key
        elif self.provider == self.PROVIDER_OPENAI:
            # Try settings, then environment
            self.api_key = (
                getattr(settings, 'OPEN_AI_API_KEY', None) or
                getattr(settings, 'OPENAI_API_KEY', None) or
                os.getenv("OPEN_AI_API_KEY") or 
                os.getenv("OPENAI_API_KEY")
            )
        elif self.provider == self.PROVIDER_ANTHROPIC:
            # Try settings, then environment
            self.api_key = (
                getattr(settings, 'ANTHROPIC_API_KEY', None) or
                os.getenv("ANTHROPIC_API_KEY")
            )
        else:
            self.api_key = None
        
        # Fallback: try reading from local_credentials.ini
        if not self.api_key:
            try:
                import configparser
                from pathlib import Path
                
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
                        if config.has_section("ai_services"):
                            if self.provider == self.PROVIDER_OPENAI:
                                if config.has_option("ai_services", "openai_api_key"):
                                    key = config.get("ai_services", "openai_api_key")
                                    if key and not key.startswith("sk-your-"):  # Skip placeholder
                                        self.api_key = key
                                        log.info("[ExternalAI] Loaded OpenAI API key from %s", config_path)
                                        break
                            elif self.provider == self.PROVIDER_ANTHROPIC:
                                if config.has_option("ai_services", "anthropic_api_key"):
                                    key = config.get("ai_services", "anthropic_api_key")
                                    if key and not key.startswith("sk-ant-your-"):  # Skip placeholder
                                        self.api_key = key
                                        log.info("[ExternalAI] Loaded Anthropic API key from %s", config_path)
                                        break
            except Exception as e:
                log.debug("[ExternalAI] Could not read local_credentials.ini: %s", e)
        
        if not self.api_key:
            log.warning("No AI API key configured for provider '%s'. External AI calls will fail.", self.provider)
        
        # Resolve model
        if model:
            self.model = model
        elif self.provider == self.PROVIDER_OPENAI:
            self.model = os.getenv("TEMPLATE_AI_MODEL", "gpt-4o")
        elif self.provider == self.PROVIDER_ANTHROPIC:
            self.model = os.getenv("TEMPLATE_AI_MODEL", "claude-3-5-sonnet-20241022")
        else:
            self.model = "gpt-4o"
        
        log.debug(
            "ExternalAIClient initialized: provider=%s model=%s timeout=%.1fs max_tokens=%d",
            self.provider, self.model, self.timeout, self.max_tokens
        )
    
    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a prompt to the AI and expect a JSON response.
        
        Parameters
        ----------
        prompt : str
            The user prompt to send.
        system_prompt : Optional[str]
            Optional system prompt to set context.
        
        Returns
        -------
        Dict[str, Any]
            Parsed JSON response from the AI.
        
        Raises
        ------
        ExternalAIError
            If the API call fails or returns invalid JSON.
        """
        if not self.api_key:
            raise ExternalAIError("No API key configured for external AI client")
        
        if self.provider == self.PROVIDER_OPENAI:
            return self._call_openai(prompt, system_prompt)
        elif self.provider == self.PROVIDER_ANTHROPIC:
            return self._call_anthropic(prompt, system_prompt)
        else:
            raise ExternalAIError(f"Unsupported provider: {self.provider}")
    
    def _call_openai(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call OpenAI API and return parsed JSON."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ExternalAIError("openai package not installed. Run: pip install openai")
        
        try:
            client = OpenAI(api_key=self.api_key, timeout=self.timeout)
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            log.info(
                "[ExternalAI] Calling OpenAI model=%s prompt_len=%d",
                self.model, len(prompt)
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format={"type": "json_object"},
            )
            
            content = response.choices[0].message.content
            log.info(
                "[ExternalAI] OpenAI response received, content_len=%d",
                len(content) if content else 0
            )
            
            if not content:
                raise ExternalAIError("Empty response from OpenAI")
            
            # Parse JSON response
            try:
                parsed = json.loads(content)
                return parsed
            except json.JSONDecodeError as e:
                log.error("[ExternalAI] Failed to parse JSON response: %s", e)
                # Try to extract JSON from markdown code blocks
                parsed = self._extract_json_from_text(content)
                if parsed:
                    return parsed
                raise ExternalAIError(f"Invalid JSON in AI response: {e}")
        
        except Exception as e:
            if isinstance(e, ExternalAIError):
                raise
            log.exception("[ExternalAI] OpenAI API error: %s", e)
            raise ExternalAIError(f"OpenAI API error: {e}")
    
    def _call_anthropic(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call Anthropic API and return parsed JSON."""
        try:
            import anthropic
        except ImportError:
            raise ExternalAIError("anthropic package not installed. Run: pip install anthropic")
        
        try:
            client = anthropic.Anthropic(api_key=self.api_key, timeout=self.timeout)
            
            log.info(
                "[ExternalAI] Calling Anthropic model=%s prompt_len=%d",
                self.model, len(prompt)
            )
            
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or "",
                messages=[{"role": "user", "content": prompt}],
            )
            
            content = message.content[0].text if message.content else ""
            log.info(
                "[ExternalAI] Anthropic response received, content_len=%d",
                len(content)
            )
            
            if not content:
                raise ExternalAIError("Empty response from Anthropic")
            
            # Parse JSON response
            try:
                parsed = json.loads(content)
                return parsed
            except json.JSONDecodeError as e:
                log.error("[ExternalAI] Failed to parse JSON response: %s", e)
                # Try to extract JSON from markdown code blocks
                parsed = self._extract_json_from_text(content)
                if parsed:
                    return parsed
                raise ExternalAIError(f"Invalid JSON in AI response: {e}")
        
        except Exception as e:
            if isinstance(e, ExternalAIError):
                raise
            log.exception("[ExternalAI] Anthropic API error: %s", e)
            raise ExternalAIError(f"Anthropic API error: {e}")
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Try to extract JSON from text that might contain markdown code blocks.
        """
        import re
        
        # Try to find JSON in code blocks
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',  # ```json ... ```
            r'```\s*([\s\S]*?)\s*```',       # ``` ... ```
            r'\{[\s\S]*\}',                   # Raw JSON object
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                json_str = match.group(1) if '```' in pattern else match.group(0)
                try:
                    return json.loads(json_str.strip())
                except json.JSONDecodeError:
                    continue
        
        return None


class ExternalAIError(Exception):
    """Exception raised when external AI call fails."""
    pass

