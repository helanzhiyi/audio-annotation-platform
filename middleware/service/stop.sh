#!/bin/bash
# Stop the Label Studio ASR Middleware service

SERVICE_NAME="ls-middleware"

echo "🛑 Stopping $SERVICE_NAME service..."
sudo systemctl stop "$SERVICE_NAME"

# Check if service stopped successfully
if ! sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service stopped successfully!"
else
    echo "⚠️  Service may still be running"
    sudo systemctl status "$SERVICE_NAME" --no-pager -l
fi