"""
Vertex AI text embeddings, used to compare attribute names/descriptions
against catalog columns for semantic matching.
"""

import math
import vertexai
from vertexai.language_models import TextEmbeddingModel
import config

_initialized = False
_model = None


def _ensure_init():
    global _initialized, _model
    if not _initialized:
        vertexai.init(project=config.PROJECT_ID, location=config.LOCATION)
        _model = TextEmbeddingModel.from_pretrained(config.EMBEDDING_MODEL)
        _initialized = True


def get_embedding(text: str) -> list[float]:
    """Return a single embedding vector for the given text."""
    _ensure_init()
    embeddings = _model.get_embeddings([text])
    return embeddings[0].values


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Standard cosine similarity between two equal-length vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_attribute_text(name: str, sample_values: list, description: str = "") -> str:
    """
    Combine an attribute's name, sample values, and description into one
    string for embedding — richer input gives better matches than name alone.
    """
    sample_str = ", ".join(str(v) for v in sample_values[:5])
    parts = [f"Attribute name: {name}"]
    if sample_str:
        parts.append(f"Sample values: {sample_str}")
    if description:
        parts.append(f"Description: {description}")
    return ". ".join(parts)
