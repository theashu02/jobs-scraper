import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from playwright.sync_api import Page

import config
from models import JobListing


class BaseScraper(ABC):
    """
    Abstract base class for all job board scrapers.
    Every scraper implemented should inherit from this class.
    """

    # Every scraper should define its unique identifier name and platform URL
    name: str = "base"
    base_url: str = ""

    def __init__(self):
        self.logger = logging.getLogger(f"Scraper.{self.name}")

    @abstractmethod
    def scrape(
        self,
        page: Page,
        query: str = "Software Engineer",
        location: str = "Remote",
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[JobListing]:
        """
        Executes the scraping logic for this specific job portal.

        :param page: Configured Playwright Page instance
        :param query: Job title / keywords to search for
        :param location: Location / country / remote
        :param limit: Maximum number of jobs to fetch
        :return: List of JobListing instances
        """
        pass

    def save_results(
        self,
        jobs: List[JobListing],
        output_dir: Optional[Path] = None,
        export_format: str = "csv",
    ) -> Optional[Path]:
        """
        Exports a list of JobListing items to CSV, JSON, or Excel.
        """
        if not jobs:
            self.logger.warning(f"No jobs to save for {self.name}.")
            return None

        out_dir = output_dir or config.DATA_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename_base = f"{self.name}_jobs_{timestamp}"

        # Convert listings to dictionaries
        data = [job.model_dump() for job in jobs]

        if export_format.lower() == "json":
            file_path = out_dir / f"{filename_base}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        elif export_format.lower() == "xlsx":
            file_path = out_dir / f"{filename_base}.xlsx"
            df = pd.DataFrame(data)
            df.to_excel(file_path, index=False)
        else:
            file_path = out_dir / f"{filename_base}.csv"
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False, encoding="utf-8")

        self.logger.info(f"Saved {len(jobs)} jobs to {file_path}")
        return file_path
