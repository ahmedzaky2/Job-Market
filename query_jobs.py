"""
CLI tool to query saved jobs from the database.

Usage examples:
  python query_jobs.py                        # show stats
  python query_jobs.py --field "AI Engineer"  # jobs for a field
  python query_jobs.py --field "DevOps Engineer" --limit 20
  python query_jobs.py --all                  # all jobs (paginated)
"""

import argparse
import json
from database import Database


def print_jobs(jobs: list[dict]):
    if not jobs:
        print("No jobs found.")
        return
    for i, j in enumerate(jobs, 1):
        print(f"\n{'─'*60}")
        print(f"#{i}  {j['title']} @ {j['company']}")
        print(f"    📍 {j['location']}")
        print(f"    🏷️  {j['field']}  |  {j['employment_type']}  |  {j['seniority_level']}")
        print(f"    🔗 {j['url']}")
        print(f"    📅 Posted: {j['posted_at']}  |  Scraped: {j['scraped_at']}")


def main():
    parser = argparse.ArgumentParser(description="Query LinkedIn jobs DB")
    parser.add_argument("--field",  type=str, help="Filter by field (e.g. 'AI Engineer')")
    parser.add_argument("--limit",  type=int, default=20, help="Number of results")
    parser.add_argument("--offset", type=int, default=0,  help="Pagination offset")
    parser.add_argument("--all",    action="store_true",  help="Show all fields")
    parser.add_argument("--stats",  action="store_true",  help="Show DB stats only")
    parser.add_argument("--json",   action="store_true",  help="Output as JSON")
    args = parser.parse_args()

    db = Database()

    if args.stats or (not args.field and not args.all):
        stats = db.get_stats()
        print("\n📊 Database Stats")
        print("=" * 40)
        print(f"  Total jobs : {stats['total_jobs']}")
        print(f"\n  By field:")
        for row in stats["by_field"]:
            print(f"    {row['field']:<25} {row['count']} jobs")
        if stats["last_run"]:
            r = stats["last_run"]
            print(f"\n  Last run   : {r['ran_at']} UTC  ({r['new_jobs']} new, {r['status']})")
        print()
        if not args.field and not args.all:
            return

    jobs = db.get_jobs(
        field=args.field,
        limit=args.limit,
        offset=args.offset
    )

    if args.json:
        print(json.dumps(jobs, indent=2))
    else:
        print_jobs(jobs)
        print(f"\n  Showing {len(jobs)} jobs (offset={args.offset})")


if __name__ == "__main__":
    main()