"""
Configuration loader for Phase 4 providers and API keys.

Loads environment variables with fallback defaults and validation.
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class WebSearchConfig:
    """Web search provider configuration."""
    duckduckgo_enabled: bool = True
    duckduckgo_instant_answers: bool = True
    brave_search_enabled: bool = False
    brave_api_key: Optional[str] = None
    rate_limit_per_minute: int = 30


@dataclass
class DockerConfig:
    """Docker container configuration."""
    enabled: bool = True
    socket: str = "npipe:////./pipe/docker_engine"  # Windows default
    timeout_seconds: int = 30
    max_memory_mb: int = 512
    image_python: str = "python:3.11-slim"
    image_nodejs: str = "node:18-slim"


@dataclass
class Z3Config:
    """Z3 SMT solver configuration."""
    enabled: bool = True
    timeout_seconds: int = 10
    solver_strategy: str = "auto"  # auto, qe, nlsat, cad


@dataclass
class KaggleConfig:
    """Kaggle API configuration for training orchestration."""
    username: Optional[str] = None
    api_key: Optional[str] = None
    dataset_owner: str = "jimsai_training"
    enabled: bool = False


@dataclass
class SystemConfig:
    """Overall system configuration."""
    environment: str = "development"
    log_level: str = "INFO"
    debug_mode: bool = False
    redis_enabled: bool = False
    redis_url: Optional[str] = None


class Config:
    """Central configuration loader."""
    
    def __init__(self, env_file: Optional[Path] = None):
        """Initialize configuration from .env file and environment variables."""
        # Load .env file if it exists
        if env_file is None:
            env_file = Path(__file__).parent.parent.parent / ".env"
        
        self._load_env_file(env_file)
        
        # Parse configurations
        self.web_search = self._load_web_search_config()
        self.docker = self._load_docker_config()
        self.z3 = self._load_z3_config()
        self.kaggle = self._load_kaggle_config()
        self.system = self._load_system_config()
    
    @staticmethod
    def _load_env_file(path: Path) -> None:
        """Load environment variables from .env file."""
        if path.exists():
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        if "=" in line:
                            key, value = line.split("=", 1)
                            if not os.environ.get(key):
                                os.environ[key] = value
    
    @staticmethod
    def _get_bool(key: str, default: bool = False) -> bool:
        """Get boolean environment variable."""
        value = os.environ.get(key, str(default)).lower()
        return value in ("true", "1", "yes", "on")
    
    @staticmethod
    def _get_str(key: str, default: str = "") -> str:
        """Get string environment variable."""
        return os.environ.get(key, default)
    
    @staticmethod
    def _get_int(key: str, default: int = 0) -> int:
        """Get integer environment variable."""
        try:
            return int(os.environ.get(key, default))
        except (ValueError, TypeError):
            return default
    
    def _load_web_search_config(self) -> WebSearchConfig:
        """Load web search configuration."""
        return WebSearchConfig(
            duckduckgo_enabled=self._get_bool("DUCKDUCKGO_API_ENABLED", True),
            duckduckgo_instant_answers=self._get_bool("DUCKDUCKGO_INSTANT_ANSWERS", True),
            brave_search_enabled=self._get_bool("BRAVE_SEARCH_ENABLED", False),
            brave_api_key=self._get_str("BRAVE_SEARCH_API_KEY"),
            rate_limit_per_minute=self._get_int("WEB_SEARCH_RATE_LIMIT_PER_MINUTE", 30),
        )
    
    def _load_docker_config(self) -> DockerConfig:
        """Load Docker configuration."""
        # Detect OS and set default socket
        default_socket = "npipe:////./pipe/docker_engine"  # Windows
        if os.name != "nt":  # Unix-like
            default_socket = "/var/run/docker.sock"
        
        return DockerConfig(
            enabled=self._get_bool("DOCKER_ENABLED", True),
            socket=self._get_str("DOCKER_SOCKET", default_socket),
            timeout_seconds=self._get_int("DOCKER_TIMEOUT_SECONDS", 30),
            max_memory_mb=self._get_int("DOCKER_MAX_MEMORY_MB", 512),
            image_python=self._get_str("DOCKER_IMAGE_PYTHON", "python:3.11-slim"),
            image_nodejs=self._get_str("DOCKER_IMAGE_NODEJS", "node:18-slim"),
        )
    
    def _load_z3_config(self) -> Z3Config:
        """Load Z3 configuration."""
        return Z3Config(
            enabled=self._get_bool("Z3_ENABLED", True),
            timeout_seconds=self._get_int("Z3_TIMEOUT_SECONDS", 10),
            solver_strategy=self._get_str("Z3_SOLVER_STRATEGY", "auto"),
        )
    
    def _load_kaggle_config(self) -> KaggleConfig:
        """Load Kaggle configuration."""
        return KaggleConfig(
            username=self._get_str("KAGGLE_USERNAME") or None,
            api_key=self._get_str("KAGGLE_API_KEY") or None,
            dataset_owner=self._get_str("KAGGLE_DATASET_OWNER", "jimsai_training"),
            enabled=self._get_bool("KAGGLE_ENABLED", False),
        )
    
    def _load_system_config(self) -> SystemConfig:
        """Load system configuration."""
        return SystemConfig(
            environment=self._get_str("ENVIRONMENT", "development"),
            log_level=self._get_str("LOG_LEVEL", "INFO"),
            debug_mode=self._get_bool("DEBUG_MODE", False),
            redis_enabled=self._get_bool("REDIS_ENABLED", False),
            redis_url=self._get_str("REDIS_URL") or None,
        )
    
    def validate(self) -> Dict[str, Any]:
        """Validate configuration and return status."""
        issues = []
        
        # Check web search
        if self.web_search.brave_search_enabled and not self.web_search.brave_api_key:
            issues.append("BRAVE_SEARCH_ENABLED but BRAVE_SEARCH_API_KEY not set")
        
        # Check Docker
        if self.docker.enabled and not os.path.exists(self.docker.socket):
            issues.append(f"Docker socket not found: {self.docker.socket}")
        
        # Check Kaggle
        if self.kaggle.enabled:
            if not self.kaggle.username or not self.kaggle.api_key:
                issues.append("KAGGLE_ENABLED but credentials missing")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "config_summary": {
                "web_search": "duckduckgo_enabled" if self.web_search.duckduckgo_enabled else "disabled",
                "docker": "enabled" if self.docker.enabled else "disabled",
                "z3": "enabled" if self.z3.enabled else "disabled",
                "kaggle": "enabled" if self.kaggle.enabled else "disabled",
                "environment": self.system.environment,
            }
        }


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get global configuration instance (singleton)."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def validate_config() -> bool:
    """Validate configuration and return True if valid."""
    config = get_config()
    result = config.validate()
    
    if not result["valid"]:
        for issue in result["issues"]:
            print(f"⚠️  Configuration Issue: {issue}")
    
    return result["valid"]
