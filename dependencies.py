#!/usr/bin/env python3
"""
Dependencies - Service Injection and Management
Handles dependency injection for the unified YOLO+LLM service
"""

import logging
from typing import Optional
from functools import lru_cache
import os

# Ensure .env is loaded so LLM_PROVIDER / LLM_MODEL and others are respected
try:
    from dotenv import load_dotenv
    load_dotenv()  # safe no-op if .env not present
except Exception:
    pass

from detector_service import get_detector_service, DetectorService
from anchors_service import get_anchors_service, AnchorsService
from verification_service import get_verification_service, VerificationService
from orchestrator import Orchestrator

logger = logging.getLogger(__name__)

# Global service instances (singletons)
_orchestrator_instance: Optional[Orchestrator] = None


@lru_cache()
def get_llm_client():
    """Get singleton LLM client instance (now with MQ+direct hybrid support)"""
    try:
        # Re-load .env here as well (in case startup order differs)
        try:
            from dotenv import load_dotenv as _ld
            _ld()
        except Exception:
            pass
        from core.hybrid_llm_client import HybridLLMClient
        from core.mq_client import create_mq_client
        from core.storage_client import create_default_storage_client

        # Default to local Ollama unless .env overrides
        provider = os.getenv("LLM_PROVIDER", "ollama")
        model = os.getenv("LLM_MODEL", "qwen2.5vl")

        # Initialize MQ client (optional - will use direct-only if not available)
        mq_client = None
        try:
            endpoint = os.getenv("AWS_ENDPOINT_URL")
            if endpoint:  # attempt LocalStack/SQS
                mq_client = create_mq_client(
                    "sqs",
                    region=os.getenv("AWS_REGION", "us-east-1"),
                    endpoint_url=endpoint,
                )
                # Probe once to verify connectivity; if fails, disable MQ
                try:
                    # Access private method safely (best-effort)
                    if hasattr(mq_client, "_get_queue_url"):
                        # Probe request queue
                        mq_client._get_queue_url("llm-vision-request.fifo")
                        logger.info("MQ connectivity probe ok; MQ enabled")
                    else:
                        logger.info("MQ client created; no probe available")
                except Exception as pe:
                    logger.warning(f"MQ probe failed ({pe}); disabling MQ and using direct-only")
                    mq_client = None
        except Exception as e:
            logger.warning(f"MQ client initialization failed, using direct-only: {e}")

        # Initialize storage client for vision data (optional)
        storage_client = None
        try:
            storage_client = create_default_storage_client()
            logger.info(f"Storage client initialized: {os.getenv('LLM_STORAGE_TYPE', 'local')}")
        except Exception as e:
            logger.warning(f"Storage client initialization failed, vision may be limited: {e}")

        # Create hybrid client with MQ+direct support
        client = HybridLLMClient(
            provider=provider,
            model=model,
            mq=mq_client,
            storage=storage_client,
            mq_timeout_s=int(os.getenv("LLM_MQ_TIMEOUT_S", "30")),
            direct_timeout_s=int(os.getenv("LLM_DIRECT_TIMEOUT_S", "120"))
        )

        logger.info(f"Hybrid LLM client initialized: {provider}/{model} (MQ={'✓' if mq_client else '✗'}, Storage={'✓' if storage_client else '✗'})")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize hybrid LLM client: {e}")
        # Fallback to basic LLM client if hybrid fails
        try:
            from core.llm_client import LLMClient
            provider = os.getenv("LLM_PROVIDER", "openai")
            model = os.getenv("LLM_MODEL", "gpt-4o-mini")
            client = LLMClient(provider=provider, model=model)
            logger.warning(f"Using fallback basic LLM client: {provider}/{model}")
            return client
        except Exception as e2:
            logger.error(f"Fallback LLM client also failed: {e2}")
            raise RuntimeError(f"LLM client initialization completely failed: {e2}")


def get_orchestrator() -> Orchestrator:
    """Get singleton orchestrator instance with all dependencies"""
    global _orchestrator_instance

    if _orchestrator_instance is None:
        try:
            # Initialize all service dependencies
            anchors_service = get_anchors_service()
            detector_service = get_detector_service()
            verification_service = get_verification_service()
            llm_client = get_llm_client()

            # Create orchestrator with dependencies
            _orchestrator_instance = Orchestrator(
                anchors_service=anchors_service,
                detector_service=detector_service,
                verification_service=verification_service,
                llm_client=llm_client
            )

            logger.info("Orchestrator singleton created successfully")

        except Exception as e:
            logger.error(f"Failed to create orchestrator: {e}")
            raise RuntimeError(f"Orchestrator initialization failed: {e}")

    return _orchestrator_instance


def get_services_health() -> dict:
    """Get health status of all services"""
    health_status = {
        "orchestrator": False,
        "detector": False,
        "anchors": False,
        "verification": False,
        "llm": False,
        "dependencies_ok": False
    }

    try:
        # Test detector service
        detector = get_detector_service()
        health_status["detector"] = True
        logger.debug("Detector service: OK")

        # Test anchors service
        anchors = get_anchors_service()
        health_status["anchors"] = True
        logger.debug("Anchors service: OK")

        # Test verification service
        verifier = get_verification_service()
        health_status["verification"] = True
        logger.debug("Verification service: OK")

        # Test LLM client
        llm = get_llm_client()
        health_status["llm"] = True
        logger.debug("LLM client: OK")

        # Test orchestrator
        orchestrator = get_orchestrator()
        health_status["orchestrator"] = True
        logger.debug("Orchestrator: OK")

        # Overall dependencies status
        health_status["dependencies_ok"] = all([
            health_status["detector"],
            health_status["anchors"],
            health_status["verification"],
            health_status["llm"],
            health_status["orchestrator"]
        ])

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        health_status["error"] = str(e)

    return health_status


def reset_services():
    """Reset all service singletons (for testing)"""
    global _orchestrator_instance

    logger.warning("Resetting all service singletons")

    # Clear orchestrator
    _orchestrator_instance = None

    # Clear service caches
    try:
        from detector_service import _detector_service_instance
        _detector_service_instance = None
    except:
        pass

    try:
        from anchors_service import _anchors_service_instance
        _anchors_service_instance = None
    except:
        pass

    try:
        from verification_service import _verification_service_instance
        _verification_service_instance = None
    except:
        pass

    # Clear LRU cache
    get_llm_client.cache_clear()

    logger.info("All service singletons reset")


def initialize_services():
    """Initialize all services (useful for startup)"""
    try:
        logger.info("Initializing all services...")

        # Initialize in dependency order
        detector = get_detector_service()
        anchors = get_anchors_service()
        verifier = get_verification_service()
        llm = get_llm_client()
        orchestrator = get_orchestrator()

        logger.info("All services initialized successfully")
        return True

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        return False


# Service configuration and settings
class ServiceConfig:
    """Configuration for services"""

    def __init__(self):
        self.load_from_env()

    def load_from_env(self):
        """Load configuration from environment variables"""
        import os

        # LLM configuration
        self.llm_provider = os.getenv("LLM_PROVIDER", "gemini")
        self.llm_model = os.getenv("LLM_MODEL", "gemini-1.5-flash")

        # YOLO configuration
        self.yolo_conf = float(os.getenv("YOLO_CONF", "0.35"))
        self.yolo_iou = float(os.getenv("YOLO_IOU", "0.45"))
        self.yolo_imgsz = int(os.getenv("YOLO_IMGSZ", "1280"))

        # Anchor configuration
        self.anchor_threshold = float(os.getenv("ANCHOR_TM_TH", "0.82"))

        # Verification configuration
        self.verification_timeout = int(os.getenv("VERIFICATION_TIMEOUT_MS", "5000"))
        self.verification_delay = int(os.getenv("VERIFICATION_DELAY_MS", "300"))

        # Cache configuration
        self.cache_size_limit = int(os.getenv("CACHE_SIZE_LIMIT", "1000"))

    def to_dict(self) -> dict:
        """Convert configuration to dictionary"""
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "yolo_conf": self.yolo_conf,
            "yolo_iou": self.yolo_iou,
            "yolo_imgsz": self.yolo_imgsz,
            "anchor_threshold": self.anchor_threshold,
            "verification_timeout": self.verification_timeout,
            "verification_delay": self.verification_delay,
            "cache_size_limit": self.cache_size_limit
        }


# Global configuration instance
service_config = ServiceConfig()


def get_service_config() -> ServiceConfig:
    """Get service configuration"""
    return service_config


# Startup and shutdown hooks
def startup_hook():
    """Startup hook for FastAPI application"""
    logger.info("Running service startup hook...")

    success = initialize_services()
    if not success:
        logger.error("Service initialization failed during startup")
        raise RuntimeError("Critical services failed to initialize")

    health = get_services_health()
    if not health.get("dependencies_ok", False):
        logger.error("Service health check failed during startup")
        raise RuntimeError("Service health check failed")

    logger.info("Service startup completed successfully")


def shutdown_hook():
    """Shutdown hook for FastAPI application"""
    logger.info("Running service shutdown hook...")

    # Clear caches and reset services
    reset_services()

    logger.info("Service shutdown completed")


# Error handling utilities
class ServiceError(Exception):
    """Base exception for service errors"""
    pass


class DetectorError(ServiceError):
    """Error in detector service"""
    pass


class AnchorsError(ServiceError):
    """Error in anchors service"""
    pass


class VerificationError(ServiceError):
    """Error in verification service"""
    pass


class LLMError(ServiceError):
    """Error in LLM service"""
    pass


class OrchestratorError(ServiceError):
    """Error in orchestrator"""
    pass
