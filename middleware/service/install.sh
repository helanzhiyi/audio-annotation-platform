#!/bin/bash
# Install Label Studio ASR Middleware as a system service

set -e

SERVICE_NAME="ls-middleware"
SERVICE_FILE="/opt/ls-middleware/service/ls-middleware.service"
SYSTEMD_DIR="/etc/systemd/system"

echo "🔧 Installing $SERVICE_NAME service..."

# Check if running as root or with sudo access
if [ "$EUID" -ne 0 ]; then
    echo "This script requires sudo privileges to install the service."
    echo "Please run: sudo $0"
    exit 1
fi

# Copy service file to systemd directory
echo "📄 Copying service file to $SYSTEMD_DIR/"
cp "$SERVICE_FILE" "$SYSTEMD_DIR/$SERVICE_NAME.service"

# Set proper permissions
chmod 644 "$SYSTEMD_DIR/$SERVICE_NAME.service"

# Reload systemd daemon
echo "🔄 Reloading systemd daemon..."
systemctl daemon-reload

# Enable service for auto-start
echo "✅ Enabling $SERVICE_NAME service for auto-start..."
systemctl enable "$SERVICE_NAME"

echo "🎉 Service installed successfully!"
echo ""
echo "Service management commands:"
echo "  sudo systemctl start $SERVICE_NAME     # Start service"
echo "  sudo systemctl stop $SERVICE_NAME      # Stop service"
echo "  sudo systemctl restart $SERVICE_NAME   # Restart service"
echo "  sudo systemctl status $SERVICE_NAME    # Check status"
echo "  journalctl -u $SERVICE_NAME -f         # View logs"
echo ""
echo "Or use the helper scripts:"
echo "  ./service/start.sh                     # Start service"
echo "  ./service/stop.sh                      # Stop service"
echo "  ./service/restart.sh                   # Restart service"
echo "  ./service/status.sh                    # Check status"
echo "  ./service/logs.sh                      # View logs"
echo ""
echo "To start the service now, run:"
echo "  sudo systemctl start $SERVICE_NAME"