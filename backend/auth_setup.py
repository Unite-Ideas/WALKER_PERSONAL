"""
One-time helper: mint a Google refresh token for the Family Dashboard backend.

Run this ONCE on your own computer, signed in as sean.michael.walker@gmail.com
(the account that receives the school email AND owns the six calendars).

Setup before running:
  1. Go to console.cloud.google.com -> create a project (e.g. "family-dashboard").
  2. APIs & Services -> Enable APIs -> enable "Gmail API" and "Google Calendar API".
  3. APIs & Services -> OAuth consent screen -> External -> add yourself as a Test user.
  4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID ->
     Application type: "Desktop app". Download the JSON, save it next to this file
     as  client_secret.json.
  5. pip install -r requirements.txt
  6. python auth_setup.py

A browser window opens; sign in as sean.michael.walker and approve. The script
prints three values — put them into GitHub repo Secrets (Settings -> Secrets and
variables -> Actions):
     GOOGLE_CLIENT_ID
     GOOGLE_CLIENT_SECRET
     GOOGLE_REFRESH_TOKEN
"""

import json
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",  # read school mail
    "https://www.googleapis.com/auth/gmail.send",      # send the email digest
    "https://www.googleapis.com/auth/calendar",        # read/write the 6 calendars
]

HERE = os.path.dirname(os.path.abspath(__file__))
CLIENT_FILE = os.path.join(HERE, "client_secret.json")


def main():
    if not os.path.exists(CLIENT_FILE):
        raise SystemExit(
            f"Missing {CLIENT_FILE}. Download your OAuth 'Desktop app' client JSON "
            "from Google Cloud Console and save it there (see the header comment)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")  # forces a refresh_token

    with open(CLIENT_FILE) as f:
        c = json.load(f)["installed"]

    print("\n=== Copy these into GitHub repo Secrets ===\n")
    print("GOOGLE_CLIENT_ID     =", c["client_id"])
    print("GOOGLE_CLIENT_SECRET =", c["client_secret"])
    print("GOOGLE_REFRESH_TOKEN =", creds.refresh_token)
    print("\n(Keep these private — the refresh token is a long-lived credential.)")


if __name__ == "__main__":
    main()
