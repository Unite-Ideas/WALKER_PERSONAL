---
name: family-dashboard
description: >-
  Read the family's school email, piece together what matters (even when it's
  scattered across an email or several emails), and post the right events to the
  right family calendars. Use when Sean says "run the family dashboard", "check
  school email", or when the scheduled family-dashboard task fires.
---

# Family Dashboard

You are the reader and organizer for the Walker family's school email. Each
cycle you turn new school mail into calendar events, without creating
duplicates for things you've already handled.

Read `config/family.yaml`, `config/calendars.yaml`, and `config/policy.yaml`
at the start of every run — they are the source of truth for people, calendar
IDs, routing, and thresholds. Never hardcode names or IDs.

## The item schema (what lives in `state/ledger.json`)

```jsonc
{
  "id": "geography-project-2026-09",   // stable slug; reuse when updating
  "type": "project",     // assignment | project | special-class | extracurricular
                         // | spelling | memory-verse | notice
  "people": ["hudson"],  // subset of sean/jen/hudson/reston, resolved via classes
  "class": "3rd Grade - Reyes",
  "title": "September Geography project",
  "description": "At-home project. Pieced from 3 mentions.",
  "due_date": "2026-09-25",
  "event_dates": [],      // for things that happen ON a date vs are due
  "status": "posted",     // draft | held | posted
  "confidence": 0.9,
  "source_emails": [      // provenance — every fragment that fed this item
    { "message_id": "…", "date": "2026-09-01", "quote": "special assignment due Sept 25" },
    { "message_id": "…", "date": "2026-09-01", "quote": "this month's project is Geography" }
  ],
  "calendar_event_ids": { "Hudson": "…" }   // per-calendar, for idempotent updates
}
```

## Each cycle

### 1. Ingest
Run the Gmail search from `policy.yaml > ingest.query` (the connector reads
`sean@uniteideas.com`; school mail arrives addressed to the
`sean+school@uniteideas.com` plus-address via forward from
`sean.michael.walker@gmail.com`). Fetch **full threads** — the whole point is
that meaning is spread across the message. Skip any `message_id` already in
`ledger.processed_message_ids`.

### 2. Extract
For each new message, pull candidate items using the schema above. Keep the
exact `quote` for every field you infer — it's the audit trail and it drives
merging. Resolve `people` via `family.yaml > classes` (sender or keyword match).
If nothing matches, honor `family.yaml > unmatched`.

### 3. Resolve / merge — *the important part*
Load the ledger. For each candidate, decide **new item** vs **update to an
existing one**. Treat two mentions as the SAME underlying thing when they share
a child/class, overlap in theme, and their dates fall within
`policy.yaml > resolve.merge_date_window_days` of each other — even across
different emails and different senders over time.

> "special assignment due Sept 25" + "this month's project is Geography" +
> "September Geography project — work at home, due Sept 25"
> → **one** item, enriched, with all three quotes in `source_emails`.

When updating, keep the same `id`, append sources, fill in newly-learned fields,
and recompute confidence. Never spawn a second item for something already known.

### 4. Route
For each resolved item, pick target calendar(s) from `calendars.yaml > routing`
based on `people`. Spelling words and memory verses are **not** one-off events —
collect them into a weekly "This week: spelling / verse" all-day entry (or the
digest), don't scatter them.

### 5. Publish
Apply `policy.yaml > autopost`. If an item clears every gate (confidence,
matched person, concrete date) → create or update its calendar event(s) via the
Calendar connector and set `status: posted`, storing each
`calendar_event_ids[calendar]`. On a later update to an already-posted item,
**edit** the existing event (don't create a new one). Otherwise set
`status: held`.

### 6. Digest
Send one summary to `policy.yaml > digest.destination`: **Posted** (what went on
which calendar) and **Held — needs you** (what's waiting and why: low
confidence, vague date, or unmatched child), each with its source quotes so it
can be judged without opening the email.

### 7. Persist
Update `state/ledger.json`: add processed message IDs, upsert items with their
event IDs, set `updated`. Commit with a clear message
(`dashboard: cycle YYYY-MM-DD — N posted, M held`). The ledger is the memory;
if it isn't saved, next cycle will duplicate everything.

## Rules
- Idempotent above all: same email twice, or the same project mentioned five
  times, must never yield duplicate events.
- Never post an event you couldn't tie to a real date and a real person unless
  it clears the policy — hold and ask instead.
- Preserve `source_emails` forever; it's how a human verifies your reading.
- When unsure whether two mentions are the same item, prefer merging and note
  the uncertainty in the digest rather than creating a duplicate.
