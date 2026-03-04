"""
Generate text embeddings for job listings using OpenAI API.
These are stored in the `embedding` column (vector(1536)) in PostgreSQL.

Set OPENAI_API_KEY in your .env to use this.
If you don't want embeddings, leave OPENAI_API_KEY blank —
the scraper will skip embedding generation and store NULL instead.
"""

import os
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def get_embedding(text: str) -> list[float] | None:
    """Return a 1536-dim embedding for the given text, or None if disabled."""
    if not _client:
        return None
    if not text or not text.strip():
        return None
    try:
        text = text.replace("\n", " ")[:8000]   # API token limit safety
        resp = _client.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        )
        return resp.data[0].embedding
    except Exception as e:
        logger.warning(f"Embedding generation failed: {e}")
        return None


def build_job_text(job: dict) -> str:
    """Combine relevant fields into a single string for embedding."""
    parts = [
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("field", ""),
        job.get("seniority_level", ""),
        job.get("description", "")[:2000],   # truncate long descriptions
    ]
    return " | ".join(p for p in parts if p)