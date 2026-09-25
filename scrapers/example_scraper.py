from typing import List
from playwright.sync_api import Page

from models import JobListing
from scrapers.base_scraper import BaseScraper


class ExampleScraper(BaseScraper):
    """
    Example template scraper demonstrating how to structure scrapers.
    It scrapes sample job listings from a public demonstration page or HTML content.
    """

    name = "example"
    base_url = "https://quotes.toscrape.com/"

    def scrape(
        self,
        page: Page,
        query: str = "Software Engineer",
        location: str = "Remote",
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[JobListing]:
        self.logger.info(
            f"Starting scraper '{self.name}' with query='{query}', location='{location}', limit={limit}"
        )

        jobs: List[JobListing] = []

        # Example demonstration: Navigate to a safe URL to test browser navigation
        self.logger.info(f"Navigating to {self.base_url}")
        page.goto(self.base_url, wait_until="domcontentloaded")

        # Mock extracting sample jobs to demonstrate data flow
        sample_titles = [
            f"Senior {query}",
            f"Lead {query}",
            f"Junior {query}",
            f"Staff {query}",
            f"Fullstack {query}",
        ]

        for i, title in enumerate(sample_titles[:limit]):
            job = JobListing(
                id=f"ex-{i+1}",
                title=title,
                company=f"TechCorp Solutions #{i+1}",
                location=location,
                salary="$120,000 - $160,000/yr",
                job_type="Full-time",
                url=f"https://example.com/careers/job-{i+1}",
                posted_date="Just now",
                description=f"Looking for an experienced {title} in {location}.",
                source=self.name,
            )
            jobs.append(job)

        self.logger.info(f"Collected {len(jobs)} jobs from {self.name}")
        return jobs
