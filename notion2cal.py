"""
Sync the "Portfolio Case Studies" work blocks from your Notion "Works Tasks"
database into a .ics calendar feed that Apple Calendar (or any app) can
subscribe to.

This only pulls rows where the "Branch" property equals "Portfolio Case
Studies" -- your Personal / Spiritual / other Professional tasks in the same
shared database are never included, since this repo (and the generated .ics
file) needs to be public for the raw URL to work without authentication.

Required environment variables (set as GitHub Actions secrets):
  NOTION_TOKEN        Internal integration secret (starts with "ntn_")
  NOTION_DATABASE_ID  The 32-character ID of the "Works Tasks" database
"""

import os
from datetime import date, datetime, timedelta, timezone

import requests
from icalendar import Calendar, Event

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_VERSION = "2022-06-28"
OUTPUT_FILE = "portfolio_sprint.ics"

# Change this if you ever rename the Branch value in Notion.
BRANCH_FILTER_VALUE = "Portfolio Case Studies"

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}

QUERY_URL = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"


def fetch_pages():
    """Query the Notion database, filtered to the Portfolio branch, handling pagination."""
    pages = []
    payload = {
        "filter": {
            "property": "Branch",
            "rich_text": {"equals": BRANCH_FILTER_VALUE},
        }
    }
    while True:
        resp = requests.post(QUERY_URL, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        payload["start_cursor"] = data["next_cursor"]
    return pages


def plain_title(title_prop):
    parts = (title_prop or {}).get("title", [])
    text = "".join(p.get("plain_text", "") for p in parts)
    return text or "(untitled)"


def parse_date(date_prop):
    """Return (start, end) as date or datetime objects, or (None, None) if unset."""
    date_obj = (date_prop or {}).get("date")
    if not date_obj or not date_obj.get("start"):
        return None, None

    def to_value(raw):
        if "T" in raw:
            return datetime.fromisoformat(raw)
        return date.fromisoformat(raw)

    start = to_value(date_obj["start"])
    end = to_value(date_obj["end"]) if date_obj.get("end") else None
    return start, end


def build_calendar(pages):
    cal = Calendar()
    cal.add("prodid", "-//Portfolio Sprint Sync//notion2cal//")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Portfolio Sprint")

    for page in pages:
        props = page.get("properties", {})
        name = plain_title(props.get("Name"))
        start, end = parse_date(props.get("Deadline"))
        if start is None:
            continue  # nothing to schedule without a date

        event = Event()
        event.add("summary", name)
        event.add("uid", f"{page['id']}@portfolio-sprint")
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("dtstart", start)

        if end:
            event.add("dtend", end)
        elif isinstance(start, datetime):
            # give timed events with no explicit end a 1-hour block
            event.add("dtend", start + timedelta(hours=1))
        # all-day events (start is a plain date) are left as single-day

        if page.get("url"):
            event.add("url", page["url"])

        cal.add_component(event)

    return cal


def main():
    pages = fetch_pages()
    cal = build_calendar(pages)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())
    print(f"Wrote {len(pages)} Portfolio Sprint event(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
