import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer
from src.models.feedback import FeedbackItem
from src.config import ClusteringConfig


class Embedder:
    def __init__(self, config: ClusteringConfig):
        self.model = SentenceTransformer(config.embedding_model)
        self.config = config

    def embed(self, items: List[FeedbackItem]) -> np.ndarray:
        texts = [item.text for item in items]
        embeddings = self.model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
        return embeddings
