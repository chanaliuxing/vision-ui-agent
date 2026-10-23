#!/usr/bin/env python3
# scripts/bootstrap_infrastructure.py
import os
import json
import boto3
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from datetime import datetime
from urllib.parse import urlparse, urlunparse

def load_env_file():
    """加载.env文件中的环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value
        print(f"✅ Loaded environment from {env_path}")
    else:
        print(f"⚠️ .env file not found at {env_path}")

def _parse_dbname_from_dsn(dsn: str) -> str:
    parsed = urlparse(dsn)
    return (parsed.path or "/postgres").lstrip("/") or "postgres"

def _replace_dbname_in_dsn(dsn: str, dbname: str) -> str:
    parsed = urlparse(dsn)
    return urlunparse(parsed._replace(path=f"/{dbname}"))

def _ensure_database_exists(dsn: str) -> None:
    target_db = _parse_dbname_from_dsn(dsn)
    maintenance_db = os.getenv("POSTGRES_MAINT_DB", "template1")
    admin_dsn = _replace_dbname_in_dsn(dsn, maintenance_db)

    admin_conn = psycopg2.connect(admin_dsn)
    admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with admin_conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (target_db,))
            if cur.fetchone():
                print(f"ℹ️ Database already exists: {target_db}")
                return
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target_db)))
            print(f"✅ Created missing database: {target_db}")
    finally:
        admin_conn.close()

def setup_postgres():
    """初始化PostgreSQL数据库和扩展"""
    try:
        # 优先使用 DATABASE；否则回退到老的 postgres/postgres 本地连接
        database_url = os.getenv('DATABASE') or (
            f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
            f"{os.getenv('POSTGRES_PASSWORD', 'postgres')}@"
            f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
            f"{os.getenv('POSTGRES_PORT', 5432)}/"
            f"{os.getenv('POSTGRES_DB', 'postgres')}"
        )

        try:
            conn = psycopg2.connect(database_url)
        except psycopg2.OperationalError as e:
            err_msg = str(e)
            if 'does not exist' in err_msg and 'database' in err_msg:
                print(f"⚠️  Target database missing, attempting auto-create: {_parse_dbname_from_dsn(database_url)}")
                _ensure_database_exists(database_url)
                conn = psycopg2.connect(database_url)
            else:
                raise
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

        with conn.cursor() as cur:
            # 尝试创建pgvector扩展
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                print("✅ PostgreSQL pgvector extension created")

                # 验证扩展是否真的可用
                cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
                result = cur.fetchone()
                if result:
                    print("✅ pgvector extension verified and working")
                else:
                    print("⚠️  pgvector extension creation command succeeded but extension not found")

            except psycopg2.errors.FeatureNotSupported as e:
                print("⚠️  PostgreSQL pgvector extension not available")
                print("   RAG memory features will be disabled")
                print("   Run ./install_pgvector.sh to install pgvector extension")
                print(f"   Error details: {e}")
            except psycopg2.Error as e:
                # 更具体的PostgreSQL错误处理
                if "could not access file" in str(e):
                    print(f"⚠️  pgvector library files not found: {e}")
                    print("   pgvector extension files may not be properly installed")
                    print("   Check if vector.dylib/vector.so exist in PostgreSQL lib directory")
                elif "extension \"vector\" already exists" in str(e):
                    print("✅ PostgreSQL pgvector extension already exists")
                else:
                    print(f"⚠️  PostgreSQL error creating pgvector extension: {e}")
                    print("   RAG memory features may be affected")
            except Exception as e:
                print(f"⚠️  Unexpected error with pgvector extension: {e}")
                print("   RAG memory features may be affected")

            # 创建基础表结构（不依赖vector扩展）
            try:
                # 这里可以添加不依赖vector的表结构
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS system_info (
                        id SERIAL PRIMARY KEY,
                        key VARCHAR(255) UNIQUE NOT NULL,
                        value TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 记录系统信息
                cur.execute("""
                    INSERT INTO system_info (key, value)
                    VALUES ('bootstrap_time', %s)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        created_at = CURRENT_TIMESTAMP;
                """, (str(datetime.now()),))

                print("✅ Basic database structure created")
            except Exception as e:
                print(f"⚠️  Failed to create basic tables: {e}")

        conn.close()
        print("✅ PostgreSQL setup completed (with graceful pgvector handling)")

    except Exception as e:
        print(f"❌ PostgreSQL setup failed: {e}")
        raise

def setup_sqs():
    """初始化SQS队列"""
    try:
        sqs = boto3.client(
            'sqs',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            endpoint_url=os.getenv('AWS_ENDPOINT_URL')
        )

        queues = [
            'llm-request.fifo',
            'llm-vision-request.fifo',
            'llm-vision-response.fifo',
            'device-demo-hp.fifo',
            'device-demo-lp.fifo',
            'device-demo-control.fifo'
        ]

        for queue_name in queues:
            try:
                attrs = {
                    'FifoQueue': 'true',
                    'ContentBasedDeduplication': 'true',
                    'ReceiveMessageWaitTimeSeconds': '0'
                }

                response = sqs.create_queue(
                    QueueName=queue_name,
                    Attributes=attrs
                )
                print(f"✅ Created queue: {queue_name}")

            except sqs.exceptions.QueueNameExists:
                print(f"ℹ️ Queue already exists: {queue_name}")

        print("✅ SQS setup completed")

    except Exception as e:
        print(f"❌ SQS setup failed: {e}")
        raise

def setup_s3():
    """初始化S3存储桶"""
    try:
        s3 = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            endpoint_url=os.getenv('AWS_ENDPOINT_URL')
        )

        buckets = ['game-artifacts', 'game-models', 'game-exports']

        for bucket_name in buckets:
            try:
                s3.create_bucket(Bucket=bucket_name)
                print(f"✅ Created bucket: {bucket_name}")
            except s3.exceptions.BucketAlreadyExists:
                print(f"ℹ️ Bucket already exists: {bucket_name}")

        print("✅ S3 setup completed")

    except Exception as e:
        # S3 is optional in local/dev. Do not fail full bootstrap when unavailable.
        print(f"⚠️  S3 setup skipped: {e}")

if __name__ == "__main__":
    print("🚀 Starting infrastructure bootstrap...")

    # 加载环境变量
    load_env_file()

    setup_postgres()
    setup_sqs()
    setup_s3()

    print("🎉 Infrastructure bootstrap completed!")
