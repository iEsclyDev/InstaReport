<div align="center">

# 🎮 Discord Bot

### InstaReport — Discord Bot Reference

[← Back to README](../README.md) &nbsp;·&nbsp; [Docs Index](index.md)

</div>

---

## Overview

The official InstaReport **Discord bot** provides the same operations as the [Telegram bot](telegram.md), directly from your Discord server. It is **cloud-hosted** and designed to operate 24/7.

It shares the same engine, licensing and backend as the Telegram bot — **activate your license once and use it from either platform.**

**Join the official server:** <https://discord.com/invite/v6ebT5aFx>

Premium users unlock the full feature set through their activated license.

---

## Getting Started

1. Join the official server: <https://discord.com/invite/v6ebT5aFx>
2. Run `/start` to see the welcome screen.
3. Run `/activate` and enter your license code.
4. Run `/status` to confirm your configuration and license.

> The bot can also be driven from **DMs** using the same commands (e.g. `report <target>`, `balance`, `status`).

---

## User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome screen |
| `/menu` | Main control panel |
| `/activate` | Activate your license code |
| `/report <target>` | Start a report |
| `/stop` | Stop your active report |
| `/resume` | Resume your last interrupted campaign |
| `/accounts` | Manage your accounts |
| `/config` | View / edit report settings |
| `/status` | View config & license info |
| `/history` | Recent run logs |
| `/favorites` | Your saved favorite targets |
| `/fav add <target>` | Add a favorite target |
| `/fav del <target>` | Remove a favorite target |
| `/balance` | Check your balance |
| `/refund <amount>` | Request a refund / withdrawal (min $100) |
| `/refundstatus` | Refund request history |
| `/banpay` | Purchase a ban/unban via crypto |
| `/banstatus` | Ban/unban request history |
| `/help` | List all commands |

---

## Admin Commands

Admin commands are reserved for authorized staff.

| Command | Description |
|---------|-------------|
| `/admin pending` | List pending ban/refund requests |
| `/admin approve <id>` | Approve a ban or refund request |
| `/admin reject <id>` | Reject a ban or refund request |
| `/setbalance <user> <amount>` | Set a user's balance |
| `/migrate` | Credit legacy approved ban requests |
| `/users` | List all licensed users |
| `/ban <user>` | Revoke a user's license |
| `/broadcast <msg>` | DM all licensed users |

---

## Features

### Reporting

Run and monitor reporting campaigns from Discord:
- `/report <target>` — confirm and launch a report
- `/resume` — resume an interrupted campaign from saved progress
- `/stop` — cancel an active report

### Account Management

- `/accounts` — manage the accounts used for reporting
- `/config` — view and edit engine settings (workers, headless, safe mode, stealth, retries, etc.)

### Balance, Ban & Refund

- `/balance` — check your earned balance
- `/banpay` — purchase a ban/unban service via crypto
- `/refund <amount>` — withdraw up to your balance (min $100)

### Favorites & History

- `/favorites` and `/fav add|del` — save frequently used targets
- `/history` — review your recent run logs

---

## 2FA / OTP and Captcha

During a report, the bot DM's you directly to collect **2FA / OTP codes** and to alert you when a **captcha** needs solving — mirroring the Telegram bot's behaviour.

---

## Frequently Asked Questions

### Do I need the desktop app to use the bot?

No. The bot is fully cloud-hosted. A license is required for premium operations. You manage accounts and configuration through the bot itself.

### Is the Discord bot the same as the Telegram bot?

It uses the **same engine and backend** and exposes the same core features. It uses Discord-native slash commands and embedded messages.

### Do I need a separate license for Discord?

No — your license works across both the Telegram and Discord bots.

### Is the bot online 24/7?

The bot is designed to operate 24/7 from the cloud.

---

## Related

- [Telegram Bot](telegram.md)
- [Installation Guide](installation.md)
- [Architecture](architecture.md)
- [Troubleshooting](troubleshooting.md)
- [FAQ](../FAQ.md)

---

<div align="center">

Copyright © 2021 – 2026 iExly. All rights reserved.

</div>