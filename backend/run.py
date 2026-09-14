#!/usr/bin/env python3
"""
Family Dashboard — daily cycle (self-hosted, runs outside Claude Cowork).

Flow: read school mail (Gmail) -> extract+merge with Claude -> post events to
Google Calendar -> send digest (Slack + email) -> persist state/ledger.json.

Auth/config come from environment (see backend/README.md) and config/*.yaml.
Run:  python backend/run.py
"""

import base64
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

import requests
import yaml
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from anthropic import Anthropic

# ---------- paths ----------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config")
LEDGER_PATH = os.path.join(ROOT, "state", "ledger.json")

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")  # override to claude-sonnet-5 to cut cost


def load_yaml(name):
    with open(os.path.join(CONFIG, name)) as f:
        return yaml.safe_load(f)


def google_services():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar",
        ],
    )
    gmail = build("gmail", "v1", credentials=creds, cache_discovery=False)
    cal = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return gmail, cal


# ---------- ledger ----------
def load_ledger():
    with open(LEDGER_PATH) as f:
        return json.load(f)


def save_ledger(led):
    led["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LEDGER_PATH, "w") as f:
        json.dump(led, f, indent=2)
        f.write("\n")


# ---------- gmail ----------
def _decode_part(data):
    return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", "replace")


def _extract_body(payload):
    """Walk a Gmail message payload and return the best text body."""
    if payload.get("mimeType", "").startswith("text/") and payload.get("body", {}).get("data"):
        return _decode_part(payload["body"]["data"])
    texts = []
    for part in payload.get("parts", []) or []:
        texts.append(_extract_body(part))
    return "\n".join(t for t in texts if t)


def fetch_new_emails(gmail, query, processed_ids):
    resp = gmail.users().messages().list(userId="me", q=query, maxResults=25).execute()
    out = []
    for m in resp.get("messages", []):
        mid = m["id"]
        if mid in processed_ids:
            continue
        full = gmail.users().messages().get(userId="me", id=mid, format="full").execute()
        headers = {h["name"].lower(): h["value"] for h in full["payload"].get("headers", [])}
        out.append({
            "id": mid,
            "from": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "date": headers.get("date", ""),
            "body": _extract_body(full["payload"])[:12000],
        })
    return out


# ---------- claude parse + merge ----------
def parse_emails(client, emails, family, ledger, today):
    open_items = [
        {"id": i["id"], "title": i["title"], "due_date": i.get("due_date"),
         "event_dates": i.get("event_dates"), "status": i["status"]}
        for i in ledger["items"]
    ]
    system = (
        "You extract school events/assignments from New Covenant Academy emails for the Walker "
        "family and return STRICT JSON only. Piece together information that is scattered across "
        "an email or several emails into single items. Never duplicate something already in the "
        "existing ledger (match by title + child + date). Dismissed items must not be resurfaced."
    )
    schema = (
        '{"items":[{"id":"stable-kebab-slug","type":"assignment|project|spelling|memory-verse|'
        'extracurricular|notice","people":["hudson|reston|sean|jen"],"class":"...","title":"...",'
        '"description":"short; include word lists / verse text / parent actions","due_date":"YYYY-MM-DD|null",'
        '"event_dates":["YYYY-MM-DD"],"time":"HH:MM|null","location":"|null","confidence":0.0,'
        '"source_message_id":"...","updates_existing_id":"existing ledger id or null"}]}'
    )
    user = (
        f"TODAY: {today}\n\n"
        f"FAMILY CONFIG (who maps to which class):\n{json.dumps(family, indent=2)}\n\n"
        f"EXISTING LEDGER ITEMS (do not duplicate these):\n{json.dumps(open_items, indent=2)}\n\n"
        f"NEW EMAILS:\n{json.dumps(emails, indent=2)}\n\n"
        f"Return ONLY JSON matching this shape (no prose, no code fences):\n{schema}"
    )
    msg = client.messages.create(
        model=MODEL, max_tokens=8000,
        system=system, messages=[{"role": "user", "content": user}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1]).get("items", [])


# ---------- routing + calendar ----------
def target_calendars(item, calendars, people_cfg):
    """Map an item's people to calendar names present in calendars.yaml."""
    names = []
    for p in item.get("people", []):
        cal = (people_cfg.get(p) or {}).get("calendar")
        if cal and cal in calendars and cal not in names:
            names.append(cal)
    if not names:
        names = ["Family"] if "Family" in calendars else (["Other"] if "Other" in calendars else [])
    return names


def post_event(cal, calendar_id, item):
    title_people = "/".join((item.get("people") or []))
    summary = f"[{title_people}] {item['title']}" if title_people else item["title"]
    date = (item.get("event_dates") or [None])[0] or item.get("due_date")
    body = {"summary": summary, "description": (item.get("description", "") + "\n\n— Family Dashboard").strip()}
    if item.get("location"):
        body["location"] = item["location"]
    if item.get("time"):
        start = f"{date}T{item['time']}:00"
        end_dt = datetime.fromisoformat(start) + timedelta(hours=1)
        body["start"] = {"dateTime": start, "timeZone": "America/Chicago"}
        body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "America/Chicago"}
    else:
        end = (datetime.fromisoformat(date) + timedelta(days=1)).date().isoformat()
        body["start"] = {"date": date}
        body["end"] = {"date": end}
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": 1440}]}
    ev = cal.events().insert(calendarId=calendar_id, body=body).execute()
    return ev["id"]


# ---------- digest ----------
def build_digest(posted, held):
    lines = [f"📚 Family Dashboard — {datetime.now().strftime('%A, %b %-d')}"]
    if posted:
        lines.append("\nAdded to the calendar:")
        for it, cals in posted:
            when = (it.get("event_dates") or [it.get("due_date")])[0] or ""
            lines.append(f"• {it['title']} — {when} → {', '.join(cals)}")
    if held:
        lines.append("\nNeeds you:")
        for it in held:
            lines.append(f"• {it['title']} — {it.get('description','')}")
    if not posted and not held:
        lines.append("\nNothing new today.")
    return "\n".join(lines)


def send_slack(text):
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    requests.post(url, json={"text": text}, timeout=20).raise_for_status()


def send_email(gmail, text):
    to = os.environ.get("DIGEST_EMAIL_TO")
    if not to:
        return
    msg = MIMEText(text)
    msg["To"] = to
    msg["Subject"] = f"Family Dashboard — {datetime.now().strftime('%b %-d')}"
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    gmail.users().messages().send(userId="me", body={"raw": raw}).execute()


# ---------- main ----------
def main():
    family = load_yaml("family.yaml")
    calendars_cfg = load_yaml("calendars.yaml")
    policy = load_yaml("policy.yaml")
    calendars = {name: c["id"] for name, c in calendars_cfg["calendars"].items() if c.get("id") and c["id"] != "TODO"}
    people_cfg = family["people"]
    ledger = load_ledger()
    processed = set(ledger.get("processed_message_ids", []))
    today = datetime.now().strftime("%Y-%m-%d")

    gmail, cal = google_services()
    query = policy["ingest"]["query"]
    emails = fetch_new_emails(gmail, query, processed)
    print(f"Found {len(emails)} new school email(s).")

    posted, held = [], []
    if emails:
        client = Anthropic()  # ANTHROPIC_API_KEY from env
        items = parse_emails(client, emails, family, ledger, today)
        gate = policy["autopost"]
        for it in items:
            date = (it.get("event_dates") or [it.get("due_date")])[0]
            eligible = (
                it.get("confidence", 0) >= gate["min_confidence"]
                and (not gate["require_matched_person"] or it.get("people"))
                and (not gate["require_concrete_date"] or bool(date))
            )
            if eligible and date:
                cals = target_calendars(it, calendars, people_cfg)
                event_ids = {}
                for name in cals:
                    try:
                        event_ids[name] = post_event(cal, calendars[name], it)
                    except Exception as e:  # one calendar failing shouldn't sink the run
                        print(f"  ! post failed for {name}: {e}")
                it["status"], it["calendar_event_ids"] = "posted", event_ids
                posted.append((it, cals))
            else:
                it["status"] = "held"
                held.append(it)
            ledger["items"].append({k: it.get(k) for k in
                ("id", "type", "people", "class", "title", "description",
                 "due_date", "event_dates", "status", "confidence",
                 "calendar_event_ids", "source_message_id")})
        for e in emails:
            processed.add(e["id"])

    ledger["processed_message_ids"] = sorted(processed)
    digest = build_digest(posted, held)
    send_slack(digest)
    send_email(gmail, digest)
    save_ledger(ledger)
    print(f"Done. Posted {len(posted)}, held {len(held)}.")
    print(digest)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        sys.exit(1)
