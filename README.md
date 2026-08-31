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

**Email bridge:** `sean.michael.walker` auto-forwards school mail into
`sean@uniteideas.com` under a **`School`** label that skips the inbox. The
dashboard reads `label:School`. (If Jen receives school mail at a separate
address later, she forwards it to `sean.michael.walker` and the same rule
carries it through.)

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

- [ ] Create the six calendars on `sean.michael.walker@gmail.com`, then have
      Claude populate `config/calendars.yaml` with their IDs.
- [ ] Fill the `classes:` section of `config/family.yaml` (teacher names,
      class names, sender addresses/domains) so mail routes to the right child.
- [ ] Set up the `sean.michael.walker → sean@uniteideas.com` forward + `School`
      filter (from the school's sender domain), skipping the inbox.
