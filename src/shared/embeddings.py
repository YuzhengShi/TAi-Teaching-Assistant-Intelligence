"""
Embedding client for vector similarity search.
Supports OpenAI and local models with batch processing.
"""

from typing import List, Optional, Union
import numpy as np
from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

from src.shared.config import settings
from src.shared.exceptions import TAiError


class EmbeddingError(TAiError):
    """Error in embedding operations."""
    pass


class EmbeddingClient:
    """Unified embedding client."""
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        batch_size: int = 100
    ):
        self.provider = provider or settings.embedding.provider
        self.model = model or settings.embedding.model
        self.batch_size = batch_size or settings.embedding.batch_size
        
        if self.provider == "openai":
            api_key = api_key or settings.llm.openai_api_key
            if not api_key:
                raise EmbeddingError("OpenAI API key not configured")
            self.client = AsyncOpenAI(api_key=api_key)
            self._local_model = None
        elif self.provider == "local":
            # Lazy load local model
            self._local_model = None
            self.client = None
        else:
            raise EmbeddingError(f"Unsupported embedding provider: {self.provider}")
    
    def _get_local_model(self):
        """Lazy load local embedding model."""
        if self._local_model is None:
            try:
                self._local_model = SentenceTransformer(self.model)
            except Exception as e:
                raise EmbeddingError(f"Failed to load local model {self.model}: {str(e)}") from e
        return self._local_model
    
    async def embed(
        self,
        texts: Union[str, List[str]],
        batch_size: Optional[int] = None
    ) -> Union[List[float], List[List[float]]]:
        """
        Generate embeddings for text(s).
        
        Args:
            texts: Single text string or list of texts
            batch_size: Override default batch size
        
        Returns:
            Single embedding vector or list of vectors
        """
        is_single = isinstance(texts, str)
        if is_single:
            texts = [texts]
        
        batch_size = batch_size or self.batch_size
        
        if self.provider == "openai":
            embeddings = await self._embed_openai(texts, batch_size)
        elif self.provider == "local":
            embeddings = await self._embed_local(texts, batch_size)
        else:
            raise EmbeddingError(f"Unsupported provider: {self.provider}")
        
        return embeddings[0] if is_single else embeddings
    
    async def _embed_openai(self, texts: List[str], batch_size: int) -> List[List[float]]:
        """Generate embeddings using OpenAI API."""
        all_embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                raise EmbeddingError(f"OpenAI embedding failed: {str(e)}") from e
        
        return all_embeddings
    
    async def _embed_local(self, texts: List[str], batch_size: int) -> List[List[float]]:
        """Generate embeddings using local model."""
        model = self._get_local_model()
        
        # SentenceTransformers encode is synchronous, but we can batch
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                embeddings = model.encode(
                    batch,
                    batch_size=len(batch),
                    show_progress_bar=False,
                    convert_to_numpy=True
                )
                # Convert to list of lists
                all_embeddings.extend(embeddings.tolist())
            except Exception as e:
                raise EmbeddingError(f"Local embedding failed: {str(e)}") from e
        
        return all_embeddings
    
    def cosine_similarity(
        self,
        vec1: List[float],
        vec2: List[float]
    ) -> float:
        """Calculate cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        
        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


# Convenience function
async def embed(texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    """Generate embeddings using default settings."""
    client = EmbeddingClient()
    return await client.embed(texts)
