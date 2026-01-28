#!/bin/bash
# Start the Label Studio ASR Middleware service

SERVICE_NAME="ls-middleware"

echo "🚀 Starting $SERVICE_NAME service..."
sudo systemctl start "$SERVICE_NAME"

# Check if service started successfully
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service started successfully!"
    echo ""
    echo "Service status:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    echo ""
    echo "To view logs: journalctl -u $SERVICE_NAME -f"
else
    echo "❌ Service failed to start!"
    echo ""
    echo "Service status:"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
    echo ""
    echo "Check logs with: journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi