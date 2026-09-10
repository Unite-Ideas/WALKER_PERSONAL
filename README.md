# Walker Family Dashboard

Reads school email, figures out what actually matters (piecing together
information that's scattered across an email or several emails), and posts
the right events to the right family calendars — automatically for
high-confidence items, with a review digest for the rest.

## The core idea

The hard problem is **reading comprehension + memory**, not parsing. School
emails spread one thing across many mentions:

> "special assignment due Sept 25" … "this month's project is Geography" …
> "keep an eye out for the September Geography project — your child works on
> this at home, due Sept 25"

Those are **one** project, not three. So the design leans on Claude to *read*,
and adds the one thing a raw model lacks: a **persistent ledger** of everything
it has already seen, so a new email *updates* an existing item instead of
creating a duplicate.

## Pipeline

```
INGEST  →  EXTRACT  →  RESOLVE/MERGE  →  ROUTE  →  PUBLISH  →  DIGEST
 (email)   (candidate   (fragments →     (which   (calendar    (what I
           items)        one real thing)  people)  events)      did/held)
                              ↑________________________________________|
                                     state/ledger.json (memory)
```

1. **Ingest** — read new school mail (see "Accounts" below).
2. **Extract** — pull structured candidate items from each message.
3. **Resolve/Merge** — reconcile candidates against the ledger; collapse
   scattered mentions into one canonical item, keeping every source snippet.
4. **Route** — decide which calendar(s) each item belongs on, per person.
5. **Publish** — high-confidence items post automatically; the rest are held.
6. **Digest** — a summary of what was posted and what's waiting for approval.

## Accounts (important)

Two Google accounts are involved. Each Claude connector logs into one.

| Role | Account |
|------|---------|
| School mail arrives here; **Calendar** connector writes here | `sean.michael.walker@gmail.com` |
| Claude **Gmail** connector reads here | `sean@uniteideas.com` |

**Email bridge:** school mail is sent to the **`sean+school@uniteideas.com`**
plus-address — either auto-forwarded from `sean.michael.walker` or forwarded by
hand. It lands in `sean@uniteideas.com`, and the dashboard finds it by that
address (`deliveredto:`/`to:`), so **no Gmail label is required**. A label is
optional and, if wanted, must be created as a filter *inside* the
`sean@uniteideas.com` account (filters only act on the account you're signed
into). (If Jen receives school mail at a separate address later, she forwards it
to the same plus-address.)

The `walkerfamilyspace@gmail.com` account isn't used — it was an early idea,
now unnecessary since the school mail and the calendars already share one
account.

**Calendars:** the six calendars (`Sean`, `Jen`, `Hudson`, `Reston`, `Family`,
`Other`) must be owned by — or shared with "Make changes to events" to —
`sean.michael.walker@gmail.com`, so the connector can write to them.

## Trust level

**Auto-add high-confidence.** An item posts automatically only when it has a
matched child/person, a concrete date, and confidence ≥ the threshold in
`config/policy.yaml`. Everything else waits in the digest for a tap.

## Layout

```
config/
  family.yaml      people + which teacher/class maps to which child
  calendars.yaml   the six calendar IDs + routing rules
  policy.yaml      confidence thresholds, digest destination, schedule
state/
  ledger.json      every known item + processed message IDs (the memory)
.claude/skills/family-dashboard/
  SKILL.md         the operating spec Claude runs each cycle
```

## Roadmap

- **Phase 0 — Foundations (this scaffold):** config, ledger, skill spec.
- **Phase 1 — Read + digest, no writes:** build trust in the reader on real mail.
- **Phase 2 — Auto-add high-confidence:** confident items post; rest held.
- **Phase 3 — The board:** point a self-hosted Skylight-style display at the
  same ledger + calendars.

## Status: Phase 0 — needs from Sean

- [x] Create the six calendars on `sean.michael.walker@gmail.com` and populate
      `config/calendars.yaml` with their IDs. *(Done 2026-09-10, Central time.)*
- [ ] Fill the `classes:` section of `config/family.yaml` (teacher names,
      class names, sender addresses/domains) so mail routes to the right child.
      *(Send a sample school email and Claude fills this in.)*
- [x] Forward school mail to `sean+school@uniteideas.com` (manual works; auto-
      forward from `sean.michael.walker` pending Google confirmation). No label
      needed — dashboard keys on the plus-address. *(Confirmed reading 2026-09-10.)*
- [ ] Choose the digest destination in `config/policy.yaml` (Slack or email).
