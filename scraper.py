import os
import sys
import io
import logging
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/scraper.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

from apify_client import ApifyClient
from database import Database
from embeddings import get_embedding, build_job_text

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN", "")
ACTOR_ID        = "harvestapi/linkedin-job-search"

JOB_FIELDS = [
    "AI Engineer",
    # "DevOps Engineer",
    # "Frontend Developer",
    # "Backend Developer",
    # "Data Scientist",
    # "Data Engineer",
]

LOCATIONS = [
    {"name": "Egypt",          "jobs": 5},   # priority
    # {"name": "United States",  "jobs": 30},   # priority
    # {"name": "United Kingdom", "jobs": 15},
    # {"name": "Germany",        "jobs": 15},
    # {"name": "Remote",         "jobs": 10},
]

def safe_str(value) -> str:
    """Safely convert any value (dict, list, None, int) to a plain string."""
    if value is None:
        return ""
    if isinstance(value, dict):
        # Handle LinkedIn location dict specifically
        # {'linkedinText': 'Cairo, Egypt', 'parsed': {'text': 'Cairo, Egypt', ...}}
        if "parsed" in value and isinstance(value["parsed"], dict):
            return value["parsed"].get("text") or value.get("linkedinText") or ""

        # Handle company dict: {'name': 'Google', 'url': '...'}
        return (
            value.get("name") or
            value.get("text") or
            value.get("linkedinText") or
            value.get("label") or
            value.get("city") or
            str(value)
        )
    if isinstance(value, list):
        return ", ".join(safe_str(v) for v in value)
    return str(value)

class LinkedInScraper:
    def __init__(self):
        if not APIFY_API_TOKEN:
            raise ValueError("APIFY_API_TOKEN env variable is not set")
        self.client = ApifyClient(APIFY_API_TOKEN)
        self.db     = Database()

    def scrape_field_location(self, field: str, location: str, count: int) -> list[dict]:
        logger.info(f"    Scraping [{location}] — target {count} jobs ...")
        run_input = {
            "jobTitles": [field],
            "location":  location,
            "count":     count,        # correct param for harvestapi actor
        }
        try:
            run   = self.client.actor(ACTOR_ID).call(run_input=run_input)
            items = list(self.client.dataset(run["defaultDatasetId"]).iterate_items())
            logger.info(f"    [{location}] Fetched {len(items)} raw jobs from Apify")
            return items
        except Exception as e:
            logger.error(f"    [{location}] Scrape failed: {e}")
            return []

    def parse_job(self, raw: dict, field: str) -> dict | None:
        try:
            job_id = safe_str(
                raw.get("id") or
                raw.get("jobId") or
                raw.get("trackingId") or
                raw.get("entityUrn") or ""
            )
            if not job_id:
                return None

            return {
                "job_id":          job_id,
                "title":           safe_str(raw.get("title") or raw.get("jobTitle") or ""),
                "company":         safe_str(raw.get("company") or raw.get("companyName") or ""),
                "location":        safe_str(raw.get("location") or raw.get("formattedLocation") or ""),
                "url":             safe_str(raw.get("jobUrl") or raw.get("url") or raw.get("applyUrl") or ""),
                "description":     safe_str(raw.get("description") or raw.get("descriptionText") or ""),
                "employment_type": safe_str(raw.get("employmentType") or raw.get("contractType") or ""),
                "seniority_level": safe_str(raw.get("seniorityLevel") or raw.get("experienceLevel") or ""),
                "posted_at":       safe_str(raw.get("postedAt") or raw.get("publishedAt") or raw.get("listedAt") or ""),
                "field":           field,
                "scraped_at":      datetime.now(timezone.utc).isoformat(),
                "embedding":       get_embedding(
                                       build_job_text({
                                           "title":    safe_str(raw.get("title") or ""),
                                           "company":  safe_str(raw.get("company") or raw.get("companyName") or ""),
                                           "location": safe_str(raw.get("location") or ""),
                                           "field":    field,
                                           "description": safe_str(raw.get("description") or ""),
                                       })
                                   ),
            }
        except Exception as e:
            logger.warning(f"    Parse error: {e} | keys: {list(raw.keys())}")
            return None

    def run(self):
        logger.info("=" * 60)
        logger.info(f"Scrape started: {datetime.now(timezone.utc).isoformat()} UTC")
        logger.info(f"Fields: {len(JOB_FIELDS)} | Locations: {len(LOCATIONS)}")
        logger.info(f"Target: ~100 jobs per field across all locations")
        logger.info("=" * 60)

        grand_total = 0

        for field in JOB_FIELDS:
            logger.info(f"")
            logger.info(f">>> Field: {field}")
            field_total = 0
            seen_ids    = set()

            for loc in LOCATIONS:
                # 1. Scrape from Apify
                raw_jobs = self.scrape_field_location(field, loc["name"], loc["jobs"])

                # 2. Parse + deduplicate within this field
                jobs = []
                for r in raw_jobs:
                    job = self.parse_job(r, field)
                    if job and job["job_id"] not in seen_ids:
                        seen_ids.add(job["job_id"])
                        jobs.append(job)

                logger.info(f"    [{loc['name']}] Parsed {len(jobs)} unique valid jobs")

                # 3. Save to DB immediately after each location
                if jobs:
                    new_count = self.db.insert_jobs(jobs)
                    self.db.log_run(
                        new_jobs=new_count,
                        status=f"partial | {field} | {loc['name']}"
                    )
                    field_total += new_count
                    logger.info(f"    [{loc['name']}] Saved {new_count} new jobs to DB")
                else:
                    logger.info(f"    [{loc['name']}] No new jobs to save")

            grand_total += field_total
            logger.info(f"  >> '{field}' done — {field_total} new jobs total")

        # Final summary log
        self.db.log_run(new_jobs=grand_total, status="success")
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"DONE. Grand total new jobs saved: {grand_total}")
        logger.info("=" * 60)
        return grand_total


if __name__ == "__main__":
    scraper = LinkedInScraper()
    scraper.run()