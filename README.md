# Multi-Platform Job Scraper Suite

A modular, extensible web scraping architecture built with **Python** and **Playwright**. Designed to run multiple job board scrapers from a unified interface with standardized outputs.

---

## 📁 Project Structure

```
jobs_scraper/
├── browser.py               # Central browser management, anti-detection flags & context pooling
├── config.py                # Global settings (timeouts, viewport, user-agent, paths)
├── models.py                # Standard Pydantic schema for JobListing
├── main.py                  # CLI orchestrator & runner for all scrapers
├── requirements.txt         # Dependencies
├── .env.example             # Environment variable template
├── data/                    # Output directory for scraped datasets (CSV/JSON/Excel)
└── scrapers/                # Modular scraper implementations
    ├── __init__.py          # Auto-discovery & registry of scrapers
    ├── base_scraper.py      # Abstract BaseScraper class with save utilities
    └── example_scraper.py   # Working template/sample scraper
```

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Run All Scrapers
```bash
python main.py
```

### 3. Run a Specific Scraper (Scrapes ALL Available Jobs by Default)
```bash
python main.py --scraper hireorbit --query "software engineer"
```

### 4. Search with Custom Limit
You can limit the number of jobs if you only want a few:
```bash
# Scrape only 10 jobs
python main.py --scraper hireorbit --query "software engineer" --limit 10

# Or scrape all jobs explicitly
python main.py --scraper hireorbit --query "software engineer" --limit all
```

### 5. Visible Browser (Debugging Mode)
```bash
python main.py --scraper example --headed
```

### 6. Export Formats
Supports `csv` (default), `json`, and `xlsx`:
```bash
python main.py --scraper example --format json
```

### 7. List Registered Scrapers
```bash
python main.py --list
```

---

## 🛠️ Adding a New Scraper (Step-by-Step)

Adding a new scraper is completely modular. You just need to create a new file in `scrapers/`:

1. Create `scrapers/indeed_scraper.py` (or any other name):
```python
from typing import List
from playwright.sync_api import Page
from models import JobListing
from scrapers.base_scraper import BaseScraper

class IndeedScraper(BaseScraper):
    name = "indeed"  # Used by --scraper indeed
    base_url = "https://www.indeed.com"

    def scrape(
        self,
        page: Page,
        query: str = "Software Engineer",
        location: str = "Remote",
        limit: int = 20,
        **kwargs,
    ) -> List[JobListing]:
        self.logger.info(f"Navigating to {self.base_url}...")
        page.goto(f"{self.base_url}/jobs?q={query}&l={location}")
        
        jobs: List[JobListing] = []
        # Add your extraction selectors here ...
        
        return jobs
```

2. **That's it!** The scraper will be **automatically discovered** by `scrapers/__init__.py` and made available in `main.py` without modifying any other files.
