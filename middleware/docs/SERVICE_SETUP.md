# Service Installation Instructions

## Quick Setup

To install the middleware as a system service, run:

```bash
cd /opt/ls-middleware
sudo ./service/install.sh
```

## Manual Installation Steps

If you prefer to install manually:

1. **Copy service file to systemd directory:**
   ```bash
   sudo cp /opt/ls-middleware/service/ls-middleware.service /etc/systemd/system/
   ```

2. **Reload systemd and enable service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ls-middleware
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start ls-middleware
   ```

## Service Management

Once installed, use these commands to manage the service:

```bash
# Start service
sudo systemctl start ls-middleware
# OR
./service/start.sh

# Stop service
sudo systemctl stop ls-middleware
# OR
./service/stop.sh

# Restart service
sudo systemctl restart ls-middleware
# OR
./service/restart.sh

# Check status
sudo systemctl status ls-middleware
# OR
./service/status.sh

# View logs
journalctl -u ls-middleware -f
# OR
./service/logs.sh
```

## Service Features

✅ **Auto-start on boot** - Service automatically starts when server reboots
✅ **Auto-restart on failure** - Service restarts if it crashes
✅ **Graceful shutdown** - Proper signal handling for clean shutdowns
✅ **Resource limits** - Memory and file descriptor limits configured
✅ **Security hardening** - Runs with restricted permissions
✅ **Centralized logging** - All logs go to systemd journal

## Troubleshooting

- **Check service status:** `./service/status.sh`
- **View recent logs:** `journalctl -u ls-middleware -n 50`
- **Follow logs in real-time:** `./service/logs.sh`
- **Restart if needed:** `./service/restart.sh`

## Uninstalling

To remove the service:

```bash
sudo systemctl stop ls-middleware
sudo systemctl disable ls-middleware
sudo rm /etc/systemd/system/ls-middleware.service
sudo systemctl daemon-reload
```