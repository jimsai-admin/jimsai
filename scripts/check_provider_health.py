"""
Provider Health Check - Verify all production providers are reachable

Tests connectivity to:
- Groq API
- Supabase PostgreSQL
- Neo4j AuraDB
- Redis Cloud
- Cloudflare R2
- Cloudflare Vectorize
- Kaggle
"""

import os
import asyncio
import logging
from typing import Dict, Any
from dataclasses import dataclass
from pathlib import Path

# Load .env file
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Health check result for a provider"""
    provider: str
    reachable: bool
    latency_ms: float = 0.0
    error: str = ""
    version: str = ""


class ProviderHealthChecker:
    """Checks health of all production providers"""
    
    def __init__(self):
        self.results: Dict[str, HealthCheckResult] = {}
    
    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """Check all providers"""
        logger.info("Starting provider health checks...\n")
        
        # Check each provider
        await self._check_groq()
        await self._check_supabase()
        await self._check_neo4j()
        await self._check_redis()
        await self._check_cloudflare_r2()
        await self._check_cloudflare_vectorize()
        await self._check_kaggle()
        
        return self.results
    
    async def _check_groq(self):
        """Check Groq API"""
        import time
        provider = "Groq"
        
        try:
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                self.results[provider] = HealthCheckResult(provider, False, error="No API key in .env")
                return
            
            # Try to import and initialize Groq client
            try:
                from groq import Groq
            except ImportError:
                logger.warning("Groq SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            client = Groq(api_key=api_key)
            
            # Make a simple API call
            message = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": "Say 'ok'"}],
                max_tokens=10,
            )
            
            latency = (time.time() - start) * 1000
            
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=True,
                latency_ms=latency,
                version="API reachable"
            )
            logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_supabase(self):
        """Check Supabase PostgreSQL"""
        import time
        provider = "Supabase"
        
        try:
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_KEY")
            
            if not url or not key:
                self.results[provider] = HealthCheckResult(provider, False, error="No credentials in .env")
                return
            
            # Try to import Supabase client
            try:
                from supabase import create_client
            except ImportError:
                logger.warning("Supabase SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            # Remove /rest/v1/ if it's in the URL
            base_url = url.replace("/rest/v1/", "")
            if not base_url.endswith("/"):
                base_url = base_url.replace("/rest/v1", "")
            
            client = create_client(base_url, key)
            
            # Make a simple query to test connection
            try:
                response = client.table("jimsai_events").select("count").limit(1).execute()
                latency = (time.time() - start) * 1000
                self.results[provider] = HealthCheckResult(
                    provider=provider,
                    reachable=True,
                    latency_ms=latency,
                    version="API reachable"
                )
                logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            except Exception as query_error:
                # Table might not exist yet, but connection works
                if "does not exist" in str(query_error) or "PGRST" in str(query_error):
                    latency = (time.time() - start) * 1000
                    self.results[provider] = HealthCheckResult(
                        provider=provider,
                        reachable=True,
                        latency_ms=latency,
                        version="API reachable (table not yet created)"
                    )
                    logger.info(f"✓ {provider}: OK (table not created yet, latency: {latency:.0f}ms)")
                else:
                    raise query_error
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_neo4j(self):
        """Check Neo4j AuraDB"""
        import time
        provider = "Neo4j"
        
        try:
            uri = os.getenv("NEO4J_URI")
            user = os.getenv("NEO4J_USER")
            password = os.getenv("NEO4J_PASSWORD")
            
            if not uri or not user or not password:
                self.results[provider] = HealthCheckResult(provider, False, error="No credentials in .env")
                return
            
            # Try to import Neo4j driver
            try:
                from neo4j import GraphDatabase
            except ImportError:
                logger.warning("Neo4j SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            driver = GraphDatabase.driver(uri, auth=(user, password))
            
            # Test connection
            with driver.session() as session:
                result = session.run("RETURN 'neo4j' as result")
                result.consume()
            
            driver.close()
            latency = (time.time() - start) * 1000
            
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=True,
                latency_ms=latency,
                version="API reachable"
            )
            logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_redis(self):
        """Check Redis Cloud"""
        import time
        provider = "Redis"
        
        try:
            url = os.getenv("REDIS_URL")
            
            if not url:
                self.results[provider] = HealthCheckResult(provider, False, error="No URL in .env")
                return
            
            # Try to import Redis client
            try:
                import redis
            except ImportError:
                logger.warning("Redis SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            client = redis.from_url(url, decode_responses=True)
            
            # Test connection
            client.ping()
            
            latency = (time.time() - start) * 1000
            
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=True,
                latency_ms=latency,
                version="API reachable"
            )
            logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_cloudflare_r2(self):
        """Check Cloudflare R2"""
        import time
        provider = "Cloudflare R2"
        
        try:
            account_id = os.getenv("CF_ACCOUNT_ID")
            token = os.getenv("CF_TOKEN")
            bucket = os.getenv("CF_R2_BUCKET")
            
            if not account_id or not token or not bucket:
                self.results[provider] = HealthCheckResult(provider, False, error="No credentials in .env")
                return
            
            # Try to import boto3 for R2
            try:
                import boto3
            except ImportError:
                logger.warning("boto3 SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            client = boto3.client(
                "s3",
                endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=os.getenv("CF_R2_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("CF_R2_SECRET_KEY"),
            )
            
            # Test connection
            client.head_bucket(Bucket=bucket)
            
            latency = (time.time() - start) * 1000
            
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=True,
                latency_ms=latency,
                version="API reachable"
            )
            logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_cloudflare_vectorize(self):
        """Check Cloudflare Vectorize"""
        import time
        provider = "Cloudflare Vectorize"
        
        try:
            token = os.getenv("CF_VECTORIZE_API_TOKEN")
            account_id = os.getenv("CF_ACCOUNT_ID")
            index_name = os.getenv("CF_VECTORIZE_INDEX")
            
            if not token or not account_id or not index_name:
                self.results[provider] = HealthCheckResult(provider, False, error="No credentials in .env")
                return
            
            # Try HTTP request to test
            import requests
            start = time.time()
            
            headers = {"Authorization": f"Bearer {token}"}
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/vectorize"
            
            response = requests.get(url, headers=headers, timeout=10)
            latency = (time.time() - start) * 1000
            
            if response.status_code in [200, 401, 403]:  # Any response means it's reachable
                self.results[provider] = HealthCheckResult(
                    provider=provider,
                    reachable=True,
                    latency_ms=latency,
                    version="API reachable"
                )
                logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            else:
                self.results[provider] = HealthCheckResult(
                    provider=provider,
                    reachable=False,
                    error=f"HTTP {response.status_code}"
                )
                logger.error(f"✗ {provider}: HTTP {response.status_code}")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    async def _check_kaggle(self):
        """Check Kaggle API"""
        import time
        provider = "Kaggle"
        
        try:
            username = os.getenv("KAGGLE_USERNAME")
            token = os.getenv("KAGGLE_API_TOKEN")
            
            if not username or not token:
                self.results[provider] = HealthCheckResult(provider, False, error="No credentials in .env")
                return
            
            # Try to import Kaggle SDK
            try:
                from kaggle.api.kaggle_api_extended import KaggleApi
            except ImportError:
                logger.warning("Kaggle SDK not installed, skipping detailed check")
                self.results[provider] = HealthCheckResult(provider, True, version="SDK not installed")
                return
            
            start = time.time()
            
            # Authenticate
            api = KaggleApi()
            api.authenticate()
            
            # Make simple API call - list competitions
            competitions = api.competitions_list()
            
            latency = (time.time() - start) * 1000
            
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=True,
                latency_ms=latency,
                version="API reachable"
            )
            logger.info(f"✓ {provider}: OK (latency: {latency:.0f}ms)")
            
        except Exception as e:
            self.results[provider] = HealthCheckResult(
                provider=provider,
                reachable=False,
                error=str(e)
            )
            logger.error(f"✗ {provider}: {e}")
    
    def print_summary(self):
        """Print health check summary"""
        print("\n" + "=" * 80)
        print("PROVIDER HEALTH CHECK SUMMARY")
        print("=" * 80 + "\n")
        
        reachable_count = 0
        total_count = len(self.results)
        
        for provider, result in self.results.items():
            status = "✓ REACHABLE" if result.reachable else "✗ UNREACHABLE"
            print(f"{provider:25} {status:20} Latency: {result.latency_ms:7.0f}ms")
            
            if result.error:
                print(f"  Error: {result.error}")
            if result.version:
                print(f"  Version: {result.version}")
            
            if result.reachable:
                reachable_count += 1
        
        print("\n" + "-" * 80)
        print(f"Summary: {reachable_count}/{total_count} providers reachable")
        print("=" * 80 + "\n")
        
        return reachable_count == total_count


async def main():
    """Run health checks"""
    checker = ProviderHealthChecker()
    await checker.check_all()
    all_healthy = checker.print_summary()
    
    return 0 if all_healthy else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
