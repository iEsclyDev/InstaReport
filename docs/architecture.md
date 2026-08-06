<div align="center">

# 🏗 Architecture

### InstaReport — Technical Overview

[← Back to README](../README.md) &nbsp;·&nbsp; [Docs Index](index.md)

</div>

---

## Overview

InstaReport is a cross-platform social media automation platform. The architecture is built around a **core reporting engine** wrapped by multiple frontends: a desktop application, a CLI and a cloud-hosted Telegram bot.

```
┌───────────────────────────────────────────────────────────────┐
│                         Frontends                              │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────────┐    │
│   │ Desktop App  │   │ CLI          │   │ Telegram Bot   │    │
│   │ (Windows/Linux) │  (--cli flag) │   │ (@iescly)      │    │
│   └──────┬───────┘   └──────┬───────┘   └───────┬────────┘    │
│          └──────────────────┼──────────────────┘             │
│                             ▼                                  │
│                  ┌─────────────────────┐                       │
│                  │  Reporting Engine   │                       │
│                  │  (browser drivers,  │                       │
│                  │   workers, timing)  │                       │
│                  └──────────┬──────────┘                       │
│                             ▼                                  │
│   ┌───────────┐  ┌─────────────┐  ┌──────────────────────┐     │
│   │  Proxies  │  │ 2FA / OTP   │  │ Licensing API        │     │
│   │  pool     │  │ collection  │  │ (iescly.duckdns.org) │     │
│   └───────────┘  └─────────────┘  └──────────────────────┘     │
└───────────────────────────────────────────────────────────────┘
```

---

## Core Engine

The engine handles all automation logic and is shared across frontends.

### Timing & Anti-Detection

- All timing constants (`T_PAGE_LOAD`, `T_POST_LOGIN`, `T_POST_CLICK`, `T_REFRESH_WAIT`, `T_TYPE_DELAY`, `T_TELEGRAM_OTP`, etc.) are routed through a delay helper that applies **±30% randomized jitter** to mimic human behaviour.
- **Exponential backoff** on retry: `min(10 × 2^attempt, 300s)` plus random jitter, replacing fixed linear waits. This greatly improves success rate under rate limits.
- **Proxy blacklisting** — proxies that fail repeatedly (threshold exceeded) are removed from rotation automatically.

### Batch Processing

- Configurable worker count (max batch workers enforced).
- **Account health pre-check** — every account is tested for a valid login session before each campaign run; dead accounts are skipped automatically.
- **Bulk target import** — load targets from a `.txt` file (one per line, `#` for comments).
- **Campaign resume** — campaign progress (targets completed, success count) is persisted to **SQLite**, enabling resume in a future release.

### Supported Platforms & Reasons

The engine supports reporting across **11 platforms**: Instagram, YouTube, X (Twitter), Telegram, Discord, Reddit, TikTok, Facebook, Snapchat, Threads and Gmail.

**8 report reasons** are available: Spam, Harassment, Impersonation, Hate speech, Nudity, Violence, Misinformation and Scam/Fraud — with localized wording for multiple languages (e.g. English, Spanish, French, German, Portuguese).

---

## Desktop Application

- Standalone binaries built with **Nuitka** for Windows and Linux.
- Frozen binaries include static imports and guards so the app runs without a Python runtime.
- On first run, the app creates an isolated `.venv` (no system Python pollution).
- `--debug`, `--headless`, `--no-dep-check` and `--cli` flags control runtime behaviour.
- Auto-update check on startup against GitHub Releases.

---

## CLI

The same engine can be driven from a terminal via the `--cli` flag, enabling headless and scripted operation.

---

## Telegram Bot

- Cloud-hosted, built with `python-telegram-bot`.
- Conversation-based flows for reporting, scheduling, account management and license activation.
- Scheduler repeats the last report configuration daily at a configured time.
- Admin command set for user management and moderation.
- Integrates with the engine via the same backend.

---

## Licensing System

- Licenses are validated **online** against the licensing API.
- Each activation sends the license key and a device **hardware ID** (derived from platform, machine and MAC) to `/licenses/validate`.
- The API returns validity, plan and expiry.
- Local license metadata is cached in a `user_license.dat` file and re-validated on startup.

### Supported Stack (Bot backend)

- `python-telegram-bot` >= 20
- `discord.py` >= 2.4
- `playwright` + `playwright-stealth`
- `cryptography`
- `requests` / `aiohttp`

---

## Security Notes

- Local credential storage uses **PBKDF2 with 480,000 iterations**.
- OTP collection has a **120-second timeout** window.
- Never share license keys or hardware IDs publicly — see [SECURITY.md](../SECURITY.md).

---

## Related

- [Installation Guide](installation.md)
- [Telegram Bot](telegram.md)
- [Troubleshooting](troubleshooting.md)
- [SECURITY.md](../SECURITY.md)

---

<div align="center">

Copyright © 2021 – 2026 iExly. All rights reserved.

</div>
