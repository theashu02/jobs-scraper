import argparse
import logging
import sys
from pathlib import Path
from typing import List

from browser import BrowserManager
from models import JobListing
from scrapers import SCRAPER_REGISTRY, list_scrapers


def setup_logger(verbose: bool = False):
    """Configures console and file logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def parse_limit(value: str):
    if value.lower() in ("all", "none", "0"):
        return None
    try:
        val = int(value)
        return val if val > 0 else None
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid limit value: '{value}'. Use a positive number or 'all'.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Multi-platform Job Scraper Suite powered by Playwright"
    )
    parser.add_argument(
        "--scraper",
        type=str,
        default="all",
        help="Specify which scraper to run (e.g., 'hireorbit', or 'all' to run all available scrapers)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="Software Engineer",
        help="Job title or keywords (default: 'Software Engineer')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="Remote",
        help="Target location (default: 'Remote')",
    )
    parser.add_argument(
        "--limit",
        type=parse_limit,
        default=None,
        help="Maximum number of listings to scrape (default: all available jobs, or pass a number like 20)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser with visible UI (useful for debugging)",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json", "xlsx"],
        default="csv",
        help="Output export format (default: 'csv')",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all registered scrapers and exit",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    return parser.parse_args()


def run():
    args = parse_args()
    setup_logger(args.verbose)
    logger = logging.getLogger("Main")

    available_scrapers = list_scrapers()

    if args.list:
        print("\nRegistered scrapers:")
        for name in available_scrapers:
            cls = SCRAPER_REGISTRY[name]
            print(f"  - {name}: {cls.__doc__.strip().splitlines()[0] if cls.__doc__ else ''}")
        return

    # Determine scrapers to execute
    if args.scraper == "all":
        targets = available_scrapers
    else:
        if args.scraper not in SCRAPER_REGISTRY:
            logger.error(
                f"Scraper '{args.scraper}' not found! Available options: {', '.join(available_scrapers)}"
            )
            sys.exit(1)
        targets = [args.scraper]

    logger.info(f"Target scrapers: {targets}")
    display_limit = args.limit if args.limit is not None else "All available jobs"
    logger.info(f"Parameters: Query='{args.query}', Location='{args.location}', Limit={display_limit}")

    all_scraped_jobs: List[JobListing] = []

    # Launch browser manager
    with BrowserManager(headless=not args.headed) as browser_mgr:
        for scraper_name in targets:
            scraper_cls = SCRAPER_REGISTRY[scraper_name]
            scraper_instance = scraper_cls()

            logger.info(f"\n=================== Running {scraper_name} ===================")
            page = browser_mgr.get_page()

            try:
                jobs = scraper_instance.scrape(
                    page=page,
                    query=args.query,
                    location=args.location,
                    limit=args.limit,
                )
                if jobs:
                    scraper_instance.save_results(jobs, export_format=args.format)
                    all_scraped_jobs.extend(jobs)
                else:
                    logger.warning(f"No jobs found by {scraper_name}.")
            except Exception as e:
                logger.error(f"Error executing scraper '{scraper_name}': {e}", exc_info=args.verbose)
            finally:
                page.close()

    # Summary
    logger.info("\n=================== Execution Summary ===================")
    logger.info(f"Total scrapers executed: {len(targets)}")
    logger.info(f"Total jobs collected across all scrapers: {len(all_scraped_jobs)}")
    logger.info("========================================================\n")


if __name__ == "__main__":
    run()
