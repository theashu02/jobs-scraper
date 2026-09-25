import logging
import re
import urllib.parse
from typing import List, Optional

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from models import JobListing
from scrapers.base_scraper import BaseScraper


class JobDivaScraper(BaseScraper):
    """
    Scraper for JobDiva Candidate Portal.
    Searches jobs by dynamic query keyword using the portal search box,
    navigates into each job listing's details, extracts complete job specifications
    (title, job ID, location, package/rate, work mode, job type, skills, full description),
    and exports to CSV.
    """

    name = "jobdiva"
    base_url = "https://www1.jobdiva.com/portal/?a=y5jdnwgsfix0t1d7osw75h145zxdtm008fvae292vxos9unusglbuzpszehgbfa0&jr_id=6aa05015a2266b538d22f8f9#/"

    def scrape(
        self,
        page: Page,
        query: str = "Software",
        location: str = "",
        limit: Optional[int] = None,
        **kwargs,
    ) -> List[JobListing]:
        self.logger.info(f"Opening JobDiva Candidate Portal (Query='{query}', Limit={limit or 'All'})")

        # 1. Navigate to portal
        try:
            page.goto(self.base_url, wait_until="domcontentloaded", timeout=40000)
        except PlaywrightTimeoutError:
            self.logger.warning("Initial navigation timed out, retrying...")
            page.goto(self.base_url, wait_until="commit", timeout=40000)

        # 2. Wait for search box to appear
        try:
            page.wait_for_selector("input.inputbox_search", timeout=30000)
        except Exception:
            self.logger.error("Could not find search input on JobDiva portal!")
            return []

        # 3. Enter search query and submit
        if query and query.strip():
            self.logger.info(f"Searching for '{query.strip()}' in JobDiva...")
            search_input = page.locator("input.inputbox_search")
            search_input.fill(query.strip())
            
            search_btn = page.locator("button:has-text('Search Jobs')").first
            if search_btn.count() > 0:
                search_btn.click()
            else:
                search_input.press("Enter")

            # Wait for search results to load
            page.wait_for_timeout(3500)

        scraped_jobs: List[JobListing] = []
        page_num = 1

        # 4. Iterate over search result pages
        while True:
            # Wait for job cards / Details buttons
            try:
                page.wait_for_selector("button:has-text('Details')", timeout=15000)
            except Exception:
                self.logger.warning("No job cards or 'Details' buttons found on this page.")
                break

            details_btns = page.locator("button:has-text('Details')").all()
            total_on_page = len(details_btns)
            self.logger.info(f"[Page {page_num}] Found {total_on_page} job listings.")

            if total_on_page == 0:
                break

            for i in range(total_on_page):
                if limit and limit > 0 and len(scraped_jobs) >= limit:
                    self.logger.info(f"Target limit of {limit} reached.")
                    break

                self.logger.info(f"[{len(scraped_jobs) + 1}/{limit or 'All'}] Opening job #{i + 1} on Page {page_num}...")

                try:
                    # Re-locate details buttons to avoid stale element reference
                    current_btns = page.locator("button:has-text('Details')").all()
                    if i >= len(current_btns):
                        break

                    current_btns[i].click()
                    page.wait_for_timeout(2500)

                    # Extract details from the open job view
                    job_item = self._extract_job_details(page)
                    if job_item:
                        scraped_jobs.append(job_item)
                        self.logger.info(
                            f"  -> Extracted: '{job_item.title}' | Location: {job_item.location} | Package: {job_item.salary}"
                        )

                    # Click 'Job List' to return back to results
                    job_list_btn = page.locator("text='Job List'").first
                    if job_list_btn.count() > 0:
                        job_list_btn.click()
                        page.wait_for_selector("button:has-text('Details')", timeout=15000)
                        page.wait_for_timeout(1000)
                    else:
                        page.go_back()
                        page.wait_for_timeout(2000)

                except Exception as e:
                    self.logger.error(f"Error extracting job #{i + 1}: {e}")
                    # Attempt recovery to job list
                    try:
                        job_list_btn = page.locator("text='Job List'").first
                        if job_list_btn.count() > 0:
                            job_list_btn.click()
                            page.wait_for_timeout(2000)
                    except Exception:
                        pass

            # Check if limit reached
            if limit and limit > 0 and len(scraped_jobs) >= limit:
                break

            # Handle pagination
            next_btn = page.locator("button[aria-label='Next Page']")
            if next_btn.count() > 0 and next_btn.is_enabled():
                self.logger.info(f"Navigating to page {page_num + 1}...")
                next_btn.click()
                page_num += 1
                page.wait_for_timeout(3500)
            else:
                self.logger.info("No further pages available.")
                break

        self.logger.info(f"Successfully scraped {len(scraped_jobs)} jobs from JobDiva.")
        return scraped_jobs

    def _extract_job_details(self, page: Page) -> Optional[JobListing]:
        """
        Parses the active job details view on JobDiva portal.
        """
        current_url = page.url
        body_text = page.inner_text("body")
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]

        # Extract Job ID from URL or text
        job_id = None
        m_id = re.search(r"#/jobs/(\d+)", current_url)
        if m_id:
            job_id = m_id.group(1)

        # Look for Title and Reference #
        # Example format on detail view: "Senior Quality Management System Developer#26-32447"
        title = "Untitled Position"
        for line in lines:
            if "#" in line and any(k in line.lower() for k in ["developer", "engineer", "manager", "specialist", "technician", "analyst", "consultant", "lead", "architect", "officer", "associate"]):
                title_clean = re.sub(r"#\d+(?:-\d+)?.*", "", line).strip()
                if title_clean:
                    title = title_clean
                    break

        if title == "Untitled Position":
            # Fallback to query param in URL if present: ?jobtitle=...
            if "jobtitle=" in current_url:
                parsed = urllib.parse.urlparse(current_url)
                params = urllib.parse.parse_qs(parsed.query or parsed.fragment.split("?")[-1])
                if "jobtitle" in params:
                    title = params["jobtitle"][0]

        # Extract Salary / Hourly Rate
        salary = "Not specified"
        m_sal = re.search(r"(\$[\d,.]+(?:\s*-\s*\$?[\d,.]+)?\s*(?:per hour|/hour|per year|/year|hr|yr))", body_text, re.IGNORECASE)
        if m_sal:
            salary = m_sal.group(1).strip()

        # Extract Location
        location = "Not specified"
        for line in lines:
            # Matches standard US locations like "Sunnyvale, CA", "Charlotte, NC - Remote"
            if re.match(r"^[A-Za-z\s.-]+,\s*[A-Z]{2}(?:\s*-\s*[A-Za-z]+)?$", line):
                location = line
                break

        # Extract Work Mode & Job Type
        work_mode = "Onsite"
        for mode in ["Remote", "Hybrid", "Onsite"]:
            if mode.lower() in [l.lower() for l in lines[:20]]:
                work_mode = mode
                break

        job_type = "Contract"
        for jt in ["Contract", "Full Time", "Full-time", "Direct Hire", "Part-time"]:
            if jt.lower() in [l.lower() for l in lines[:20]]:
                job_type = jt
                break

        # Adjust location if Remote or Hybrid
        if work_mode in ("Remote", "Hybrid") and work_mode not in location:
            location = f"{location} ({work_mode})" if location != "Not specified" else work_mode

        # Extract Start Date
        posted_date = None
        for line in lines:
            if line.lower().startswith("starts "):
                posted_date = line
                break

        # Extract Description & Skills
        desc_start = False
        desc_lines = []
        skills_lines = []
        in_skills = False

        for line in lines:
            if "job description" in line.lower():
                desc_start = True
                continue
            if not desc_start:
                continue

            if any(k in line.lower() for k in ["top skills:", "required skills:", "qualifications:"]):
                in_skills = True
                continue
            elif in_skills and any(k in line.lower() for k in ["responsibilities:", "requirements:", "about the company:", "benefits:"]):
                in_skills = False

            if in_skills and len(line) > 10:
                skills_lines.append(line)

            desc_lines.append(line)

        description = "\n".join(desc_lines).strip() or body_text
        skills = "; ".join(skills_lines[:10]) if skills_lines else ""

        # Extract Company (detect staffing agency / client)
        company = "JobDiva Client"
        if "talentburst" in body_text.lower():
            company = "TalentBurst"

        return JobListing(
            id=job_id,
            title=title,
            company=company,
            location=location,
            salary=salary,
            job_type=job_type,
            url=current_url,
            apply_url=current_url,
            posted_date=posted_date,
            skills=skills,
            description=description,
            source=self.name,
        )
