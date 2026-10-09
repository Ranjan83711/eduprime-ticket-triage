"""One-time: authorise the app to send mail as the support Gmail account, via the Gmail API.

    cd backend && python -m scripts.gmail_auth

Needs GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET (a Google Cloud "Desktop app" OAuth client) in .env.
Opens the browser, you sign in as the support account and allow "Send email on your behalf",
and the refresh token is written straight into .env. It is never printed.
"""
import http.server
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import httpx

from app.config import GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, ROOT_DIR

PORT = 8765
REDIRECT = f"http://localhost:{PORT}/"
SCOPE = "https://www.googleapis.com/auth/gmail.send"  # send only: the app cannot read or delete mail with it


def save_to_env(key: str, value: str) -> None:
    env = ROOT_DIR / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    line = f"{key}={value}"
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    env.write_text(text, encoding="utf-8")


def main() -> None:
    if not (GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET):
        sys.exit("Set GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET in .env first.")
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] != state:
                self.send_response(400); self.end_headers(); self.wfile.write(b"State mismatch."); return
            result["code"] = q.get("code", [None])[0]
            result["error"] = q.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done. You can close this tab and go back to the terminal.</h2>")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", PORT), Handler)
    thread = threading.Thread(target=server.handle_request)
    thread.start()

    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": GMAIL_CLIENT_ID, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
    })
    print("Opening the browser. Sign in as the SUPPORT Gmail account and click Allow.")
    print("If it doesn't open, paste this URL into the browser:\n" + url)
    webbrowser.open(url)
    thread.join(timeout=300)
    server.server_close()

    if not result.get("code"):
        sys.exit(f"No authorisation received ({result.get('error') or 'timed out'}).")
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "code": result["code"], "client_id": GMAIL_CLIENT_ID, "client_secret": GMAIL_CLIENT_SECRET,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    })
    if r.status_code != 200 or "refresh_token" not in r.json():
        sys.exit(f"Token exchange failed: {r.status_code} {r.text[:200]}")
    save_to_env("GMAIL_REFRESH_TOKEN", r.json()["refresh_token"])
    print("Saved GMAIL_REFRESH_TOKEN to .env (not printed). Sending will now use the Gmail API.")


if __name__ == "__main__":
    main()
