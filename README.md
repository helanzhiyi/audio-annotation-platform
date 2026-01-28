# Audio Transcription System

A complete audio transcription system built for research and development, consisting of three integrated components that work together to provide automated speech recognition (ASR) capabilities through Label Studio.

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Audio Import  │───▶│  Label Studio    │◀──▶│   Middleware    │
│    System       │    │   Annotation     │    │   (FastAPI)     │
│                 │    │   Platform       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                ▲                        │
                                │                        ▼
                        ┌──────────────────┐    ┌─────────────────┐
                        │   Docker         │    │  External ASR   │
                        │   Container      │    │  Agents         │
                        └──────────────────┘    └─────────────────┘
```

## 📁 Components

### 1. **Middleware** (`/middleware/`)
- **Purpose**: FastAPI-based service that bridges Label Studio with external transcription agents
- **Key Features**:
  - Task distribution and locking mechanism
  - Direct audio streaming with range request support
  - Skip task functionality with cooldown
  - Redis-based audit logging
  - Systemd service integration

### 2. **Label Studio** (`/label-studio/`)
- **Purpose**: Web-based annotation platform for audio transcription tasks
- **Configuration**: Docker-based deployment with PostgreSQL backend
- **Features**: Task management, annotation interface, project organization
- **Setup**: Interactive configuration script (`setup.sh`) for environment setup
- **Documentation**: See `/label-studio/README.md` for detailed configuration

### 3. **Audio Import** (`/audio-import/`)
- **Purpose**: Utilities for importing and preprocessing audio files
- **Functionality**: Batch audio file processing and Label Studio integration

## 🚀 Quick Start

### Prerequisites
- Ubuntu/Amazon Linux/CentOS system
- Docker and Docker Compose v2+ (plugin format)
- Python 3.10+ (Python 3.11 recommended)
- Redis server (required for middleware task locking)
- Sudo access

### Installation

> **Note**: The deployment script is fully portable and automatically detects the current user, sets proper permissions, and configures services correctly.

1. **Install system dependencies:**

   **For Ubuntu/Debian:**
   ```bash
   # Install Docker (if not already installed)
   sudo apt update
   sudo apt install apt-transport-https ca-certificates curl software-properties-common
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt update
   sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin redis-server python3.11

   # Add current user to docker group
   sudo usermod -aG docker $USER

   # Start and enable services
   sudo systemctl start docker redis
   sudo systemctl enable docker redis

   # Verify Redis is running
   redis-cli ping  # Should respond with "PONG"

   # Log out and back in to apply docker group membership
   ```

   **For Amazon Linux 2023 / RHEL / CentOS:**
   ```bash
   # Install Docker
   sudo yum update -y
   sudo yum install docker -y

   # Install Docker Compose plugin
   sudo mkdir -p /usr/local/lib/docker/cli-plugins
   sudo curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose
   sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

   # Install Redis and Python 3.11
   sudo yum install redis python3.11 -y

   # Add current user to docker group
   sudo usermod -aG docker $USER

   # Start and enable services
   sudo systemctl start docker redis
   sudo systemctl enable docker redis

   # Verify Redis is running
   redis-cli ping  # Should respond with "PONG"

   # Log out and back in to apply docker group membership
   ```

2. **Deploy the system:**
   ```bash
   git clone https://github.com/openchlsystem/openchs_rnd.git
   cd openchs_rnd/tasks/asr/audio_transcription_system
   sudo ./scripts/deploy.sh
   ```

   The deployment script will:
   - Copy all components to `/opt/`
   - Set up Python virtual environments
   - Install system services
   - Create necessary directories with proper permissions
   - Display detailed next steps

3. **Configure Label Studio environment:**
   ```bash
   cd /opt/label-studio
   ./setup.sh
   ```

   The setup script will:
   - Auto-detect your EC2 public IP (for cloud deployments)
   - Prompt for Label Studio host URL (critical for CSS/JS loading)
   - Generate secure passwords and secret keys
   - Create `.env` file with proper configuration

   **Important**: For cloud deployments (EC2, etc.), the script detects your public IP automatically. This ensures Label Studio serves CSS/JS correctly when accessed from outside.

4. **Create Docker network (one-time):**
   ```bash
   docker network create label-studio-net
   ```

5. **Start Label Studio:**
   ```bash
   cd /opt/label-studio
   docker compose up -d
   ```

   Check logs to verify startup:
   ```bash
   docker compose logs -f
   ```

6. **Set up Label Studio admin user:**
   - Navigate to the URL shown during setup (e.g., `http://YOUR_PUBLIC_IP:8080`)
   - Create an admin account through the web interface
   - Go to **Organizations → API Token Settings**, then click **Enable** under "Legacy Tokens"
   - Go to **Account & Settings → API** to get your API token (copy the entire token)

7. **Configure middleware with API token:**
   ```bash
   # Edit the middleware environment file
   sudo nano /opt/ls-middleware/config.env
   # Update LABEL_STUDIO_API_KEY with your token from step 6
   ```

8. **Create a transcription project:**
   - In Label Studio, create a new project
   - Select "Audio" as data type
   - Configure labeling interface for transcription
   - Note the project ID (usually 1 for first project)

9. **Start middleware service:**
   ```bash
   sudo systemctl start ls-middleware
   ```

10. **Verify deployment:**
    ```bash
    # Check middleware status
    sudo systemctl status ls-middleware

    # Test health endpoint
    curl http://localhost:8010/api/health

    # Check Label Studio
    docker compose -f /opt/label-studio/docker-compose.yml ps
    ```

## 📋 API Endpoints

### Core Endpoints
- `GET /api/tasks/next/{agent_id}` - Get next available task
- `GET /api/audio/stream/{task_id}/{agent_id}` - Stream audio file
- `POST /api/tasks/{task_id}/submit` - Submit transcription results
- `POST /api/tasks/{task_id}/skip` - Skip task (30min cooldown)

### Management
- `GET /api/health` - Health check
- `GET /api/stats` - System statistics

## 🛠️ Development

### Testing
The system includes comprehensive testing tools:
- **Browser testing**: `/web/transcription_frontend_template.html`
- **Automated testing**: Python test suite
- **API testing**: cURL command examples

### Service Management
```bash
# Check status
sudo systemctl status ls-middleware

# View logs
sudo journalctl -u ls-middleware -f

# Restart service
sudo systemctl restart ls-middleware
```

## 📊 Workflow

1. **Audio Import**: Batch import audio files into Label Studio
2. **Task Creation**: Label Studio creates transcription tasks
3. **Agent Connection**: External ASR agents request tasks via middleware
4. **Audio Streaming**: Middleware serves audio files directly from filesystem
5. **Transcription**: Agents process audio and submit results
6. **Completion**: Results stored in Label Studio for review/export

## 🔧 Configuration

### Environment Variables
```bash
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_TOKEN=your_token
REDIS_URL=redis://localhost:6379
TZ_SYSTEM_SECRET=your_secret
PROJECT_ID=1
```

### Supported Audio Formats
- WAV, MP3, M4A, OGG, FLAC, WebM, Opus

## 📚 Documentation

- **Label Studio Setup & Configuration**: `/label-studio/README.md`
  - Environment configuration guide
  - CSS/JS loading troubleshooting
  - Deployment checklist
  - Security best practices
- **Middleware Setup**: `/middleware/docs/CLAUDE.md`
  - Service management
  - API endpoints
  - Architecture details
- **Frontend Template**: `/middleware/web/transcription_frontend_template.html`

## 🔒 Security Features

- Token-based authentication
- Agent access verification
- Task locking mechanism
- Audit logging
- Systemd security hardening

## 🏃‍♂️ Performance

- **Direct file serving**: No proxy overhead
- **Range request support**: Efficient audio seeking
- **Redis caching**: Fast task distribution
- **Async processing**: High concurrency support

## 📝 License

This project is part of the OpenCHS R&D initiative.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Make changes in appropriate component directory
4. Test using provided testing tools
5. Submit pull request

## 🐛 Troubleshooting

### Common Issues

#### 1. **Label Studio CSS/JS not loading (interface broken)**
**Problem**: Label Studio interface loads but has no styling, looks completely broken
**Symptom**: Browser console shows CSS/JS files being requested from `localhost` instead of your public IP

**Root Cause**: `LABEL_STUDIO_HOST` environment variable not configured correctly

**Solution**:
```bash
# Stop Label Studio
cd /opt/label-studio
docker compose down

# Run setup script (it will detect your public IP)
./setup.sh

# Restart Label Studio
docker compose up -d
```

Or manually edit `/opt/label-studio/.env` and set:
```
LABEL_STUDIO_HOST=http://YOUR_PUBLIC_IP:8080
```

**Why this happens**: Label Studio uses the `LABEL_STUDIO_HOST` variable to generate URLs for static assets. If not set or set to `localhost`, CSS/JS requests fail when accessing from outside.

See `/label-studio/README.md` for more details.

#### 2. **Label Studio container restarting with permission errors**
**Problem**: `PermissionError: [Errno 13] Permission denied: '/label-studio/data/test_data'`
**Solution**: The deployment script now automatically handles this, but if you encounter it:
```bash
sudo mkdir -p /opt/label-studio/{data,media,export}
sudo mkdir -p /opt/label-studio/data/{media,export,upload,test_data}
sudo chown -R 1001:1001 /opt/label-studio/data /opt/label-studio/media /opt/label-studio/export
```

#### 3. **Middleware service failing with API key error**
**Problem**: `RuntimeError: 'LABEL_STUDIO_API_KEY' environment variable must be set`
**Solution**:
1. Create Label Studio admin user first via web interface
2. Get API token from Label Studio Account & Settings
3. Update `/opt/ls-middleware/config.env` with real token
4. Restart service: `sudo systemctl restart ls-middleware`

#### 4. **Middleware failing with 401 Invalid token error**
**Problem**: `401 Client Error: Unauthorized for url: http://localhost:8080/api/projects/1` with "Invalid token" message
**Root Cause**: API token in middleware config is invalid or database was reset (tokens are stored in PostgreSQL)

**Solution**:
```bash
# 1. Access Label Studio web interface
# Navigate to http://YOUR_PUBLIC_IP:8080

# 2. Create new admin account (if database was reset) or log in

# 3. Enable Legacy Tokens:
# Go to Organizations → API Token Settings
# Click "Enable" under "Legacy Tokens"

# 4. Get API token:
# Go to Account & Settings → API
# Copy the entire token

# 5. Update middleware config
sudo nano /opt/ls-middleware/config.env
# Update LABEL_STUDIO_API_KEY=your_token_here

# 6. Restart middleware
sudo systemctl restart ls-middleware

# 7. Verify
curl http://localhost:8010/api/health
# Should show: "label_studio":"connected","project_id":1
```

**Note**: If you reset PostgreSQL (e.g., `docker compose down -v`), you MUST regenerate the API token because all user accounts and tokens are deleted.

#### 5. **Middleware failing with 404 project error**
**Problem**: `404 Client Error: Not Found for url: http://localhost:8080/api/projects/1`
**Solution**: Create a transcription project in Label Studio web interface before starting middleware

#### 6. **Docker network issues**
**Problem**: Label Studio containers fail to start with network errors
**Solution**:
```bash
sudo docker network create label-studio-net
```

#### 7. **Redis connection refused error**
**Problem**: `Error 111 connecting to localhost:6379. Connection refused.`
**Symptom**: Middleware fails to start with Redis connection error in logs

**Root Cause**: Redis server is not running or not installed

**Solution:**
```bash
# Check if Redis is installed
redis-cli --version

# If not installed (Amazon Linux/RHEL/CentOS):
sudo yum install redis -y

# If not installed (Ubuntu/Debian):
sudo apt install redis-server -y

# Start and enable Redis
sudo systemctl start redis
sudo systemctl enable redis

# Verify Redis is running
redis-cli ping  # Should return "PONG"

# Restart middleware
sudo systemctl restart ls-middleware
```

#### 8. **Python version compatibility error**
**Problem**: `TypeError: unsupported operand type(s) for |: '_GenericAlias' and 'type'`
**Symptom**: Middleware fails to start with type annotation errors

**Root Cause**: Python 3.9 or earlier installed, but label-studio-sdk requires Python 3.10+

**Solution:**
```bash
# Install Python 3.11
sudo yum install python3.11 -y  # Amazon Linux/RHEL/CentOS
# or
sudo apt install python3.11 -y  # Ubuntu/Debian

# Recreate virtual environment with Python 3.11
cd /opt/ls-middleware
sudo rm -rf venv
sudo python3.11 -m venv venv
sudo chown -R $USER:$USER venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate

# Restart middleware
sudo systemctl restart ls-middleware
```

#### 9. **Service user permission issues**
**Problem**: Systemd service fails with user-related errors
**Solution**: The deployment script now automatically detects and sets the correct user. For manual fixes:
```bash
sudo sed -i "s/User=administrator/User=$USER/g; s/Group=administrator/Group=$USER/g" /etc/systemd/system/ls-middleware.service
sudo systemctl daemon-reload
```

### Verification Commands
```bash
# Check all services status
sudo systemctl status ls-middleware
docker compose -f /opt/label-studio/docker-compose.yml ps
redis-cli ping

# Test API endpoints
curl http://localhost:8080  # Label Studio web interface
curl http://localhost:8010/api/health  # Middleware health check

# Check logs
sudo journalctl -u ls-middleware -f  # Follow middleware logs
docker compose -f /opt/label-studio/docker-compose.yml logs -f  # Follow Label Studio logs
```

### Port Usage
- **8080**: Label Studio web interface
- **8010**: Middleware API
- **5432**: PostgreSQL (localhost only)
- **6379**: Redis (localhost only)

## 📝 Deployment Notes

### Improvements Made
- **✅ Portable deployment**: Script automatically detects user and sets correct permissions
- **✅ Container permissions**: Automated handling of Label Studio container user (1001:1001)
- **✅ Service configuration**: Dynamic systemd service file generation with correct user
- **✅ Environment loading**: Systemd service properly loads `.env` files
- **✅ Docker Compose v2**: Updated to use modern `docker compose` plugin format
- **✅ Network setup**: Automated Docker network creation
- **✅ Comprehensive troubleshooting**: Real-world deployment issues documented

### Deployment Validation
After deployment, verify system health:
```bash
# All services should show healthy status
curl http://localhost:8010/api/health
# Expected: {"status":"healthy","label_studio":"connected","redis":"connected","project_id":1}

# Web interfaces should be accessible
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080  # Should return 302
curl -s -o /dev/null -w "%{http_code}" http://localhost:8010/api/health  # Should return 200
```

---

**System Status**: Production-ready ✅
**Last Updated**: September 2025
**Maintained by**: OpenCHS R&D Team