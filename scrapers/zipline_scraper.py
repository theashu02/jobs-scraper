import html
import re
import urllib.parse
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from models import JobListing
from scrapers.base_scraper import BaseScraper


class ZiplineScraper(BaseScraper):
    """
    Scraper for Zipline (https://www.zipline.com/open-roles).
    Searches jobs by dynamic title/keyword and location, scrolls to lazy-load
    all open positions, visits each job detail page, and extracts comprehensive
    listing details (title, company, location, salary/package, apply link,
    requirements, description).
    """

    name = "zipline"
    base_url = "https://www.zipline.com/open-roles"
    greenhouse_api_base = "https://boards-api.greenhouse.io/v1/boards/flyzipline/jobs"

    def scrape(
        self,
        page: Page,
        query: str = "software engineer",
        location: str = "",
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[JobListing]:
        # 1. Build parameterized search URL
        params = {}
        if query and query.strip():
            params["q"] = query.strip()
        if location and location.strip():
            params["locations"] = location.strip()

        if params:
            search_url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        else:
            search_url = self.base_url

        self.logger.info(f"Opening Zipline open roles: {search_url} (Limit: {limit or 'All'})")

        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(3000)
        except PlaywrightTimeoutError:
            self.logger.warning("Initial page load timed out, retrying...")
            page.goto(search_url, wait_until="load", timeout=35000)
            page.wait_for_timeout(3000)

        # 2. Scroll dynamically until all job cards are rendered
        job_links = self._scroll_and_collect_job_links(page, limit)

        if not job_links:
            self.logger.warning(
                f"No open roles found matching query='{query}' and location='{location}'."
            )
            return []

        # Apply user limit if requested
        if limit and limit > 0:
            target_links = job_links[:limit]
            self.logger.info(f"Proceeding to scrape details for {len(target_links)} jobs (limit={limit})...")
        else:
            target_links = job_links
            self.logger.info(f"Proceeding to scrape details for ALL {len(target_links)} jobs found...")

        scraped_jobs: List[JobListing] = []

        # 3. Visit each job detail page and extract details
        for index, job_url in enumerate(target_links, start=1):
            self.logger.info(f"[{index}/{len(target_links)}] Fetching detail page: {job_url}")
            try:
                # Extract job ID/token from URL
                job_token = job_url.rstrip("/").split("/")[-1].split("?")[0]

                # Navigate in browser so user can see it in --headed mode
                page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1000)

                job_item = self._extract_job_details(page, job_url, job_token)
                if job_item:
                    scraped_jobs.append(job_item)
                    self.logger.info(
                        f"  -> Extracted: '{job_item.title}' | Location: {job_item.location} | Package: {job_item.salary}"
                    )
            except Exception as e:
                self.logger.error(f"Failed to scrape Zipline job at {job_url}: {e}")

        self.logger.info(
            f"Successfully scraped {len(scraped_jobs)} jobs from Zipline (query='{query}', location='{location}')."
        )
        return scraped_jobs

    def _scroll_and_collect_job_links(self, page: Page, limit: Optional[int]) -> List[str]:
        """
        Scrolls the page down repeatedly to trigger lazy-loading of all job cards.
        """
        self.logger.info("Scrolling page to load all matching jobs...")
        collected_links: List[str] = []
        consecutive_same_count = 0
        max_scroll_attempts = 40

        # Wait up to 10 seconds for initial cards to render in the DOM
        try:
            page.wait_for_selector("a[href*='/open-roles/']", timeout=10000)
        except Exception:
            pass

        for scroll_i in range(max_scroll_attempts):
            soup = BeautifulSoup(page.content(), "html.parser")
            current_cards = [
                a.get("href")
                for a in soup.find_all("a", href=True)
                if "/open-roles/" in a.get("href", "") and a.get("href", "").rstrip("/") != "/open-roles"
            ]

            # Normalize URLs
            normalized = []
            for h in current_cards:
                full_url = urllib.parse.urljoin(self.base_url, h)
                if full_url not in normalized:
                    normalized.append(full_url)

            if len(normalized) > len(collected_links):
                consecutive_same_count = 0
                collected_links = normalized
                self.logger.info(f"Loaded {len(collected_links)} job cards so far...")
            elif len(normalized) > 0:
                consecutive_same_count += 1
                if consecutive_same_count >= 3:
                    break
            else:
                # Still 0 cards, wait briefly before retrying
                page.wait_for_timeout(1000)
                consecutive_same_count += 1
                if consecutive_same_count >= 5:
                    break

            # Scroll down to trigger next batch
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)

            # If user set a limit and we've reached it, stop scrolling
            if limit and limit > 0 and len(collected_links) >= limit:
                break

        self.logger.info(f"Finished scrolling. Found {len(collected_links)} total jobs.")
        return collected_links

    def _extract_job_details(self, page: Page, job_url: str, job_token: str) -> Optional[JobListing]:
        """
        Extracts structured job details using Zipline's Greenhouse API and page DOM.
        """
        # Try fetching structured data from Greenhouse endpoint
        api_data = {}
        try:
            api_url = f"{self.greenhouse_api_base}/{job_token}?content=true"
            res = requests.get(api_url, timeout=10)
            if res.status_code == 200:
                api_data = res.json()
        except Exception as e:
            self.logger.debug(f"Greenhouse API lookup error for {job_token}: {e}")

        # 1. Title
        title = api_data.get("title")
        if not title:
            h1_el = page.query_selector("h1")
            title = h1_el.inner_text().strip() if h1_el else page.title().split("|")[0].strip()

        # 2. Company
        company = api_data.get("company_name", "Zipline")

        # 3. Location
        location = "Not specified"
        if "location" in api_data and isinstance(api_data["location"], dict):
            location = api_data["location"].get("name", "Not specified")
        elif "offices" in api_data and api_data["offices"]:
            location = api_data["offices"][0].get("location", "Not specified")

        # 4. Description & Content
        content_html = api_data.get("content", "")
        if content_html:
            unescaped_html = html.unescape(content_html)
            content_soup = BeautifulSoup(unescaped_html, "html.parser")
            desc_text = content_soup.get_text("\n", strip=True)
        else:
            content_soup = BeautifulSoup(page.content(), "html.parser")
            desc_text = page.inner_text("body")

        # 5. Salary / Package extraction
        salary = "Not specified"
        salary_matches = re.findall(
            r"\$[\d,]+(?:\s*-\s*\$[\d,]+)?(?:\s*(?:per year|per month|per hour|annually|/yr|/hr))?",
            desc_text,
            re.IGNORECASE,
        )
        if salary_matches:
            # Filter valid compensation numbers
            valid_salaries = [
                s.strip()
                for s in salary_matches
                if len(s.replace(",", "").replace("$", "").split("-")[0].strip()) >= 4
            ]
            if valid_salaries:
                salary = valid_salaries[0]

        # 6. Job Type (Full-time, Internship, etc.)
        job_type = "Full-time"
        title_lower = title.lower()
        if "intern" in title_lower:
            job_type = "Internship"
        elif "contract" in title_lower:
            job_type = "Contract"

        # 7. Skills & Requirements
        skills_list = []
        if content_html:
            for header in content_soup.find_all(["h2", "h3", "h4", "strong"]):
                h_text = header.get_text(strip=True).lower()
                if any(k in h_text for k in ["what you'll bring", "qualifications", "requirements", "what we're looking for"]):
                    parent = header.parent if header.name == "strong" else header
                    next_list = parent.find_next(["ul", "ol"])
                    if next_list:
                        skills_list = [li.get_text(strip=True) for li in next_list.find_all("li")]
                    break

        # 8. Apply URL
        apply_url = api_data.get("absolute_url") or f"{job_url}?gh_jid={job_token}"

        # 9. Posted Date
        posted_date = api_data.get("updated_at") or api_data.get("first_published")
        if posted_date and "T" in str(posted_date):
            posted_date = str(posted_date).split("T")[0]

        return JobListing(
            id=job_token,
            title=title,
            company=company,
            location=location,
            salary=salary,
            job_type=job_type,
            url=job_url,
            apply_url=apply_url,
            posted_date=posted_date,
            skills="; ".join(skills_list) if skills_list else "",
            description=desc_text,
            source=self.name,
        )
