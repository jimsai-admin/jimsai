"""
Production Configuration & Deployment Templates

Provides environment-specific configurations for deploying JimsAI at different scales:
- Development: Local with mocked providers
- Staging: Real providers, limited traffic
- Production: Full-scale with real providers, multi-tenant
"""

import os
from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class Environment(Enum):
    """Deployment environment"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentTemplate:
    """Base deployment configuration"""
    
    def __init__(self, environment: Environment):
        self.environment = environment
        self.providers_config: Dict[str, Dict[str, Any]] = {}
        self.database_config: Dict[str, Any] = {}
        self.cache_config: Dict[str, Any] = {}
        self.monitoring_config: Dict[str, Any] = {}
    
    def load_from_env(self):
        """Load configuration from environment variables"""
        raise NotImplementedError
    
    def validate(self) -> bool:
        """Validate configuration is complete"""
        raise NotImplementedError
    
    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get configuration for specific provider"""
        return self.providers_config.get(provider, {})


class DevelopmentTemplate(DeploymentTemplate):
    """Development environment configuration (local machine)"""
    
    def __init__(self):
        super().__init__(Environment.DEVELOPMENT)
        self.load_from_env()
    
    def load_from_env(self):
        """Load dev configuration"""
        
        # Providers: Use mock implementations
        self.providers_config = {
            'groq': {
                'enabled': True,
                'type': 'mock',  # Mocked responses
                'model_t1': 'mock-t1',
                'model_t2': 'mock-t2',
            },
            'supabase': {
                'enabled': True,
                'type': 'mock',
                'db_type': 'sqlite',  # SQLite for local
                'db_path': ':memory:',
            },
            'vectorize': {
                'enabled': True,
                'type': 'mock',
            },
            'neo4j': {
                'enabled': False,  # Optional locally
            },
            'r2': {
                'enabled': False,  # Local file storage instead
            },
            'kaggle': {
                'enabled': False,  # Skip training locally
            },
        }
        
        # Database
        self.database_config = {
            'type': 'sqlite',
            'path': 'jimsai-dev.db',
            'pool_size': 1,
            'echo': True,  # Log SQL
        }
        
        # Cache
        self.cache_config = {
            'type': 'memory',  # In-memory cache
            'ttl_seconds': 300,
        }
        
        # Monitoring
        self.monitoring_config = {
            'enabled': True,
            'log_level': 'DEBUG',
            'metrics_enabled': False,
        }
    
    def validate(self) -> bool:
        """Validate dev configuration"""
        return True


class StagingTemplate(DeploymentTemplate):
    """Staging environment configuration (limited real providers)"""
    
    def __init__(self):
        super().__init__(Environment.STAGING)
        self.load_from_env()
    
    def load_from_env(self):
        """Load staging configuration"""
        
        # Providers: Real but with limits
        self.providers_config = {
            'groq': {
                'enabled': True,
                'type': 'real',
                'api_key': os.getenv('GROQ_API_KEY_STAGING'),
                'model_t1': 'mixtral-8x7b-32768',
                'model_t2': 'llama2-70b-4096',
                'rate_limit': 100,  # 100 req/min
            },
            'supabase': {
                'enabled': True,
                'type': 'real',
                'url': os.getenv('SUPABASE_URL_STAGING'),
                'key': os.getenv('SUPABASE_KEY_STAGING'),
                'db_pool_size': 5,
            },
            'vectorize': {
                'enabled': True,
                'type': 'real',
                'account_id': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
                'api_token': os.getenv('CLOUDFLARE_API_TOKEN'),
            },
            'neo4j': {
                'enabled': True,
                'type': 'real',
                'endpoint': os.getenv('NEO4J_STAGING_ENDPOINT', 'bolt://localhost:7687'),
                'username': os.getenv('NEO4J_USERNAME_STAGING'),
                'password': os.getenv('NEO4J_PASSWORD_STAGING'),
            },
            'r2': {
                'enabled': True,
                'type': 'real',
                'account_id': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
                'bucket': 'jimsai-staging',
            },
            'kaggle': {
                'enabled': True,
                'type': 'real',
                'username': os.getenv('KAGGLE_USERNAME'),
                'api_key': os.getenv('KAGGLE_API_KEY'),
                'max_jobs': 2,  # Limit concurrent jobs
            },
        }
        
        # Database
        self.database_config = {
            'type': 'postgresql',
            'host': os.getenv('DB_HOST_STAGING', 'localhost'),
            'port': int(os.getenv('DB_PORT_STAGING', '5432')),
            'user': os.getenv('DB_USER_STAGING'),
            'password': os.getenv('DB_PASSWORD_STAGING'),
            'database': os.getenv('DB_NAME_STAGING', 'jimsai_staging'),
            'pool_size': 20,
            'max_overflow': 10,
            'ssl_mode': 'require',
        }
        
        # Cache
        self.cache_config = {
            'type': 'redis',
            'host': os.getenv('REDIS_HOST_STAGING', 'localhost'),
            'port': int(os.getenv('REDIS_PORT_STAGING', '6379')),
            'db': 0,
            'ttl_seconds': 600,
        }
        
        # Monitoring
        self.monitoring_config = {
            'enabled': True,
            'log_level': 'INFO',
            'metrics_enabled': True,
            'prometheus_port': 9090,
            'tracing_enabled': True,
        }
    
    def validate(self) -> bool:
        """Validate staging configuration"""
        required_env_vars = [
            'GROQ_API_KEY_STAGING',
            'SUPABASE_URL_STAGING',
            'SUPABASE_KEY_STAGING',
            'CLOUDFLARE_ACCOUNT_ID',
        ]
        return all(os.getenv(var) for var in required_env_vars)


class ProductionTemplate(DeploymentTemplate):
    """Production environment configuration (full-scale, multi-tenant)"""
    
    def __init__(self):
        super().__init__(Environment.PRODUCTION)
        self.load_from_env()
    
    def load_from_env(self):
        """Load production configuration"""
        
        # Providers: All real with high performance
        self.providers_config = {
            'groq': {
                'enabled': True,
                'type': 'real',
                'api_key': os.getenv('GROQ_API_KEY_PROD'),
                'model_t1': 'mixtral-8x7b-32768',
                'model_t2': 'llama2-70b-4096',
                'rate_limit': 10000,  # 10k req/min
                'timeout_seconds': 30,
                'retry_attempts': 3,
            },
            'supabase': {
                'enabled': True,
                'type': 'real',
                'url': os.getenv('SUPABASE_URL_PROD'),
                'key': os.getenv('SUPABASE_KEY_PROD'),
                'db_pool_size': 50,
                'max_overflow': 20,
                'ssl_mode': 'require',
            },
            'vectorize': {
                'enabled': True,
                'type': 'real',
                'account_id': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
                'api_token': os.getenv('CLOUDFLARE_API_TOKEN'),
                'index_replicas': 3,  # High availability
            },
            'neo4j': {
                'enabled': True,
                'type': 'real',
                'endpoint': os.getenv('NEO4J_PROD_ENDPOINT'),
                'username': os.getenv('NEO4J_USERNAME_PROD'),
                'password': os.getenv('NEO4J_PASSWORD_PROD'),
                'cluster': True,  # Cluster mode
            },
            'r2': {
                'enabled': True,
                'type': 'real',
                'account_id': os.getenv('CLOUDFLARE_ACCOUNT_ID'),
                'bucket': 'jimsai-prod',
                'caching_rules': {
                    'images': 86400,  # 1 day
                    'models': 604800,  # 7 days
                },
            },
            'kaggle': {
                'enabled': True,
                'type': 'real',
                'username': os.getenv('KAGGLE_USERNAME'),
                'api_key': os.getenv('KAGGLE_API_KEY'),
                'max_jobs': 10,  # More concurrent jobs
                'gpu_quota': 'high',
            },
        }
        
        # Database
        self.database_config = {
            'type': 'postgresql',
            'host': os.getenv('DB_HOST_PROD'),
            'port': int(os.getenv('DB_PORT_PROD', '5432')),
            'user': os.getenv('DB_USER_PROD'),
            'password': os.getenv('DB_PASSWORD_PROD'),
            'database': os.getenv('DB_NAME_PROD', 'jimsai'),
            'pool_size': 100,
            'max_overflow': 50,
            'ssl_mode': 'require',
            'replication': True,  # Enable replication
            'backup_enabled': True,
            'backup_interval_hours': 6,
        }
        
        # Cache
        self.cache_config = {
            'type': 'redis_cluster',
            'nodes': os.getenv('REDIS_CLUSTER_NODES', '').split(','),
            'cluster_mode': True,
            'ttl_seconds': 3600,
            'max_memory_mb': 10000,
            'eviction_policy': 'allkeys-lru',
        }
        
        # Monitoring
        self.monitoring_config = {
            'enabled': True,
            'log_level': 'INFO',
            'metrics_enabled': True,
            'prometheus_enabled': True,
            'prometheus_port': 9090,
            'tracing_enabled': True,
            'tracing_sample_rate': 0.1,  # 10% sampling
            'alerting_enabled': True,
            'alert_channels': ['slack', 'pagerduty'],
        }
    
    def validate(self) -> bool:
        """Validate production configuration"""
        required_env_vars = [
            'GROQ_API_KEY_PROD',
            'SUPABASE_URL_PROD',
            'SUPABASE_KEY_PROD',
            'CLOUDFLARE_ACCOUNT_ID',
            'CLOUDFLARE_API_TOKEN',
            'NEO4J_PROD_ENDPOINT',
            'DB_HOST_PROD',
            'DB_USER_PROD',
            'DB_PASSWORD_PROD',
            'REDIS_CLUSTER_NODES',
        ]
        return all(os.getenv(var) for var in required_env_vars)


# ============================================================================
# Configuration Manager
# ============================================================================

class ConfigurationManager:
    """Manages environment-specific configuration"""
    
    _instance: Optional['ConfigurationManager'] = None
    
    def __init__(self, environment: Optional[str] = None):
        env_str = environment or os.getenv('JIMSAI_ENV', 'development')
        
        try:
            self.environment = Environment(env_str)
        except ValueError:
            self.environment = Environment.DEVELOPMENT
        
        # Load appropriate template
        if self.environment == Environment.DEVELOPMENT:
            self.template = DevelopmentTemplate()
        elif self.environment == Environment.STAGING:
            self.template = StagingTemplate()
        else:
            self.template = ProductionTemplate()
        
        # Validate configuration
        if not self.template.validate():
            raise RuntimeError(
                f"Invalid configuration for {self.environment.value} environment. "
                "Check required environment variables."
            )
    
    @classmethod
    def get_instance(cls, environment: Optional[str] = None) -> 'ConfigurationManager':
        """Singleton access"""
        if cls._instance is None:
            cls._instance = ConfigurationManager(environment)
        return cls._instance
    
    @property
    def env(self) -> Environment:
        """Current environment"""
        return self.environment
    
    def is_development(self) -> bool:
        """Check if development environment"""
        return self.environment == Environment.DEVELOPMENT
    
    def is_staging(self) -> bool:
        """Check if staging environment"""
        return self.environment == Environment.STAGING
    
    def is_production(self) -> bool:
        """Check if production environment"""
        return self.environment == Environment.PRODUCTION
    
    def get_provider_config(self, provider: str) -> Dict[str, Any]:
        """Get provider configuration"""
        return self.template.get_provider_config(provider)
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration"""
        return self.template.database_config
    
    def get_cache_config(self) -> Dict[str, Any]:
        """Get cache configuration"""
        return self.template.cache_config
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """Get monitoring configuration"""
        return self.template.monitoring_config


# ============================================================================
# Environment Setup Examples
# ============================================================================

"""
Development Setup:
    export JIMSAI_ENV=development
    python -c "from prototype.jimsai.config import ConfigurationManager; cm = ConfigurationManager.get_instance(); print(cm.env)"

Staging Setup:
    export JIMSAI_ENV=staging
    export GROQ_API_KEY_STAGING=sk_...
    export SUPABASE_URL_STAGING=https://...
    export SUPABASE_KEY_STAGING=eyJ...
    export CLOUDFLARE_ACCOUNT_ID=...
    export CLOUDFLARE_API_TOKEN=...

Production Setup:
    export JIMSAI_ENV=production
    export GROQ_API_KEY_PROD=sk_...
    export SUPABASE_URL_PROD=https://...
    export SUPABASE_KEY_PROD=eyJ...
    export NEO4J_PROD_ENDPOINT=bolt+s://...
    export DB_HOST_PROD=postgres.example.com
    export DB_USER_PROD=jimsai
    export DB_PASSWORD_PROD=...
    export REDIS_CLUSTER_NODES=redis1:6379,redis2:6379,redis3:6379
"""
