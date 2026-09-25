import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Chromium / Browser Defaults
BROWSER_TYPE = "chromium"
DEFAULT_HEADLESS = os.getenv("HEADLESS", "true").lower() in ("true", "1", "yes")
DEFAULT_TIMEOUT_MS = int(os.getenv("DEFAULT_TIMEOUT_MS", "30000"))
SLOW_MO_MS = int(os.getenv("SLOW_MO_MS", "0"))  # Milliseconds to delay each action (useful in --headed)
CHROME_CHANNEL = os.getenv("CHROME_CHANNEL", None)  # None = Playwright Chromium, "chrome" = installed Google Chrome

USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)
VIEWPORT = {"width": 1920, "height": 1080}
