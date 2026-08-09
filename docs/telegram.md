<div align="center">

# 🤖 Telegram Bot

### InstaReport — Bot Reference

[← Back to README](../README.md) &nbsp;·&nbsp; [Docs Index](index.md)

</div>

---

## Overview

The official Telegram bot — [@instaReportV2Bot](https://t.me/instaReportV2Bot) — lets you execute supported operations directly from your phone. It is **cloud-hosted** and designed to operate 24/7.

> 💡 A **Discord bot** with the same engine, backend and license is also available — see the [Discord Bot reference](discord.md).

Premium users unlock the full feature set through their activated license.

---

## Getting Started

1. Open the official bot: <https://t.me/instaReportV2Bot>
2. Send `/start` to show the main menu.
3. Send `/activate CODE` with your license key.
4. Send `/status` to confirm your configuration and stats.

---

## User Commands

| Command | Description |
|---------|-------------|
| `/start` | Show main menu |
| `/menu` | Open main menu |
| `/activate CODE` | Activate license |
| `/status` | Current config & stats |
| `/report <target>` | Start a report |
| `/stop` | Stop all reports |
| `/accounts` | Manage accounts |
| `/config` | View / edit settings |
| `/history [n]` | Recent runs |
| `/schedule` | Auto-report scheduling |
| `/favorites` | Saved targets |
| `/lookup` | Scrape public profile stats |
| `/unban` | Submit an appeal to a platform |
| `/balance` | Check balance |
| `/refund` | Request a refund |
| `/help` | Show this message |

---

## Admin Commands

Admin commands are reserved for authorized support staff.

| Command | Description |
|---------|-------------|
| `/users` | Manage users |
| `/ban` | Ban a user |
| `/broadcast` | Broadcast a message |
| `/banpay` | Manage ban/pay orders |
| `/admin_pending` | Review pending requests |
| `/admin_approve` | Approve a request |
| `/admin_reject` | Reject a request |
| `/set_balance` | Set user balance |
| `/migrate_balances` | Migrate balances |

---

## Scheduling

The bot supports automatic reporting through the `/schedule` command.

- **Status:** ON / OFF
- **Time:** daily start time in 24h `HH:MM` format
- **Repeat:** whether the schedule repeats each day
- **Interval:** repeat interval in minutes (30–1440)

The scheduler repeats the **last report configuration** at the configured time each day.

---

## Account Management

- `/accounts` — manage the accounts used for reporting.
- `/config` — view and edit engine settings (workers, headless, safe mode, stealth, retries, etc.).

---

## Lookup

The `/lookup` command scrapes **public profile statistics** for supported platforms without requiring the desktop app.

---

## Favorites

The `/favorites` command saves frequently used targets for one-tap reuse in later reports.

---

## Frequently Asked Questions

### Do I need the desktop app to use the bot?

No. The bot is fully cloud-hosted. A license is required for premium operations.

### Can I use the bot on multiple devices?

Yes — the bot runs on Telegram and is accessible from any device with your account.

### Is the bot online 24/7?

The bot is designed to operate 24/7 from the cloud.

---

## Related

- [Discord Bot](discord.md)
- [Installation Guide](installation.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](../FAQ.md)

---

<div align="center">

Copyright © 2021 – 2026 iEsclyDev. All rights reserved.

</div>
