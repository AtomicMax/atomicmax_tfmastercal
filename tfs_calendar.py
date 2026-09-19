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
    "us",
    "midmester",
    "mid-mester",
    "9th grade",
    "11th grade",
    "freshman",
    "junior",
    "volleyball",
    "vball",
    "no school",
    "school closed",
    "school holiday",
    "off date",
    "one act play",
    "christmas card contest",
    "all school",
    "commencement",
    "convocation",
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
    is_volleyball_sac = (
        re.search(r"\bvolleyball\b", clean)
        and re.search(r"\bsac\b", clean)
    )
    if is_volleyball_sac and (
        re.search(r"\bmiddle school\b", clean)
        or re.search(r"\bms\b", clean)
    ):
        return True
    if any(ex in clean for ex in EXCLUDED_KEYWORDS):
        return False
    if re.search(r"\blower school\b|\bls\b", clean):
        return False
    if re.search(r"\bmiddle school\b|\bms\b", clean):
        return False
    return any(
        keyword in clean
        if " " in keyword
        else re.search(rf"\b{re.escape(keyword)}\b", clean)
        for keyword in ALLOWED_KEYWORDS
    )


def parse_occurrence_range(occur_id: str):
    if not occur_id:
        return None, None

    match = re.search(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z_(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}Z", occur_id)
    if match:
        start_date = date.fromisoformat(match.group(1))
        end_date = date.fromisoformat(match.group(2))
        return start_date, end_date

    match = re.search(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", occur_id)
    if match:
        return date.fromisoformat(match.group(1)), date.fromisoformat(match.group(1))

    return None, None


def extract_events_from_html(html: str, url: str):
    soup = BeautifulSoup(html, "html.parser")
    events = []
    seen_events = set()

    for article in soup.select("article"):
        title_link = None
        for link in article.select("a.fsCalendarEventLink"):
            if "fsReadMoreLink" in link.get("class", []):
                continue
            text = " ".join(link.get_text(" ", strip=True).split())
            if text:
                title_link = link
                break

        if title_link is None:
            continue

        title = " ".join(title_link.get_text(" ", strip=True).split())
        if not is_target_event(title):
            continue

        if title in seen_events:
            continue
        seen_events.add(title)

        current = article.get("data-occur-id") or title_link.get("data-occur-id")
        start_date, end_date = parse_occurrence_range(current)

        if start_date is None:
            time_tags = article.select("time[datetime]")
            if not time_tags:
                continue
            try:
                start_date = datetime.fromisoformat(time_tags[0].get("datetime")).date()
            except ValueError:
                continue
            end_date = start_date + timedelta(days=1)
        else:
            end_date = end_date + timedelta(days=1)

        events.append({
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "source": url,
        })

    return events


def run():
    print("Fetching TFS events...")
    cal = Calendar()
    cal.add("prodid", "-//TFS Upper School Calendar//EN")
    cal.add("version", "2.0")

    count = 0
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }

    seen_titles = set()
    for url in CALENDAR_URLS:
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                for item in extract_events_from_html(res.text, url):
                    title = item["title"]
                    if title in seen_titles:
                        continue
                    seen_titles.add(title)

                    event = Event()
                    event.add("summary", title)
                    event.add("dtstart", item["start_date"])
                    event.add("dtend", item["end_date"])
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