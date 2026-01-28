# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a complete **Audio Transcription System** consisting of three main components:

1. **Label Studio ASR Middleware** (`/opt/ls-middleware/`) - FastAPI service managing task distribution
2. **Label Studio Instance** (`/opt/label-studio/`) - Dockerized annotation platform
3. **Audio Import System** (`/opt/audio-import/`) - Batch audio file import utilities

The system manages audio transcription tasks between Label Studio (annotation platform) and external transcription agents (TZ system), handling task distribution, audio streaming, and transcription collection.

## Git Management

The system is managed from git repository at `/home/administrator/openchs_rnd/tasks/asr/audio_transcription_system` and kept in sync with production locations using:

```bash
# Located at /home/administrator/openchs_rnd/tasks/asr/audio-transcription-dev/
ls
dev_workflow.md  README.md  sync_from_git.sh  sync_to_git.sh

# Sync changes from git to production
./sync_from_git.sh

# Sync changes from production to git
./sync_to_git.sh
```

## Development Commands

### Running the Application

#### As a System Service (Recommended for Production)
```bash
# Install as system service (one-time setup)
cd /opt/ls-middleware
sudo ./service/install.sh

# Manage the service
sudo systemctl start ls-middleware      # Start service
sudo systemctl stop ls-middleware       # Stop service
sudo systemctl restart ls-middleware    # Restart service
sudo systemctl status ls-middleware     # Check status
journalctl -u ls-middleware -f          # View logs

# Or use helper scripts
./service/start.sh                      # Start service
./service/stop.sh                       # Stop service
./service/restart.sh                    # Restart service
./service/status.sh                     # Check status
./service/logs.sh                       # View logs
```

#### Manual Development Mode
```bash
# Activate virtual environment
source venv/bin/activate

# Start the server (default port 8010)
python app.py

# Or with uvicorn directly
uvicorn app:app --host 0.0.0.0 --port 8010 --reload
```

### Installing Dependencies
```bash
# Install from requirements.txt
pip install -r requirements.txt
```

### Testing & Frontend Development
```bash
# Start the server
source venv/bin/activate
python app.py

# Copy the frontend template to your development machine
# Template located at: ./web/transcription_frontend_template.html
# Update the serverUrl in the template to point to your VPN IP
```

## File Structure

### Production Files
```
/opt/ls-middleware/
├── app.py                                    # Main FastAPI application
├── config.env                              # Environment configuration
├── requirements.txt                         # Python dependencies
├── venv/                                   # Virtual environment
├── docs/                                   # Documentation
│   ├── CLAUDE.md                          # Project documentation
│   └── SERVICE_SETUP.md                   # Service installation guide
├── service/                               # Service management
│   ├── ls-middleware.service              # systemd service definition
│   ├── install.sh                         # Service installation script
│   ├── start.sh                           # Start service helper
│   ├── stop.sh                            # Stop service helper
│   ├── restart.sh                         # Restart service helper
│   ├── status.sh                          # Status check helper
│   └── logs.sh                            # Log viewing helper
├── web/                                   # Frontend template
│   └── transcription_frontend_template.html
└── backup/                                # Backup files
    └── requirements_full_backup.txt
```

## Architecture

### Core Components

- **app.py**: Main FastAPI application with optimized audio streaming
- **config.env**: Environment configuration (Label Studio URL, API keys, Redis)
- **transcription_frontend_template.html**: Production-ready frontend template

### Key Dependencies
- **FastAPI**: Web framework
- **label-studio-sdk**: Label Studio API client
- **Redis**: Task locking and audit logging
- **FastAPI FileResponse**: Direct file serving for audio streaming

### API Endpoints
- `POST /api/tasks/request` - Request task assignment for agent
- `GET /api/audio/stream/{task_id}/{agent_id}` - Stream audio files directly from filesystem
- `POST /api/tasks/{task_id}/submit` - Submit transcription
- `POST /api/tasks/{task_id}/skip` - Skip a task and release for other agents
- `GET /api/tasks/available/count` - Get available task count (with optional agent_id filter)
- `GET /api/agents/{agent_id}/stats` - Agent statistics

### Data Flow
1. External agents request tasks via API
2. System locks unlabeled tasks in Redis to prevent conflicts (respects skip cooldowns)
3. Agents stream audio files directly from filesystem with authentication
4. Agents can skip tasks if unable to process (30-minute cooldown per agent)
5. Agents submit transcriptions back to the system
6. System creates annotations in Label Studio and cleans up locks

### Audio Streaming Architecture
- **Direct File Serving**: Files served directly from `/opt/label-studio/media/` filesystem
- **HTTP Range Support**: Automatic support for partial content requests (seeking)
- **Multiple Formats**: Supports wav, mp3, m4a, ogg, flac, webm, opus
- **Access Control**: File access restricted to agents with valid task locks
- **Performance**: No memory buffering, efficient for large audio files

### Configuration
- Environment variables loaded from `config.env`
- Requires Label Studio URL and API key
- Redis for distributed task locking
- TZ system API key for authentication

### Security
- API key authentication via `X-API-Key` header
- Task access control (agents can only access their assigned tasks)
- Audit logging for task assignments and completions

### Service Management
- **Auto-start on boot**: Service automatically starts when server reboots
- **Auto-restart on failure**: Service restarts if it crashes or stops unexpectedly
- **Graceful shutdown**: Proper signal handling for clean shutdowns
- **Resource limits**: Memory and file descriptor limits configured
- **Security hardening**: Runs with restricted permissions and isolated temp directories
- **Centralized logging**: All logs accessible via systemd journal
- **Easy management**: Simple scripts for start/stop/status operations

## Complete System Architecture

### Directory Structure
```
/opt/ls-middleware/     # FastAPI middleware service
├── app.py              # Main application
├── app_audio_fixed.py  # Alternative with audio fixes
├── config.env          # Environment configuration
├── requirements.txt    # Python dependencies
└── test_*.py          # Test scripts

/opt/label-studio/      # Label Studio instance
├── docker-compose.yml  # Docker setup with PostgreSQL
├── .env               # Docker environment config
├── init_admin.sh      # Admin user setup script
├── data/              # Label Studio data
├── media/             # Audio file storage
│   └── project_1/     # Project-specific media files
├── export/            # Export directory
└── backups/           # Database backups

/opt/audio-import/      # Audio import utilities
├── import_final.py    # Production import script
├── README.md          # Usage documentation
├── pending/           # Files to be imported
├── processed/         # Successfully imported
└── failed/            # Failed imports
```

### System Components

#### 1. Label Studio (Port 8080)
- **Service**: Docker container with PostgreSQL backend
- **Access**: http://localhost:8080 or http://192.168.8.13:8080
- **Admin**: admin@labelstudio.local / AdminPass123!
- **Database**: PostgreSQL container (port 5432)
- **Media Storage**: `/opt/label-studio/media/project_1/` (host) → `/label-studio/data/media/project_1/` (container)

#### 2. ASR Middleware (Port 8010)
- **Service**: FastAPI application
- **Purpose**: Task distribution and transcription collection
- **Redis**: localhost:6379 for task locking
- **Integration**: Uses Label Studio SDK

#### 3. Audio Import System
- **Purpose**: Batch import audio files into Label Studio
- **Process**: Copy files to media directory → Create Label Studio tasks
- **Support**: Multiple audio formats (wav, mp3, m4a, ogg, flac, webm, opus)
- **Features**: Hash-based deduplication, metadata extraction, permission management

### Workflow Integration

1. **Audio Import**: `import_final.py` copies audio files to `/opt/label-studio/media/project_1/`
2. **Task Creation**: Import scripts create Label Studio tasks with audio URLs
3. **Task Distribution**: Middleware assigns tasks to agents via Redis locking
4. **Audio Access**: Agents stream audio through middleware with authentication
5. **Transcription**: Agents submit transcriptions back to Label Studio via middleware

### Key Commands

#### Label Studio Management
```bash
# Start Label Studio stack
cd /opt/label-studio && docker-compose up -d

# Create admin user
./init_admin.sh

# Check logs
docker-compose logs -f label-studio

# Stop services
docker-compose down
```

#### Audio Import
```bash
# Import audio files
cd /opt/audio-import
./import_final.py /path/to/audio/files

# See README.md for detailed usage
```

#### Middleware Operations
```bash
# Start middleware (from /opt/ls-middleware/)
source venv/bin/activate
python app.py

# Test complete workflow
python test_complete_flow.py
```