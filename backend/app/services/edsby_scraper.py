"""Edsby grade scraper using Playwright async API.

Supports two login paths:
1. Office365 SSO (used by NNDSB and many Ontario school boards):
   - Start at /p/BasePublic/
   - Click Office365 link
   - Microsoft login -> ADFS -> Edsby parent home
2. Direct /core/login with JS-encrypted password (fallback for non-SSO schools)

Multi-child support:
- Parent home page shows child selector cards (e.g. "RT\nRowen Larry Toshack")
- Clicking a child navigates to /p/BaseParentChild/{nid}
- Classes section on child page contains current grades
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
    nid: str  # Edsby's internal node ID (extracted from URL)
    grades: List[EdsbyGrade] = field(default_factory=list)


class EdsbyAuthError(Exception):
    pass


class EdsbyUnavailableError(Exception):
    pass


class EdsbyScraper:
    """Edsby scraper with async Playwright + NNDSB Office365 SSO support."""

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._page = None
        self._browser = None
        self._context = None
        self._pw = None
        self._parent_url = None

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

        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self._page = await self._context.new_page()

    async def _try_o365_login(self) -> bool:
        """Try Office365 SSO login flow (NNDSB-style)."""
        import asyncio
        page = self._page

        try:
            await page.goto(f"{self.base_url}/p/BasePublic/", wait_until="networkidle", timeout=20000)
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot reach Edsby public page: {e}")

        await asyncio.sleep(2)

        # Check if there's an Office365 SSO link
        o365_link = await page.query_selector("a[href*='office365']")
        if not o365_link:
            return False  # Fall back to direct login

        await o365_link.click()

        try:
            await page.wait_for_url("**login.microsoftonline.com**", timeout=15000)
        except Exception:
            return False

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)

        # Microsoft email page
        email_field = await page.query_selector("input[name='loginfmt'], input[type='email']")
        if not email_field:
            raise EdsbyUnavailableError("Microsoft login email field not found")
        await email_field.fill(self.username)

        next_btn = await page.query_selector("#idSIButton9, input[type='submit']")
        if next_btn:
            await next_btn.click()
        else:
            await email_field.press("Enter")

        await asyncio.sleep(4)

        # Could be ADFS or Microsoft password page
        pwd_field = await page.query_selector("input[name='Password'], input[type='password'], #passwordInput")
        if pwd_field:
            await pwd_field.fill(self.password)
            submit_btn = await page.query_selector("#submitButton, #idSIButton9, input[type='submit']")
            if submit_btn:
                await submit_btn.click()
            else:
                await pwd_field.press("Enter")
        else:
            # Microsoft password page
            pwd_field = await page.query_selector("input[name='passwd'], input[type='password']")
            if not pwd_field:
                raise EdsbyUnavailableError("Password field not found on login page")
            await pwd_field.fill(self.password)
            submit_btn = await page.query_selector("#idSIButton9, input[type='submit']")
            if submit_btn:
                await submit_btn.click()
            else:
                await pwd_field.press("Enter")

        await asyncio.sleep(5)

        # Wait for redirect back to Edsby
        for i in range(15):
            await asyncio.sleep(2)
            url = page.url.lower()
            if self.base_url.lower() in url and "login" not in url and "microsoft" not in url and "adfs" not in url:
                break

        if "/login" in page.url.lower() or "microsoft" in page.url.lower() or "adfs" in page.url.lower():
            body_text = await page.inner_text("body")
            if "bad" in body_text.lower() or "incorrect" in body_text.lower():
                raise EdsbyAuthError("Invalid Edsby username or password")
            elif "disabled" in body_text.lower() or "locked" in body_text.lower():
                raise EdsbyAuthError("Edsby account temporarily disabled due to too many failed attempts")
            return False

        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        self._parent_url = page.url
        return True

    async def _try_direct_login(self) -> bool:
        """Fallback: direct /core/login with JS-encrypted password."""
        import asyncio
        page = self._page

        try:
            await page.goto(f"{self.base_url}/core/login", wait_until="networkidle", timeout=20000)
        except Exception as e:
            raise EdsbyUnavailableError(f"Cannot reach Edsby login page: {e}")

        if "/login" not in page.url:
            return True

        await page.fill("input[name='userid']", self.username)
        await page.fill("input[name='password']", self.password)

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

        await asyncio.sleep(3)
        current_url = page.url
        body_text = await page.inner_text("body")

        if "/login" in current_url.lower():
            if "bad" in body_text.lower() or "incorrect" in body_text.lower():
                raise EdsbyAuthError("Invalid Edsby username or password")
            elif "disabled" in body_text.lower() or "locked" in body_text.lower():
                raise EdsbyAuthError("Edsby account temporarily disabled due to too many failed attempts")
            else:
                raise EdsbyAuthError(f"Edsby login failed. Page: {current_url}")

        self._parent_url = page.url
        return True

    async def login(self) -> bool:
        """Log into Edsby. Tries Office365 SSO first, then falls back to direct login."""
        await self._init_playwright()

        try:
            if await self._try_o365_login():
                return True
        except EdsbyAuthError:
            raise
        except Exception as e:
            # If O365 fails for technical reasons, try direct login
            pass

        return await self._try_direct_login()

    async def discover_children(self) -> List[EdsbyChild]:
        """Discover all children linked to this parent account."""
        import asyncio
        if not self._page:
            await self.login()

        page = self._page
        children: List[EdsbyChild] = []
        seen_names = set()

        # Strategy 1: Look for role=link elements with child initials + name pattern
        link_els = await page.query_selector_all("[role='link']")
        child_names = []
        for el in link_els:
            text = (await el.inner_text()).strip()
            if "\n" in text:
                parts = text.split("\n")
                if len(parts) >= 2:
                    initials = parts[0].strip()
                    name = parts[1].strip()
                    if re.match(r"^[A-Z]{2,4}$", initials) and len(name.split()) >= 2:
                        if name in seen_names:
                            continue
                        if "Settings" in name or "Messages" in name or "Calendar" in name:
                            continue
                        if name == "Chris Toshack":
                            continue
                        # Likely a child
                        seen_names.add(name)
                        child_names.append(name)

        # Strategy 2: Regex body text for "XX\nFirst Last" patterns
        if not child_names:
            body_text = await page.inner_text("body")
            pattern = r"([A-Z]{2,4})\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
            matches = re.findall(pattern, body_text)
            for initials, name in matches:
                if name in seen_names:
                    continue
                if "Settings" in name or "Messages" in name or "Calendar" in name or "Chris Toshack" in name:
                    continue
                seen_names.add(name)
                child_names.append(name)

        # For each child name, click to get their nid, then go back
        for name in child_names:
            nid = ""
            try:
                # Re-query the element each time since page may have navigated
                await page.goto(self._parent_url or self.base_url, wait_until="networkidle")
                await asyncio.sleep(3)

                el = await page.wait_for_selector(f"text={name}", timeout=5000)
                if el:
                    await el.click()
                    await asyncio.sleep(4)
                    child_url = page.url
                    match = re.search(r'/BaseParentChild/(\d+)', child_url)
                    if match:
                        nid = match.group(1)
            except Exception:
                pass

            children.append(EdsbyChild(name=name, nid=nid))

        # Return to parent page
        if self._parent_url:
            try:
                await page.goto(self._parent_url, wait_until="networkidle")
                await asyncio.sleep(2)
            except Exception:
                pass

        return children

    async def _navigate_to_child(self, child: EdsbyChild) -> bool:
        """Navigate to a specific child's page."""
        import asyncio
        page = self._page

        # If we have a nid, go directly
        if child.nid:
            try:
                await page.goto(f"{self.base_url}/p/BaseParentChild/{child.nid}", wait_until="networkidle")
                await asyncio.sleep(3)
                return True
            except Exception:
                pass

        # Otherwise try clicking by name
        try:
            el = await page.wait_for_selector(f"text={child.name}", timeout=5000)
            if el:
                await el.click()
                await asyncio.sleep(4)
                return True
        except Exception:
            pass

        return False

    async def scrape_child_grades(self, child: EdsbyChild) -> List[EdsbyGrade]:
        """Scrape grades for a specific child from their Edsby page."""
        import asyncio
        from bs4 import BeautifulSoup

        page = self._page
        grades: List[EdsbyGrade] = []

        if not await self._navigate_to_child(child):
            return grades

        # Wait for content to settle
        await asyncio.sleep(2)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        text = soup.get_text("\n")
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        in_classes = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if line == "Classes":
                in_classes = True
                i += 1
                continue
            if in_classes and line in ["Recent Activity", "Schedule Absence", "Portfolio", "Learning Story", "View Report Cards", "Overall"]:
                in_classes = False
            if in_classes:
                # Find percentage grades in the next few lines
                if re.match(r"^\d+(\.\d+)?%$", line):
                    grade = line.replace("%", "")
                    subject = None
                    course_code = None

                    # Look backwards up to 4 lines
                    for back in range(1, min(5, i)):
                        candidate = lines[i - back]
                        # Course code: all uppercase alphanumeric starting with letter
                        if re.match(r"^[A-Z][A-Z0-9]{2,}$", candidate):
                            course_code = candidate
                        # Subject: starts with capital letter, has words/spaces/hyphens/ampersands
                        elif re.match(r"^[A-Z][a-zA-Z\s\-&]{2,}$", candidate) and not re.match(r"^[A-Z]+$", candidate):
                            if not subject:
                                subject = candidate

                    if subject:
                        grades.append(EdsbyGrade(
                            subject=subject,
                            grade=grade,
                            grade_date=date.today(),
                            category=course_code,
                        ))
                    i += 1
                else:
                    i += 1
            else:
                i += 1

        # Deduplicate by subject
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
        import asyncio
        children = await self.discover_children()
        for child in children:
            child.grades = await self.scrape_child_grades(child)
            # Go back to parent page for next child
            if self._parent_url:
                await self._page.goto(self._parent_url, wait_until="networkidle")
                await asyncio.sleep(3)
        return children

    async def scrape_grades(self, child_name: Optional[str] = None) -> List[EdsbyGrade]:
        """Scrape grades. If child_name specified, return only that child's grades."""
        children = await self.scrape_all_children_grades()

        if child_name and children:
            child_name_lower = child_name.lower()
            for child in children:
                if child_name_lower in child.name.lower():
                    return child.grades
            return children[0].grades if children else []

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
