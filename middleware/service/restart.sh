#!/bin/bash
# Restart the Label Studio ASR Middleware service

SERVICE_NAME="ls-middleware"

echo "🔄 Restarting $SERVICE_NAME service..."
sudo systemctl restart "$SERVICE_NAME"

# Wait a moment for service to start
sleep 2

# Check if service restarted successfully
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service restarted successfully!"
    echo ""
    echo "Service status:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
else
    echo "❌ Service failed to restart!"
    echo ""
    echo "Service status:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    echo ""
    echo "Check logs with: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi