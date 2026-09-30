# Integrations — Telegram bot + Gmail (Windows & macOS)

Secrets never sit in a file: bot token, Google client secret and Google refresh token go to
**Windows Credential Manager / macOS Keychain** (`vault.py`, via `keyring`). Customize →
Integrations shows which store is in use. (macOS may ask once to allow Keychain access →
Always Allow.)

## Telegram
1. Telegram → @BotFather → `/newbot` → copy the token.
2. Customize → Integrations → paste token, tick *enabled*, **Save & restart**.
3. The panel shows `/pair 123456`; send that to your bot. Only that chat is answered from then on.

## Gmail — "Sign in with Google" (read-only)
One-time Google setup (Google requires it for every desktop app; free):
1. https://console.cloud.google.com → new project.
2. APIs & Services → Library → enable **Gmail API**.
3. OAuth consent screen → External → add your Gmail as a **test user**
   (publish to "In production" for personal use to avoid the 7-day token expiry; the
   "unverified app" warning is normal for your own project — Advanced → continue).
4. Credentials → Create credentials → OAuth client ID → **Desktop app**.
5. Paste the Client ID (and secret) in Customize → Integrations → Save → **Sign in with Google**.
   Your browser opens Google's own page; Night Crew only receives a revocable token.
6. Add allowed senders (`name@site.com` or `@site.com`), tick *enabled*, Save.

Revoke any time: **Sign out** in the panel, or myaccount.google.com/permissions.
Email text is only forwarded to you as a notification — never executed.
