#!/usr/bin/env python3
"""
Mock Services for Testing
Stage 13: Automated Regression & E2E Testing

Comprehensive mock services for isolated testing:
1. Mock LLM services with configurable responses
2. Mock YOLO detection service
3. Mock OCR service with predictable results
4. Mock SQS queue service
5. Mock billing and payment services
6. Test data generation and management
"""

import json
import time
import random
import base64
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

class MockMode(Enum):
    NORMAL = "normal"          # Normal successful responses
    SLOW = "slow"              # Slow responses (testing timeouts)
    ERROR = "error"            # Error responses (testing error handling)
    FLAKY = "flaky"           # Intermittent failures
    CHAOTIC = "chaotic"       # Random behavior

@dataclass
class MockConfig:
    """Configuration for mock services"""
    mode: MockMode = MockMode.NORMAL
    response_delay: float = 0.1  # Base response delay
    error_rate: float = 0.0      # Error probability (0.0 - 1.0)
    slow_factor: float = 5.0     # Slow response multiplier

class MockLLMService:
    """Mock LLM service with configurable responses"""

    def __init__(self, config: MockConfig = None):
        self.config = config or MockConfig()
        self.request_count = 0
        self.predefined_responses = {
            "vision_picker": {
                "thinking": "I can see several UI elements in the image. Let me analyze each candidate.",
                "choice": 1,
                "confidence": 0.85,
                "reasoning": "Element 1 appears to be a clickable button with the target text."
            },
            "workflow_generation": {
                "workflow": {
                    "start": "step1",
                    "states": {
                        "step1": {
                            "actions": [
                                {"do": "click", "label": "login_button"}
                            ]
                        }
                    }
                }
            },
            "text_classification": {
                "category": "automation",
                "confidence": 0.92,
                "keywords": ["click", "button", "navigate"]
            }
        }

    def _simulate_delay(self):
        """Simulate network delay based on configuration"""
        delay = self.config.response_delay

        if self.config.mode == MockMode.SLOW:
            delay *= self.config.slow_factor
        elif self.config.mode == MockMode.FLAKY and random.random() < 0.3:
            delay *= 2.0

        time.sleep(delay)

    def _should_error(self) -> bool:
        """Determine if request should return error"""
        if self.config.mode == MockMode.ERROR:
            return True
        elif self.config.mode == MockMode.FLAKY:
            return random.random() < self.config.error_rate
        elif self.config.mode == MockMode.CHAOTIC:
            return random.random() < 0.2
        return False

    def generate_response(self, request_type: str, prompt: str = None) -> Dict[str, Any]:
        """Generate mock LLM response"""
        self.request_count += 1
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock LLM service error")

        # Return predefined response based on request type
        base_response = self.predefined_responses.get(request_type, {
            "response": f"Mock response for {request_type}",
            "confidence": random.uniform(0.7, 0.95)
        })

        # Add metadata
        response = {
            **base_response,
            "mock_metadata": {
                "request_id": str(uuid.uuid4()),
                "request_count": self.request_count,
                "model": "mock-llm-v1",
                "timestamp": time.time(),
                "mode": self.config.mode.value
            }
        }

        return response

class MockYOLOService:
    """Mock YOLO detection service"""

    def __init__(self, config: MockConfig = None):
        self.config = config or MockConfig()
        self.detection_templates = [
            {
                "class": "button",
                "confidence": 0.89,
                "bbox": [100, 50, 200, 80],
                "label": "Login Button"
            },
            {
                "class": "textbox",
                "confidence": 0.92,
                "bbox": [100, 120, 300, 150],
                "label": "Username Field"
            },
            {
                "class": "textbox",
                "confidence": 0.91,
                "bbox": [100, 160, 300, 190],
                "label": "Password Field"
            },
            {
                "class": "link",
                "confidence": 0.87,
                "bbox": [400, 200, 500, 220],
                "label": "Forgot Password"
            }
        ]

    def detect(self, image_data: bytes = None, image_path: str = None) -> List[Dict[str, Any]]:
        """Perform mock object detection"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock YOLO service error")

        # Return random subset of detection templates
        num_detections = random.randint(1, len(self.detection_templates))
        detections = random.sample(self.detection_templates, num_detections)

        # Add random variations
        result = []
        for i, detection in enumerate(detections):
            varied_detection = detection.copy()

            # Add small random variations to bbox
            bbox = detection["bbox"]
            varied_detection["bbox"] = [
                bbox[0] + random.randint(-10, 10),
                bbox[1] + random.randint(-10, 10),
                bbox[2] + random.randint(-10, 10),
                bbox[3] + random.randint(-10, 10)
            ]

            # Vary confidence slightly
            varied_detection["confidence"] = max(0.5, min(0.99,
                detection["confidence"] + random.uniform(-0.1, 0.1)))

            # Add detection ID
            varied_detection["id"] = i

            result.append(varied_detection)

        return result

    def _simulate_delay(self):
        """Simulate processing delay"""
        delay = self.config.response_delay * 2  # YOLO is slower than text

        if self.config.mode == MockMode.SLOW:
            delay *= self.config.slow_factor

        time.sleep(delay)

    def _should_error(self) -> bool:
        """Determine if request should return error"""
        return self.config.mode == MockMode.ERROR or \
               (self.config.mode == MockMode.FLAKY and random.random() < 0.1)

class MockOCRService:
    """Mock OCR service with predictable text extraction"""

    def __init__(self, config: MockConfig = None):
        self.config = config or MockConfig()
        self.text_templates = [
            {"text": "Login", "bbox": [100, 50, 140, 70], "confidence": 0.95},
            {"text": "Username", "bbox": [50, 120, 120, 140], "confidence": 0.92},
            {"text": "Password", "bbox": [50, 160, 120, 180], "confidence": 0.93},
            {"text": "Submit", "bbox": [200, 220, 250, 240], "confidence": 0.89},
            {"text": "Forgot Password?", "bbox": [300, 250, 420, 270], "confidence": 0.87},
            {"text": "Create Account", "bbox": [100, 300, 220, 320], "confidence": 0.91}
        ]

    def extract_text(self, image_data: bytes = None) -> List[Dict[str, Any]]:
        """Extract text from image"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock OCR service error")

        # Return random subset of text templates
        num_texts = random.randint(2, len(self.text_templates))
        texts = random.sample(self.text_templates, num_texts)

        return texts

    def _simulate_delay(self):
        """Simulate OCR processing delay"""
        delay = self.config.response_delay * 1.5

        if self.config.mode == MockMode.SLOW:
            delay *= self.config.slow_factor

        time.sleep(delay)

    def _should_error(self) -> bool:
        """Determine if request should return error"""
        return self.config.mode == MockMode.ERROR or \
               (self.config.mode == MockMode.FLAKY and random.random() < 0.05)

class MockSQSService:
    """Mock SQS service for message queue testing"""

    def __init__(self, config: MockConfig = None):
        self.config = config or MockConfig()
        self.queues: Dict[str, List[Dict]] = {}
        self.message_counter = 0

    def send_message(self, queue_name: str, message_body: str,
                    message_attributes: Dict = None) -> Dict[str, Any]:
        """Send message to queue"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock SQS send error")

        if queue_name not in self.queues:
            self.queues[queue_name] = []

        self.message_counter += 1
        message = {
            "MessageId": str(uuid.uuid4()),
            "MD5OfBody": "mock_md5_hash",
            "Body": message_body,
            "Attributes": message_attributes or {},
            "ReceiptHandle": f"mock_receipt_{self.message_counter}",
            "Timestamp": time.time()
        }

        self.queues[queue_name].append(message)

        return {
            "MessageId": message["MessageId"],
            "MD5OfBody": message["MD5OfBody"]
        }

    def receive_messages(self, queue_name: str, max_messages: int = 1) -> List[Dict[str, Any]]:
        """Receive messages from queue"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock SQS receive error")

        if queue_name not in self.queues:
            return []

        messages = self.queues[queue_name][:max_messages]
        self.queues[queue_name] = self.queues[queue_name][max_messages:]

        return messages

    def delete_message(self, queue_name: str, receipt_handle: str) -> bool:
        """Delete message from queue"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock SQS delete error")

        return True  # Mock always succeeds

    def _simulate_delay(self):
        """Simulate SQS latency"""
        delay = self.config.response_delay * 0.5  # SQS is fast
        time.sleep(delay)

    def _should_error(self) -> bool:
        """Determine if request should return error"""
        return self.config.mode == MockMode.ERROR or \
               (self.config.mode == MockMode.FLAKY and random.random() < 0.02)

class MockBillingService:
    """Mock billing and payment service"""

    def __init__(self, config: MockConfig = None):
        self.config = config or MockConfig()
        self.customers: Dict[str, Dict] = {}
        self.transactions: List[Dict] = []

    def create_customer(self, email: str, payment_method: str = None) -> Dict[str, Any]:
        """Create mock customer"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock billing service error")

        customer_id = f"cust_mock_{len(self.customers) + 1}"
        customer = {
            "id": customer_id,
            "email": email,
            "payment_method": payment_method,
            "created": time.time(),
            "balance": 0.0
        }

        self.customers[customer_id] = customer
        return customer

    def charge_customer(self, customer_id: str, amount: float,
                       description: str = None) -> Dict[str, Any]:
        """Charge customer"""
        self._simulate_delay()

        if self._should_error():
            raise Exception("Mock payment failed")

        transaction_id = f"txn_mock_{len(self.transactions) + 1}"
        transaction = {
            "id": transaction_id,
            "customer_id": customer_id,
            "amount": amount,
            "currency": "usd",
            "description": description,
            "status": "succeeded",
            "created": time.time()
        }

        self.transactions.append(transaction)

        # Update customer balance
        if customer_id in self.customers:
            self.customers[customer_id]["balance"] += amount

        return transaction

    def _simulate_delay(self):
        """Simulate payment processing delay"""
        delay = self.config.response_delay * 3.0  # Payments are slower
        time.sleep(delay)

    def _should_error(self) -> bool:
        """Determine if request should return error"""
        return self.config.mode == MockMode.ERROR or \
               (self.config.mode == MockMode.FLAKY and random.random() < 0.1)

class MockServiceRegistry:
    """Registry for all mock services"""

    def __init__(self, base_config: MockConfig = None):
        self.base_config = base_config or MockConfig()
        self.services = {
            "llm": MockLLMService(self.base_config),
            "yolo": MockYOLOService(self.base_config),
            "ocr": MockOCRService(self.base_config),
            "sqs": MockSQSService(self.base_config),
            "billing": MockBillingService(self.base_config)
        }

        # Statistics
        self.stats = {
            "requests_total": 0,
            "requests_successful": 0,
            "requests_failed": 0,
            "average_response_time": 0.0
        }

    def get_service(self, service_name: str):
        """Get mock service by name"""
        return self.services.get(service_name)

    def set_mode(self, mode: MockMode):
        """Set mode for all services"""
        self.base_config.mode = mode
        for service in self.services.values():
            service.config.mode = mode

    def reset_all(self):
        """Reset all services to initial state"""
        self.__init__(self.base_config)

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        return {
            **self.stats,
            "services": {
                name: {
                    "mode": service.config.mode.value,
                    "error_rate": service.config.error_rate
                }
                for name, service in self.services.items()
            }
        }

class MockHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for mock services"""

    def __init__(self, *args, service_registry: MockServiceRegistry = None, **kwargs):
        self.service_registry = service_registry or MockServiceRegistry()
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """Handle GET requests"""
        if self.path == "/health":
            self._send_json_response({"status": "healthy", "mock": True})
        elif self.path == "/stats":
            self._send_json_response(self.service_registry.get_stats())
        else:
            self._send_error(404, "Not found")

    def do_POST(self):
        """Handle POST requests"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            request_data = json.loads(post_data.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        try:
            if self.path == "/llm/generate":
                response = self._handle_llm_request(request_data)
            elif self.path == "/yolo/detect":
                response = self._handle_yolo_request(request_data)
            elif self.path == "/ocr/extract":
                response = self._handle_ocr_request(request_data)
            elif self.path == "/sqs/send":
                response = self._handle_sqs_send(request_data)
            elif self.path == "/billing/charge":
                response = self._handle_billing_charge(request_data)
            else:
                self._send_error(404, "Endpoint not found")
                return

            self._send_json_response(response)

        except Exception as e:
            self._send_error(500, str(e))

    def _handle_llm_request(self, data: Dict) -> Dict:
        """Handle LLM generation request"""
        llm_service = self.service_registry.get_service("llm")
        request_type = data.get("type", "general")
        prompt = data.get("prompt", "")

        return llm_service.generate_response(request_type, prompt)

    def _handle_yolo_request(self, data: Dict) -> Dict:
        """Handle YOLO detection request"""
        yolo_service = self.service_registry.get_service("yolo")

        # Mock image data
        image_data = data.get("image", "")
        detections = yolo_service.detect(image_data.encode() if image_data else None)

        return {"detections": detections}

    def _handle_ocr_request(self, data: Dict) -> Dict:
        """Handle OCR extraction request"""
        ocr_service = self.service_registry.get_service("ocr")

        # Mock image data
        image_data = data.get("image", "")
        texts = ocr_service.extract_text(image_data.encode() if image_data else None)

        return {"texts": texts}

    def _handle_sqs_send(self, data: Dict) -> Dict:
        """Handle SQS send message request"""
        sqs_service = self.service_registry.get_service("sqs")

        queue_name = data.get("queue_name", "default")
        message_body = data.get("message_body", "")

        return sqs_service.send_message(queue_name, message_body)

    def _handle_billing_charge(self, data: Dict) -> Dict:
        """Handle billing charge request"""
        billing_service = self.service_registry.get_service("billing")

        customer_id = data.get("customer_id")
        amount = data.get("amount", 0.0)
        description = data.get("description", "Test charge")

        return billing_service.charge_customer(customer_id, amount, description)

    def _send_json_response(self, data: Dict, status_code: int = 200):
        """Send JSON response"""
        response_json = json.dumps(data, indent=2)

        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(response_json)))
        self.end_headers()

        self.wfile.write(response_json.encode('utf-8'))

    def _send_error(self, status_code: int, message: str):
        """Send error response"""
        error_data = {"error": message, "status_code": status_code}
        self._send_json_response(error_data, status_code)

    def log_message(self, format, *args):
        """Override to reduce log noise"""
        pass

def start_mock_server(port: int = 8899, config: MockConfig = None):
    """Start mock services HTTP server"""
    service_registry = MockServiceRegistry(config)

    def handler(*args, **kwargs):
        MockHTTPHandler(*args, service_registry=service_registry, **kwargs)

    server = HTTPServer(('localhost', port), handler)
    print(f"🔧 Mock services server started on http://localhost:{port}")
    print(f"   Mode: {config.mode.value if config else 'normal'}")
    print("   Endpoints:")
    print("     GET  /health - Health check")
    print("     GET  /stats - Service statistics")
    print("     POST /llm/generate - Mock LLM responses")
    print("     POST /yolo/detect - Mock object detection")
    print("     POST /ocr/extract - Mock text extraction")
    print("     POST /sqs/send - Mock message queue")
    print("     POST /billing/charge - Mock billing")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Mock server stopped")
        server.shutdown()

if __name__ == "__main__":
    import sys

    # Parse command line arguments
    port = 8899
    mode = MockMode.NORMAL

    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    if len(sys.argv) > 2:
        mode = MockMode(sys.argv[2])

    config = MockConfig(mode=mode)
    start_mock_server(port, config)