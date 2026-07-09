# napcat-login-watchdog

Standalone watchdog for NapCat login state. It checks service health, OneBot connectivity, OneBot
HTTP API account status, NapCat login markers, and sends email alerts with fresh QR recovery
helpers.

## Features

- Checks systemd status for the bot service and `napcat.service`.
- Checks the bot TCP port.
- Checks OneBot reverse WebSocket connection with `ss`.
- Optionally calls NapCat OneBot HTTP API `get_login_info` and `get_status`.
- Scans recent journal logs for explicit offline, login-expired, QR, or manual verification markers.
- Sends an offline email only when state changes from healthy to unhealthy.
- Sends an optional recovery email when state returns to healthy.
- Attaches the newest fresh NapCat QR image when available.
- Can refresh QR by authorized IMAP replies.
- Can refresh QR by a tokenized click link webhook.

## Install

With conda:

```bash
cd /opt
git clone git@github.com:DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
conda create -n napcat-login-watchdog python=3.11 -y
/opt/miniconda3/envs/napcat-login-watchdog/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

With a plain Python virtual environment:

```bash
cd /opt
git clone git@github.com:DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
python3.11 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set SMTP credentials, alert recipients, service names, and QR paths.

## Configuration Guide

### Already Running With systemd

This is the default mode. Set the service names and bot port:

```bash
WATCHDOG_SERVICE_CHECK_MODE=systemd
WATCHDOG_BOT_SERVICE=qq-rolebot.service
WATCHDOG_NAPCAT_SERVICE=napcat.service
WATCHDOG_HOST=127.0.0.1
WATCHDOG_PORT=8080
```

### Docker, Compose, pm2, supervisor, or Manual Start

Use command checks when NapCat or your bot is not managed by systemd:

```bash
WATCHDOG_SERVICE_CHECK_MODE=command
WATCHDOG_BOT_CHECK_COMMAND='test "$(docker inspect --format="{{.State.Running}}" qq-rolebot)" = true'
WATCHDOG_NAPCAT_CHECK_COMMAND='test "$(docker inspect --format="{{.State.Running}}" napcat)" = true'
```

For Compose logs, replace journalctl with a custom log command:

```bash
WATCHDOG_LOG_COMMAND='docker logs --since {minutes}m napcat'
```

Supported placeholders are `{minutes}`, `{since}`, `{bot_service}`, and `{napcat_service}`.

If you only want to check the OneBot HTTP API and bot TCP port, skip service checks:

```bash
WATCHDOG_SERVICE_CHECK_MODE=none
```

### No Reverse WebSocket Socket Check

Some environments do not have `ss`, or the OneBot connection is hidden inside a container network.
Disable the socket check and rely on OneBot HTTP API instead:

```bash
WATCHDOG_ONEBOT_CONNECTION_CHECK=none
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
```

## OneBot HTTP API

For reliable account-state detection, configure NapCat with an HTTP server bound to localhost:

```json
{
  "enable": true,
  "name": "napcat-login-watchdog",
  "host": "127.0.0.1",
  "port": 3001,
  "enableCors": false,
  "enableWebsocket": false,
  "messagePostFormat": "array",
  "token": "same-onebot-token",
  "debug": false
}
```

Then set:

```bash
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
WATCHDOG_ONEBOT_HTTP_API_BASE=http://127.0.0.1:3001
WATCHDOG_ONEBOT_HTTP_API_TOKEN=same-onebot-token
```

Do not expose the OneBot HTTP API to the public internet.

## Email Providers

QQ Mail with authorization code:

```bash
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_SSL=true
SMTP_USER=your@qq.com
SMTP_PASSWORD=qq-mail-authorization-code
ALERT_EMAIL_FROM=your@qq.com
ALERT_EMAIL_TO=admin@example.com
IMAP_HOST=imap.qq.com
IMAP_PORT=993
IMAP_USER=your@qq.com
IMAP_PASSWORD=qq-mail-authorization-code
```

Gmail with app password:

```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SSL=false
SMTP_STARTTLS=true
SMTP_USER=your@gmail.com
SMTP_PASSWORD=gmail-app-password
ALERT_EMAIL_FROM=your@gmail.com
ALERT_EMAIL_TO=admin@example.com
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your@gmail.com
IMAP_PASSWORD=gmail-app-password
```

Outlook or Microsoft 365:

```bash
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_SSL=false
SMTP_STARTTLS=true
SMTP_USER=your@outlook.com
SMTP_PASSWORD=account-or-app-password
ALERT_EMAIL_FROM=your@outlook.com
ALERT_EMAIL_TO=admin@example.com
IMAP_HOST=outlook.office365.com
IMAP_PORT=993
IMAP_USER=your@outlook.com
IMAP_PASSWORD=account-or-app-password
```

If your provider requires implicit TLS on port 465, use `SMTP_SSL=true`. If it requires STARTTLS on
port 587, use `SMTP_SSL=false` and `SMTP_STARTTLS=true`.

## Run Manually

```bash
set -a
. /opt/napcat-login-watchdog/.env
set +a
napcat-login-watchdog run
```

Expected output:

```text
status=healthy
```

or:

```text
status=unhealthy
reason=OneBot HTTP API status check failed
reason=NapCat login requires QR/manual verification
```

## Diagnose Configuration

Run this before enabling the timer:

```bash
set -a
. /opt/napcat-login-watchdog/.env
set +a
napcat-login-watchdog doctor
```

Example output:

```text
[ok] bot service - qq-rolebot.service is healthy
[ok] napcat service - napcat.service is healthy
[ok] tcp port - 127.0.0.1:8080 is reachable
[ok] OneBot reverse WebSocket - connection check passed
[ok] OneBot HTTP API - status check passed
[warn] QR image - no fresh QR image currently available
[ok] SMTP - login succeeded
[skip] IMAP - WATCHDOG_REPLY_ENABLED=false
```

## systemd

```bash
cp deploy/systemd/napcat-login-watchdog.service /etc/systemd/system/
cp deploy/systemd/napcat-login-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog.timer
```

Optional click webhook:

```bash
cp deploy/systemd/napcat-login-watchdog-click.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog-click.service
```

If `WATCHDOG_CLICK_PUBLIC_BASE_URL` is set, alert emails include a tokenized button that calls the
webhook to refresh the QR and send a new QR email.

## Development

```bash
python -m pytest -q
python -m ruff check .
```

Never commit real `.env` files, QR URLs, QR images, SMTP passwords, OneBot tokens, QQ passwords, or
server private keys.
