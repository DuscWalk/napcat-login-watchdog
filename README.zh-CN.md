# napcat-login-watchdog

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个独立的 NapCat 登录状态 watchdog。它会检测 NapCat/机器人服务、OneBot 连接、OneBot HTTP API 登录状态和 NapCat 日志中的登录失效标记，并在账号掉线或需要扫码时发送邮件告警。邮件可以附带最新二维码，也可以通过回复邮件或点击链接刷新二维码。

它解决的是一个很常见的问题：你用 NapCat 部署了 QQ 群聊 bot，但账号经常被 QQ 风控下线，需要重新扫码。你不想每次都 SSH 到服务器、翻 `journalctl`、从日志里找二维码。

## 功能

- 检查 bot 服务和 `napcat.service` 的 systemd 状态。
- 检查 bot TCP 端口。
- 通过 `ss` 检查 OneBot 反向 WebSocket 是否连接。
- 可选调用 NapCat OneBot HTTP API 的 `get_login_info` 和 `get_status`。
- 扫描近期日志中的登录失效、二维码、人工验证等明确标记。
- 只在 healthy/unhealthy 状态转换时发送离线或恢复邮件，避免刷屏。
- 自动附带最新的 NapCat 登录二维码图片。
- 支持管理员回复邮件触发刷新二维码。
- 支持带 token 的点击链接触发刷新二维码。
- 提供 `doctor`、`test-email`、`test-alert` 用于上线前验证。

## 实际使用流程

1. NapCat bot 正常运行。
2. QQ 风控让账号登录态失效。
3. watchdog 通过 OneBot HTTP API、WebSocket、服务状态或 NapCat 日志发现异常。
4. watchdog 按配置刷新 NapCat，找到新二维码，发送邮件。
5. 你直接扫邮件附件里的二维码，不需要登录服务器翻日志。
6. 如果二维码过期，可以回复邮件里的 `qr`，或者点击邮件里的刷新链接。

## 要求

- Linux 服务器。
- Python 3.11 或更新版本。
- 已安装并运行 NapCat。
- 一个可检测的 bot 服务或 OneBot 接收端，除非你明确关闭这类检查。
- 一个可用的 SMTP 邮箱用于发送告警。
- 可选 IMAP 邮箱，用于“回复邮件刷新二维码”。
- 可选 HTTPS 反向代理，用于“点击链接刷新二维码”。

## 安装

服务器没有 GitHub SSH key 时，用 HTTPS：

```bash
cd /opt
git clone https://github.com/DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
```

也可以用 SSH：

```bash
cd /opt
git clone git@github.com:DuscWalk/napcat-login-watchdog.git
cd /opt/napcat-login-watchdog
```

使用 conda：

```bash
conda create -n napcat-login-watchdog python=3.11 -y
/opt/miniconda3/envs/napcat-login-watchdog/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

使用 Python venv：

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e .
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，填写服务名、端口、OneBot HTTP API、SMTP/IMAP、二维码路径等配置。

如果 `napcat-login-watchdog` 不在 `PATH` 中，可以用绝对路径：

```bash
/opt/miniconda3/envs/napcat-login-watchdog/bin/napcat-login-watchdog doctor
/opt/napcat-login-watchdog/.venv/bin/napcat-login-watchdog doctor
```

## 首次配置流程

1. 配置如何检测 bot 和 NapCat 进程。
2. 配置 OneBot HTTP API，用于可靠检测账号登录状态。
3. 配置 SMTP；如果需要回复邮件刷新二维码，再配置 IMAP。
4. 运行 `napcat-login-watchdog doctor`。
5. 运行 `napcat-login-watchdog test-email`。
6. 当 NapCat 能生成二维码时，运行 `napcat-login-watchdog test-alert`。
7. 启用 systemd timer 或 cron。
8. 可选：启用点击链接 webhook，并通过 HTTPS 反向代理暴露。

## 配置不同运行方式

### systemd

默认适合 systemd：

```bash
WATCHDOG_SERVICE_CHECK_MODE=systemd
WATCHDOG_BOT_SERVICE=qq-rolebot.service
WATCHDOG_NAPCAT_SERVICE=napcat.service
WATCHDOG_HOST=127.0.0.1
WATCHDOG_PORT=8080
```

### Docker、Compose、pm2、supervisor 或手动启动

如果 NapCat 或 bot 不是 systemd 服务，用命令检测：

```bash
WATCHDOG_SERVICE_CHECK_MODE=command
WATCHDOG_BOT_CHECK_COMMAND='test "$(docker inspect --format="{{.State.Running}}" qq-rolebot)" = true'
WATCHDOG_NAPCAT_CHECK_COMMAND='test "$(docker inspect --format="{{.State.Running}}" napcat)" = true'
```

Docker 日志可以这样接入：

```bash
WATCHDOG_LOG_COMMAND='docker logs --since {minutes}m napcat'
```

支持的占位符：`{minutes}`、`{since}`、`{bot_service}`、`{napcat_service}`。

如果只想依赖 OneBot HTTP API 和 bot TCP 端口，可以跳过服务检测：

```bash
WATCHDOG_SERVICE_CHECK_MODE=none
```

### 关闭反向 WebSocket socket 检测

有些环境没有 `ss`，或者 OneBot 连接藏在容器网络里。可以关闭 socket 检测，改用 OneBot HTTP API：

```bash
WATCHDOG_ONEBOT_CONNECTION_CHECK=none
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
```

## OneBot HTTP API

为了可靠检测账号状态，建议给 NapCat 配置一个只绑定本机的 HTTP server：

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

把这个对象插入到 NapCat 配置里的 `network.httpServers` 数组中。不要用这段内容替换整个配置文件，也不要删掉已有的 `websocketClients`。

然后在 `.env` 中设置：

```bash
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
WATCHDOG_ONEBOT_HTTP_API_BASE=http://127.0.0.1:3001
WATCHDOG_ONEBOT_HTTP_API_TOKEN=same-onebot-token
```

不要把 OneBot HTTP API 暴露到公网。

常见 NapCat 配置和二维码位置：

```bash
find /root/Napcat -name 'onebot11_*.json' -o -name 'qrcode.png'
find /opt -path '*napcat*' -name 'onebot11_*.json' 2>/dev/null
```

如果 NapCat 在 Docker 里：

```bash
docker exec -it napcat sh -lc "find / -name 'onebot11_*.json' -o -name 'qrcode.png' 2>/dev/null | head -50"
```

修改 NapCat OneBot 配置后，重启 NapCat，然后运行 `napcat-login-watchdog doctor`。

## 邮箱配置

QQ 邮箱授权码：

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

Gmail app password：

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

Outlook 或 Microsoft 365：

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

如果邮箱服务商要求 465 隐式 TLS，用 `SMTP_SSL=true`。如果要求 587 STARTTLS，用 `SMTP_SSL=false` 和 `SMTP_STARTTLS=true`。

## 手动运行和验证

加载配置：

```bash
set -a
. /opt/napcat-login-watchdog/.env
set +a
```

运行一次检查：

```bash
napcat-login-watchdog run
```

可能输出：

```text
status=healthy
```

或：

```text
status=unhealthy
reason=OneBot HTTP API status check failed
reason=NapCat login requires QR/manual verification
```

发送普通测试邮件：

```bash
napcat-login-watchdog test-email
```

发送带二维码附件的测试告警邮件：

```bash
napcat-login-watchdog test-alert
```

`test-alert` 会执行 `WATCHDOG_QR_REFRESH_COMMAND`，等待 `WATCHDOG_QR_REFRESH_WAIT_SECONDS`，查找新鲜二维码，并把二维码作为附件发出。启用 timer 前建议跑一次，确认“从邮件扫码登录”这条链路真的可用。

## 诊断

启用定时器前先运行：

```bash
set -a
. /opt/napcat-login-watchdog/.env
set +a
napcat-login-watchdog doctor
```

示例输出：

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

`doctor` 只诊断，不发送告警邮件，也不重启 NapCat。要验证邮件投递用 `test-email`，要验证二维码附件链路用 `test-alert`。

## 命令参考

```bash
napcat-login-watchdog run
napcat-login-watchdog doctor
napcat-login-watchdog test-email
napcat-login-watchdog test-alert
napcat-login-watchdog serve-click-webhook
```

- `run`：执行一次 watchdog 检查，更新状态，并在状态转换时发送邮件。
- `doctor`：打印诊断结果，不发邮件，不刷新二维码。
- `test-email`：发送一封普通测试邮件。
- `test-alert`：刷新/查找二维码，并发送一封带附件的测试邮件。
- `serve-click-webhook`：启动可选的点击链接刷新二维码 HTTP 服务。

## systemd

如果使用 `/opt/miniconda3/envs/napcat-login-watchdog`：

```bash
cp deploy/systemd/napcat-login-watchdog.service /etc/systemd/system/
cp deploy/systemd/napcat-login-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog.timer
```

如果使用 `/opt/napcat-login-watchdog/.venv`：

```bash
cp deploy/systemd/napcat-login-watchdog-venv.service /etc/systemd/system/napcat-login-watchdog.service
cp deploy/systemd/napcat-login-watchdog.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog.timer
```

可选点击链接 webhook：

```bash
cp deploy/systemd/napcat-login-watchdog-click.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog-click.service
```

venv 版本：

```bash
cp deploy/systemd/napcat-login-watchdog-click-venv.service /etc/systemd/system/napcat-login-watchdog-click.service
systemctl daemon-reload
systemctl enable --now napcat-login-watchdog-click.service
```

如果设置了 `WATCHDOG_CLICK_PUBLIC_BASE_URL`，告警邮件里会出现一个带 token 的按钮，用于请求新二维码邮件。

项目自带的 systemd unit 默认以 root 运行。这是为了读取 `/root/Napcat/**/cache/qrcode.png` 并执行 `systemctl restart napcat.service`。如果你改成普通用户运行，需要确保该用户有二维码读取权限和刷新命令执行权限。

## cron

如果发行版不用 systemd，可以用 cron：

```bash
(crontab -l 2>/dev/null; cat deploy/cron/napcat-login-watchdog) | crontab -
```

如果你用 conda 而不是 `.venv`，先编辑 `deploy/cron/napcat-login-watchdog`。

## 点击链接 webhook 和 HTTPS

本地 webhook 建议只绑定 localhost：

```bash
WATCHDOG_CLICK_HOST=127.0.0.1
WATCHDOG_CLICK_PORT=18081
WATCHDOG_CLICK_PUBLIC_BASE_URL=https://watchdog.example.com
```

然后用 Nginx 或 Caddy 做 HTTPS 反向代理：

```bash
deploy/reverse-proxy/nginx-watchdog-click.conf
deploy/reverse-proxy/Caddyfile
```

邮件里的链接 token 可以触发二维码刷新，所以请使用 HTTPS，不要公开告警邮件截图。

## Docker

Compose 示例：

```bash
deploy/compose/docker-compose.example.yml
```

从仓库根目录运行：

```bash
docker compose -f deploy/compose/docker-compose.example.yml up -d --build
```

启用点击链接 webhook：

```bash
docker compose -f deploy/compose/docker-compose.example.yml --profile webhook up -d --build
```

Docker 部署建议配置：

```bash
WATCHDOG_SERVICE_CHECK_MODE=command
WATCHDOG_ONEBOT_CONNECTION_CHECK=none
WATCHDOG_REQUIRE_ONEBOT_HTTP_API=true
WATCHDOG_LOG_COMMAND='docker logs --since {minutes}m napcat'
WATCHDOG_STATE_PATH=/data/state.json
```

如果需要二维码附件，请挂载 NapCat 配置/cache 目录，让 `WATCHDOG_QR_GLOB` 能找到 `qrcode.png`；或者把 `WATCHDOG_QR_REFRESH_COMMAND` 设置成重启 NapCat 容器的命令。

## 排障

### `doctor` 显示 SMTP failed

确认邮箱服务商允许 SMTP 登录。QQ 邮箱、Gmail 和很多企业邮箱都需要授权码或 app password，而不是普通登录密码。

### `doctor` 显示 OneBot HTTP API failed

确认 NapCat 监听了配置的本机端口：

```bash
ss -ltnp | grep ':3001'
```

也可以手动调用接口。注意不要泄露 token：

```bash
curl -sS -H "Authorization: Bearer $WATCHDOG_ONEBOT_HTTP_API_TOKEN" \
  -X POST "$WATCHDOG_ONEBOT_HTTP_API_BASE/get_status" \
  -H "Content-Type: application/json" \
  -d '{}'
```

### 找不到二维码

先让 NapCat 生成新二维码，再搜索常见位置：

```bash
find /root/Napcat /opt -name qrcode.png 2>/dev/null
```

然后把 `WATCHDOG_QR_PATH` 设置成精确文件路径，或者调整 `WATCHDOG_QR_GLOB`。

### 只收到一次离线邮件

这是预期行为。watchdog 只在状态从 healthy 变为 unhealthy 时发送离线邮件，避免刷屏。账号仍然 unhealthy 时，可以通过回复邮件或点击链接请求新二维码。

## 安全注意事项

- 不要把 OneBot HTTP API 暴露到公网。
- `.env` 建议保持 `600` 权限。
- 不要在 issue、聊天或日志里公开二维码 URL、WebUI URL、OneBot token、SMTP 密码或 QQ 密码。
- 二维码附件可以授予登录权限，请把告警邮件当作敏感信息。
- 如果暴露点击链接 webhook，请使用 HTTPS，并让本地服务只绑定 localhost。

## 开发

```bash
python -m pytest -q
python -m ruff check .
```
