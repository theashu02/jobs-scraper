import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Dict, Type

from scrapers.base_scraper import BaseScraper

SCRAPER_REGISTRY: Dict[str, Type[BaseScraper]] = {}


def register_scrapers():
    """
    Dynamically discovers and registers all BaseScraper subclasses
    found within the scrapers package directory.
    """
    package_dir = Path(__file__).resolve().parent

    for _, module_name, is_pkg in pkgutil.iter_modules([str(package_dir)]):
        if is_pkg or module_name == "base_scraper":
            continue

        full_module_name = f"scrapers.{module_name}"
        module = importlib.import_module(full_module_name)

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseScraper) and obj is not BaseScraper:
                if obj.name and obj.name != "base":
                    SCRAPER_REGISTRY[obj.name] = obj


# Auto-load available scrapers on module import
register_scrapers()


def get_scraper(name: str) -> Type[BaseScraper]:
    """Retrieve scraper class by name."""
    if name not in SCRAPER_REGISTRY:
        raise KeyError(
            f"Scraper '{name}' not found. Available scrapers: {list(SCRAPER_REGISTRY.keys())}"
        )
    return SCRAPER_REGISTRY[name]


def list_scrapers() -> list[str]:
    """List names of all registered scrapers."""
    return list(SCRAPER_REGISTRY.keys())
