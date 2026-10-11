"""Send email through the Gmail API (local runs, where no Gmail connector exists).

Scope is gmail.send only: this can send mail as the owner but cannot read, label or
delete anything. The OAuth client and token live outside the repo:

  DH_GMAIL_CLIENT  OAuth client JSON (desktop app)    default ~/.claude/atc-gmail-client.json
  DH_GMAIL_TOKEN   saved token, created by --auth     default ~/.claude/dealhunter-gmail-token.json
"""

import base64
import os
from email.mime.text import MIMEText

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CLAUDE_DIR = os.path.join(os.path.expanduser("~"), ".claude")
CLIENT = os.environ.get("DH_GMAIL_CLIENT") or os.path.join(CLAUDE_DIR, "atc-gmail-client.json")
TOKEN = os.environ.get("DH_GMAIL_TOKEN") or os.path.join(CLAUDE_DIR, "dealhunter-gmail-token.json")


class AuthRequired(RuntimeError):
    pass


def creds(interactive: bool = False):
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    c = Credentials.from_authorized_user_file(TOKEN, SCOPES) if os.path.exists(TOKEN) else None
    if c and c.expired and c.refresh_token:
        try:
            c.refresh(Request())
        except RefreshError:
            c = None
    if not c or not c.valid:
        if not interactive:
            raise AuthRequired("Gmail send token missing or revoked: run `python -m dealhunter email --auth`.")
        from google_auth_oauthlib.flow import InstalledAppFlow

        c = InstalledAppFlow.from_client_secrets_file(CLIENT, SCOPES).run_local_server(port=0)
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(c.to_json())
    return c


def send(to: str, subject: str, body: str) -> str:
    from googleapiclient.discovery import build

    msg = MIMEText(body, "plain", "utf-8")
    msg["To"], msg["Subject"] = to, subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc = build("gmail", "v1", credentials=creds(), cache_discovery=False)
    return svc.users().messages().send(userId="me", body={"raw": raw}).execute()["id"]
