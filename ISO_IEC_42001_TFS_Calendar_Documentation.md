# TFS Calendar Feed Governance and ISO/IEC 42001 Documentation

## 1. Document Control

- Document type: AI governance and operational assurance documentation
- Standard context: ISO/IEC 42001-aligned governance, risk, controls, and evidence documentation
- System name: TFS Calendar Feed Automation and Publication System
- Owner: AtomicMax
- Repository: AtomicMax/atomicmax_tfmastercal
- Primary environment: GitHub Actions, GitHub Pages, Python automation
- Version: 1.0
- Effective date: 2026-09-18

## 2. Purpose
This document provides the governance, control, and traceability information required to demonstrate responsible design, operation, and oversight for the TFS calendar publication system. It is intended to support alignment with ISO/IEC 42001 expectations for documented context, risk awareness, operational controls, validation, and evidence.

## 3. System Scope and Context
The system is a scheduled automation process that:
- retrieves event data from public Tallulah Falls School sources
- filters relevant Upper School content
- converts the selected content into valid ICS calendar entries
- publishes the resulting feed for subscription in external calendar clients
- supports routine monitoring and controlled maintenance through versioned code and workflow automation

This system is a low-risk decision-support and publication automation mechanism, designed to transform external source content into a curated, school-calendar feed. It does not perform autonomous decision-making affecting safety, employment, admissions, or high-impact human outcomes. However, it does involve data classification, information processing, and the application of rules that affect the published content shown to end users.

## 4. Organizational Roles and Responsibilities

### System Owner
- defines scope and intended use
- approves system changes and publication settings
- reviews risk and control documentation

### Developer / Maintainer
- maintains the Python script and GitHub workflow
- monitors source drift, broken selectors, and publishing failures
- validates events and updates filtering rules as needed

### Reviewer / Quality Assurance
- verifies that published events are accurate, relevant, and consistent with school calendars
- confirms the ICS file remains valid and externally consumable
- reviews incidents, errors, and false-positive/false-negative event inclusion

### End User / Consumer
- subscribes to the published ICS feed using a compatible calendar client
- uses the feed as a source of informational scheduling content

## 5. System Boundary and Dependencies

### In-Scope Components
- Python script: `tfs_calendar.py`
- dependency file: `requirements.txt`
- automation workflow: `.github/workflows/update_calendar.yml`
- output artifact: `atomicmax_tfmastercal`
- published feed: GitHub Pages-hosted ICS file

### External Dependencies
- Tallulah Falls School public website and athletics calendar content
- GitHub Actions execution environment
- GitHub Pages hosting service
- calendar clients such as Apple Calendar and Google Calendar

### Out-of-Scope Elements
- direct integration with school administrative systems
- personal data storage or user account management
- AI model inference or autonomous ranking beyond content filtering rules

## 6. Lifecycle of the System
The lifecycle follows a simple control model consistent with ISO/IEC 42001 documentation expectations:

1. Define purpose and intended use
2. Validate the source content and event rules
3. Implement filtering and date extraction logic
4. Automate generation and deployment through GitHub Actions
5. Publish and verify feed availability
6. Monitor change drift and review event quality
7. Maintain controlled updates through versioned deployment

## 7. Data and Information Sources
The system uses publicly available information from:
- https://www.tallulahfalls.org/about/calendars
- https://tfsathletics.com/composite

These sources are treated as public-facing reference material for schedule publication. The automation does not collect personally identifiable information beyond what is included in the public web content itself.

## 8. Decision Logic and Control Measures
The automation applies rule-based filters to determine event relevance. The control logic includes:
- keyword allow-listing for Upper School content
- exclusion of clearly unrelated grade levels or school divisions
- removal of navigation text and metadata such as “about …” and “read more”
- deduplication to prevent repeated events
- date parsing based on source context instead of defaulting to current date
- generation of an ICS file with valid event start and end date values

These checks are intended to reduce false positives and maintain content quality.

## 9. Risk Management

### Risk 1: Incorrect event inclusion
Potential impact: users see irrelevant or non-school events.
Control: allow-list vocabulary and exclusion rules reduce the inclusion of non-target content.

### Risk 2: Incorrect date assignment
Potential impact: event appears on the wrong day or in the wrong time period.
Control: parse dates from nearby source text and validate final output before publication.

### Risk 3: Duplicate entries
Potential impact: cluttered calendar and poor user experience.
Control: deduplicate exact event titles and filter metadata strings.

### Risk 4: Publishing failure or broken deployment
Potential impact: calendar feed inaccessible or stale.
Control: GitHub Actions workflow validates successful runs, creates the `site/` artifact, and deploys to GitHub Pages.

### Risk 5: External source drift
Potential impact: website structure changes and the scraper produces incomplete results.
Control: periodic review of output, code adaptation when structure changes, and controlled versioned updates.

## 10. Human Oversight and Validation
The system is designed to be auditable and reviewable. Human oversight includes:
- checking source relevance before publication changes
- validating event titles and dates after generation
- confirming that the ICS file is accessible and valid
- reviewing workflow status on push and scheduled runs

## 11. Technical Architecture Summary

### Core files
- `tfs_calendar.py` — ingestion, filtering, date parsing, and ICS generation
- `requirements.txt` — project runtime dependencies
- `.github/workflows/update_calendar.yml` — automated deployment job
- `atomicmax_tfmastercal` — generated ICS output
- `site/atomicmax_tfmastercal.ics` — published artifact

### Feed URL
https://atomicmax.github.io/atomicmax_tfmastercal/atomicmax_tfmastercal.ics

### Deployment model
- Source-controlled repository
- automated execution in GitHub Actions
- artifact creation under `site/`
- deployment via GitHub Pages

## 12. Validated Evidence
The final validation run confirmed that the system generates real event dates rather than defaulting to the current date. Representative output included:

```text
('Upper School Midmester Week', '2026-09-17', '2026-09-18')
('One Act Play - Upper School', '2026-09-21', '2026-09-22')
('TFS Christmas Card Contest Submissions', '2026-10-24', '2026-10-25')
```

This evidence demonstrates the system is producing date-aware calendar entries that align with the source content.

## 13. Monitoring and Review
The repository should be reviewed on a recurring basis to confirm:
- the external source pages remain accessible
- the feed still resolves without errors
- the published calendar continues to contain valid and relevant events
- no duplicate, stale, or unrelated content is appearing

Review triggers include:
- workflow failures
- source page changes
- user-reported inaccurate calendar entries
- changes to school event structure or naming conventions

## 14. Change Control and Recordkeeping
Changes to the system should be managed through version control and documented review. Minimum records include:
- repository commit history
- workflow execution status
- changes to event filtering logic
- validation output from script execution
- deployment and publication records

## 15. Controls Matrix

| Area | Control | Evidence |
|---|---|---|
| Governance | Defined purpose and scope | This document |
| Data source handling | Public-source intake only | Source URL list |
| Data quality | Allow-list and exclusion filtering | Python rule logic |
| Accuracy | Real date parsing | event validation output |
| Integrity | Duplicate filtering | deduplication logic |
| Deployment | GitHub Actions automated deploy | workflow file |
| Publication | GitHub Pages hosting | published ICS URL |
| Monitoring | scheduled and manual runs | workflow triggers |
| Review | human oversight and validation | validation evidence |

## 16. Appendix A: Final Workflow File

```yaml
name: Initialize atomicmax master calendar feed

permissions:
  contents: write
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

## 17. Appendix B: Final Python Source

```python
from datetime import date, timedelta
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

## 18. Conclusion
This document provides the governance and evidence artifacts required to support responsible operation of the TFS calendar automation system under an ISO/IEC 42001-aligned management-system approach. It captures system purpose, scope, roles, risk controls, operational logic, publication controls, and validation evidence, while remaining grounded in the actual implementation and deployment model used in this project.
