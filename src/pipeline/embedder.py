import logging
import numpy as np
from typing import List
from sentence_transformers import SentenceTransformer
from src.models.feedback import FeedbackItem
from src.config import ClusteringConfig

logger = logging.getLogger(__name__)


class Embedder:
    def __init__(self, config: ClusteringConfig):
        self.model = SentenceTransformer(config.embedding_model)
        self.config = config

    def embed(self, items: List[FeedbackItem]) -> np.ndarray:
        texts = [item.text for item in items]
        logger.info("Generating embeddings for %d feedback items using %s...", len(items), self.config.embedding_model)
        embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
        logger.debug("Generated embeddings matrix of shape %s", embeddings.shape)
        return embeddings
