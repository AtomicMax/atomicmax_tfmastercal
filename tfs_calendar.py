#!/usr/bin/env python3
"""Generate a Google-safe ICS feed from the TFS master calendar.

Includes school-wide events, breaks, holidays, special events, athletics that
are not Middle/Lower School only, and Tallulah Together. Excludes events that
are Middle School or Lower School only.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from zoneinfo import ZoneInfo

import re
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event, vText

EASTERN = ZoneInfo("America/New_York")
UTC = timezone.utc

CALENDAR_PAGE = "https://www.tallulahfalls.org/about/calendars"
CALENDAR_ELEMENT_URL = "https://www.tallulahfalls.org/fs/elements/3846"
CALENDAR_ELEMENT_ID = 3846
PAGE_ID = 518
ATHLETICS_URL = "https://tfsathletics.com/composite"
SMORE_URLS = [
    "https://app.smore.com/n/cfta4",
]

YEAR_START = date(2026, 8, 1)
YEAR_END = date(2027, 6, 15)
# First Monday of classes is an A week: ABABA, then BABAB, repeating.
AB_PATTERN_START = date(2026, 8, 10)
AB_PATTERN_END = date(2027, 5, 21)
# Newsletter confirmation: Monday, September 21, 2026 is an A Day / A week.
AB_KNOWN_A_MONDAY = date(2026, 9, 21)

OUTPUT_BASENAME = "atomicmax_tfmastercal"
FEED_NAME = "TFS Master Calendar"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)

OCCUR_RE = re.compile(
    r"(?P<id>\d+)_(?P<start>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
    r"_(?P<end>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)"
)

# Events matching these are treated as Middle/Lower School only,
# unless a school-wide override also appears in the title.
MS_LS_ONLY = [
    r"\blower school\b",
    r"\bmiddle school\b",
    r"\bls/ms\b",
    r"\bms/ls\b",
    r"\blower/middle\b",
    r"\bmiddle/lower\b",
    r"\bls\b",
    r"\bms\b",
    r"\b4th grade\b",
    r"\b5th grade\b",
    r"\b6th grade\b",
    r"\b7th grade\b",
    r"\b8th grade\b",
    r"\bfourth grade\b",
    r"\bfifth grade\b",
    r"\bsixth grade\b",
    r"\bseventh grade\b",
    r"\beighth grade\b",
    r"\b[4-8]th(?:\s*(?:,|&|and|/)\s*[4-8]th)+\s+grades?\b",
]

# If present, keep the event even when an MS/LS token also appears.
SCHOOLWIDE_OVERRIDE = [
    r"tallulah together",
    r"\ball school\b",
    r"\ball-school\b",
    r"\bwhole school\b",
    r"\bupper school\b",
    r"\bgrades 4-12\b",
    r"\b4-12\b",
]

NOISE_PREFIXES = (
    "about ",
    "read more",
    "load more",
    "monthly calendar",
    "calendar rss",
    "event search",
)

BIRTHDAY_RE = re.compile(r"\b(birthdays?|happy birthday|b-?day)\b", re.I)
SCHOLARSHIP_RE = re.compile(r"\bscholarships?\b", re.I)
MONTH_NAME = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def is_noise(title: str) -> bool:
    lowered = title.lower().strip()
    if not lowered or len(lowered) < 3:
        return True
    return any(lowered.startswith(prefix) for prefix in NOISE_PREFIXES)


GRADE_4_TO_8_RE = re.compile(
    r"\b(?:4th|5th|6th|7th|8th|fourth|fifth|sixth|seventh|eighth)\s+grade[ds]?\b"
    r"|\b[4-8]th(?:\s*(?:,|&|and|/)\s*[4-8]th)+\s+grades?\b",
    re.I,
)


def is_ms_or_ls_only(title: str) -> bool:
    """Return True when the event is Middle School or Lower School only."""
    lowered = title.lower()
    hard_keep = any(
        re.search(pattern, lowered)
        for pattern in (
            r"tallulah together",
            r"\ball school\b",
            r"\ball-school\b",
            r"\bwhole school\b",
            r"\bgrades 4-12\b",
            r"\b4-12\b",
            r"\b4th\s*[-–]\s*12th\b",
        )
    )
    # "8th Grade to Upper School" is still an 8th-grade event.
    if GRADE_4_TO_8_RE.search(title) and not hard_keep:
        return True
    if any(re.search(pattern, lowered) for pattern in SCHOOLWIDE_OVERRIDE):
        return False
    return any(re.search(pattern, lowered) for pattern in MS_LS_ONLY)


def keep_event(title: str) -> bool:
    if is_noise(title):
        return False
    if BIRTHDAY_RE.search(title):
        return False
    if SCHOLARSHIP_RE.search(title):
        return False
    if is_ms_or_ls_only(title):
        return False
    return True


def parse_occur_id(occur_id: str | None):
    if not occur_id:
        return None, None
    match = OCCUR_RE.search(occur_id)
    if not match:
        return None, None
    start = datetime.fromisoformat(match.group("start").replace("Z", "+00:00"))
    end = datetime.fromisoformat(match.group("end").replace("Z", "+00:00"))
    return start, end


def is_all_day_range(start: datetime, end: datetime) -> bool:
    return (
        start.tzinfo is not None
        and start.hour == 0
        and start.minute == 0
        and start.second == 0
        and end.hour == 0
        and end.minute == 0
        and end.second == 0
    )


def parse_time_tag(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=EASTERN).astimezone(UTC)
    return parsed.astimezone(UTC)


def session() -> requests.Session:
    sess = requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    return sess


def extract_articles(html: str, source: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    events = []
    for article in soup.select("article"):
        title_link = None
        for link in article.select("a.fsCalendarEventLink"):
            if "fsReadMoreLink" in link.get("class", []):
                continue
            text = clean_title(link.get_text(" ", strip=True))
            if text:
                title_link = link
                break
        if title_link is None:
            continue

        title = clean_title(title_link.get_text(" ", strip=True))
        if not keep_event(title):
            continue

        occur_id = article.get("data-occur-id") or title_link.get("data-occur-id")
        start, end = parse_occur_id(occur_id)
        marked_all_day = bool(article.select_one(".fsAllDay"))

        if start is None:
            start_tag = article.select_one("time.fsStartTime[datetime]")
            end_tag = article.select_one("time.fsEndTime[datetime]")
            start = parse_time_tag(start_tag.get("datetime") if start_tag else None)
            end = parse_time_tag(end_tag.get("datetime") if end_tag else None)
            if start is None:
                continue
            if end is None:
                end = start + timedelta(hours=1)

        all_day = marked_all_day or is_all_day_range(start, end)
        if all_day:
            start_day = start.date()
            end_dt = datetime(end.year, end.month, end.day, tzinfo=UTC)
            start_dt = datetime(start_day.year, start_day.month, start_day.day, tzinfo=UTC)
            if end_dt <= start_dt:
                end_dt = start_dt + timedelta(days=1)
            events.append(
                {
                    "title": title,
                    "start": start_dt,
                    "end": end_dt,
                    "all_day": True,
                    "source": source,
                    "occur_id": occur_id or "",
                }
            )
        else:
            labeled = title_with_time(title, start, end)
            day = start.astimezone(EASTERN).date()
            events.append(all_day_event(labeled, day, source, occur_id=occur_id or ""))
    return events


def fetch_master_calendar(sess: requests.Session) -> list[dict]:
    events: list[dict] = []
    start_row = 1
    empty_pages = 0
    while start_row <= 2000:
        params = {
            "keywords": "",
            "start_date": YEAR_START.isoformat(),
            "end_date": YEAR_END.isoformat(),
            "is_draft": "false",
            "is_load_more": "true",
            "page_id": PAGE_ID,
            "parent_id": CALENDAR_ELEMENT_ID,
            "start_row": start_row,
        }
        response = sess.get(CALENDAR_ELEMENT_URL, params=params, timeout=30)
        response.raise_for_status()
        page_events = extract_articles(response.text, CALENDAR_PAGE)
        raw_titles = BeautifulSoup(response.text, "html.parser").select("a.fsCalendarEventLink")
        raw_count = sum(
            1
            for link in raw_titles
            if "fsReadMoreLink" not in link.get("class", [])
            and clean_title(link.get_text(" ", strip=True))
        )
        print(f"Fetched start_row={start_row}: {raw_count} listed, {len(page_events)} kept")
        if raw_count == 0:
            empty_pages += 1
            if empty_pages >= 2:
                break
            start_row += 7
            continue
        empty_pages = 0
        events.extend(page_events)
        start_row += raw_count
    return events


def fetch_page_fallback(sess: requests.Session, url: str) -> list[dict]:
    try:
        response = sess.get(url, timeout=30)
        if response.status_code != 200:
            return []
        return extract_articles(response.text, url)
    except requests.RequestException as exc:
        print(f"Error fetching {url}: {exc}")
        return []


def event_uid(item: dict) -> str:
    key = "|".join(
        [
            item["title"],
            item["start"].isoformat(),
            item["end"].isoformat(),
            item.get("occur_id", ""),
        ]
    )
    return str(uuid5(NAMESPACE_URL, f"tfs-master-cal:{key}"))


def strip_time_and_dates(title: str) -> str:
    text = title.lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"\d{1,2}:\d{2}\s*[ap]\.?m\.?", " ", text)
    text = re.sub(r"\d{1,2}\s*[ap]\.?m\.?", " ", text)
    text = re.sub(
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        " ",
        text,
    )
    text = re.sub(
        r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def event_family(title: str) -> str:
    text = strip_time_and_dates(title)
    if re.search(r"\bclub day\b", text):
        return "club-day"
    if re.search(r"\bung\b|\bapply for free\b", text):
        return "ung-visit"
    if re.search(r"\bmercer\b", text):
        return "mercer-visit"
    if re.search(r"\bcollege visit", text):
        return "college-visit"
    return text


def title_quality(item: dict) -> tuple:
    title = item["title"]
    source = item.get("source", "")
    official = 0 if "tallulahfalls.org" in source else 1
    smore = 1 if "smore.com" in source else 0
    junk = 1 if re.search(r"^(on campus|we will|there will)|college visits:", title, re.I) else 0
    longish = len(title)
    return (official, smore, junk, longish)


def same_day(a: dict, b: dict) -> bool:
    return a["start"].date() == b["start"].date()


def is_near_duplicate(a: dict, b: dict) -> bool:
    if not same_day(a, b):
        return False
    if a["title"] == b["title"]:
        return True
    fa, fb = event_family(a["title"]), event_family(b["title"])
    if fa and fa == fb:
        return True
    na, nb = strip_time_and_dates(a["title"]), strip_time_and_dates(b["title"])
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True
    return False


def dedupe(events: list[dict]) -> list[dict]:
    ranked = sorted(events, key=title_quality)
    kept: list[dict] = []
    for item in ranked:
        if any(is_near_duplicate(item, existing) for existing in kept):
            continue
        kept.append(item)
    kept.sort(key=lambda item: (item["start"], item["title"]))
    return kept


def format_clock(when: datetime) -> str:
    local = when.astimezone(EASTERN)
    return local.strftime("%I:%M %p").lstrip("0")


def title_with_time(title: str, start: datetime, end: datetime | None = None) -> str:
    if re.search(r"\d{1,2}:\d{2}\s*[AP]M", title, re.I):
        return title
    start_local = start.astimezone(EASTERN)
    if end is None:
        return f"{title} ({format_clock(start_local)})"
    end_local = end.astimezone(EASTERN)
    if end_local.date() != start_local.date():
        return f"{title} ({format_clock(start_local)}–{end_local.strftime('%b %d')} {format_clock(end_local)})"
    if format_clock(start_local) == format_clock(end_local):
        return f"{title} ({format_clock(start_local)})"
    return f"{title} ({format_clock(start_local)}–{format_clock(end_local)})"


def all_day_event(title: str, day: date, source: str, occur_id: str = "", description: str = "") -> dict:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return {
        "title": title,
        "start": start,
        "end": end,
        "all_day": True,
        "source": source,
        "occur_id": occur_id,
        "description": description,
    }


def timed_event(title: str, start_local: datetime, end_local: datetime, source: str) -> dict:
    """Store as all-day; keep the clock in the title."""
    labeled = title_with_time(title, start_local, end_local)
    day = start_local.astimezone(EASTERN).date()
    return all_day_event(labeled, day, source)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def is_a_week(monday: date) -> bool:
    """A weeks and B weeks alternate. Seeded by classes-begin Monday = A week."""
    weeks = (monday - monday_of(AB_PATTERN_START)).days // 7
    return weeks % 2 == 0


def week_letter(monday: date) -> str:
    return "A" if is_a_week(monday) else "B"


def day_letter(day: date) -> str:
    """In-week pattern: A week = ABABA, B week = BABAB."""
    monday = monday_of(day)
    index = day.weekday()  # Mon=0 ... Fri=4
    if is_a_week(monday):
        return "A" if index % 2 == 0 else "B"
    return "B" if index % 2 == 0 else "A"


def generate_ab_week_labels() -> list[dict]:
    events = []
    monday = monday_of(AB_PATTERN_START)
    last = monday_of(AB_PATTERN_END)
    source = "TFS A/B week pattern"
    while monday <= last:
        letter = week_letter(monday)
        events.append(all_day_event(f"{letter} Week", monday, source, occur_id=f"ab-week-{monday.isoformat()}"))
        # Daily US A / US B labels for weekdays in that week.
        for offset in range(5):
            day = monday + timedelta(days=offset)
            if day < AB_PATTERN_START or day > AB_PATTERN_END:
                continue
            events.append(
                all_day_event(
                    f"US {day_letter(day)} Day",
                    day,
                    source,
                    occur_id=f"ab-day-{day.isoformat()}",
                )
            )
        monday += timedelta(days=7)
    # Sanity check against the newsletter's known A Monday.
    assert week_letter(AB_KNOWN_A_MONDAY) == "A", "AB week seed does not match Sep 21 A Day"
    return events


def guess_year(month: int, day: int) -> int:
    for year in (2026, 2027):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if YEAR_START <= candidate <= YEAR_END:
            return year
    return 2026 if month >= 8 else 2027


def parse_clock(text: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", text, re.I)
    if not match:
        match = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)", text, re.I)
        if not match:
            return None
        hour = int(match.group(1))
        minute = 0
        meridiem = match.group(3).lower().replace(".", "")
    else:
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3).lower().replace(".", "")
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def parse_smore_date(text: str) -> date | None:
    match = re.search(
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?,?\s*"
        r"(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})",
        text,
        re.I,
    )
    if match:
        month = MONTH_NAME[match.group(1).lower()]
        day = int(match.group(2))
        return date(guess_year(month, day), month, day)
    match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?\b",
        text,
        re.I,
    )
    if not match:
        return None
    month = MONTH_NAME[match.group(1).lower()]
    day = int(match.group(2))
    return date(guess_year(month, day), month, day)


def is_human_smore_text(text: str) -> bool:
    if not text or len(text) < 8:
        return False
    if text in {"strong", "li", "p", "h1", "h2", "div", "header"}:
        return False
    if re.fullmatch(r"[a-z]{1,12}", text):
        return False
    if re.search(r"\b(t strong|\"t\":|\"c\":|\"a\":)\b", text):
        return False
    if text.startswith(("a c ", "c ")):
        return False
    return True


def smore_payload_strings(html: str) -> list[str]:
    """Smore renders in JS. Dated copy lives in escaped JSON strings in the page."""
    parts = []
    for raw in re.findall(r'\\"(.*?)\\"', html):
        text = (
            raw.replace("&quot;", '"')
            .replace("&#39;", "'")
            .replace("&amp;", "&")
            .replace("\\n", " ")
            .replace("\\u2013", "–")
            .replace("\\u2014", "—")
            .replace("\\u2019", "'")
            .strip()
        )
        if is_human_smore_text(text):
            parts.append(text)
    return parts


def smore_plain_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible = soup.get_text("\n", strip=True)
    payload = "\n".join(smore_payload_strings(html))
    text = visible + "\n" + payload
    return re.sub(r"\n{2,}", "\n", text)


def smore_usable_text(text: str) -> str:
    """Keep the intro/top section plus college, club, and activity notes.

    Drop scholarship listings and anything after that heading.
    """
    lowered = text.lower()
    cut_points = []
    for marker in ("\nscholarships\n", "\nscholarship\n", "new $", "award deadline"):
        idx = lowered.find(marker)
        if idx != -1:
            cut_points.append(idx)
    if cut_points:
        text = text[: min(cut_points)]
    # The top weekly section is before the photo-heavy Midmester gallery.
    mid = re.search(r"\nMidmester\n", text)
    top = text[: mid.start()] if mid else text[:2500]
    extra_chunks = []
    for heading in (
        "College Visits",
        "Club Day",
        "Important Events",
        "Sports",
        "Reminders",
    ):
        found = re.search(rf"{re.escape(heading)}.*?(?=\n[A-Z][^\n]{{0,40}}\n|$)", text, re.I | re.S)
        if found:
            extra_chunks.append(found.group(0))
    return top + "\n" + "\n".join(extra_chunks)


def extract_smore_events(text: str, source: str) -> list[dict]:
    events = []
    usable = smore_usable_text(text)
    sentences = [clean_title(part) for part in re.split(r"(?<=[.!])\s+|\n+", usable) if clean_title(part)]
    seen_titles = set()
    for sentence in sentences:
        if not sentence or not keep_event(sentence):
            continue
        day = parse_smore_date(sentence)
        if day is None:
            continue
        lowered = sentence.lower()
        if re.search(r"\ban?\s+a day\b|\ban?\s+b day\b", lowered):
            continue
        clocks = list(re.finditer(r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)", sentence, re.I))
        if not clocks:
            clocks = list(re.finditer(r"(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(a\.?m\.?|p\.?m\.?)", sentence, re.I))
        title = re.sub(r"^(we will have|there will be)\s+", "", sentence, flags=re.I)
        title = re.sub(r"\s+", " ", title).strip(" :;-")
        if not is_human_smore_text(title):
            continue
        if re.search(r"[{}=]|\bfalse\b|\btrue\b", title):
            continue
        if re.match(r"^\d{1,2}(?::\d{2})?", title):
            continue
        interesting = bool(
            re.search(
                r"\b(college|university|ung|mercer|club|activity|activities|visit|assembly|invite|on campus|learning center|media center)\b",
                title,
                re.I,
            )
        )
        if not interesting:
            continue
        if re.fullmatch(
            r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?,?\s*"
            r"(january|february|march|april|may|june|july|august|september|october|november|december)"
            r"\s+\d{1,2},?",
            title,
            re.I,
        ):
            continue
        if len(title) > 140:
            title = title[:137] + "..."
        key = (title[:80], day)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        if clocks and parse_clock(clocks[0].group(0)):
            start_h, start_m = parse_clock(clocks[0].group(0))
            start_local = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=EASTERN)
            if len(clocks) >= 2 and parse_clock(clocks[1].group(0)):
                end_h, end_m = parse_clock(clocks[1].group(0))
                end_local = datetime(day.year, day.month, day.day, end_h, end_m, tzinfo=EASTERN)
                if end_local <= start_local:
                    end_local += timedelta(hours=1)
            else:
                end_local = start_local + timedelta(hours=1)
            events.append(timed_event(title, start_local, end_local, source))
        else:
            events.append(all_day_event(title, day, source))
    return events


def fetch_smore_events(sess: requests.Session) -> list[dict]:
    events = []
    for url in SMORE_URLS:
        try:
            response = sess.get(url, timeout=30)
            if response.status_code != 200:
                print(f"Smore fetch failed {response.status_code}: {url}")
                continue
            text = smore_plain_text(response.text)
            found = extract_smore_events(text, url)
            print(f"Smore {url}: {len(found)} dated events kept")
            events.extend(found)
        except requests.RequestException as exc:
            print(f"Error fetching Smore {url}: {exc}")
    return events


def add_event(calendar: Calendar, item: dict, now: datetime) -> None:
    event = Event()
    event.add("uid", event_uid(item))
    event.add("dtstamp", now)
    event.add("summary", item["title"])
    details = item.get("description") or ""
    source_line = f"Source: {item['source']}"
    event.add("description", f"{details}\n{source_line}".strip() if details else source_line)
    event.add("url", vText(item["source"]))
    event.add("transp", "TRANSPARENT")

    start_day = item["start"].date()
    end_day = item["end"].date()
    if end_day <= start_day:
        end_day = start_day + timedelta(days=1)
    event.add("dtstart", start_day)
    event.add("dtend", end_day)

    calendar.add_component(event)


VOLLEYBALL_RE = re.compile(r"\bvolley(?:ball)?\b", re.I)
RIFLE_RE = re.compile(r"\bprecision rifle|\brifle team\b|\brifle\b", re.I)
SPORT_RE = re.compile(
    r"\b(volleyball|volley|softball|baseball|basketball|soccer|tennis|golf|"
    r"football|swimming|swim|cheer|track|cross country|\bxc\b|rifle)\b",
    re.I,
)
LEVEL_RE = re.compile(r"\b(JV/?V|JVB|JV|VG|VB|V|Varsity|Junior Varsity)\b", re.I)


def first_clock_label(title: str) -> str:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*([ap]\.?m\.?)?", title, re.I)
    if not match:
        match = re.search(r"\b(\d{1,2}):(\d{2})\b", title)
        if not match:
            return ""
        return f"{int(match.group(1))}:{match.group(2)}"
    hour = int(match.group(1))
    minute = match.group(2) or "00"
    mer = (match.group(3) or "").lower().replace(".", "")
    if mer:
        return f"{hour}:{minute} {mer.upper()}"
    return f"{hour}:{minute}"


def venue_and_opponent(title: str) -> tuple[str, str]:
    home = bool(re.search(r"\bhome\b|\(home\)", title, re.I))
    away = bool(re.search(r"\s@\s|\baway\b", title, re.I))
    venue = "Home" if home and not away else "Away" if away or "@" in title else ""
    opp = ""
    match = re.search(
        r"(?:HOME\s*v(?:s)?\.?|\(HOME\)\s*vs\.?|vs\.?|v\.?|@)\s+([^0-9(]+)",
        title,
        re.I,
    )
    if match:
        opp = clean_title(match.group(1))
        opp = re.sub(r"\b(tri-match|tourney|tournament|tba)\b.*", "", opp, flags=re.I).strip(" -")
    return venue, opp


def sport_level(title: str) -> str:
    match = LEVEL_RE.search(title)
    token = match.group(1) if match else "V"
    token = token.replace("Varsity", "V").replace("Junior Varsity", "JV")
    if token.upper() in {"V", "VB", "VG"} and "jv" not in title.lower():
        return "V"
    if token.upper().startswith("JV"):
        return "JV" if "V" not in token.upper()[2:] else "JV/V"
    return token


def sport_name(title: str) -> str:
    lowered = title.lower()
    names = [
        ("volleyball", "Volleyball"),
        ("softball", "Softball"),
        ("basketball", "Basketball"),
        ("cross country", "Cross Country"),
        ("baseball", "Baseball"),
        ("soccer", "Soccer"),
        ("tennis", "Tennis"),
        ("golf", "Golf"),
        ("football", "Football"),
        ("swim", "Swim"),
        ("cheer", "Cheer"),
        ("track", "Track"),
        ("precision rifle", "Precision Rifle"),
        ("rifle", "Precision Rifle"),
    ]
    for needle, label in names:
        if needle in lowered:
            return label
    return "Sports"


def is_sport(title: str) -> bool:
    if re.search(r"interest meeting|sleepover|rafting", title, re.I):
        return False
    return bool(SPORT_RE.search(title))


def is_unique_sport(title: str) -> bool:
    return bool(VOLLEYBALL_RE.search(title) or RIFLE_RE.search(title))


def format_sport_title(title: str) -> tuple[str, str]:
    name = sport_name(title)
    level = sport_level(title)
    venue, opponent = venue_and_opponent(title)
    clock = first_clock_label(title)
    if name == "Volleyball":
        core = f"{level} Volleyball Game"
    elif name == "Precision Rifle":
        core = f"{level} Precision Rifle"
    else:
        core = f"{level} {name}"
    if venue:
        core = f"{core} {venue}"
    brief = f"{core} - {clock}" if clock else core
    details = []
    if opponent:
        details.append(f"Opponent: {opponent}")
    extra = clean_title(re.sub(r"\([^)]*\)", " ", title))
    if extra and extra.lower() not in brief.lower():
        details.append(extra)
    return brief, "\n".join(details)


def format_early_release(title: str) -> tuple[str, str]:
    clock = first_clock_label(title)
    if "noon" in title.lower() and not clock:
        clock = "12:00 PM"
    brief = f"Early Release - {clock}" if clock else "Early Release"
    return brief, title


def format_generic(title: str) -> tuple[str, str]:
    original = title
    clock = first_clock_label(title)
    text = re.sub(r"\([^)]*\)", " ", title)
    text = re.sub(
        r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday),?\s*"
        r"(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s*",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\d{1,2}:\d{2}\s*[ap]\.?m\.?", " ", text, flags=re.I)
    text = clean_title(text).strip(" -")
    lowered = text.lower()
    if "club day" in lowered:
        text = "Club Day"
    elif "ung" in lowered or "apply for free" in lowered:
        text = "UNG Apply for Free Day"
    elif "mercer" in lowered:
        text = "Mercer University Visit"
    if len(text) > 60:
        text = text[:57] + "..."
    if clock and clock.lower() not in text.lower():
        text = f"{text} - {clock}"
    return text, original


def reshape_event(item: dict) -> dict:
    title = item["title"]
    if re.search(r"\bearly release\b|\bhalf day\b", title, re.I):
        brief, details = format_early_release(title)
    elif is_sport(title):
        brief, details = format_sport_title(title)
    elif item.get("source", "").find("smore.com") != -1:
        brief, details = format_generic(title)
    else:
        brief, details = format_generic(title) if len(title) > 70 else (title, "")
        # Drop appended clock-in-parens from older conversion; keep brief official names.
        brief = re.sub(r"\s*\(\d{1,2}:\d{2} [AP]M(?:–[^)]+)?\)\s*$", "", brief)
        clock = first_clock_label(title)
        if clock and is_sport(title):
            brief, details = format_sport_title(title)
        elif clock and "club day" in title.lower():
            brief, details = format_generic(title)
    item = dict(item)
    item["title"] = brief
    extra = item.get("description") or ""
    item["description"] = "\n".join(part for part in (details, extra) if part)
    return item


def merge_same_day_sports(events: list[dict]) -> list[dict]:
    groups: dict[date, list[dict]] = {}
    others: list[dict] = []
    for item in events:
        if is_sport(item["title"]) and not is_unique_sport(item["title"]):
            groups.setdefault(item["start"].date(), []).append(item)
        else:
            others.append(item)
    merged = []
    for day, items in groups.items():
        if len(items) == 1:
            merged.append(items[0])
            continue
        clocks = [first_clock_label(i["title"]) for i in items]
        clocks = [c for c in clocks if c]
        clock = clocks[0] if clocks else ""
        names = []
        for item in items:
            name = sport_name(item["title"])
            if name not in names:
                names.append(name)
        joined = ", ".join(names) if names else "Athletics"
        title = f"{joined} - {clock}" if clock else joined
        lines = []
        for item in items:
            line = item["title"]
            if item.get("description"):
                line = f"{line} — {item['description'].splitlines()[0]}"
            lines.append(line)
        merged.append(
            all_day_event(
                title,
                day,
                items[0]["source"],
                occur_id=f"sports-{day.isoformat()}",
                description="\n".join(lines),
            )
        )
    return others + merged


def run() -> None:
    print("Fetching TFS master calendar...")
    sess = session()
    events = fetch_master_calendar(sess)
    events.extend(fetch_page_fallback(sess, ATHLETICS_URL))
    events.extend(fetch_smore_events(sess))
    events.extend(generate_ab_week_labels())
    events = [item for item in events if keep_event(item["title"])]
    events = dedupe(events)
    events = [reshape_event(item) for item in events]
    events = merge_same_day_sports(events)
    events = dedupe(events)

    calendar = Calendar()
    calendar.add("prodid", "-//TFS Master Calendar//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", FEED_NAME)
    calendar.add("x-wr-timezone", "America/New_York")

    now = datetime.now(tz=UTC)
    for item in events:
        add_event(calendar, item, now)

    payload = calendar.to_ical()
    with open(OUTPUT_BASENAME, "wb") as handle:
        handle.write(payload)
    with open(f"{OUTPUT_BASENAME}.ics", "wb") as handle:
        handle.write(payload)

    print(f"Done. Wrote {OUTPUT_BASENAME} and {OUTPUT_BASENAME}.ics with {len(events)} events.")
    for item in events[:25]:
        kind = "all-day" if item["all_day"] else "timed"
        print(f"  [{kind}] {item['start']} — {item['title']}")
    if len(events) > 25:
        print(f"  ... {len(events) - 25} more")


if __name__ == "__main__":
    