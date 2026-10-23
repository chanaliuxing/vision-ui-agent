#!/usr/bin/env python3
"""
Services and Context System - Stage 2 Implementation
Dependency injection system for workflow services
"""

from typing import Dict, Any, Optional, Type, TypeVar, Generic
from dataclasses import dataclass, field
import threading
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ServiceRegistry:
    """Registry for managing service instances"""

    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def register(self, name: str, service: Any):
        """Register a service instance"""
        with self._lock:
            self._services[name] = service
            logger.info(f"Registered service: {name}")

    def get(self, name: str) -> Optional[Any]:
        """Get a service instance"""
        with self._lock:
            return self._services.get(name)

    def unregister(self, name: str) -> bool:
        """Unregister a service"""
        with self._lock:
            if name in self._services:
                del self._services[name]
                logger.info(f"Unregistered service: {name}")
                return True
            return False

    def list_services(self) -> list:
        """List all registered services"""
        with self._lock:
            return list(self._services.keys())

@dataclass
class Context:
    """Context object for workflow execution"""
    workflow_id: str = ""
    session_id: str = ""
    user_id: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    _services: Optional[ServiceRegistry] = field(default_factory=ServiceRegistry)

    def set_variable(self, key: str, value: Any):
        """Set a context variable"""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a context variable"""
        return self.variables.get(key, default)

    def set_metadata(self, key: str, value: Any):
        """Set metadata"""
        self.metadata[key] = value

    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata"""
        return self.metadata.get(key, default)

    def get_service(self, name: str) -> Optional[Any]:
        """Get a service from the registry"""
        if self._services:
            return self._services.get(name)
        return None

    def register_service(self, name: str, service: Any):
        """Register a service in the context"""
        if not self._services:
            self._services = ServiceRegistry()
        self._services.register(name, service)

class Services:
    """Global services container"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.registry = ServiceRegistry()
            self._initialized = True

    def register(self, name: str, service: Any):
        """Register a global service"""
        self.registry.register(name, service)

    def get(self, name: str) -> Optional[Any]:
        """Get a global service"""
        return self.registry.get(name)

    def unregister(self, name: str) -> bool:
        """Unregister a global service"""
        return self.registry.unregister(name)

    def list_services(self) -> list:
        """List all global services"""
        return self.registry.list_services()

class ServiceProvider(Generic[T]):
    """Service provider for dependency injection"""

    def __init__(self, service_type: Type[T]):
        self.service_type = service_type
        self._instance: Optional[T] = None

    def get_instance(self, context: Optional[Context] = None) -> T:
        """Get service instance, creating if necessary"""
        if self._instance is None:
            self._instance = self._create_instance(context)
        return self._instance

    def _create_instance(self, context: Optional[Context] = None) -> T:
        """Create a new service instance"""
        try:
            if context:
                return self.service_type(context=context)
            else:
                return self.service_type()
        except TypeError:
            # Fallback if constructor doesn't accept context
            return self.service_type()

def get_global_services() -> Services:
    """Get the global services instance"""
    return Services()

def create_context(workflow_id: str = "", session_id: str = "", user_id: str = "") -> Context:
    """Create a new context instance"""
    return Context(
        workflow_id=workflow_id,
        session_id=session_id,
        user_id=user_id
    )