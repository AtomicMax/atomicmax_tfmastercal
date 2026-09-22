# TFS Calendar Feed Implementation v091826

## Version Record

- Version: `v091826`
- Version date: 2026-09-18
- Implementation commit: `8d35c72`
- Repository: `AtomicMax/atomicmax_tfmastercal`
- System: TFS Calendar Feed Automation and GitHub Pages Publication
- Storage: Google Drive-backed TFS Calendar project folder

## Current Status

This is the dated documentation record for the current deployed implementation. The full current implementation document, including the complete Python source and workflow source, is maintained at:

- [TFS_Calendar_Current_Implementation_2026-09-18.md](TFS_Calendar_Current_Implementation_2026-09-18.md)

The source files represented by this version are:

- [tfs_calendar.py](tfs_calendar.py)
- [update_calendar.yml](.github/workflows/update_calendar.yml)
- [requirements.txt](requirements.txt)

## Published Feed

Subscription URL:

https://atomicmax.github.io/atomicmax_tfmastercal/atomicmax_tfmastercal.ics

The URL is unchanged for this version.

## Current Behavior

The generator currently:

- includes Upper School and standalone `US` event titles
- includes Volleyball and VBall events
- includes TFS off dates such as No School, School Closed, School Holiday, Break, Holiday, and Off Date
- excludes Lower School, `LS`, Middle School, and `MS` events by default
- includes Middle School Volleyball events when the title also contains `SAC`
- preserves timed event start and end times
- writes all-day events as date-only ICS values
- retains separate recurring occurrences
- expands multi-day all-day ranges into one entry for each day
- deduplicates only identical title/start/end combinations

## Verified Output for v091826

The deployed feed was verified with HTTP 200 and contains 11 entries:

- Upper School Midmester Week: September 13, 14, 15, 16, 17, and 18, 2026
- Upper School Midmester Presentations and Assembly Schedule: September 21, 2026, 9:30 AM–10:30 AM
- One Act Play - Upper School: October 22, 23, and 24, 2026, 7:00 PM–9:00 PM
- TFS Christmas Card Contest Submissions: October 28, 2026

## Dependencies

```text
beautifulsoup4==4.12.3
icalendar==6.1.0
requests==2.32.3
```

## Deployment

GitHub Actions runs on pushes to `main`, daily at 06:00 UTC, and manual workflow dispatch. It installs the dependencies, runs `python tfs_calendar.py`, copies `atomicmax_tfmastercal` to `site/atomicmax_tfmastercal.ics`, and deploys the artifact through GitHub Pages.

Current workflow permissions:

```yaml
permissions:
  contents: read
  pages: write
  id-token: write
```

## Validation Evidence

Local validation confirmed:

- six separate all-day Midmester daily entries
- three separate One Act Play occurrences
- timed event values retained as 7:00 PM–9:00 PM
- all-day entries represented with `VALUE=DATE`
- no Python diagnostics in `tfs_calendar.py`

The GitHub Actions deployment for commit `8d35c72` completed successfully, and the live feed was then verified with 11 entries.

## Source Pages

- https://www.tallulahfalls.org/about/calendars
- https://tfsathletics.com/composite

## Versioning Note

This file is the dated `v091826` record and does not replace the existing implementation or ISO/IEC 42001 documentation files. The code and workflow remain in the repository files listed above, and the complete source appendix remains in `TFS_Calendar_Current_Implementation_2026-09-18.md`.
