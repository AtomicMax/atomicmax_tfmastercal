from datetime import date, datetime, timedelta
import re
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import requests

MONTH_MAP = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

# Live TFS web pages to pull events from
CALENDAR_URLS = [
    "https://www.tallulahfalls.org/about/calendars",
    "https://tfsathletics.com/composite",
]

# Keywords to INCLUDE
ALLOWED_KEYWORDS = [
    "upper school",
    "midmester",
    "mid-mester",
    "9th grade",
    "11th grade",
    "freshman",
    "junior",
    "volleyball",
    "vball",
    "one act play",
    "christmas card contest",
    "all school",
    "commencement",
    "convocation",
    "no school",
    "break",
    "holiday",
]

# Keywords to EXCLUDE
EXCLUDED_KEYWORDS = [
    "presidential scholar",
    "presidential scholars",
    "scholar",
    "lower school",
    "middle school",
    "4th grade",
    "5th grade",
    "6th grade",
    "7th grade",
    "8th grade",
    "10th grade",
    "12th grade",
    "senior",
    "sophomore",
    "ms tennis",
    "ms volleyball",
    "ms cross country",
    "ms softball",
]


def is_target_event(text: str) -> bool:
    clean = text.lower().strip()
    if not clean:
        return False
    if clean.startswith("about ") or clean.startswith("read more"):
        return False
    if clean.startswith("load more") or clean.startswith("monthly calendar"):
        return False
    if any(ex in clean for ex in EXCLUDED_KEYWORDS):
        return False
    return any(inc in clean for inc in ALLOWED_KEYWORDS)


def parse_event_date(lines, event_index):
    window = lines[max(0, event_index - 10) : min(len(lines), event_index + 15)]
    tokens = []
    for line in window:
        tokens.extend(re.split(r"[\s|]+", line.strip()))
    tokens = [t for t in tokens if t]

    for pos, token in enumerate(tokens):
        key = token.strip().lower().rstrip(".")
        month = MONTH_MAP.get(key)
        if month is None:
            continue

        for day_pos in range(pos + 1, min(len(tokens), pos + 8)):
            day_text = tokens[day_pos].strip().rstrip(",")
            if not day_text.isdigit() or not (1 <= int(day_text) <= 31):
                continue
            for year_pos in range(day_pos + 1, min(len(tokens), day_pos + 4)):
                year_text = tokens[year_pos].strip().rstrip(",")
                if year_text.isdigit() and len(year_text) == 4:
                    return date(int(year_text), month, int(day_text))

    return None


def run():
    print("Fetching TFS events...")
    cal = Calendar()
    cal.add("prodid", "-//TFS Upper School Calendar//EN")
    cal.add("version", "2.0")

    count = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    for url in CALENDAR_URLS:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                lines = [
                    line.strip()
                    for line in soup.get_text().split("\n")
                    if len(line.strip()) > 5
                ]

                seen = set()
                for idx, line in enumerate(lines):
                    if not is_target_event(line):
                        continue
                    cleaned = re.sub(r"\s+", " ", line).strip()
                    if not cleaned or cleaned in seen:
                        continue
                    seen.add(cleaned)

                    event_date = parse_event_date(lines, idx)
                    if event_date is None:
                        continue

                    event = Event()
                    event.add("summary", cleaned)
                    event.add("dtstart", event_date)
                    event.add("dtend", event_date + timedelta(days=1))
                    event.add("description", f"Source: {url}")
                    cal.add_component(event)
                    count += 1
        except Exception as e:
            print(f"Error checking {url}: {e}")

    filename = "atomicmax_tfmastercal"
    with open(filename, "wb") as f:
        f.write(cal.to_ical())

    print(f"Done! Created '{filename}' with {count} events.")


if __name__ == "__main__":
    run()