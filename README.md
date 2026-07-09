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

Clone with HTTPS if the server does not have a GitHub SSH key:

```bash
cd /opt
git clone https://github.com/DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
```

Or clone with SSH:

```bash
cd /opt
git clone git@github.com:DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
```

With conda:

```bash
conda create -n napcat-login-watchdog python=3.11 -y
/opt/miniconda3/envs/napcat-login-watchdog/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

With a plain Python virtual environment:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set SMTP credentials, alert recipients, service names, and QR paths.

## First Setup Flow

1. Configure how to detect your bot and NapCat process.
2. Configure OneBot HTTP API for reliable login-state checks.
3. Configure SMTP, and optionally IMAP for reply-to-email QR refresh.
4. Run `napcat-login-watchdog doctor`.
5. Run `napcat-login-watchdog test-email`.
6. Enable the timer.
7. Optional: enable the click webhook behind HTTPS.

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

Common NapCat config locations include:

```bash
find /root/Napcat -name 'onebot11_*.json' -o -name 'qrcode.png'
find /opt -path '*napcat*' -name 'onebot11_*.json' 2>/dev/null
```

If NapCat runs in Docker, search inside the mounted config volume, or run:

```bash
docker exec -it napcat sh -lc "find / -name 'onebot11_*.json' -o -name 'qrcode.png' 2>/dev/null | head -50"
```

After changing NapCat's OneBot config, restart NapCat and run `napcat-login-watchdog doctor`.

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

Send a real test email:

```bash
napcat-login-watchdog test-email
```

This command sends one message to `ALERT_EMAIL_TO`. Use it before enabling the timer.

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

Use the conda units if you installed with `/opt/miniconda3/envs/napcat-login-watchdog`:

```bash
cp deploy/systemd/napcat-login-watchdog.service /etc/systemd/system/
cp deploy/systemd/napcat-login-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog.timer
```

Use the venv unit if you installed with `/opt/napcat-login-watchdog/.venv`:

```bash
cp deploy/systemd/napcat-login-watchdog-venv.service /etc/systemd/system/napcat-login-watchdog.service
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

For venv:

```bash
cp deploy/systemd/napcat-login-watchdog-click-venv.service /etc/systemd/system/napcat-login-watchdog-click.service
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog-click.service
```

If `WATCHDOG_CLICK_PUBLIC_BASE_URL` is set, alert emails include a tokenized button that calls the
webhook to refresh the QR and send a new QR email.

## cron

If your Linux distribution does not use systemd, run the watchdog from cron:

```bash
crontab deploy/cron/napcat-login-watchdog
```

Edit the file first if you installed with conda instead of `.venv`.

## Click Webhook Behind HTTPS

Keep the webhook itself bound to localhost:

```bash
WATCHDOG_CLICK_HOST=127.0.0.1
WATCHDOG_CLICK_PORT=18081
WATCHDOG_CLICK_PUBLIC_BASE_URL=https://watchdog.example.com
```

Then put Nginx or Caddy in front of it:

```bash
deploy/reverse-proxy/nginx-watchdog-click.conf
deploy/reverse-proxy/Caddyfile
```

The token in the email URL authorizes QR refresh, so use HTTPS and do not publish screenshots of
alert emails.

## Docker Notes

A minimal Compose example is available at:

```bash
deploy/compose/docker-compose.example.yml
```

For Docker deployments, prefer:

```bash
WATCHDOG_SERVICE_CHECK_MODE=command
WATCHDOG_ONEBOT_CONNECTION_CHECK=none
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
WATCHDOG_LOG_COMMAND='docker logs --since {minutes}m napcat'
```

Mount the NapCat config/cache volume so `WATCHDOG_QR_GLOB` can find `qrcode.png`, or set
`WATCHDOG_QR_REFRESH_COMMAND` to a command that restarts the NapCat container.

## Development

```bash
python -m pytest -q
python -m ruff check .
```

Never commit real `.env` files, QR URLs, QR images, SMTP passwords, OneBot tokens, QQ passwords, or
server private keys.
