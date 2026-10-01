import logging
import os
from typing import List, Optional, Tuple

import requests
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

import config
from models import JobListing
from scrapers.base_scraper import BaseScraper


class ApplynxtScraper(BaseScraper):
    """
    Scraper for ApplyNxt (https://www.applynxt.com/).
    
    Workflow:
    1. Launches ApplyNxt in Chromium (Playwright).
    2. Navigates to https://www.applynxt.com/ and clicks 'Login' in top right.
    3. Authenticates with credentials (default: deadlock0002@gmail.com / Ashu@0512).
    4. Intercepts and extracts session token ('rr_access_token') and API key ('x-api-key').
    5. Directly queries the backend API (https://rezryt-backend.onrender.com/api/jobs/board)
       with dynamic parameters (search query, date_from, limit, and cursor pagination last_key).
    6. Normalizes listings into standardized JobListing models and exports to CSV.
    """

    name = "applynxt"
    base_url = "https://www.applynxt.com/"
    api_base_url = "https://rezryt-backend.onrender.com/api/jobs/board"
    default_api_key = "b5d1d1b9e1c3abb1d2251f50ce2eab94afa4433f4911bb8f65d3fdc07bfc85cb"

    def __init__(self):
        super().__init__()
        self.email = os.getenv("APPLYNXT_EMAIL", "deadlock0002@gmail.com")
        self.password = os.getenv("APPLYNXT_PASSWORD", "Ashu@0512")
        self.captured_api_key = None

    def _login(self, page: Page) -> Tuple[Optional[str], str]:
        """
        Executes browser-based login on ApplyNxt and returns (access_token, api_key).
        """
        self.logger.info(f"Opening ApplyNxt landing page: {self.base_url}")

        # Listen for requests to capture x-api-key header dynamically
        def handle_request(req):
            if "rezryt-backend" in req.url:
                for k, v in req.headers.items():
                    if k.lower() == "x-api-key" and v:
                        self.captured_api_key = v

        page.on("request", handle_request)

        try:
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            self.logger.warning("Initial navigation timed out; retrying load...")
            page.goto(self.base_url, wait_until="load", timeout=40000)
            page.wait_for_timeout(2000)

        # Check if already authenticated in local storage
        existing_token = page.evaluate("() => localStorage.getItem('rr_access_token')")
        if existing_token:
            self.logger.info("Found existing session token in localStorage.")
            api_key = self.captured_api_key or self.default_api_key
            return existing_token, api_key

        # Click top-right Login button
        self.logger.info("Locating Login button...")
        login_btn = page.query_selector(
            "a:has-text('Login'), button:has-text('Login'), a[href*='login'], button[href*='login']"
        )
        if login_btn:
            self.logger.info("Clicking Login button...")
            login_btn.click()
            page.wait_for_timeout(1500)
        else:
            self.logger.warning("No explicit Login button found, checking if form already present.")

        # Locate Email & Password input fields
        self.logger.info("Waiting for login form inputs...")
        email_selector = "input[type='email'], input[name='email'], input[placeholder*='email' i]"
        pwd_selector = "input[type='password'], input[name='password'], input[placeholder*='password' i]"

        try:
            page.wait_for_selector(email_selector, timeout=12000)
        except PlaywrightTimeoutError:
            self.logger.error("Email input field did not appear.")
            return None, self.default_api_key

        # Fill credentials
        self.logger.info(f"Submitting credentials for: {self.email}")
        email_inp = page.query_selector(email_selector)
        pwd_inp = page.query_selector(pwd_selector)

        if email_inp:
            email_inp.fill(self.email)
        if pwd_inp:
            pwd_inp.fill(self.password)

        page.wait_for_timeout(500)

        # Click Submit button
        submit_btn = page.query_selector(
            "button[type='submit'], button:has-text('Sign In'), button:has-text('Login'), button:has-text('Log in')"
        )
        if submit_btn:
            submit_btn.click()
        else:
            # Fallback: press Enter on password input
            if pwd_inp:
                pwd_inp.press("Enter")

        # Wait for localStorage token to be populated post-login
        self.logger.info("Waiting for authentication token...")
        try:
            page.wait_for_function(
                "() => !!localStorage.getItem('rr_access_token')",
                timeout=20000,
            )
        except PlaywrightTimeoutError:
            self.logger.warning("Timeout waiting for rr_access_token in localStorage. Checking once more...")

        page.wait_for_timeout(2000)
        token = page.evaluate("() => localStorage.getItem('rr_access_token')")
        api_key = self.captured_api_key or self.default_api_key

        if token:
            self.logger.info("Authentication successful! Acquired JWT bearer token.")
        else:
            self.logger.error("Failed to acquire authentication token from ApplyNxt login.")

        return token, api_key

    def scrape(
        self,
        page: Page,
        query: str = "Software Engineer",
        location: str = "",
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[JobListing]:
        """
        Scrapes ApplyNxt jobs by logging in via browser, retrieving authorization,
        and querying backend API endpoint with dynamic search & cursor pagination.
        """
        # 1. Perform browser login and obtain session token
        token, api_key = self._login(page)
        if not token:
            self.logger.error("Cannot proceed with scraping without authentication token.")
            return []

        # 2. Setup HTTP session for querying rezryt-backend API
        session = requests.Session()
        session.headers.update({
            "referer": "https://www.applynxt.com/",
            "origin": "https://www.applynxt.com",
            "user-agent": config.USER_AGENT,
            "x-api-key": api_key,
            "authorization": f"Bearer {token}",
            "accept": "application/json",
        })

        date_from = kwargs.get("date_from", "2026-09-30")
        page_size = min(20, limit) if limit else 20
        last_key = None
        all_jobs: List[JobListing] = []

        display_limit = limit if limit is not None else "All"
        self.logger.info(
            f"Querying ApplyNxt API | Search: '{query}' | Date From: {date_from} | Target Limit: {display_limit}"
        )

        page_num = 1
        while True:
            params = {
                "limit": page_size,
            }
            if query and query.strip():
                params["search"] = query.strip()
            if date_from:
                params["date_from"] = date_from
            if last_key is not None:
                params["last_key"] = last_key

            self.logger.info(f"Fetching API page {page_num} (params: {params})...")

            try:
                resp = session.get(self.api_base_url, params=params, timeout=25)
            except Exception as e:
                self.logger.error(f"Network error querying ApplyNxt backend: {e}")
                break

            if resp.status_code != 200:
                self.logger.error(
                    f"API request failed with status {resp.status_code}: {resp.text[:300]}"
                )
                break

            try:
                data = resp.json()
            except Exception as e:
                self.logger.error(f"Failed to parse JSON response: {e}")
                break

            if not data.get("success", False):
                self.logger.warning(f"API indicated success=false: {data}")
                break

            jobs_data = data.get("jobs", [])
            total_available = data.get("total", len(jobs_data))
            next_key = data.get("next_key")

            self.logger.info(
                f"Page {page_num} returned {len(jobs_data)} jobs (Total reported: {total_available}, next_key: {next_key})"
            )

            if not jobs_data:
                self.logger.info("No more jobs returned by API.")
                break

            for item in jobs_data:
                # Location and remote handling
                loc = (item.get("location") or "").strip()
                remote_type = (item.get("remote_type") or "").strip()
                if remote_type and remote_type.lower() not in loc.lower():
                    full_location = f"{loc} ({remote_type})" if loc else remote_type
                else:
                    full_location = loc or "Remote"

                # Filter by location if specified by user
                if location and location.strip():
                    loc_target = location.strip().lower()
                    if loc_target not in full_location.lower():
                        continue

                # Combine skills and tags
                combined_skills = []
                raw_skills = item.get("skills")
                if isinstance(raw_skills, list):
                    combined_skills.extend([s for s in raw_skills if s])
                elif raw_skills:
                    combined_skills.append(str(raw_skills))

                raw_tags = item.get("tags")
                if isinstance(raw_tags, list):
                    for tag in raw_tags:
                        if tag and tag not in combined_skills:
                            combined_skills.append(tag)

                skills_str = "; ".join(str(s) for s in combined_skills)

                job = JobListing(
                    id=item.get("jobId") or item.get("_board_job_id"),
                    title=item.get("jobTitle") or "Untitled Role",
                    company=item.get("company") or "ApplyNxt Partner",
                    location=full_location,
                    salary=item.get("salary") or "Not specified",
                    job_type=item.get("employment_type") or "Full-time",
                    url=item.get("jobLink") or self.base_url,
                    apply_url=item.get("jobLink") or None,
                    posted_date=item.get("posted_date") or item.get("finishedAt") or None,
                    skills=skills_str,
                    description=item.get("jobDescription") or "",
                    source=self.name,
                )
                all_jobs.append(job)

                if limit and len(all_jobs) >= limit:
                    break

            if limit and len(all_jobs) >= limit:
                self.logger.info(f"Reached requested limit of {limit} jobs.")
                break

            # If no cursor returned or cursor is identical, end pagination
            if next_key is None or str(next_key) == str(last_key):
                self.logger.info("Reached the end of pagination (next_key exhausted).")
                break

            last_key = next_key
            page_num += 1

        self.logger.info(f"Finished scraping ApplyNxt. Collected {len(all_jobs)} jobs.")
        return all_jobs
