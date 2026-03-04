"""
Database layer — PostgreSQL with pgvector.
Connection string is read from DATABASE_URL env variable.
"""

import os
import logging
import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:123456789@127.0.0.1:5432/linkedin_jobs"
)


class Database:
    def __init__(self):
        self._test_connection()

    # ── Connection ─────────────────────────────────────────────────────────
    def _connect(self):
        conn = psycopg2.connect(DATABASE_URL)
        register_vector(conn)           # enable vector type support
        return conn

    def _test_connection(self):
        try:
            with self._connect() as conn:
                conn.cursor().execute("SELECT 1")
            logger.info("✅ PostgreSQL connected successfully")
        except Exception as e:
            logger.error(f"❌ DB connection failed: {e}")
            raise

    # ── Write ──────────────────────────────────────────────────────────────
    def insert_jobs(self, jobs: list[dict]) -> int:
        """
        Upsert jobs by job_id (INSERT ... ON CONFLICT DO NOTHING).
        Each job dict may optionally include an 'embedding' key (list[float]).
        Returns count of newly inserted rows.
        """
        if not jobs:
            return 0

        sql = """
            INSERT INTO jobs (
                job_id, title, company, location, url,
                description, employment_type, seniority_level,
                posted_at, field, scraped_at, embedding
            ) VALUES (
                %(job_id)s, %(title)s, %(company)s, %(location)s, %(url)s,
                %(description)s, %(employment_type)s, %(seniority_level)s,
                %(posted_at)s, %(field)s, %(scraped_at)s, %(embedding)s
            )
            ON CONFLICT (job_id) DO NOTHING
        """

        new_count = 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                for job in jobs:
                    # embedding should be a Python list[float] or None
                    job.setdefault("embedding", None)
                    cur.execute(sql, job)
                    new_count += cur.rowcount
            conn.commit()

        return new_count

    def log_run(self, new_jobs: int, status: str = "success"):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO scrape_runs (new_jobs, status) VALUES (%s, %s)",
                    (new_jobs, status)
                )
            conn.commit()

    # ── Read ───────────────────────────────────────────────────────────────
    def get_jobs(
        self,
        field: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        sql    = "SELECT * FROM jobs"
        params: list = []
        if field:
            sql += " WHERE field = %s"
            params.append(field)
        sql += " ORDER BY scraped_at DESC LIMIT %s OFFSET %s"
        params += [limit, offset]

        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    def get_stats(self) -> dict:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) AS total FROM jobs")
                total = cur.fetchone()["total"]

                cur.execute("""
                    SELECT field, COUNT(*) AS count
                    FROM jobs GROUP BY field ORDER BY count DESC
                """)
                by_field = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT ran_at, new_jobs, status
                    FROM scrape_runs ORDER BY id DESC LIMIT 1
                """)
                last_run = cur.fetchone()

        return {
            "total_jobs": total,
            "by_field":   by_field,
            "last_run":   dict(last_run) if last_run else None,
        }

    # ── Vector similarity search ───────────────────────────────────────────
    def search_similar(self, embedding: list[float], limit: int = 10) -> list[dict]:
        """
        Find the most similar jobs to a given embedding vector
        using cosine similarity (pgvector <=> operator).

        Usage:
            from embeddings import get_embedding
            vec = get_embedding("machine learning platform engineer")
            similar = db.search_similar(vec, limit=5)
        """
        sql = """
            SELECT id, job_id, title, company, location, field, url,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM jobs
            WHERE embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (embedding, embedding, limit))
                return [dict(r) for r in cur.fetchall()]