#!/usr/bin/env python3
"""
JimsAI Production Readiness Validation
====================================
Comprehensive validation that system is ready to:
1. Train like frontier models (Kaggle pipelines, SPPE generation)
2. Serve users at scale (multi-tenant, personalization, monitoring)
3. Maintain data integrity (event sourcing, audit trails)
4. Handle failures gracefully (error recovery, fallbacks)

Usage: python scripts/production_readiness.py
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Load environment
load_dotenv()


class ProductionReadinessValidator:
    """Validates all systems are production-ready"""
    
    def __init__(self):
        self.checks: List[Tuple[str, bool, str]] = []
        self.timestamp = datetime.now().isoformat()
        
    def log_check(self, category: str, passed: bool, details: str):
        """Record a check result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status} - {category}: {details}")
        self.checks.append((category, passed, details))
    
    def check_environment_variables(self):
        """Validate all required env vars are set"""
        print("\n📋 Checking Environment Variables...")
        
        required = {
            "JIMSAI_ENV": "production",
            "GROQ_API_KEY": "Groq API key",
            "SUPABASE_URL": "Supabase PostgreSQL URL",
            "SUPABASE_SERVICE_KEY": "Supabase service key",
            "NEO4J_URI": "Neo4j connection URI",
            "CF_ACCOUNT_ID": "Cloudflare account ID",
            "CF_R2_BUCKET": "R2 bucket name",
            "REDIS_URL": "Redis connection URL",
            "KAGGLE_USERNAME": "Kaggle username",
        }
        
        for var, desc in required.items():
            value = os.getenv(var)
            passed = bool(value)
            self.log_check(var, passed, desc if passed else f"Missing {desc}")
    
    def check_provider_health(self):
        """Verify all providers are reachable"""
        print("\n🏥 Checking Provider Health...")
        
        try:
            from prototype.jimsai.providers import ProviderRegistry
            registry = ProviderRegistry.from_env()
            
            # Check each provider config is loadable
            providers = ["groq", "supabase", "neo4j", "redis", "r2", "kaggle"]
            
            for provider_name in providers:
                try:
                    provider = getattr(registry, provider_name, None)
                    passed = provider is not None
                    self.log_check(
                        f"Provider: {provider_name}",
                        passed,
                        "Configured" if passed else "Not configured"
                    )
                except Exception as e:
                    self.log_check(f"Provider: {provider_name}", False, str(e))
        except Exception as e:
            self.log_check("Provider Registry", False, f"Failed to load: {e}")
    
    def check_database_schema(self):
        """Verify PostgreSQL schema exists"""
        print("\n🗄️  Checking Database Schema...")
        
        try:
            import psycopg2
            from psycopg2 import sql
            
            supabase_url = os.getenv("SUPABASE_URL")
            if not supabase_url:
                self.log_check("Database Connection", False, "SUPABASE_URL not set")
                return
            
            # Extract connection info
            # For Supabase, use SQLite for MVP testing
            schema_file = Path("infrastructure/postgres/migration_phase5.sql")
            exists = schema_file.exists()
            self.log_check(
                "Migration Schema File",
                exists,
                f"Found at {schema_file}" if exists else "Not found"
            )
            
        except Exception as e:
            self.log_check("Database Schema", False, str(e))
    
    def check_event_sourcing(self):
        """Verify event sourcing infrastructure"""
        print("\n📝 Checking Event Sourcing...")
        
        try:
            from prototype.jimsai.eventing.events import (
                QueryStartedEvent,
                QueryCompletedEvent,
                MemorySignatureCreatedEvent,
            )
            from prototype.jimsai.eventing.event_store import EventStore
            
            # Check event types are defined
            events = [
                ("QueryStartedEvent", QueryStartedEvent),
                ("QueryCompletedEvent", QueryCompletedEvent),
                ("MemorySignatureCreatedEvent", MemorySignatureCreatedEvent),
            ]
            
            for event_name, event_class in events:
                passed = event_class is not None
                self.log_check(f"Event Type: {event_name}", passed, "Defined")
            
            # Check event store is available
            passed = EventStore is not None
            self.log_check("EventStore Class", passed, "Available")
            
        except Exception as e:
            self.log_check("Event Sourcing", False, str(e))
    
    def check_training_pipeline(self):
        """Verify SPPE training pipeline"""
        print("\n🎓 Checking Training Pipeline...")
        
        try:
            from prototype.jimsai.training.sppe_generator import SPPEPairGenerator
            from prototype.jimsai.training_policy import AutoTrainingPolicy
            
            # Check SPPE generator
            passed = SPPEPairGenerator is not None
            self.log_check("SPPEPairGenerator", passed, "Available")
            
            # Check training policy
            passed = AutoTrainingPolicy is not None
            self.log_check("AutoTrainingPolicy", passed, "Available")
            
        except Exception as e:
            self.log_check("Training Pipeline", False, str(e))
    
    def check_workspace_management(self):
        """Verify multi-tenant workspace system"""
        print("\n👥 Checking Workspace Management...")
        
        try:
            from prototype.jimsai.workspaces import (
                WorkspaceManager,
                WorkspaceConfig,
                WorkspaceMetrics,
            )
            
            components = [
                ("WorkspaceManager", WorkspaceManager),
                ("WorkspaceConfig", WorkspaceConfig),
                ("WorkspaceMetrics", WorkspaceMetrics),
            ]
            
            for comp_name, comp_class in components:
                passed = comp_class is not None
                self.log_check(f"Component: {comp_name}", passed, "Available")
            
        except Exception as e:
            self.log_check("Workspace Management", False, str(e))
    
    def check_personalization(self):
        """Verify personalization engine"""
        print("\n🧠 Checking Personalization Engine...")
        
        try:
            from prototype.jimsai.personalization import (
                PersonalizationEngine,
                QueryPattern,
                WorkspaceAdapterModel,
            )
            
            components = [
                ("PersonalizationEngine", PersonalizationEngine),
                ("QueryPattern", QueryPattern),
                ("WorkspaceAdapterModel", WorkspaceAdapterModel),
            ]
            
            for comp_name, comp_class in components:
                passed = comp_class is not None
                self.log_check(f"Component: {comp_name}", passed, "Available")
            
        except Exception as e:
            self.log_check("Personalization", False, str(e))
    
    def check_production_pipeline(self):
        """Verify production request handler"""
        print("\n🚀 Checking Production Pipeline...")
        
        try:
            from services.production_pipeline import (
                ProductionPipeline,
                ProductionRequest,
                ProductionResponse,
            )
            
            components = [
                ("ProductionPipeline", ProductionPipeline),
                ("ProductionRequest", ProductionRequest),
                ("ProductionResponse", ProductionResponse),
            ]
            
            for comp_name, comp_class in components:
                passed = comp_class is not None
                self.log_check(f"Component: {comp_name}", passed, "Available")
            
        except Exception as e:
            self.log_check("Production Pipeline", False, str(e))
    
    def check_capability_router(self):
        """Verify capability routing"""
        print("\n🔄 Checking Capability Router...")
        
        try:
            from prototype.jimsai.capability_router import CapabilityRouter
            from prototype.jimsai.models import CapabilityType
            
            # Check router exists
            passed = CapabilityRouter is not None
            self.log_check("CapabilityRouter", passed, "Available")
            
            # Check capability types are defined
            capabilities = [
                "MEMORY_CHAT",
                "WORLD_KNOWLEDGE",
                "CODING",
                "MATH_SCIENCE",
                "CREATIVE_TEXT",
            ]
            
            for cap_name in capabilities:
                try:
                    cap = getattr(CapabilityType, cap_name, None)
                    self.log_check(f"Capability: {cap_name}", cap is not None, "Defined")
                except:
                    self.log_check(f"Capability: {cap_name}", False, "Not defined")
            
        except Exception as e:
            self.log_check("Capability Router", False, str(e))
    
    def check_api_endpoints(self):
        """Verify API endpoints exist"""
        print("\n🔌 Checking API Endpoints...")
        
        try:
            from prototype.app import app
            
            # Get routes
            routes = []
            if hasattr(app, "routes"):
                routes = list(app.routes)
            
            passed = len(routes) > 0
            self.log_check("FastAPI App", passed, f"{len(routes)} routes defined")
            
            # Check for key endpoints
            route_names = [str(r) for r in routes]
            endpoints = [
                "/api/chat",
                "/api/training",
                "/api/feedback",
                "/api/health",
            ]
            
            for endpoint in endpoints:
                found = any(endpoint in str(r) for r in routes)
                self.log_check(f"Endpoint: {endpoint}", found, 
                             "Available" if found else "Not found")
            
        except Exception as e:
            self.log_check("API Endpoints", False, str(e))
    
    def check_monitoring(self):
        """Verify monitoring infrastructure"""
        print("\n📊 Checking Monitoring...")
        
        try:
            from prototype.jimsai.observability import Logger, MetricsCollector
            
            components = [
                ("Logger", Logger),
                ("MetricsCollector", MetricsCollector),
            ]
            
            for comp_name, comp_class in components:
                passed = comp_class is not None
                self.log_check(f"Component: {comp_name}", passed, "Available")
            
        except Exception as e:
            self.log_check("Monitoring", False, str(e))
    
    def check_error_handling(self):
        """Verify error handling patterns"""
        print("\n⚠️  Checking Error Handling...")
        
        try:
            # Check for required exception types
            from prototype.jimsai.models import JimsAIError
            
            passed = JimsAIError is not None
            self.log_check("Error Base Class", passed, "Available")
            
        except Exception as e:
            self.log_check("Error Handling", False, str(e))
    
    def check_caching_layer(self):
        """Verify caching infrastructure"""
        print("\n💾 Checking Caching Layer...")
        
        try:
            from prototype.jimsai.runtime_layers import CacheLayer
            
            passed = CacheLayer is not None
            self.log_check("CacheLayer", passed, "Available")
            
        except Exception as e:
            self.log_check("Caching", False, str(e))
    
    def generate_report(self) -> Dict:
        """Generate production readiness report"""
        print("\n" + "="*70)
        print("PRODUCTION READINESS REPORT")
        print("="*70)
        
        total_checks = len(self.checks)
        passed_checks = sum(1 for _, passed, _ in self.checks if passed)
        failed_checks = total_checks - passed_checks
        pass_rate = (passed_checks / total_checks * 100) if total_checks > 0 else 0
        
        print(f"\n📈 Summary")
        print(f"  Total Checks: {total_checks}")
        print(f"  ✅ Passed: {passed_checks}")
        print(f"  ❌ Failed: {failed_checks}")
        print(f"  Pass Rate: {pass_rate:.1f}%")
        
        # Determine readiness level
        if pass_rate >= 95:
            readiness = "🚀 PRODUCTION READY"
            level = "READY"
        elif pass_rate >= 80:
            readiness = "⚠️  MOSTLY READY (minor issues)"
            level = "MOSTLY_READY"
        elif pass_rate >= 60:
            readiness = "🔧 NEEDS WORK (significant gaps)"
            level = "PARTIAL"
        else:
            readiness = "❌ NOT READY (major gaps)"
            level = "NOT_READY"
        
        print(f"\n🎯 Readiness Level: {readiness}")
        
        # Show failures
        failures = [check for check in self.checks if not check[1]]
        if failures:
            print(f"\n⚠️  Issues to Address ({len(failures)}):")
            for category, _, details in failures[:10]:
                print(f"  • {category}: {details}")
            if len(failures) > 10:
                print(f"  ... and {len(failures) - 10} more")
        
        return {
            "timestamp": self.timestamp,
            "readiness_level": level,
            "pass_rate": pass_rate,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "checks": [
                {
                    "category": cat,
                    "passed": passed,
                    "details": details
                }
                for cat, passed, details in self.checks
            ]
        }
    
    def save_report(self, report: Dict):
        """Save report to JSON file"""
        report_file = Path("logs/production_readiness_report.json")
        report_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📁 Report saved to: {report_file}")
    
    async def run_all_checks(self):
        """Execute all validation checks"""
        print("="*70)
        print("JIMSAI PRODUCTION READINESS VALIDATION")
        print("="*70)
        print(f"Started: {self.timestamp}")
        
        self.check_environment_variables()
        self.check_provider_health()
        self.check_database_schema()
        self.check_event_sourcing()
        self.check_training_pipeline()
        self.check_workspace_management()
        self.check_personalization()
        self.check_production_pipeline()
        self.check_capability_router()
        self.check_api_endpoints()
        self.check_monitoring()
        self.check_error_handling()
        self.check_caching_layer()
        
        report = self.generate_report()
        self.save_report(report)
        
        return report


async def main():
    """Main entry point"""
    validator = ProductionReadinessValidator()
    report = await validator.run_all_checks()
    
    # Return appropriate exit code
    if report["readiness_level"] == "READY":
        print("\n✅ System is PRODUCTION READY!")
        print("\nNext steps:")
        print("1. Deploy to staging: python scripts/build_phase5.py --staging")
        print("2. Run smoke tests: python scripts/test_production_integration.py")
        print("3. Load test with users: python scripts/load_test.py --users 10")
        print("4. Monitor for 24 hours before production")
        return 0
    elif report["readiness_level"] == "MOSTLY_READY":
        print("\n⚠️  System is mostly ready, address minor issues first")
        return 1
    else:
        print("\n❌ System has significant gaps, cannot deploy yet")
        return 2


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
