"""
Local Settings Loader

This module provides utilities to load local development credentials
from a local_credentials.ini file that is NOT committed to git.

Usage:
------
1. Copy local_credentials.example.ini to local_credentials.ini
2. Fill in the actual credentials
3. Import and use get_local_config() to access settings

The settings module will automatically detect and use this configuration
when ENVIRONMENT_MODE is set or local_credentials.ini exists.
"""

import os
import configparser
from pathlib import Path
from typing import Optional, Dict, Any

# Base directory of the Django project
BASE_DIR = Path(__file__).resolve().parent.parent

# Path to local credentials file
LOCAL_CREDENTIALS_FILE = BASE_DIR / "local_credentials.ini"


def get_local_config() -> Optional[configparser.ConfigParser]:
    """
    Load and return the local credentials configuration.
    
    Returns None if the file doesn't exist (production mode).
    """
    if not LOCAL_CREDENTIALS_FILE.exists():
        return None
    
    config = configparser.ConfigParser()
    config.read(LOCAL_CREDENTIALS_FILE)
    return config


def get_environment_mode() -> str:
    """
    Determine the current environment mode.
    
    Priority:
    1. ENVIRONMENT_MODE environment variable
    2. Value from local_credentials.ini
    3. Default to 'production'
    """
    # Check environment variable first
    env_mode = os.environ.get("ENVIRONMENT_MODE")
    if env_mode:
        return env_mode.lower()
    
    # Check local config file
    config = get_local_config()
    if config and config.has_option("environment", "mode"):
        return config.get("environment", "mode").lower()
    
    return "production"


def get_database_config(db_type: str = "default") -> Dict[str, Any]:
    """
    Get database configuration based on environment mode.
    
    Args:
        db_type: 'production', 'homologation', or 'default' (auto-select based on mode)
    
    Returns:
        Dictionary with Django database configuration
    """
    config = get_local_config()
    mode = get_environment_mode()
    
    # In production mode without local config, return empty (use settings.py defaults)
    if not config:
        return {}
    
    # Determine which database section to use
    if db_type == "default":
        if mode in ("local", "homolog", "homologation"):
            section = "homologation_database"
        else:
            section = "production_database"
    elif db_type == "production":
        section = "production_database"
    elif db_type in ("homolog", "homologation"):
        section = "homologation_database"
    else:
        section = "production_database"
    
    if not config.has_section(section):
        return {}
    
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config.get(section, "name", fallback="railway"),
        "USER": config.get(section, "user", fallback="postgres"),
        "PASSWORD": config.get(section, "password", fallback=""),
        "HOST": config.get(section, "host", fallback="localhost"),
        "PORT": config.get(section, "port", fallback="5432"),
    }


def get_redis_url() -> Optional[str]:
    """
    Get Redis URL for Celery from local config.
    """
    config = get_local_config()
    if not config:
        return None
    
    if config.has_option("redis", "url"):
        return config.get("redis", "url")
    
    return None


def get_service_url(service: str) -> Optional[str]:
    """
    Get service URL override from local config.
    
    Args:
        service: 'embedding_service' or 'llm_service'
    """
    config = get_local_config()
    if not config:
        return None
    
    if config.has_option(service, "base_url"):
        return config.get(service, "base_url")
    
    return None


def is_local_mode() -> bool:
    """Check if running in local development mode."""
    return get_environment_mode() in ("local", "homolog", "homologation", "development", "dev")


def is_homolog_mode() -> bool:
    """Check if running in homologation mode."""
    return get_environment_mode() in ("homolog", "homologation")


def apply_local_settings(settings_module: dict) -> dict:
    """
    Apply local settings overrides to the Django settings.
    
    This function modifies the settings dictionary in-place and returns it.
    Call this at the end of settings.py.
    
    Usage in settings.py:
        from nord_backend.local_settings_loader import apply_local_settings
        globals().update(apply_local_settings(globals()))
    """
    mode = get_environment_mode()
    config = get_local_config()
    
    if not config or mode == "production":
        return settings_module
    
    # Apply database settings
    db_config = get_database_config("default")
    if db_config:
        settings_module["DATABASES"] = {
            "default": db_config,
            # Also provide access to production DB for cloning operations
            "production": get_database_config("production"),
        }
    
    # Apply Redis/Celery settings
    redis_url = get_redis_url()
    if redis_url:
        settings_module["CELERY_BROKER_URL"] = redis_url
        settings_module["CELERY_RESULT_BACKEND"] = redis_url
        # Disable eager mode when Redis is available
        settings_module["CELERY_TASK_ALWAYS_EAGER"] = False
        settings_module["CELERY_TASK_EAGER_PROPAGATES"] = False
    else:
        # No Redis = run Celery tasks synchronously (no worker needed!)
        settings_module["CELERY_TASK_ALWAYS_EAGER"] = True
        settings_module["CELERY_TASK_EAGER_PROPAGATES"] = True
    
    # Apply service URL overrides
    embed_url = get_service_url("embedding_service")
    if embed_url:
        settings_module["EMBED_BASE_URL"] = embed_url
        settings_module["EMBED_SVC_URL"] = embed_url
    
    llm_url = get_service_url("llm_service")
    if llm_url:
        settings_module["LLM_BASE_URL"] = llm_url
    
    # Mark that we're in local mode
    settings_module["LOCAL_MODE"] = True
    settings_module["ENVIRONMENT_MODE"] = mode
    
    return settings_module


# Export useful constants
__all__ = [
    "get_local_config",
    "get_environment_mode", 
    "get_database_config",
    "get_redis_url",
    "get_service_url",
    "is_local_mode",
    "is_homolog_mode",
    "apply_local_settings",
    "LOCAL_CREDENTIALS_FILE",
]

