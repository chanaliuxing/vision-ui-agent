"""
Sprint H: Embedding服务
提供统一的嵌入向量生成接口，支持多种提供商
"""
import os
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time
from dataclasses import dataclass
import numpy as np

# 加载环境变量
def load_env_file():
    """加载.env文件中的环境变量"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 加载环境变量
load_env_file()

logger = logging.getLogger(__name__)

# 导入可选依赖
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


@dataclass
class EmbeddingConfig:
    """嵌入配置"""
    provider: str
    model_name: str
    dimension: int
    api_key: Optional[str] = None
    batch_size: int = 100
    timeout: int = 30


class EmbeddingProvider(ABC):
    """嵌入提供商抽象基类"""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self.model = config.model_name
        self.dim = config.dimension

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成嵌入向量"""
        pass


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI嵌入提供商"""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        if not HAS_OPENAI:
            raise ImportError("openai library not installed")

        self.client = openai.AsyncOpenAI(
            api_key=config.api_key or os.getenv("OPENAI_API_KEY")
        )

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """使用OpenAI API生成嵌入"""
        try:
            # 分批处理以避免超出API限制
            all_embeddings = []
            batch_size = self.config.batch_size

            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]

                response = await self.client.embeddings.create(
                    input=batch,
                    model=self.model
                )

                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

                # 避免速率限制
                if i + batch_size < len(texts):
                    await asyncio.sleep(0.1)

            return all_embeddings

        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise


class SentenceTransformersProvider(EmbeddingProvider):
    """Sentence Transformers嵌入提供商（本地模型）"""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        if not HAS_SENTENCE_TRANSFORMERS:
            raise ImportError("sentence-transformers library not installed")

        self.model_instance = SentenceTransformer(config.model_name)
        # 更新实际维度
        self.dim = self.model_instance.get_sentence_embedding_dimension()

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """使用本地模型生成嵌入"""
        try:
            # 在线程池中运行以避免阻塞
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self.model_instance.encode,
                texts
            )

            return embeddings.tolist()

        except Exception as e:
            logger.error(f"SentenceTransformers embedding failed: {e}")
            raise


class MockEmbeddingProvider(EmbeddingProvider):
    """模拟嵌入提供商（用于测试）"""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """生成随机嵌入向量"""
        import random

        # 基于文本内容生成确定性的"假"嵌入
        embeddings = []
        for text in texts:
            # 使用文本哈希作为种子，确保相同文本产生相同嵌入
            random.seed(hash(text) % (2**32))
            embedding = [random.random() * 2 - 1 for _ in range(self.dim)]
            embeddings.append(embedding)

        return embeddings


def to_dimension(vectors: List[List[float]], target_dim: int = 1024) -> List[List[float]]:
    """
    统一向量维度到目标维度
    - 高维 -> 截断
    - 低维 -> 零填充
    """
    normalized = []

    for vec in vectors:
        if len(vec) == target_dim:
            normalized.append(vec)
        elif len(vec) > target_dim:
            # 截断
            normalized.append(vec[:target_dim])
        else:
            # 零填充
            padded = vec + [0.0] * (target_dim - len(vec))
            normalized.append(padded)

    return normalized


class EmbeddingService:
    """嵌入服务主类"""

    def __init__(self):
        self.providers: Dict[str, EmbeddingProvider] = {}
        self.default_provider = None
        self._setup_providers()

    def _setup_providers(self):
        """设置可用的嵌入提供商"""
        configs = [
            # OpenAI提供商
            EmbeddingConfig(
                provider="openai",
                model_name="text-embedding-3-large",
                dimension=1536,
                api_key=os.getenv("OPENAI_API_KEY")
            ),
            # 本地模型提供商
            EmbeddingConfig(
                provider="sentence_transformers",
                model_name="all-MiniLM-L6-v2",
                dimension=384
            ),
            # 模拟提供商（测试用）
            EmbeddingConfig(
                provider="mock",
                model_name="mock-model",
                dimension=1024
            )
        ]

        # 尝试初始化各个提供商
        for config in configs:
            try:
                if config.provider == "openai" and HAS_OPENAI and config.api_key:
                    provider = OpenAIEmbeddingProvider(config)
                elif config.provider == "sentence_transformers" and HAS_SENTENCE_TRANSFORMERS:
                    provider = SentenceTransformersProvider(config)
                elif config.provider == "mock":
                    provider = MockEmbeddingProvider(config)
                else:
                    continue

                self.providers[config.provider] = provider

                # 设置默认提供商（优先级：OpenAI > SentenceTransformers > Mock）
                if not self.default_provider:
                    self.default_provider = provider
                elif config.provider == "openai" and self.default_provider.config.provider != "openai":
                    self.default_provider = provider
                elif config.provider == "sentence_transformers" and self.default_provider.config.provider == "mock":
                    self.default_provider = provider

                logger.info(f"Initialized embedding provider: {config.provider}")

            except Exception as e:
                logger.warning(f"Failed to initialize provider {config.provider}: {e}")

        if not self.providers:
            raise RuntimeError("No embedding providers available")

        logger.info(f"Default embedding provider: {self.default_provider.config.provider}")

    async def embed_batch(self, texts: List[str], provider: str = None,
                         target_dim: int = 1024) -> List[List[float]]:
        """批量生成嵌入向量"""
        if not texts:
            return []

        # 选择提供商
        if provider and provider in self.providers:
            selected_provider = self.providers[provider]
        else:
            selected_provider = self.default_provider

        logger.info(f"Generating embeddings for {len(texts)} texts using {selected_provider.config.provider}")

        start_time = time.time()
        try:
            # 生成嵌入
            embeddings = await selected_provider.embed(texts)

            # 统一维度
            normalized = to_dimension(embeddings, target_dim)

            duration = time.time() - start_time
            logger.info(f"Generated {len(normalized)} embeddings in {duration:.2f}s")

            return normalized

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    async def embed_single(self, text: str, provider: str = None,
                          target_dim: int = 1024) -> List[float]:
        """生成单个文本的嵌入向量"""
        embeddings = await self.embed_batch([text], provider, target_dim)
        return embeddings[0] if embeddings else []

    def get_available_providers(self) -> List[Dict[str, Any]]:
        """获取可用的嵌入提供商信息"""
        return [
            {
                "provider": provider.config.provider,
                "model": provider.config.model_name,
                "dimension": provider.config.dimension,
                "is_default": provider == self.default_provider
            }
            for provider in self.providers.values()
        ]


# 全局服务实例
embedding_service = EmbeddingService()


# 便利函数
async def embed_texts(texts: List[str], provider: str = None) -> List[List[float]]:
    """便利函数：生成嵌入向量"""
    return await embedding_service.embed_batch(texts, provider)


async def embed_text(text: str, provider: str = None) -> List[float]:
    """便利函数：生成单个嵌入向量"""
    return await embedding_service.embed_single(text, provider)


def build_fingerprint_text(row: Dict[str, Any]) -> str:
    """
    构建指纹文本（与E阶段的fingerprint逻辑一致）
    """
    host = row.get("host", "")
    fingerprint = row.get("fingerprint", "")
    meta = row.get("page_state_meta") or {}

    left_ratio = meta.get("left_ratio", "")
    right_ratio = meta.get("right_ratio", "")
    dpr = meta.get("dpr", 1)

    return f"{host}|{fingerprint}|{left_ratio}|{right_ratio}|{dpr}"


def build_trajectory_text(row: Dict[str, Any]) -> str:
    """
    构建轨迹文本（动作签名序列）
    """
    # 优先使用candidate_action_sigs，回退到action_sigs
    action_sigs = row.get("candidate_action_sigs") or row.get("action_sigs") or []

    if isinstance(action_sigs, list):
        return ";".join(action_sigs)
    else:
        return str(action_sigs)


# 测试函数
async def test_embedding_service():
    """测试嵌入服务"""
    test_texts = [
        "Click apply button on Indeed job page",
        "Scroll down to view more job listings",
        "Extract job title and company information"
    ]

    try:
        # 测试批量嵌入
        embeddings = await embed_texts(test_texts)
        print(f"Generated {len(embeddings)} embeddings")
        print(f"Embedding dimension: {len(embeddings[0])}")

        # 测试单个嵌入
        single_embedding = await embed_text("Test single embedding")
        print(f"Single embedding dimension: {len(single_embedding)}")

        # 显示可用提供商
        providers = embedding_service.get_available_providers()
        print("Available providers:")
        for provider in providers:
            print(f"  {provider}")

        return True

    except Exception as e:
        print(f"Embedding test failed: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(test_embedding_service())