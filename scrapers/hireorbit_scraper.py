import json
import re
import urllib.parse
from typing import List, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from models import JobListing
from scrapers.base_scraper import BaseScraper


class HireorbitScraper(BaseScraper):
    """
    Scraper for Hireorbit (https://hireorbit.social-networking.me/).
    Searches for jobs dynamically by keyword and visits each job detail page
    to extract comprehensive job information (title, company, description,
    package/salary, apply URL, location, type, skills, etc.).
    """

    name = "hireorbit"
    base_url = "https://hireorbit.social-networking.me"

    def scrape(
        self,
        page: Page,
        query: str = "software engineer",
        location: str = "Remote",
        limit: int = 20,
        **kwargs,
    ) -> List[JobListing]:
        # Construct search URL dynamically
        encoded_query = urllib.parse.quote_plus(query.strip())
        search_url = f"{self.base_url}/search?q={encoded_query}"

        self.logger.info(f"Opening Hireorbit search: {search_url} (Limit: {limit})")

        try:
            page.goto(search_url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeoutError:
            self.logger.warning("Network idle timed out, waiting for DOM content loaded...")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

        # Parse job cards from the search result grid
        soup = BeautifulSoup(page.content(), "html.parser")
        card_elements = soup.select(".card, a.card")

        if not card_elements:
            # Fallback search for job links if .card selector varies
            card_elements = [
                a for a in soup.find_all("a", href=True)
                if "/remote-jobs/" in a["href"] and a.get("class") and "rel-card" not in a.get("class", [])
            ]

        self.logger.info(f"Found {len(card_elements)} job cards for query '{query}'.")

        job_links = []
        for card in card_elements:
            href = card.get("href")
            if href and href not in job_links:
                if not href.startswith("http"):
                    href = urllib.parse.urljoin(self.base_url, href)
                job_links.append(href)

        # Apply user limit (scrape all if limit is None or <= 0)
        if limit and limit > 0:
            target_links = job_links[:limit]
            self.logger.info(f"Proceeding to scrape details for {len(target_links)} jobs (limit={limit})...")
        else:
            target_links = job_links
            self.logger.info(f"Proceeding to scrape details for ALL {len(target_links)} jobs found...")

        scraped_jobs: List[JobListing] = []

        for index, job_url in enumerate(target_links, start=1):
            self.logger.info(f"[{index}/{len(target_links)}] Fetching detail page: {job_url}")
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
                detail_soup = BeautifulSoup(page.content(), "html.parser")

                job_item = self._parse_job_detail(detail_soup, job_url)
                if job_item:
                    scraped_jobs.append(job_item)
                    self.logger.info(
                        f"  -> Extracted: '{job_item.title}' | Company: {job_item.company} | Package: {job_item.salary}"
                    )
            except Exception as e:
                self.logger.error(f"Failed to scrape job at {job_url}: {e}")

        self.logger.info(
            f"Successfully scraped {len(scraped_jobs)} jobs from Hireorbit for query '{query}'."
        )
        return scraped_jobs

    def _parse_job_detail(self, soup: BeautifulSoup, job_url: str) -> Optional[JobListing]:
        """
        Extracts structured data from the job detail page HTML
        using schema.org JSON-LD and DOM elements.
        """
        # 1. Job Title
        title_elem = soup.select_one(".job-hero h1, h1")
        title = title_elem.get_text(strip=True) if title_elem else "Untitled Position"

        # 2. Posted Date
        date_elem = soup.select_one(".job-date")
        posted_date = (
            date_elem.get_text(strip=True).replace("Posted", "").strip()
            if date_elem
            else None
        )

        # 3. Direct External Apply Link
        apply_elem = soup.select_one(".apply-cta-bottom a.apply-cta, a.apply-cta, a.mob-active")
        apply_url = apply_elem.get("href") if apply_elem else None

        # 4. Parse Schema.org JSON-LD if present
        json_ld_data = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "JobPosting":
                    json_ld_data = data
                    break
            except Exception:
                continue

        # Salary / Package extraction
        salary = "Not specified"
        if "baseSalary" in json_ld_data:
            bs = json_ld_data["baseSalary"]
            val = bs.get("value", {})
            curr = bs.get("currency", "USD")
            unit = val.get("unitText", "").lower()
            min_v = val.get("minValue")
            max_v = val.get("maxValue")
            if min_v and max_v:
                salary = f"${min_v:,} - ${max_v:,} {curr}/{unit}".strip()
            elif min_v:
                salary = f"${min_v:,} {curr}/{unit}".strip()

        # Job Type (Full-time, Part-time, etc.)
        job_type = json_ld_data.get("employmentType") or "Full-time"
        if isinstance(job_type, str):
            job_type = job_type.replace("_", " ").title()

        # Location extraction
        location = "Remote"
        if "applicantLocationRequirements" in json_ld_data:
            reqs = json_ld_data["applicantLocationRequirements"]
            if isinstance(reqs, list):
                countries = [
                    r.get("name")
                    for r in reqs
                    if isinstance(r, dict) and "name" in r
                ]
                if countries:
                    if len(countries) > 3:
                        location = f"Remote ({', '.join(countries[:3])} +{len(countries)-3} more)"
                    else:
                        location = f"Remote ({', '.join(countries)})"
        elif "jobLocation" in json_ld_data:
            jl = json_ld_data["jobLocation"]
            addr = jl.get("address", {})
            country = addr.get("addressCountry")
            if country:
                location = f"Remote ({country})"

        # Clean Description & Extract Text
        content_box = soup.select_one(".content-box")
        description_text = ""
        skills_list = []

        if content_box:
            # Find skills section if explicitly present
            for p_tag in content_box.find_all(["p", "h3", "h2"]):
                if "skill" in p_tag.get_text(strip=True).lower():
                    next_sib = p_tag.find_next_sibling()
                    if next_sib and next_sib.name in ("ul", "ol"):
                        skills_list = [li.get_text(strip=True) for li in next_sib.find_all("li")]
                    break

            # Clone and remove CTA button before getting text
            cloned_box = BeautifulSoup(str(content_box), "html.parser")
            for cta in cloned_box.select(".apply-cta-bottom, .apply-cta"):
                cta.decompose()
            description_text = cloned_box.get_text("\n", strip=True)

        # Company Name Detection
        company = "Not specified"

        # Check Company Overview block first (most accurate for Hireorbit listings)
        if description_text:
            m_co = re.search(
                r"Company Overview\s*[:\n\-]+\s*([A-Za-z0-9\s&.,'-]+?)(?:\.\s+It was founded|\s+It was founded|\s+is\b)",
                description_text,
                re.IGNORECASE,
            )
            if m_co:
                cand = m_co.group(1).strip()
                if cand and len(cand) < 60:
                    company = cand

        # Fallback to JSON-LD if not detected
        if company == "Not specified" and "hiringOrganization" in json_ld_data:
            org_name = json_ld_data["hiringOrganization"].get("name", "")
            if org_name and org_name.lower() not in ("member", "hireorbit", "organization"):
                company = org_name

        # Fallback to introductory sentence pattern: "... [Company] is a company on a mission ..."
        if company == "Not specified" and description_text:
            m_intro = re.search(
                r"(?:open to candidates in [^.]+\.\s+)?([A-Za-z0-9\s&.,'-]+?)\s+is (?:a company|one of the nation)",
                description_text,
                re.IGNORECASE,
            )
            if m_intro:
                cand = m_intro.group(1).strip()
                if cand and len(cand) < 60:
                    company = cand

        # Unique ID from URL slug
        job_slug = job_url.rstrip("/").split("/")[-1]

        return JobListing(
            id=job_slug,
            title=title,
            company=company,
            location=location,
            salary=salary,
            job_type=job_type,
            url=job_url,
            apply_url=apply_url,
            posted_date=posted_date or json_ld_data.get("datePosted"),
            skills="; ".join(skills_list) if skills_list else "",
            description=description_text,
            source=self.name,
        )
