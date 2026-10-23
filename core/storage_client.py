"""
Object Storage abstraction for vision data
Supports S3, MinIO, or local filesystem storage
"""
import os
import logging
import hashlib
from typing import Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class StorageClient(ABC):
    """Abstract storage client interface"""

    @abstractmethod
    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Upload object to storage"""
        pass

    @abstractmethod
    def get_signed_url(self, key: str, expires_in: int = 300) -> str:
        """Get signed URL for object access"""
        pass

    @abstractmethod
    def delete_object(self, key: str) -> bool:
        """Delete object from storage"""
        pass


class S3StorageClient(StorageClient):
    """AWS S3 / MinIO compatible storage client"""

    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: str = None):
        try:
            import boto3
            self.s3 = boto3.client('s3', region_name=region, endpoint_url=endpoint_url)
            self.bucket = bucket
        except ImportError:
            raise RuntimeError("boto3 required for S3 storage client")

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Upload object to S3/MinIO"""
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption='AES256'  # Enable encryption
            )
            logger.debug(f"S3 uploaded object: s3://{self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload S3 object {key}: {e}")
            return False

    def get_signed_url(self, key: str, expires_in: int = 300) -> str:
        """Generate presigned URL for S3 object"""
        try:
            url = self.s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': key},
                ExpiresIn=expires_in
            )
            logger.debug(f"S3 generated signed URL for {key} (expires in {expires_in}s)")
            return url
        except Exception as e:
            logger.error(f"Failed to generate S3 signed URL for {key}: {e}")
            return f"s3://{self.bucket}/{key}"  # Fallback to S3 URI

    def delete_object(self, key: str) -> bool:
        """Delete object from S3"""
        try:
            self.s3.delete_object(Bucket=self.bucket, Key=key)
            logger.debug(f"S3 deleted object: s3://{self.bucket}/{key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete S3 object {key}: {e}")
            return False


class LocalStorageClient(StorageClient):
    """Local filesystem storage client (for testing/development)"""

    def __init__(self, base_path: str = "/tmp/llm-vision-storage"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _get_file_path(self, key: str) -> str:
        """Get full file path for key"""
        # Sanitize key to prevent path traversal
        safe_key = key.replace('..', '').replace('/', os.sep)
        return os.path.join(self.base_path, safe_key)

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Save object to local filesystem"""
        try:
            file_path = self._get_file_path(key)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'wb') as f:
                f.write(data)

            logger.debug(f"Local storage saved: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save local file {key}: {e}")
            return False

    def get_signed_url(self, key: str, expires_in: int = 300) -> str:
        """Return file:// URL for local files"""
        file_path = self._get_file_path(key)
        return f"file://{os.path.abspath(file_path)}"

    def delete_object(self, key: str) -> bool:
        """Delete local file"""
        try:
            file_path = self._get_file_path(key)
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug(f"Local storage deleted: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete local file {key}: {e}")
            return False


class MockStorageClient(StorageClient):
    """Mock storage client for testing"""

    def __init__(self):
        self.objects = {}  # key -> bytes

    def put_object(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        self.objects[key] = data
        return True

    def get_signed_url(self, key: str, expires_in: int = 300) -> str:
        if key in self.objects:
            return f"mock://storage/{key}?expires={expires_in}"
        return f"mock://storage/{key}?error=not_found"

    def delete_object(self, key: str) -> bool:
        if key in self.objects:
            del self.objects[key]
        return True


def create_storage_client(storage_type: str = "s3", **kwargs) -> StorageClient:
    """Factory function to create storage client"""
    if storage_type == "s3":
        return S3StorageClient(**kwargs)
    elif storage_type == "local":
        return LocalStorageClient(**kwargs)
    elif storage_type == "mock":
        return MockStorageClient()
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")


# Convenience function to create default storage client from environment
def create_default_storage_client() -> Optional[StorageClient]:
    """Create storage client based on environment variables"""
    storage_type = os.getenv('LLM_STORAGE_TYPE', 'local')

    try:
        if storage_type == 's3':
            return S3StorageClient(
                bucket=os.getenv('LLM_STORAGE_BUCKET', 'llm-vision-data'),
                region=os.getenv('AWS_REGION', 'us-east-1'),
                endpoint_url=os.getenv('AWS_ENDPOINT_URL')
            )
        elif storage_type == 'local':
            return LocalStorageClient(
                base_path=os.getenv('LLM_STORAGE_PATH', '/tmp/llm-vision-storage')
            )
        else:
            logger.warning(f"Unknown storage type: {storage_type}, using local")
            return LocalStorageClient()

    except Exception as e:
        logger.error(f"Failed to create storage client: {e}")
        return None