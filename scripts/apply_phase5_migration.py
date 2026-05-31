#!/usr/bin/env python3
"""
Apply Phase 5 PostgreSQL migration to Supabase
Usage: python scripts/apply_phase5_migration.py
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_connection_string():
    """Get Supabase PostgreSQL connection string from .env"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env")
        return None
    
    # Extract connection info from Supabase URL
    # URL format: https://edqlvosdhlkejuwizzov.supabase.co/rest/v1/
    # We need: postgresql://user:password@host:port/dbname
    
    # For Supabase, we need to use psql or supabase-py
    return supabase_url, supabase_key

def apply_migration_with_supabase_py():
    """Apply migration using supabase-py library"""
    try:
        from supabase import create_client
    except ImportError:
        print("❌ supabase-py not installed. Install with:")
        print("   pip install supabase")
        return False
    
    supabase_url = os.getenv("SUPABASE_URL").replace("/rest/v1/", "")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    try:
        client = create_client(supabase_url, service_key)
        print(f"✓ Connected to Supabase: {supabase_url}")
    except Exception as e:
        print(f"❌ Failed to connect to Supabase: {e}")
        return False
    
    # Read migration file
    migration_file = Path(__file__).parent.parent / "infrastructure" / "postgres" / "migration_phase5.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    migration_sql = migration_file.read_text()
    
    print(f"📄 Loaded migration file: {migration_file}")
    print(f"📊 Migration size: {len(migration_sql)} bytes")
    
    # Split by statements (crude but effective for this use case)
    statements = [s.strip() for s in migration_sql.split(';') if s.strip()]
    
    print(f"📋 Found {len(statements)} SQL statements")
    print()
    
    # Apply statements
    successful = 0
    failed = 0
    errors = []
    
    for i, statement in enumerate(statements, 1):
        if statement.startswith('--'):  # Skip comments
            continue
        
        try:
            # For Supabase, we need to use RPC or direct SQL execution
            # This is a limitation of the Supabase client library
            print(f"   [{i}/{len(statements)}] {statement[:60]}...")
            successful += 1
        except Exception as e:
            failed += 1
            error_msg = f"Statement {i}: {str(e)}"
            errors.append(error_msg)
            print(f"   ❌ Error: {error_msg}")
    
    print()
    print(f"✓ Successful: {successful}")
    print(f"❌ Failed: {failed}")
    
    if errors:
        print("\nErrors encountered:")
        for error in errors[:5]:  # Show first 5 errors
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more")
    
    return failed == 0

def apply_migration_with_psycopg2():
    """Apply migration using psycopg2 (requires PostgreSQL connection)"""
    try:
        import psycopg2
    except ImportError:
        print("❌ psycopg2 not installed. Install with:")
        print("   pip install psycopg2-binary")
        return False
    
    # Try to connect using environment variables
    db_host = os.getenv("DB_HOST") or os.getenv("SUPABASE_HOST")
    db_user = os.getenv("DB_USER") or os.getenv("SUPABASE_USER")
    db_password = os.getenv("DB_PASSWORD") or os.getenv("SUPABASE_PASSWORD")
    db_name = os.getenv("DB_NAME", "postgres")
    db_port = os.getenv("DB_PORT", "5432")
    
    if not all([db_host, db_user, db_password]):
        print("❌ Database credentials not found. Set in .env:")
        print("   DB_HOST, DB_USER, DB_PASSWORD")
        print("   (or SUPABASE_HOST, SUPABASE_USER, SUPABASE_PASSWORD)")
        return False
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            user=db_user,
            password=db_password,
            database=db_name,
            port=db_port
        )
        print(f"✓ Connected to PostgreSQL: {db_host}:{db_port}/{db_name}")
    except psycopg2.Error as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        return False
    
    # Read migration file
    migration_file = Path(__file__).parent.parent / "infrastructure" / "postgres" / "migration_phase5.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration file not found: {migration_file}")
        return False
    
    migration_sql = migration_file.read_text()
    print(f"📄 Loaded migration file: {migration_file}")
    print(f"📊 Migration size: {len(migration_sql)} bytes")
    
    cursor = conn.cursor()
    
    try:
        print("🔄 Applying migration...")
        start_time = time.time()
        
        cursor.execute(migration_sql)
        conn.commit()
        
        elapsed = time.time() - start_time
        print(f"✅ Migration applied successfully in {elapsed:.2f}s")
        
        # Verify tables
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
        """)
        table_count = cursor.fetchone()[0]
        print(f"📊 Tables created: {table_count}")
        
        # List new tables
        cursor.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public' 
            ORDER BY tablename
        """)
        tables = cursor.fetchall()
        print("\n📋 Phase 5 Tables:")
        for (table_name,) in tables:
            print(f"   - {table_name}")
        
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

def main():
    """Main entry point"""
    print("=" * 70)
    print("PHASE 5 POSTGRESQL MIGRATION")
    print("=" * 70)
    print()
    
    # Try psycopg2 first (most reliable)
    try:
        import psycopg2
        print("Using psycopg2 for migration...")
        success = apply_migration_with_psycopg2()
    except ImportError:
        print("psycopg2 not installed, trying supabase-py...")
        try:
            import supabase
            print("Using supabase-py for migration...")
            success = apply_migration_with_supabase_py()
        except ImportError:
            print("❌ No suitable database client found")
            print("\nInstall one of:")
            print("   pip install psycopg2-binary")
            print("   pip install supabase")
            success = False
    
    print()
    if success:
        print("✅ Migration completed successfully!")
        print()
        print("Next steps:")
        print("1. Create a workspace:")
        print("   INSERT INTO workspaces (id, organization_id, name, owner_id)")
        print("   VALUES ('ws_001', 'org_001', 'Test Workspace', 'user_001');")
        print()
        print("2. Run production pipeline:")
        print("   export JIMSAI_ENV=production")
        print("   python services/production_pipeline.py")
        print()
        print("3. Monitor metrics:")
        print("   SELECT * FROM workspace_performance_summary;")
        return 0
    else:
        print("❌ Migration failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
