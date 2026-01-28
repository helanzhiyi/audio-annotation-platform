#!/bin/bash
# Check the status of the Label Studio ASR Middleware service

SERVICE_NAME="ls-middleware"

echo "📊 $SERVICE_NAME service status:"
echo ""

# Show detailed service status
sudo systemctl status "$SERVICE_NAME" --no-pager -l

echo ""
echo "🔍 Quick status check:"
if sudo systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Service is RUNNING"
else
    echo "❌ Service is STOPPED"
fi

if sudo systemctl is-enabled --quiet "$SERVICE_NAME"; then
    echo "✅ Service is ENABLED (auto-start on boot)"
else
    echo "⚠️  Service is DISABLED (will not auto-start)"
fi

echo ""
echo "📝 Recent logs (last 10 lines):"
journalctl -u "$SERVICE_NAME" -n 10 --no-pager

echo ""
echo "💡 Useful commands:"
echo "  journalctl -u $SERVICE_NAME -f         # Follow logs in real-time"
echo "  journalctl -u $SERVICE_NAME -n 50      # Show last 50 log entries"
echo "  sudo systemctl restart $SERVICE_NAME   # Restart service"