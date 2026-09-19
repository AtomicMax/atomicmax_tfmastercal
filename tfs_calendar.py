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
    r"\b(?:4th|5th|6th|7th|8th|fourth|fifth|sixth|seventh|eighth)\s+grades?\b"
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


def dedupe(events: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in events:
        key = (item["title"], item["start"], item["end"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    unique.sort(key=lambda item: (item["start"], item["title"]))
    return unique


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


def all_day_event(title: str, day: date, source: str, occur_id: str = "") -> dict:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    return {
        "title": title,
        "start": start,
        "end": end,
        "all_day": True,
        "source": source,
        "occur_id": occur_id,
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
    # Join short payload fragments so "UNG:" + "Thursday, September 24," stay together.
    lines = [clean_title(part) for part in re.split(r"\n+", usable) if clean_title(part)]
    windows = []
    for i, line in enumerate(lines):
        chunk = line
        if i + 1 < len(lines):
            chunk = clean_title(chunk + " " + lines[i + 1])
        if i + 2 < len(lines):
            chunk = clean_title(chunk + " " + lines[i + 2])
        windows.append(chunk)
        windows.append(line)
    seen_titles = set()
    for sentence in windows:
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
    event.add("description", f"Source: {item['source']}")
    event.add("url", vText(item["source"]))
    event.add("transp", "TRANSPARENT")

    start_day = item["start"].date()
    end_day = item["end"].date()
    if end_day <= start_day:
        end_day = start_day + timedelta(days=1)
    event.add("dtstart", start_day)
    event.add("dtend", end_day)

    calendar.add_component(event)


def run() -> None:
    print("Fetching TFS master calendar...")
    sess = session()
    events = fetch_master_calendar(sess)
    events.extend(fetch_page_fallback(sess, ATHLETICS_URL))
    events.extend(fetch_smore_events(sess))
    events.extend(generate_ab_week_labels())
    events = [item for item in events if keep_event(item["title"])]
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
    run()