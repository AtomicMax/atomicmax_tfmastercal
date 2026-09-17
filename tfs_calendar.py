from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
from icalendar import Calendar, Event
import requests

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
    clean = text.lower()
    if any(ex in clean for ex in EXCLUDED_KEYWORDS):
        return False
    return any(inc in clean for inc in ALLOWED_KEYWORDS)


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

                # De-duplicate entries
                for line in set(lines):
                    if is_target_event(line):
                        event = Event()
                        event.add("summary", line)
                        event.add("dtstart", datetime.now().date())
                        event.add(
                            "dtend", datetime.now().date() + timedelta(days=1)
                        )
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