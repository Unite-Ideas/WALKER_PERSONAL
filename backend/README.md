# Family Dashboard — backend (scheduled, self-hosted)

A plain Python job that runs the daily cycle **outside** Claude Cowork, so it
isn't subject to the org's "Always allow" policy. It authenticates with its own
Google / Anthropic / Slack credentials.

```
Gmail (read school mail)  ─┐
                           ├─► Claude API (extract + merge vs. ledger)
state/ledger.json (memory)─┘        │
                                    ├─► Google Calendar (post events)
                                    ├─► Slack + email (digest)
                                    └─► commit updated state/ledger.json
```

## One-account simplification
The school mail *arrives* at **sean.michael.walker@gmail.com**, which also owns
the six calendars — so the backend uses that **one** Google account for both
reading mail and writing calendars. No forwarding, no plus-address, no uniteideas
hop needed anymore (that was only to feed Claude's connector).

## What you need to set up (one time)

### 1. Google credentials → run `auth_setup.py`
Follow the header comment in `auth_setup.py`. It gives you three values.

### 2. Anthropic API key
console.anthropic.com → API keys → create one.

### 3. Slack incoming webhook (for the digest)
api.slack.com/apps → Create App → **Incoming Webhooks** → add one to the channel
you want the digest in (e.g. a private `#family` channel). Copy the webhook URL.
*(A channel, not a DM — webhooks post to channels. If you'd rather it DM you, say
so and we'll switch to a Slack bot token instead.)*

### 4. Put them all in GitHub repo Secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | From |
|--------|------|
| `GOOGLE_CLIENT_ID` | auth_setup.py |
| `GOOGLE_CLIENT_SECRET` | auth_setup.py |
| `GOOGLE_REFRESH_TOKEN` | auth_setup.py |
| `ANTHROPIC_API_KEY` | Anthropic console |
| `SLACK_WEBHOOK_URL` | Slack app |
| `DIGEST_EMAIL_TO` | e.g. `sean.michael.walker@gmail.com` |

## Going live
- The schedule (`.github/workflows/family-dashboard.yml`) only fires from the
  repo's **default branch** — so this has to be merged to the default branch
  before the 6 AM cron runs. Until then, run it by hand from the **Actions** tab
  (**Run workflow**) on any branch to test.
- Config still comes from `config/*.yaml`; memory is `state/ledger.json` (shared
  with everything we've already built).

## Files
- `run.py` — the pipeline entry point *(being written next)*
- `auth_setup.py` — one-time Google refresh-token helper
- `requirements.txt` — Python deps
