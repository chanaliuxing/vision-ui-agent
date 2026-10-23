"""Mock adapters for testing without browser integration"""

class MockDomAdapter:
    def __init__(self):
        self.current_page = "list"
        self.mock_posts = [
            {"bbox": {"x": 100, "y": 100, "w": 200, "h": 50}, "title": "Post 1"},
            {"bbox": {"x": 100, "y": 200, "w": 200, "h": 50}, "title": "Post 2"},
            {"bbox": {"x": 100, "y": 300, "w": 200, "h": 50}, "title": "Post 3"}
        ]

    def open(self, url):
        print(f"MockDOM: Opening {url}")
        self.current_page = "list"
        return {"ok": True}

    def exists(self, selector):
        if self.current_page == "list" and selector == ".post-item":
            return True
        elif self.current_page == "detail" and selector == ".detail":
            return True
        return False

    def extract(self, query):
        if "posts" in query and self.current_page == "list":
            return self.mock_posts  # 直接返回列表，而不是包装在字典中
        return {}

    def go_back(self):
        print("MockDOM: Going back")
        self.current_page = "list"
        return {"ok": True}

class MockOsAdapter:
    def move_to(self, x, y):
        print(f"MockOS: Moving cursor to ({x}, {y})")

    def click(self):
        print("MockOS: Clicking")
        # 模拟点击后切换到详情页面
        if hasattr(self, '_dom_adapter'):
            self._dom_adapter.current_page = "detail"

    def scroll(self, pixels):
        print(f"MockOS: Scrolling {pixels} pixels")

class MockLogger:
    def info(self, message, extra=None):
        print(f"LOG: {message}")

    def error(self, message, extra=None):
        print(f"ERROR: {message}")