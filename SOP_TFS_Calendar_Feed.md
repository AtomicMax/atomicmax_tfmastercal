# TFS Calendar Feed SOP

## Purpose
This document describes the standard operation and maintenance process for the TFS Upper School calendar feed generated from the Tallulah Falls School public calendar sources and published as an ICS feed through GitHub Pages.

## Scope
This SOP covers:
- workflow configuration
- dependency management
- source scraping and filtering
- scheduled refreshes
- deployment to GitHub Pages
- calendar subscription URL
- troubleshooting steps

## System Overview
The project uses:
- Python to scrape and filter calendar data
- GitHub Actions to automate the process
- GitHub Pages to host the generated ICS feed
- an ICS URL for subscription in Google Calendar, Apple Calendar, and similar clients

## Repository
Repository name:
- AtomicMax/atomicmax_tfmastercal

Project directory:
- /Users/emmamaxwell/Library/CloudStorage/GoogleDrive-emma@maxwellfamily.me/My Drive/TFS_Calendar

## Core Files
- `tfs_calendar.py` — generates the calendar feed
- `requirements.txt` — Python dependencies
- `.github/workflows/update_calendar.yml` — automation workflow
- `site/atomicmax_tfmastercal.ics` — deployed output file

## Feed URL
The subscription URL is:

https://atomicmax.github.io/atomicmax_tfmastercal/atomicmax_tfmastercal.ics

## Workflow Behavior
The workflow runs on:
- push to main
- daily schedule at 06:00 UTC
- manual workflow dispatch

The workflow does the following:
1. checks out the repository
2. sets up Python
3. installs dependencies from `requirements.txt`
4. runs `python tfs_calendar.py`
5. creates a `site/` directory
6. copies the generated ICS file into `site/atomicmax_tfmastercal.ics`
7. uploads the artifact to GitHub Pages
8. deploys the site through the official GitHub Pages actions

## Script Logic
The Python script:
- fetches the TFS calendar sources
- filters for allowed Upper School event keywords
- excludes lower/middle school and other disallowed content
- parses dates from nearby source text
- deduplicates title strings
- skips link metadata such as “about …” and “read more”
- writes a valid ICS calendar file

## Required Dependencies
`requirements.txt` contains:

```text
beautifulsoup4==4.12.3
icalendar==6.1.0
requests==2.32.3
```

## Local Run Commands
Run from the project root:

```zsh
cd "/Users/emmamaxwell/Library/CloudStorage/GoogleDrive-emma@maxwellfamily.me/My Drive/TFS_Calendar"
python3 -m pip install -r requirements.txt
python3 tfs_calendar.py
mkdir -p site
cp atomicmax_tfmastercal site/atomicmax_tfmastercal.ics
ls -R site
```

## Git Push Commands
Use the following to upload updates:

```zsh
cd "/Users/emmamaxwell/Library/CloudStorage/GoogleDrive-emma@maxwellfamily.me/My Drive/TFS_Calendar"
git add .
git commit -m "Update calendar feed"
git push origin main
```

## Troubleshooting
### If the feed URL returns 404
Check:
- GitHub Pages source is set to GitHub Actions
- the workflow ran successfully
- the repo name matches the published URL
- the deployed artifact exists in the `site/` folder

### If events show only today
Check:
- `tfs_calendar.py` is assigning real parsed dates, not `datetime.now()`
- date extraction logic is working against real source text

### If duplicate entries appear
Check:
- “about …” and “read more” strings are filtered out
- deduplication is applied to exact title matches

### If Google Calendar shows the calendar name but no events
Check:
- Google Calendar sync delay
- the feed URL is still valid by downloading the ICS file in a browser
- the feed contains valid VEVENT entries

## Validation Evidence
The local validation run confirmed the feed includes real dates, for example:

```text
('Upper School Midmester Week', '2026-09-17', '2026-09-18')
('One Act Play - Upper School', '2026-09-21', '2026-09-22')
('TFS Christmas Card Contest Submissions', '2026-10-24', '2026-10-25')
```

## Final Notes
This feed is intended to be a live subscription-based calendar for Upper School events. It updates automatically through scheduled GitHub Actions runs and remains published through GitHub Pages.

## Current Workflow File
```yaml
name: Initialize atomicmax master calendar feed

permissions:
  contents: read
  pages: write
  id-token: write

on:
  push:
    branches:
      - main
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Checkout repository
        uses: actions/checkout@v5

      - name: Set up Python 3.10
        uses: actions/setup-python@v6
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi

      - name: Run aggregator script
        run: python tfs_calendar.py

      - name: Prepare GitHub Pages output
        run: |
          mkdir -p site
          cp atomicmax_tfmastercal site/atomicmax_tfmastercal.ics

      - name: Upload Pages artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: ./site

      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

## Current Script File
```python
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

CALENDAR_URLS = [
    "https://www.tallulahfalls.org/about/calendars",
    "https://tfsathletics.com/composite",
]

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
```

## ISO Guidance Alignment
This document aligns with a simple operational documentation model:
- purpose
- scope
- responsibilities
- process flow
- validation
- troubleshooting
- versioned workflow
- evidence of successful output

The project maintains clear operational evidence by capturing the exact commands, workflow file, and final output locations needed to reproduce and validate the feed.
