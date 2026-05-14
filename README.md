# Voice2Text Task Reminder

A Telegram bot that accepts voice commands, transcribes them, parses structured intents via LLM, and manages personal reminders/tasks with inline button UX.

Designed as a **voice command layer** — Telegram is one input adapter, HTTP API is another, with a shared core pipeline.

## Architecture

```
Input Sources
  ├── Telegram (voice / text)
  └── HTTP POST /capture/audio | /capture/text

Core Pipeline
  CaptureService → TranscriptionService → IntentParser → ActionRouter
                                                              │
                                               ┌─────────────┴──────────────┐
                                          TaskService              ReminderService
                                               │                        │
                                          Repository              Repository
                                               └──────── SQLite ─────────┘

Output
  └── Telegram (messages + inline buttons) + APScheduler (timed reminders)
```

### Modules

| Module | Description |
|--------|-------------|
| `app/domain/` | Models (SQLAlchemy), schemas (Pydantic), enums |
| `app/storage/` | DB setup, async repositories |
| `app/providers/stt/` | STT abstraction: Mock, OpenAI-compatible, Groq |
| `app/providers/llm/` | LLM abstraction: Mock, OpenRouter |
| `app/services/` | TaskService, ReminderService, CaptureService, ActionRouter, Renderer |
| `app/adapters/telegram/` | aiogram bot, handlers, callbacks |
| `app/adapters/http/` | FastAPI capture API |
| `app/scheduler/` | APScheduler reminder firing |
| `app/container.py` | DI container — wires everything together |

## Setup

### 1. Install dependencies

```bash
make install
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your tokens
```

Key variables:
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY` — for real LLM parsing
- `STT_PROVIDER=openai` + `STT_API_KEY` — for real speech-to-text (or `groq`)
- `STT_PROVIDER=mock` / `LLM_PROVIDER=mock` — for local testing without API keys

### 3. Run

```bash
make run
```

Starts Telegram bot polling + FastAPI on port 8000 in a single process.

### 4. Run tests

```bash
make test
```

All tests use in-memory SQLite and mock providers — no real API calls.

### 5. Docker

```bash
make docker-up    # build + start
make docker-down  # stop
make docker-logs  # tail logs
```

## Telegram UX

1. Send a **voice message** → bot transcribes → parses intent → creates task
2. If confident: replies with task confirmation + inline buttons
3. If unsure: asks a clarification question
4. Inline buttons: **✅ Выполнено** / **🔁 Позже** / **❌ Отменить**
5. At reminder time: bot sends a reminder message with snooze options
6. `/list` — show active tasks
7. `/done` — show completed tasks

## HTTP API

```
POST /capture/text   — process text command
POST /capture/audio  — process audio file (multipart)
GET  /capture/health — health check
```

Example:
```bash
curl -X POST http://localhost:8000/capture/text \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123", "text": "Remind me to call mom tomorrow morning"}'
```

## Database Migrations

```bash
make migrate                  # apply migrations
make migrate-create msg="add column"  # generate new migration
```

## Production Deployment

CI/CD is handled by **GitHub Actions** (`.github/workflows/deploy.yml`):
push to `master` → run full CI → rsync files to VPS → `docker compose up -d --build`.

### 1. Server setup (one-time)

```bash
# On your VPS as root:
adduser deploy
usermod -aG docker deploy   # re-login required for group to take effect
mkdir -p /opt/voice-bot
chown deploy:deploy /opt/voice-bot

# Copy your .env to the server (never commit it):
scp .env deploy@your-vps:/opt/voice-bot/.env
```

> **Note:** do not deploy as root. The `deploy` user has Docker access but no other privileges.
> The private SSH key lives only on GitHub — never on the server.

### 2. GitHub Secrets

Add these in **Settings → Secrets → Actions**:

| Secret | Example | Required |
|--------|---------|----------|
| `VPS_HOST` | `123.45.67.89` | ✅ |
| `VPS_USER` | `deploy` | ✅ |
| `VPS_SSH_KEY` | `-----BEGIN OPENSSH...` | ✅ |
| `DEPLOY_PATH` | `/opt/voice-bot` | ✅ |
| `VPS_PORT` | `22` | optional (default 22) |

Generate a dedicated SSH key pair:
```bash
ssh-keygen -t ed25519 -C "github-deploy" -f ~/.ssh/deploy_key
# Add deploy_key.pub to /home/deploy/.ssh/authorized_keys on the server
# Paste deploy_key (private) into GitHub secret VPS_SSH_KEY
```

### 3. SQLite persistence

The database lives in `./data/app.db` on the server (volume mount).
It survives redeploys and server restarts.

```bash
# Manual backup:
cp /opt/voice-bot/data/app.db /opt/voice-bot/data/app.db.bak
```

> Automate backups with a cron job or `rsync` to off-site storage.

### 4. Observability

```bash
# Container status
make prod-ps

# Tail logs
make prod-logs

# Restart
make prod-restart

# Memory / CPU
make prod-stats          # docker stats
```

Or directly:
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f app
docker compose -f docker-compose.prod.yml restart app
docker stats
```

### 5. Memory troubleshooting (OOM at 256 MB)

Container is limited to **256 MB RAM**. If it OOM-kills:

```bash
docker compose -f docker-compose.prod.yml logs app | tail -50
docker stats  # check live usage
```

Before raising the limit, investigate first:
- Use 1 uvicorn worker (already default — no `--workers` flag)
- Check for memory leaks in APScheduler job accumulation
- Profile with `docker stats` over time

Only increase `mem_limit` in `docker-compose.prod.yml` if optimization is exhausted.

## Extending

To add a new **input adapter** (e.g. mobile shortcut):
- Call `CaptureService.process_text()` or `process_voice()`
- Pass result to `ActionRouter.route()`
- Handle `ActionResult` in your adapter

To add a new **output adapter** (e.g. Google Keep mirror):
- Implement a listener on `TaskService.create_task()` result
- Or hook into `ActionRouter` result post-processing

To add a new **LLM provider**:
- Implement `BaseIntentParser` in `app/providers/llm/`
- Register in `app/container.py` `_build_llm()`

To add a new **STT provider**:
- Implement `BaseTranscriptionProvider` in `app/providers/stt/`
- Register in `app/container.py` `_build_stt()`
