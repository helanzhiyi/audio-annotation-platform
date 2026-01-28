# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## System Overview

An integrated audio transcription system with three components working together:

1. **Middleware** (`/middleware/`) - FastAPI service managing task distribution to external transcription agents
2. **Label Studio** (`/label-studio/`) - Dockerized annotation platform (backend + web UI)
3. **Audio Import** (`/audio-import/`) - Batch audio file import utilities

**Key Architectural Insight**: The middleware doesn't proxy audio files. It serves them directly from the filesystem at `/opt/label-studio/media/` with HTTP range request support for efficient seeking. This is a critical performance design decision.

## Development Commands

### Middleware Service

```bash
# Development mode
cd middleware
source venv/bin/activate
python app.py  # Runs on port 8010

# Production service management
sudo systemctl start ls-middleware
sudo systemctl stop ls-middleware
sudo systemctl restart ls-middleware
sudo systemctl status ls-middleware
sudo journalctl -u ls-middleware -f  # View logs

# Install/reinstall service
cd /opt/ls-middleware
sudo ./service/install.sh

# Dependencies
pip install -r requirements.txt  # Inside venv
```

### Label Studio

```bash
# First-time setup (REQUIRED)
cd label-studio
./setup.sh  # Creates .env with passwords, auto-detects public IP

# Docker network (one-time)
docker network create label-studio-net

# Start/stop
docker compose up -d
docker compose down
docker compose logs -f

# Database backup
docker exec ls-postgres pg_dump -U labelstudio labelstudio > backups/backup_$(date +%Y%m%d).sql
```

### Audio Import

```bash
cd audio-import
source venv/bin/activate
python import_audio.py /path/to/audio/files

# Uses config from /opt/ls-middleware/config.env
# Automatically extracts audio duration metadata using librosa
```

### System Deployment

```bash
# Deploy from git to /opt/ (one-time)
sudo ./scripts/deploy.sh
# - Copies all components to /opt/
# - Creates virtual environments
# - Installs systemd service
# - Sets up directories with correct permissions
```

## Architecture

### Data Flow

1. **Import Phase**: `import_audio.py` copies files to `/opt/label-studio/media/project_X/` and creates Label Studio tasks with duration metadata
2. **Task Assignment**: Middleware queries Label Studio for unlabeled tasks, locks them in Redis (respects skip cooldowns)
3. **Audio Streaming**: Agents stream audio via `GET /api/audio/stream/{task_id}/{agent_id}` - served directly from filesystem
4. **Transcription**: Agents submit results via `POST /api/tasks/{task_id}/submit`
5. **Completion**: Middleware creates Label Studio annotations and releases Redis locks

### Assignment Queue Architecture

The middleware maintains a **dual-layer cache** for performance:

- **Redis assignment_queue**: List of unlabeled task IDs synced every 30 seconds from Label Studio
- **In-memory stats_cache**: Eventual consistency stats for dashboard (total_unlabeled, total_locked, available)
- **completed_tasks set**: Prevents re-adding completed tasks to queue

This design allows fast task assignment without hitting Label Studio API on every request.

### Task Locking System

- **Redis keys**: `task:locked:{task_id}` stores agent assignment
- **Skip cooldown**: `task:skip:{task_id}:{agent_id}` with 30-minute TTL
- **Audit trail**: Tasks logged in PostgreSQL `transcription_sessions` table
- **Agent stats**: Cumulative stats in `agent_stats` table

### Storage Architecture

```
/opt/label-studio/
├── data/              # Label Studio internal data (container user 1001:1001)
├── media/             # Audio files (container user 1001:1001)
│   └── project_1/     # Project-specific media
├── export/            # Export directory
└── backups/           # PostgreSQL backups
```

**Critical**: Label Studio container runs as user 1001:1001. The middleware reads audio files from this directory, so permissions must allow both.

### Database Configuration

Both Label Studio and middleware use the **same PostgreSQL instance**:
- Label Studio: Internal schema for tasks/annotations
- Middleware: `transcription_sessions` and `agent_stats` tables

Connection details are synced via environment files. When setting up, ensure `config.env` has matching PostgreSQL credentials from Label Studio's `.env`.

## API Endpoints (Middleware)

**Core Workflow**:
- `POST /api/tasks/request` - Get next available task for agent (checks skip cooldowns)
- `GET /api/audio/stream/{task_id}/{agent_id}` - Stream audio with range support
- `POST /api/tasks/{task_id}/submit` - Submit transcription (auto-calculates earnings)
- `POST /api/tasks/{task_id}/skip` - Skip task (30-min cooldown per agent)

**Management**:
- `GET /api/health` - Health check (includes Label Studio connectivity)
- `GET /api/stats` - System stats from cache
- `GET /api/tasks/available/count` - Available task count with agent filter
- `GET /api/agents/{agent_id}/stats` - Agent performance stats from database

## Configuration Files

### Middleware (`/opt/ls-middleware/config.env`)
```bash
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=<from Label Studio Account Settings>
LS_PROJECT_ID=1
REDIS_URL=redis://localhost:6379
POSTGRES_DB=labelstudio
POSTGRES_USER=labelstudio
POSTGRES_PASSWORD=<must match Label Studio .env>
TZ_SYSTEM_API_KEY=<generated API key for agents>
```

### Label Studio (`/opt/label-studio/.env`)
Generated by `setup.sh`:
- `LABEL_STUDIO_HOST` - **Critical**: Must be public IP/domain for CSS/JS loading
- `POSTGRES_PASSWORD` - Must be synced to middleware config
- `SECRET_KEY` - Django secret

**Important**: After running `setup.sh`, manually update middleware's `config.env` with the PostgreSQL password.

## Important Files

- **middleware/app.py**: Main FastAPI application with async Redis, assignment queue sync, and audio streaming
- **middleware/models.py**: SQLAlchemy models for transcription sessions and agent stats
- **middleware/models_async.py**: Async database session management
- **middleware/web/transcription_frontend_template.html**: Browser-based testing interface
- **middleware/web/dashboard.html**: Agent stats dashboard
- **audio-import/import_audio.py**: Import with duration metadata extraction
- **label-studio/setup.sh**: Interactive environment configuration script
- **scripts/deploy.sh**: System deployment automation

## Testing

```bash
# Start all services first
cd /opt/label-studio && docker compose up -d
sudo systemctl start ls-middleware

# Test health
curl http://localhost:8010/api/health

# Browser testing
# Open middleware/web/transcription_frontend_template.html
# Update serverUrl to point to middleware (e.g., http://192.168.x.x:8010)

# API testing with cURL
curl -H "X-API-Key: $TZ_SYSTEM_API_KEY" \
  http://localhost:8010/api/tasks/request \
  -d '{"agent_id": 123}'
```

## Common Issues

### Label Studio CSS/JS Not Loading
**Symptom**: Web interface has no styling, browser console shows CSS/JS from `localhost`
**Fix**: Run `cd /opt/label-studio && ./setup.sh` to set correct `LABEL_STUDIO_HOST` with public IP

### Middleware 401 Invalid Token
**Cause**: API token invalid or database was reset (tokens stored in PostgreSQL)
**Fix**:
1. Go to Label Studio → Organizations → API Token Settings → Enable Legacy Tokens
2. Get token from Account & Settings → API
3. Update `/opt/ls-middleware/config.env` with new token
4. `sudo systemctl restart ls-middleware`

### Redis Connection Refused
**Cause**: Redis not running
**Fix**: `sudo systemctl start redis && sudo systemctl enable redis`

### Permission Errors on Audio Files
**Fix**: `sudo chown -R 1001:1001 /opt/label-studio/media`

## Port Usage

- **8080**: Label Studio web interface
- **8010**: Middleware API
- **5432**: PostgreSQL (localhost only)
- **6379**: Redis (localhost only)

## Python Dependencies

Middleware requires:
- Python 3.10+ (3.11 recommended) - Label Studio SDK uses `|` type annotations
- Key packages: `fastapi`, `label-studio-sdk`, `redis`, `sqlalchemy`, `librosa`, `psycopg2-binary`

Audio import requires:
- `label-studio-sdk`, `librosa`, `soundfile` for duration extraction
