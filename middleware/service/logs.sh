#!/bin/bash
# View logs for the Label Studio ASR Middleware service

SERVICE_NAME="ls-middleware"

echo "📝 Viewing $SERVICE_NAME service logs..."
echo "Press Ctrl+C to exit"
echo ""

# Follow logs in real-time
journalctl -u "$SERVICE_NAME" -f --since "1 hour ago"