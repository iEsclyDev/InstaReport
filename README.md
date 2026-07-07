# InstaReport — Linux Guide

This guide covers two things:

1. **Hosting InstaReport on a Linux server** (VPS, dedicated server, etc.)
2. **Obfuscating the code** to protect it from being read or modified

---

## 1. Hosting on Linux

### Requirements

- A Linux server (Ubuntu 22.04 / Debian 12 recommended)
- Python 3.10 or newer
- At least 2 GB RAM (4 GB recommended)
- A desktop environment is **not** required — the app runs headless

### Step 1 — Connect to your server

```bash
ssh root@your-server-ip
```

### Step 2 — Install system packages

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl
```

### Step 3 — Upload or clone InstaReport

Upload the zip via SCP from your local machine:

```bash
# On your local machine:
scp InstaReport-Linux.zip root@your-server-ip:/root/
```

Or extract it on the server:

```bash
# On the server:
cd /root
unzip InstaReport-Linux.zip -d instareport
cd instareport
```

### Step 4 — Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### Step 5 — Configure

Copy the example config (or let the app create one on first run):

```bash
# The config will be created automatically at:
# ~/.local/share/instareport/instareport_config.json
```

Environment variables can be placed in a `.env` file:

```bash
echo 'LICENSE_KEY=your-key-here' >> .env
echo 'INSTAREPORT_DATA=/root/instareport_data' >> .env
```

### Step 6 — Run

```bash
# GUI mode (requires X11 / VNC):
./run.sh

# CLI mode (headless, no screen needed):
python3 main.py --cli

# Headless browser mode:
python3 main.py --headless
```

---

### Running 24/7 (background)

#### Option A — tmux (simplest)

```bash
apt install -y tmux
tmux new -s instareport
python3 main.py --headless
# Press Ctrl+B then D to detach
# Re-attach later with: tmux attach -t instareport
```

#### Option B — systemd service (auto-start on boot)

Create a service file:

```bash
nano /etc/systemd/system/instareport.service
```

Paste this (adjust paths to match your setup):

```ini
[Unit]
Description=InstaReport Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/instareport
Environment=INSTAREPORT_DATA=/root/instareport_data
ExecStart=/root/instareport/venv/bin/python /root/instareport/main.py --headless
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
systemctl daemon-reload
systemctl enable instareport
systemctl start instareport

# Check status:
systemctl status instareport

# View logs:
journalctl -u instareport -f
```

---

## 2. Code Obfuscation

Obfuscation makes the Python source code hard to read or reverse-engineer. This is useful if you distribute InstaReport to clients and want to protect your logic.

### Option A — PyArmor (recommended)

[PyArmor](https://pyarmor.readthedocs.io/) obfuscates `.py` files into encrypted bytecode.

#### Install

```bash
pip install pyarmor
```

#### Obfuscate the whole project

```bash
cd /root/instareport

# Obfuscate everything in the instareport/ folder
pyarmor gen -r instareport/

# Obfuscate entry scripts too
pyarmor gen main.py main_cli.py main_gui.py
```

This creates obfuscated files **in-place** or in a `dist/` folder depending on your PyArmor version.

#### Test it

```bash
python3 main.py --headless
```

#### Distribute

Zip the obfuscated folder and send it to your client. They **must** install PyArmor to run it:

```bash
pip install pyarmor
python3 main.py
```

### Option B — Compile to .pyc only

Remove the `.py` source and keep only compiled `.pyc` files:

```bash
cd /root/instareport
python3 -m compileall .
find . -name '*.py' -delete
```

This is **not true obfuscation** — `.pyc` can be decompiled — but it stops casual reading.

### Option C — Cython (advanced)

Compile Python to native `.so` shared libraries:

```bash
pip install cython
# Then write a setup.py to compile each module
```

This is the strongest protection but requires more setup.

---

### Quick comparison

| Method | Protection level | Ease | Client needs |
|--------|----------------|------|-------------|
| PyArmor | High | Easy | `pip install pyarmor` |
| .pyc only | Low | Trivial | Nothing |
| Cython | Very high | Moderate | Nothing |

---

## Need help?

- Open an issue on the project repository
- Contact support via the Telegram channel
