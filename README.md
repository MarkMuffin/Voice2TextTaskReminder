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
| `app/providers/stt/` | STT abstraction: Mock, OpenAI-compatible, Groq, OpenRouter, fallback route |
| `app/providers/llm/` | LLM abstraction: Mock, Groq, OpenRouter, fallback route |
| `app/services/` | TaskService, ReminderService, CaptureService, ActionRouter, Renderer |
| `app/adapters/telegram/` | aiogram bot, handlers, callbacks |
| `app/adapters/http/` | FastAPI capture API |
| `app/scheduler/` | APScheduler reminder firing |
| `app/container.py` | DI container — wires everything together |

## Command parsing: direct parser and LLM

`CaptureService` first tries the local `DirectReminderParser`, then delegates to the LLM only when the local parser declines the command. The direct parser handles unambiguous one-off Russian `напомни` commands without a network call; recurring, task-management, incomplete, and unclear commands go to the LLM.

For numeric dates, the contract is intentionally strict: `DD.MM[.YYYY]` is a reminder date only when it appears in the command slot immediately after `напомни` (allowing the filler words `мне` and `пожалуйста`). The same text elsewhere remains part of the task title, so quantities and version numbers cannot silently become dates.

| Command | Result |
|---------|--------|
| `Напомни 12.08 сходить в казино` | Reminder on 12 August (09:00 if no time is given) |
| `Напомни мне 12.08 купить молоко` | Reminder on 12 August; `мне` is ignored |
| `Напомни сходить в казино 12.08` | Unscheduled task; `12.08` stays in the title |
| `Напомни обновить Python 3.11` | Unscheduled task; `3.11` stays in the title |
| `Напомни 12 августа сходить в казино` | Reminder on 12 August; month-name dates are unambiguous |

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
- `LLM_PROVIDER=fallback` + `GROQ_API_KEY` / `OPENROUTER_API_KEY` — tries Groq first, then OpenRouter
- `GROQ_MODEL=openai/gpt-oss-120b` and `OPENROUTER_MODEL=deepseek/deepseek-v4-flash` — primary and fallback LLM models
- `STT_PROVIDER=fallback` — tries Groq Whisper, then OpenRouter STT, then OpenAI-compatible STT when `STT_API_KEY` is configured
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

### 4. Cloudflare R2 SQLite backups

The app can upload a SQLite snapshot to any S3-compatible Cloudflare R2 bucket.
Backups are disabled by default and check hourly when enabled.

```bash
ENABLE_DB_BACKUP_TO_R2=true
DB_BACKUP_INTERVAL_SECONDS=3600
DB_BACKUP_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
DB_BACKUP_R2_BUCKET=your-bucket
DB_BACKUP_R2_ACCESS_KEY_ID=your-access-key-id
DB_BACKUP_R2_SECRET_ACCESS_KEY=your-secret-access-key
DB_BACKUP_R2_PREFIX=db-backups
DB_BACKUP_R2_REGION=auto
```

Each run creates a consistent SQLite snapshot and compares its SHA-256 checksum
with the current `latest` backup metadata. If the database has not changed,
the upload is skipped. When it has changed, the app writes both:
- `db-backups/latest/app.db`
- `db-backups/snapshots/<timestamp>-app.db`

Configure an R2 lifecycle rule for the `db-backups/snapshots/` prefix if you do
not want hourly historical snapshots retained forever.

### 5. Observability

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

### 6. Memory troubleshooting (OOM at 256 MB)

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

## Recurring Tasks

Tasks that repeat automatically on a schedule — daily, weekly, or monthly.

### How it works

A **`RecurringTask`** is a template (stores the schedule). It never fires reminders itself.
Every 60 seconds a background job checks which templates are due and spawns a regular **`Task`** for each — which then goes through the normal reminder flow.

```
RecurringTask (template)
      ↓  background job every 60s
   generate_due_instances()
      ↓  creates
   Task (with remind_at) + Reminder
      ↓  existing flow
   APScheduler DateTrigger → bot.send_message
```

### Usage

Say or type (Russian/English):

```
каждую пятницу в 17 пополнить фонд
каждый день в 9 выпить таблетки
каждое 1-е число в 10 оплатить аренду
```

Commands:
- `/scheduled` — view all active recurring rules with pause/cancel buttons

### Guarantees

| Concern | Behaviour |
|---|---|
| Duplicate runs | Idempotency check — same slot never creates two tasks |
| Bot was down for days | Creates **one** catch-up instance, skips the rest, advances to future |
| Pause & resume | Resume recalculates `next_run_at` from *now* — missed cycles skipped |

### Configuration

```env
ENABLE_RECURRING_TASKS=true
RECURRING_TASK_GENERATOR_INTERVAL_SECONDS=60
```

Set `ENABLE_RECURRING_TASKS=false` to disable completely — all existing commands unaffected.

### HTTP API

```
POST   /recurring-tasks              # create rule (body: RecurringTaskCreate)
GET    /recurring-tasks?user_id=X    # list active/paused rules
POST   /recurring-tasks/{id}/cancel
POST   /recurring-tasks/{id}/pause
POST   /recurring-tasks/{id}/resume
```

### Database migration

```bash
make migrate   # applies 002_add_recurring_tasks
```

Adds `recurring_tasks` table and two nullable columns to `tasks` (`recurring_task_id`, `scheduled_for`). Fully backward-compatible — existing data untouched.

---

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
