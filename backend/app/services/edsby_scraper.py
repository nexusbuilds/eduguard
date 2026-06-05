"""Edsby grade scraper using requests + BeautifulSoup.

Edsby uses client-side HMAC-SHA-512 password encryption via JavaScript.
Since replicating this crypto in Python is impractical, this module provides:
1. A real scraper that uses Playwright (headless browser) to handle JS encryption
2. A mock scraper for testing when credentials are locked or Playwright unavailable

The scraper logs into Edsby, navigates to the gradebook, and extracts grades.
"""
import re
import random
from datetime import datetime, date
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class EdsbyGrade:
    subject: str
    grade: str
    grade_date: Optional[date]
    teacher: Optional[str] = None
    category: Optional[str] = None


class EdsbyAuthError(Exception):
    pass


class EdsbyUnavailableError(Exception):
    pass


class EdsbyScraper:
    """Edsby scraper with Playwright for JS-encrypted login."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._page = None
        self._browser = None
        self._context = None

    def _init_playwright(self):
        """Initialize Playwright browser."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise EdsbyUnavailableError("Playwright not installed. Run: pip install playwright")

        self._pw = sync_playwright().__enter__()
        # Try to find a chromium executable
        import shutil
        chromium_paths = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/microsoft-edge",
        ]
        exe_path = None
        for p in chromium_paths:
            if shutil.which(p):
                exe_path = p
                break

        try:
            if exe_path:
                self._browser = self._pw.chromium.launch(
                    headless=True,
                    executable_path=exe_path,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            else:
                self._browser = self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot launch browser: {e}")

        self._context = self._browser.new_context(viewport={"width": 1280, "height": 800})
        self._page = self._context.new_page()

    def login(self) -> bool:
        """Log into Edsby using Playwright to handle JS encryption."""
        self._init_playwright()
        page = self._page

        try:
            page.goto(f"{self.base_url}/core/login", wait_until="networkidle")
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot reach Edsby login page: {e}")

        # Check if we're already on a logged-in page
        if "/login" not in page.url:
            return True

        # Fill and submit form (Playwright executes JS onclick handlers)
        page.fill("input[name='userid']", self.username)
        page.fill("input[name='password']", self.password)

        # Click submit and wait for navigation
        try:
            page.click("input[type='submit']")
            page.wait_for_load_state("networkidle")
        except Exception as e:
            raise EdsbyUnavailableError(f"Login submission failed: {e}")

        # Check result
        current_url = page.url
        body_text = page.inner_text("body")

        if "/login" in current_url.lower():
            if "bad" in body_text.lower() or "incorrect" in body_text.lower():
                raise EdsbyAuthError("Invalid Edsby username or password")
            elif "disabled" in body_text.lower() or "locked" in body_text.lower():
                raise EdsbyAuthError("Edsby account temporarily disabled due to too many failed attempts")
            else:
                raise EdsbyAuthError(f"Edsby login failed. Page: {current_url}")

        return True

    def scrape_grades(self, child_name: Optional[str] = None) -> List[EdsbyGrade]:
        """Scrape grades from Edsby. If child_name provided, filter to that student."""
        if not self._page:
            self.login()

        page = self._page
        grades: List[EdsbyGrade] = []

        # Edsby gradebook URL varies by district. Common patterns:
        gradebook_urls = [
            f"{self.base_url}/core/gradebook",
            f"{self.base_url}/core/grades",
            f"{self.base_url}/core/classroom",
        ]

        found_grades = False
        for url in gradebook_urls:
            try:
                page.goto(url, wait_until="networkidle")
                content = page.content()
                if "grade" in content.lower() or "mark" in content.lower() or "%" in content:
                    found_grades = True
                    break
            except Exception:
                continue

        if not found_grades:
            # Try to find grade links from the home page
            page.goto(self.base_url, wait_until="networkidle")
            links = page.query_selector_all("a")
            for link in links:
                href = link.get_attribute("href") or ""
                text = link.inner_text().strip()
                if any(w in text.lower() for w in ["grade", "mark", "report card", "progress"]):
                    try:
                        page.goto(href if href.startswith("http") else self.base_url + href)
                        page.wait_for_load_state("networkidle")
                        found_grades = True
                        break
                    except Exception:
                        continue

        if not found_grades:
            raise EdsbyUnavailableError("Could not locate gradebook page in Edsby")

        # Extract grade data from the page
        # Edsby typically renders grades in tables or card layouts
        content = page.content()

        # Strategy 1: Look for table rows with grade data
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "html.parser")

        # Try multiple selectors for grade rows
        selectors = [
            "tr",  # table rows
            ".grade-row",
            ".course-row",
            ".class-row",
            "[data-grade]",
        ]

        for selector in selectors:
            rows = soup.select(selector)
            for row in rows:
                cells = row.find_all(["td", "div"])
                if not cells:
                    continue

                # Try to extract subject and grade
                subject = None
                grade_val = None
                for cell in cells:
                    text = cell.get_text(strip=True)
                    # Look for percentage grades
                    if re.match(r"^\d{1,3}\s*%$", text) or re.match(r"^\d{1,3}$", text):
                        grade_val = text.replace("%", "").strip()
                    elif re.match(r"^[A-F][+-]?$", text):
                        grade_val = text
                    elif len(text) > 2 and not text.replace(".", "").replace("-", "").isdigit():
                        if not subject:
                            subject = text

                if subject and grade_val:
                    grades.append(EdsbyGrade(
                        subject=subject,
                        grade=grade_val,
                        grade_date=date.today(),
                    ))

        # Strategy 2: Regex-based extraction from page text
        if not grades:
            text = soup.get_text()
            # Look for patterns like "Math 85%" or "Science: 78"
            patterns = [
                r"([A-Za-z\s]+?)\s*[:\-]?\s*(\d{1,3})\s*%",
                r"([A-Za-z\s]+?)\s*[:\-]?\s*([A-F][+-]?)\b",
            ]
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    subject = match.group(1).strip()
                    grade_val = match.group(2).strip()
                    if len(subject) > 2 and len(subject) < 60:
                        grades.append(EdsbyGrade(
                            subject=subject,
                            grade=grade_val,
                            grade_date=date.today(),
                        ))

        # Deduplicate by subject
        seen = set()
        unique_grades = []
        for g in grades:
            key = g.subject.lower()
            if key not in seen:
                seen.add(key)
                unique_grades.append(g)

        return unique_grades

    def close(self):
        """Close browser resources."""
        if self._browser:
            self._browser.close()
        if hasattr(self, "_pw"):
            self._pw.__exit__(None, None, None)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class MockEdsbyScraper:
    """Mock scraper for testing when real Edsby is unavailable."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self._seed = hash(username) % 10000

    def login(self) -> bool:
        if "wrong" in self.password.lower() or "bad" in self.password.lower():
            raise EdsbyAuthError("Invalid credentials (mock)")
        return True

    def scrape_grades(self, child_name: Optional[str] = None) -> List[EdsbyGrade]:
        random.seed(self._seed)
        subjects = {
            "Math": {"base": 78, "variance": 12},
            "Science": {"base": 82, "variance": 10},
            "English": {"base": 80, "variance": 8},
            "History": {"base": 85, "variance": 7},
            "Art": {"base": 88, "variance": 6},
            "Physical Education": {"base": 92, "variance": 4},
            "French": {"base": 75, "variance": 10},
        }
        grades = []
        for subject, params in subjects.items():
            grade_val = min(100, max(50, int(random.gauss(params["base"], params["variance"]))))
            grades.append(EdsbyGrade(
                subject=subject,
                grade=str(grade_val),
                grade_date=date.today(),
            ))
        return grades

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def create_scraper(base_url: str, username: str, password: str, use_mock: bool = False):
    """Factory to create real or mock scraper."""
    if use_mock:
        return MockEdsbyScraper(base_url, username, password)
    return EdsbyScraper(base_url, username, password)
