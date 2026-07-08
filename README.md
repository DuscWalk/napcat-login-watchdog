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

```bash
cd /opt
git clone git@github.com:DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
conda create -n napcat-login-watchdog python=3.11 -y
/opt/miniconda3/envs/napcat-login-watchdog/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set SMTP credentials, alert recipients, service names, and QR paths.

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
