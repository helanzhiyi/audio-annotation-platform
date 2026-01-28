#!/bin/bash

# Audio Transcription System Deployment Script
# This script deploys the system from the Git repository to /opt/

set -e

echo "🚀 Deploying Audio Transcription System..."

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
   echo "❌ This script must be run as root or with sudo"
   exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Get the user who invoked sudo (or current user if not using sudo)
DEPLOY_USER="${SUDO_USER:-$(logname 2>/dev/null || whoami)}"

echo "📁 Repository root: $REPO_ROOT"
echo "👤 Deploy user: $DEPLOY_USER"

# Create /opt directories
echo "📂 Creating /opt directories..."
mkdir -p /opt/ls-middleware
mkdir -p /opt/label-studio
mkdir -p /opt/audio-import

# Deploy middleware
echo "🔧 Deploying middleware..."
cp -r "$REPO_ROOT"/middleware/* /opt/ls-middleware/
chown -R $DEPLOY_USER:$DEPLOY_USER /opt/ls-middleware

# Deploy Label Studio config (including hidden files like .env.example)
echo "🏷️ Deploying Label Studio config..."
shopt -s dotglob  # Enable copying hidden files
cp -r "$REPO_ROOT"/label-studio/* /opt/label-studio/
shopt -u dotglob  # Disable dotglob after use
chown -R $DEPLOY_USER:$DEPLOY_USER /opt/label-studio

# Deploy audio import
echo "🎵 Deploying audio import..."
cp -r "$REPO_ROOT"/audio-import/* /opt/audio-import/
chown -R $DEPLOY_USER:$DEPLOY_USER /opt/audio-import

# Create Python virtual environment for middleware
echo "🐍 Setting up Python virtual environment..."
cd /opt/ls-middleware
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Install systemd service with correct user and environment
echo "⚙️ Installing systemd service..."
# Replace placeholder user in service file with actual deploy user and add environment file
sed "s/User=administrator/User=$DEPLOY_USER/g; s/Group=administrator/Group=$DEPLOY_USER/g" \
    service/ls-middleware.service | \
sed '/Environment=PYTHONUNBUFFERED=1/a EnvironmentFile=/opt/ls-middleware/config.env' \
    > /etc/systemd/system/ls-middleware.service
systemctl daemon-reload
systemctl enable ls-middleware

# Create necessary directories with proper permissions
echo "📁 Creating necessary directories with proper permissions..."
mkdir -p /opt/label-studio/{data,media,export}
mkdir -p /opt/label-studio/data/{media,export,upload,test_data}

# Note: Label Studio environment will be configured interactively
# The .env.example file is deployed, but .env must be created by running setup.sh
echo "📝 Note: Label Studio environment configuration (.env) must be created by running setup.sh"

# Create middleware environment file
if [ ! -f /opt/ls-middleware/config.env ]; then
    cat > /opt/ls-middleware/config.env << EOF
# Middleware Environment Configuration

# Label Studio Connection
LABEL_STUDIO_URL=http://localhost:8080
LABEL_STUDIO_API_KEY=placeholder_will_be_generated_after_ls_starts
LS_PROJECT_ID=1

# Redis Configuration
REDIS_URL=redis://localhost:6379

# PostgreSQL Configuration (will be synced from Label Studio setup)
POSTGRES_DB=labelstudio
POSTGRES_USER=labelstudio
POSTGRES_PASSWORD=placeholder_will_be_synced_from_label_studio_setup

# API Security
TZ_SYSTEM_API_KEY=$(openssl rand -hex 32)
EOF
    chown $DEPLOY_USER:$DEPLOY_USER /opt/ls-middleware/config.env
fi

# Set permissions for Label Studio directories
# Label Studio container runs as user ID 1001, so we need to set ownership accordingly
echo "🔒 Setting Label Studio directory permissions for container user (1001:1001)..."
chown -R 1001:1001 /opt/label-studio/data /opt/label-studio/media /opt/label-studio/export

# Ensure the deploy user can still manage the docker-compose files
chown $DEPLOY_USER:$DEPLOY_USER /opt/label-studio/docker-compose.yml
chown $DEPLOY_USER:$DEPLOY_USER /opt/label-studio/.env.example
chown $DEPLOY_USER:$DEPLOY_USER /opt/label-studio/setup.sh
chown $DEPLOY_USER:$DEPLOY_USER /opt/label-studio/README.md

echo "✅ Deployment completed successfully!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 NEXT STEPS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  Configure Label Studio environment:"
echo "    cd /opt/label-studio"
echo "    sudo -u $DEPLOY_USER ./setup.sh"
echo ""
echo "2️⃣  Create Docker network (one-time):"
echo "    docker network create label-studio-net"
echo ""
echo "3️⃣  Start Label Studio:"
echo "    cd /opt/label-studio && docker compose up -d"
echo ""
echo "4️⃣  Create Label Studio admin user:"
echo "    - Navigate to http://YOUR_IP:8080"
echo "    - Create admin account via web interface"
echo "    - Get API token from Account & Settings"
echo ""
echo "5️⃣  Update middleware configuration:"
echo "    sudo nano /opt/ls-middleware/config.env"
echo "    # Update LABEL_STUDIO_API_KEY with token from step 4"
echo ""
echo "6️⃣  Start middleware service:"
echo "    systemctl start ls-middleware"
echo ""
echo "7️⃣  Verify deployment:"
echo "    systemctl status ls-middleware"
echo "    curl http://localhost:8010/api/health"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 For detailed documentation, see:"
echo "    /opt/label-studio/README.md"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"