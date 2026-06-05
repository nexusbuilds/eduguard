"""Edsby grade scraper using Playwright async API with JS-encrypted login.

Edsby uses client-side HMAC-SHA-512 password encryption via JavaScript.
This module uses Playwright (headless browser) to handle the encryption natively.

Multi-child support:
- After login, Edsby parent portal shows child selector cards
- Each child has their own classes, grades, and assignments
- The scraper discovers all children, then navigates to each child's gradebook
"""
import re
import random
import shutil
from datetime import datetime, date
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class EdsbyGrade:
    subject: str
    grade: str
    grade_date: Optional[date]
    teacher: Optional[str] = None
    category: Optional[str] = None


@dataclass
class EdsbyChild:
    """Represents a student/child found in the parent's Edsby account."""
    name: str
    nid: str  # Edsby's internal node ID
    grades: List[EdsbyGrade] = field(default_factory=list)


class EdsbyAuthError(Exception):
    pass


class EdsbyUnavailableError(Exception):
    pass


class EdsbyScraper:
    """Edsby scraper with async Playwright for JS-encrypted login + multi-child support."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._page = None
        self._browser = None
        self._context = None
        self._pw = None

    async def _init_playwright(self):
        """Initialize Playwright browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise EdsbyUnavailableError("Playwright not installed. Run: pip install playwright")

        self._pw = await async_playwright().start()
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
                self._browser = await self._pw.chromium.launch(
                    headless=True,
                    executable_path=exe_path,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            else:
                self._browser = await self._pw.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot launch browser: {e}")

        self._context = await self._browser.new_context(viewport={"width": 1280, "height": 800})
        self._page = await self._context.new_page()

    async def login(self) -> bool:
        """Log into Edsby using Playwright to handle JS encryption."""
        await self._init_playwright()
        page = self._page

        try:
            await page.goto(f"{self.base_url}/core/login", wait_until="networkidle")
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot reach Edsby login page: {e}")

        if "/login" not in page.url:
            return True

        await page.fill("input[name='userid']", self.username)
        await page.fill("input[name='password']", self.password)

        # Trigger JS encryption and enable disabled fields
        await page.evaluate("""() => {
            const form = document.querySelector('form');
            if (typeof doPasswordEncrypt === 'function') {
                doPasswordEncrypt(form);
            }
            ['sauthdata', 'cauthdata', 'extpassword'].forEach(n => {
                const el = form.querySelector("input[name=" + n + "]");
                if (el) el.disabled = false;
            });
        }""")

        try:
            await page.click("input[type='submit']")
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            raise EdsbyUnavailableError(f"Login submission failed: {e}")

        current_url = page.url
        body_text = await page.inner_text("body")

        if "/login" in current_url.lower():
            if "bad" in body_text.lower() or "incorrect" in body_text.lower():
                raise EdsbyAuthError("Invalid Edsby username or password")
            elif "disabled" in body_text.lower() or "locked" in body_text.lower():
                raise EdsbyAuthError("Edsby account temporarily disabled due to too many failed attempts")
            else:
                raise EdsbyAuthError(f"Edsby login failed. Page: {current_url}")

        return True

    async def discover_children(self) -> List[EdsbyChild]:
        """Discover all children linked to this parent account."""
        if not self._page:
            await self.login()

        page = self._page
        children: List[EdsbyChild] = []

        # Strategy 1: Look for student/child cards on home page with data-nid
        nids = await page.evaluate("""() => {
            const cards = document.querySelectorAll('[data-nid]');
            return Array.from(cards).map(el => ({
                nid: el.getAttribute('data-nid'),
                text: el.innerText.trim().substring(0, 100),
            })).filter(x => x.nid && x.nid.length > 5);
        }""")

        for item in nids:
            text = item['text']
            nid = item['nid']
            # Filter out non-student items (look for names, not generic UI elements)
            if text and len(text) > 1 and not any(bad in text.lower() for bad in ['login', 'password', 'submit', 'cancel', 'edsby']):
                children.append(EdsbyChild(name=text, nid=nid))

        # Strategy 2: Look for links to student profiles
        if not children:
            links = await page.query_selector_all("a")
            for link in links:
                href = await link.get_attribute("href") or ""
                text = (await link.inner_text()).strip()
                # Edsby student links typically contain /p/ or /node/ with student IDs
                if "/p/" in href or "/node/" in href or "student" in href.lower():
                    if len(text) > 1 and len(text) < 60 and text not in [c.name for c in children]:
                        # Extract nid from href if possible
                        nid_match = re.search(r'/(\d+)$', href) or re.search(r'nid=(\d+)', href)
                        nid = nid_match.group(1) if nid_match else href
                        children.append(EdsbyChild(name=text, nid=nid))

        # Strategy 3: Look for panel/class cards with student photos/names
        if not children:
            cards = await page.query_selector_all(".card, .panel, .tile, [class*='student'], [class*='child']")
            for card in cards:
                text = (await card.inner_text()).strip()
                if len(text) > 1 and len(text) < 60:
                    nid = await card.get_attribute("data-nid") or await card.get_attribute("onclick") or ""
                    children.append(EdsbyChild(name=text, nid=nid))

        return children

    async def _navigate_to_child_grades(self, child: EdsbyChild) -> bool:
        """Navigate to a specific child's gradebook page."""
        page = self._page

        # Strategy 1: Click the child's card/link by data-nid
        if child.nid:
            clicked = await page.evaluate(f"""(nid) => {{
                const el = document.querySelector(`[data-nid="${{nid}}"]`);
                if (el) {{ el.click(); return true; }}
                return false;
            }}""", child.nid)
            if clicked:
                await page.wait_for_load_state("networkidle")
                return True

        # Strategy 2: Look for a grades/report card link after clicking child
        links = await page.query_selector_all("a")
        for link in links:
            text = (await link.inner_text()).strip().lower()
            href = await link.get_attribute("href") or ""
            if any(w in text for w in ["grade", "report card", "progress", "mark", "transcript"]):
                try:
                    await link.click()
                    await page.wait_for_load_state("networkidle")
                    return True
                except Exception:
                    continue

        # Strategy 3: Direct URL construction
        grade_urls = [
            f"{self.base_url}/core/node/{child.nid}",
            f"{self.base_url}/core/p/{child.nid}",
            f"{self.base_url}/core/grades?student={child.nid}",
        ]
        for url in grade_urls:
            try:
                await page.goto(url, wait_until="networkidle")
                return True
            except Exception:
                continue

        return False

    async def scrape_child_grades(self, child: EdsbyChild) -> List[EdsbyGrade]:
        """Scrape grades for a specific child."""
        page = self._page
        grades: List[EdsbyGrade] = []

        # Navigate to child's grades
        if not await self._navigate_to_child_grades(child):
            return grades

        content = await page.content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(content, "html.parser")

        # Edsby gradebook structures vary. Try multiple extraction strategies:

        # Strategy A: Look for table rows with subject + grade
        for row in soup.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            subject = None
            grade_val = None
            for cell in cells:
                text = cell.get_text(strip=True)
                # Grade patterns
                if re.match(r"^\d{1,3}\s*%$", text) or re.match(r"^\d{1,3}$", text):
                    grade_val = text.replace("%", "").strip()
                elif re.match(r"^[A-F][+-]?$", text):
                    grade_val = text
                elif len(text) > 2 and len(text) < 60 and not text.replace(".", "").replace("-", "").isdigit():
                    if not subject:
                        subject = text

            if subject and grade_val:
                grades.append(EdsbyGrade(
                    subject=subject,
                    grade=grade_val,
                    grade_date=date.today(),
                ))

        # Strategy B: Look for div cards with class names and grades
        if not grades:
            for div in soup.find_all("div"):
                text = div.get_text(strip=True)
                # Look for patterns like "Math\n85%" within a single div
                match = re.search(r"([A-Za-z][A-Za-z\s]{2,40})\s*[:\-]?\s*(\d{1,3})\s*%", text)
                if match:
                    grades.append(EdsbyGrade(
                        subject=match.group(1).strip(),
                        grade=match.group(2).strip(),
                        grade_date=date.today(),
                    ))

        # Strategy C: Regex on full page text
        if not grades:
            text = soup.get_text()
            patterns = [
                r"([A-Za-z][A-Za-z\s]{2,30})\s*[:\-]?\s*(\d{1,3})\s*%",
                r"([A-Za-z][A-Za-z\s]{2,30})\s*[:\-]?\s*([A-F][+-]?)\b",
            ]
            seen = set()
            for pattern in patterns:
                for match in re.finditer(pattern, text):
                    subject = match.group(1).strip()
                    grade_val = match.group(2).strip()
                    key = subject.lower()
                    if key not in seen and len(subject) > 2 and len(subject) < 50:
                        seen.add(key)
                        grades.append(EdsbyGrade(
                            subject=subject,
                            grade=grade_val,
                            grade_date=date.today(),
                        ))

        # Deduplicate
        seen = set()
        unique = []
        for g in grades:
            key = g.subject.lower()
            if key not in seen:
                seen.add(key)
                unique.append(g)

        return unique

    async def scrape_all_children_grades(self) -> List[EdsbyChild]:
        """Discover all children and scrape grades for each."""
        children = await self.discover_children()
        for child in children:
            child.grades = await self.scrape_child_grades(child)
            # Go back to home page for next child
            await self._page.goto(self.base_url, wait_until="networkidle")
        return children

    async def scrape_grades(self, child_name: Optional[str] = None) -> List[EdsbyGrade]:
        """Scrape grades. If child_name specified, return only that child's grades."""
        children = await self.scrape_all_children_grades()

        if child_name and children:
            # Find matching child
            child_name_lower = child_name.lower()
            for child in children:
                if child_name_lower in child.name.lower():
                    return child.grades
            # If no exact match, return first child's grades with a warning
            return children[0].grades if children else []

        # Return all grades flattened
        all_grades = []
        for child in children:
            all_grades.extend(child.grades)
        return all_grades

    async def close(self):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class MockEdsbyScraper:
    """Mock scraper for testing when real Edsby is unavailable."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self._seed = hash(username) % 10000

    async def login(self) -> bool:
        if "wrong" in self.password.lower() or "bad" in self.password.lower():
            raise EdsbyAuthError("Invalid credentials (mock)")
        return True

    async def discover_children(self) -> List[EdsbyChild]:
        return [
            EdsbyChild(name="Rowen Toshack", nid="mock_rowen", grades=[]),
            EdsbyChild(name="Alex Toshack", nid="mock_alex", grades=[]),
        ]

    async def scrape_child_grades(self, child: EdsbyChild) -> List[EdsbyGrade]:
        random.seed(self._seed + hash(child.name))
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

    async def scrape_all_children_grades(self) -> List[EdsbyChild]:
        children = await self.discover_children()
        for child in children:
            child.grades = await self.scrape_child_grades(child)
        return children

    async def scrape_grades(self, child_name: Optional[str] = None) -> List[EdsbyGrade]:
        children = await self.scrape_all_children_grades()
        if child_name:
            for child in children:
                if child_name.lower() in child.name.lower():
                    return child.grades
        return [g for c in children for g in c.grades]

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def create_scraper(base_url: str, username: str, password: str, use_mock: bool = False):
    """Factory to create real or mock scraper."""
    if use_mock:
        return MockEdsbyScraper(base_url, username, password)
    return EdsbyScraper(base_url, username, password)
