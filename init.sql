-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Jobs table ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    id               SERIAL PRIMARY KEY,
    job_id           TEXT UNIQUE NOT NULL,       -- LinkedIn job ID (dedup key)
    title            TEXT,
    company          TEXT,
    location         TEXT,
    url              TEXT,
    description      TEXT,
    employment_type  TEXT,
    seniority_level  TEXT,
    posted_at        TEXT,
    field            TEXT,                        -- AI / DevOps / Frontend / etc.
    scraped_at       TIMESTAMPTZ DEFAULT NOW(),
    created_at       TIMESTAMPTZ DEFAULT NOW(),

    -- pgvector: 1536-dim embedding of title + description (OpenAI ada-002 size)
    -- Set to NULL if you don't use embeddings
    embedding        vector(1536)
);

-- ── Indexes ─────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_field      ON jobs(field);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_company    ON jobs(company);

-- Vector similarity index (IVFFlat — fast approximate nearest-neighbour)
-- Uncomment after you have > 1000 rows for best performance
-- CREATE INDEX ON jobs USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ── Scrape run log ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scrape_runs (
    id        SERIAL PRIMARY KEY,
    ran_at    TIMESTAMPTZ DEFAULT NOW(),
    new_jobs  INTEGER,
    status    TEXT
);