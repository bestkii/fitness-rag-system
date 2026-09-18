from __future__ import annotations

import os
import re
import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin, urlparse, urlunparse

from .config import XHS_DB_PATH, XHS_PROFILE_DIR


XHS_ORIGIN = "https://www.xiaohongshu.com"
XHS_EXPLORE_URL = f"{XHS_ORIGIN}/explore"
CHALLENGE_PHRASES = (
    "安全验证",
    "访问频繁",
    "网络环境存在风险",
    "操作频繁",
    "滑块验证",
    "请输入验证码",
)
FITNESS_TOPIC_TERMS = (
    "健身",
    "训练",
    "运动",
    "跑步",
    "夜跑",
    "游泳",
    "网球",
    "瑜伽",
    "普拉提",
    "力量",
    "有氧",
    "减脂",
    "增肌",
    "肌肉",
    "深蹲",
    "硬拉",
    "心率",
)


class XiaohongshuCollectorError(RuntimeError):
    """Base error for the conservative browser collector."""


class XiaohongshuLoginRequired(XiaohongshuCollectorError):
    """Raised when the website asks the user to log in again."""


class XiaohongshuChallengeDetected(XiaohongshuCollectorError):
    """Raised when collection must stop for a verification or risk-control page."""


@dataclass(frozen=True)
class XiaohongshuNote:
    keyword: str
    note_id: str
    title: str
    url: str
    author: str | None
    visible_text: str
    like_count: int | None
    collected_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_note_url(value: str) -> str | None:
    absolute = urljoin(XHS_ORIGIN, value.strip())
    parsed = urlparse(absolute)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or hostname not in {
        "xiaohongshu.com",
        "www.xiaohongshu.com",
    }:
        return None
    match = re.match(r"^/(?:explore|discovery/item)/([A-Za-z0-9]+)", parsed.path)
    if not match:
        return None
    clean_path = f"/explore/{match.group(1)}"
    return urlunparse(("https", "www.xiaohongshu.com", clean_path, "", "", ""))


def parse_visible_count(value: str | None) -> int | None:
    if not value:
        return None
    compact = value.strip().casefold().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([万亿km]?)\+?", compact)
    if not match:
        return None
    multiplier = {"": 1, "万": 10_000, "亿": 100_000_000, "k": 1_000, "m": 1_000_000}
    return int(float(match.group(1)) * multiplier[match.group(2)])


def _compact(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _note_from_raw(keyword: str, item: dict[str, Any], collected_at: str) -> XiaohongshuNote | None:
    url = normalize_note_url(str(item.get("url", "")))
    if not url:
        return None
    note_id = url.rsplit("/", 1)[-1]
    visible_text = _compact(str(item.get("visible_text", "")), 1200)
    title = _compact(str(item.get("title", "")), 160)
    if not title and visible_text:
        title = visible_text.splitlines()[0][:160]
    if not title:
        return None
    author = _compact(str(item.get("author", "")), 80)
    author = re.sub(r"\s+\d+(?:\.\d+)?\s*[万亿kKmM]?\+?$", "", author).strip() or None
    return XiaohongshuNote(
        keyword=_compact(keyword, 100),
        note_id=note_id,
        title=title,
        url=url,
        author=author,
        visible_text=visible_text,
        like_count=parse_visible_count(str(item.get("like_text", ""))),
        collected_at=collected_at,
    )


def normalize_notes(keyword: str, raw_items: list[dict[str, Any]]) -> list[XiaohongshuNote]:
    collected_at = datetime.now(timezone.utc).isoformat()
    notes: list[XiaohongshuNote] = []
    seen_urls: set[str] = set()
    for item in raw_items:
        note = _note_from_raw(keyword, item, collected_at)
        if note is None or note.url in seen_urls:
            continue
        seen_urls.add(note.url)
        notes.append(note)
    return notes


class XiaohongshuTopicStore:
    def __init__(self, path: Path = XHS_DB_PATH):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS xhs_notes (
                keyword TEXT NOT NULL,
                note_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                author TEXT,
                visible_text TEXT NOT NULL,
                like_count INTEGER,
                collected_at TEXT NOT NULL,
                PRIMARY KEY (keyword, note_id)
            )
            """
        )
        return connection

    def save(self, notes: list[XiaohongshuNote]) -> int:
        if not notes:
            return 0
        with closing(self._connect()) as connection:
            connection.executemany(
                """
                INSERT INTO xhs_notes (
                    keyword, note_id, title, url, author, visible_text,
                    like_count, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(keyword, note_id) DO UPDATE SET
                    title = excluded.title,
                    url = excluded.url,
                    author = excluded.author,
                    visible_text = excluded.visible_text,
                    like_count = excluded.like_count,
                    collected_at = excluded.collected_at
                """,
                [
                    (
                        note.keyword,
                        note.note_id,
                        note.title,
                        note.url,
                        note.author,
                        note.visible_text,
                        note.like_count,
                        note.collected_at,
                    )
                    for note in notes
                ],
            )
            connection.commit()
        return len(notes)

    def list(self, keyword: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 100))
        with closing(self._connect()) as connection:
            if keyword:
                rows = connection.execute(
                    """
                    SELECT * FROM xhs_notes
                    WHERE keyword = ?
                    ORDER BY like_count IS NULL, like_count DESC, collected_at DESC
                    LIMIT ?
                    """,
                    (_compact(keyword, 100), safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM xhs_notes
                    ORDER BY collected_at DESC, like_count IS NULL, like_count DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [dict(row) for row in rows]


class XiaohongshuCollector:
    """Visible, low-volume DOM collector for public search-result cards."""

    def __init__(
        self,
        profile_dir: Path = XHS_PROFILE_DIR,
        browser_channel: str | None = None,
    ):
        self.profile_dir = profile_dir
        self.browser_channel = browser_channel or os.environ.get(
            "XHS_BROWSER_CHANNEL", "chrome"
        )

    @staticmethod
    def _playwright():
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise XiaohongshuCollectorError(
                "Playwright is not installed. Run: pip install -r requirements.txt"
            ) from exc
        return sync_playwright

    def launch_context(self, playwright: Any, *, headless: bool = False):
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        try:
            return playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                channel=self.browser_channel,
                headless=headless,
                locale="zh-CN",
                viewport={"width": 1360, "height": 900},
            )
        except Exception as exc:
            raise XiaohongshuCollectorError(
                f"Could not launch browser channel '{self.browser_channel}'."
            ) from exc

    @staticmethod
    def _page_text(page: Any) -> str:
        try:
            return page.locator("body").inner_text(timeout=5_000)
        except Exception:
            return ""

    @classmethod
    def _guard_page(cls, page: Any) -> None:
        body = cls._page_text(page)
        if any(phrase in body for phrase in CHALLENGE_PHRASES):
            raise XiaohongshuChallengeDetected(
                "Xiaohongshu requested verification or reported frequent access; collection stopped."
            )
        note_links = page.locator('a[href*="/explore/"], a[href*="/discovery/item/"]').count()
        if "扫码登录" in body and note_links == 0:
            raise XiaohongshuLoginRequired(
                "Xiaohongshu login is required. Run the login helper and scan the QR code yourself."
            )

    @staticmethod
    def _extract_visible_cards(page: Any) -> list[dict[str, Any]]:
        return page.eval_on_selector_all(
            'a[href*="/explore/"], a[href*="/discovery/item/"]',
            r"""
            (anchors) => anchors.map((anchor) => {
              let container = anchor.closest('section, article, li, .note-item');
              if (!container) {
                container = anchor.parentElement;
                for (let depth = 0; depth < 4 && container?.parentElement; depth += 1) {
                  const text = (container.innerText || '').trim();
                  if (text.length >= 12 && text.length <= 1200) break;
                  container = container.parentElement;
                }
              }
              const visibleText = (container?.innerText || anchor.innerText || '')
                .replace(/\s+/g, ' ').trim();
              const titleNode = container?.querySelector(
                '[class*="title"], [class*="desc"], [class*="content"]'
              );
              const authorNode = container?.querySelector(
                '[class*="author"] [class*="name"], [class*="author"], [class*="user"] [class*="name"]'
              );
              const likeNode = container?.querySelector(
                '[class*="like"] [class*="count"], [class*="like-count"], [class*="count"]'
              );
              const fallbackTitle = visibleText.split(' ').slice(0, 18).join(' ');
              return {
                url: anchor.href,
                title: (anchor.getAttribute('title') || titleNode?.innerText || fallbackTitle || '').trim(),
                author: (authorNode?.innerText || '').trim(),
                like_text: (likeNode?.innerText || '').trim(),
                visible_text: visibleText,
              };
            })
            """,
        )

    @staticmethod
    def _navigate_without_network_idle(page: Any, url: str) -> None:
        page.evaluate("(target) => { window.location.href = target; }", url)
        for _ in range(20):
            page.wait_for_timeout(500)
            if page.url.startswith(url.split("?", 1)[0]):
                return
        raise XiaohongshuCollectorError("Xiaohongshu page navigation did not complete.")

    def collect_home_fitness(
        self,
        *,
        limit: int = 20,
        max_scrolls: int = 5,
        headless: bool = False,
    ) -> list[XiaohongshuNote]:
        """Collect fitness-related cards from the public personalized home feed."""

        safe_limit = max(1, min(limit, 30))
        safe_scrolls = max(0, min(max_scrolls, 5))
        sync_playwright = self._playwright()
        with sync_playwright() as playwright:
            context = self.launch_context(playwright, headless=headless)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                self._navigate_without_network_idle(page, XHS_EXPLORE_URL)
                page.wait_for_timeout(8_000)
                self._guard_page(page)
                raw: list[dict[str, Any]] = []
                for scroll_index in range(safe_scrolls + 1):
                    raw.extend(self._extract_visible_cards(page))
                    notes = normalize_notes("首页健身筛选", raw)
                    matches = [
                        note
                        for note in notes
                        if any(
                            term in f"{note.title} {note.visible_text}"
                            for term in FITNESS_TOPIC_TERMS
                        )
                    ]
                    if len(matches) >= safe_limit or scroll_index == safe_scrolls:
                        return matches[:safe_limit]
                    page.mouse.wheel(0, 1_100)
                    page.wait_for_timeout(1_500)
                    self._guard_page(page)
                return []
            finally:
                context.close()

    def collect(
        self,
        keyword: str,
        *,
        limit: int = 20,
        max_scrolls: int = 3,
        headless: bool = False,
    ) -> list[XiaohongshuNote]:
        keyword = _compact(keyword, 100)
        if len(keyword) < 2:
            raise ValueError("Keyword must contain at least two characters.")
        safe_limit = max(1, min(limit, 30))
        safe_scrolls = max(0, min(max_scrolls, 5))
        search_url = (
            f"{XHS_ORIGIN}/search_result?keyword={quote(keyword)}"
            "&source=web_search_result_notes"
        )
        sync_playwright = self._playwright()
        with sync_playwright() as playwright:
            context = self.launch_context(playwright, headless=headless)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                self._navigate_without_network_idle(page, search_url)
                page.wait_for_timeout(2_000)
                self._guard_page(page)
                raw: list[dict[str, Any]] = []
                for scroll_index in range(safe_scrolls + 1):
                    raw.extend(self._extract_visible_cards(page))
                    notes = normalize_notes(keyword, raw)
                    if len(notes) >= safe_limit or scroll_index == safe_scrolls:
                        return notes[:safe_limit]
                    page.mouse.wheel(0, 900)
                    page.wait_for_timeout(1_500)
                    self._guard_page(page)
                return normalize_notes(keyword, raw)[:safe_limit]
            finally:
                context.close()


def open_login_session() -> None:
    collector = XiaohongshuCollector()
    sync_playwright = collector._playwright()
    with sync_playwright() as playwright:
        context = collector.launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(XHS_EXPLORE_URL, wait_until="domcontentloaded", timeout=30_000)
            print("请在打开的浏览器里自行完成小红书登录。完成后回到这里按 Enter 保存会话。")
            input()
        finally:
            context.close()
