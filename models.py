from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class JobListing(BaseModel):
    """Standardized schema for all scraped job listings across different platforms."""
    id: Optional[str] = Field(default=None, description="Unique job ID from source if available")
    title: str = Field(..., description="Job title")
    company: str = Field(default="Not specified", description="Company name")
    location: Optional[str] = Field(default="Remote", description="Job location or Remote status")
    salary: Optional[str] = Field(default="Not specified", description="Salary/compensation/package details")
    job_type: Optional[str] = Field(default="Full-time", description="Full-time, Part-time, Contract, etc.")
    url: str = Field(..., description="Portal listing page URL")
    apply_url: Optional[str] = Field(default=None, description="Direct external application link")
    posted_date: Optional[str] = Field(default=None, description="Date posted or text representation")
    skills: Optional[str] = Field(default="", description="Required skills or tags")
    description: Optional[str] = Field(default="", description="Snippet or full description")
    source: str = Field(..., description="Name of the job portal/board")
    scraped_at: datetime = Field(default_factory=datetime.utcnow, description="Scraping timestamp")
