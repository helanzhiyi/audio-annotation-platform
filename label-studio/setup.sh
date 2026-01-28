#!/bin/bash
set -e

# Label Studio Setup Script
# This script configures the environment for Label Studio deployment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
ENV_EXAMPLE="$SCRIPT_DIR/.env.example"

echo "========================================"
echo "Label Studio Environment Setup"
echo "========================================"
echo ""

# Check if .env already exists
if [ -f "$ENV_FILE" ]; then
    echo "⚠️  .env file already exists!"
    read -p "Do you want to reconfigure? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Setup cancelled. Using existing .env file."
        exit 0
    fi
    # Backup existing .env
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%s)"
    echo "✓ Backed up existing .env file"
fi

# Copy template
if [ ! -f "$ENV_EXAMPLE" ]; then
    echo "❌ Error: .env.example not found!"
    exit 1
fi

cp "$ENV_EXAMPLE" "$ENV_FILE"
echo "✓ Created .env file from template"
echo ""

# Function to detect public IP
detect_public_ip() {
    # Try AWS metadata service (for EC2)
    local aws_ip=$(curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    if [ -n "$aws_ip" ]; then
        echo "$aws_ip"
        return
    fi

    # Try external IP services
    local ext_ip=$(curl -s --connect-timeout 2 https://api.ipify.org 2>/dev/null || echo "")
    if [ -n "$ext_ip" ]; then
        echo "$ext_ip"
        return
    fi

    echo ""
}

# Detect if running on EC2 or cloud
PUBLIC_IP=$(detect_public_ip)

echo "Configuration:"
echo "-------------"

# Configure LABEL_STUDIO_HOST
if [ -n "$PUBLIC_IP" ]; then
    echo "✓ Detected public IP: $PUBLIC_IP"
    read -p "Use this IP for Label Studio host? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        LABEL_STUDIO_HOST="http://$PUBLIC_IP:8080"
    else
        read -p "Enter Label Studio host URL (e.g., http://your-domain.com:8080): " LABEL_STUDIO_HOST
    fi
else
    echo "ℹ️  No public IP detected (local deployment)"
    read -p "Enter Label Studio host URL [http://localhost:8080]: " LABEL_STUDIO_HOST
    LABEL_STUDIO_HOST=${LABEL_STUDIO_HOST:-http://localhost:8080}
fi

# Generate PostgreSQL password
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)
echo "✓ Generated PostgreSQL password"

# Generate Django secret key
SECRET_KEY=$(openssl rand -base64 50 | tr -d "=+/" | cut -c1-50)
echo "✓ Generated Django secret key"

# Update .env file using a more portable approach
# Create a temporary file with the updated values
TEMP_FILE="${ENV_FILE}.tmp"
> "$TEMP_FILE"

while IFS= read -r line; do
    if [[ "$line" =~ ^LABEL_STUDIO_HOST= ]]; then
        echo "LABEL_STUDIO_HOST=$LABEL_STUDIO_HOST"
    elif [[ "$line" =~ ^POSTGRES_PASSWORD= ]]; then
        echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
    elif [[ "$line" =~ ^SECRET_KEY= ]]; then
        echo "SECRET_KEY=$SECRET_KEY"
    else
        echo "$line"
    fi
done < "$ENV_FILE" > "$TEMP_FILE"

# Replace original file with updated one
mv "$TEMP_FILE" "$ENV_FILE"

echo ""
echo "========================================"
echo "Syncing PostgreSQL credentials to middleware..."
echo "========================================"

# Check if middleware config exists and sync PostgreSQL credentials
MIDDLEWARE_CONFIG="/opt/ls-middleware/config.env"
if [ -f "$MIDDLEWARE_CONFIG" ]; then
    echo "✓ Found middleware config at $MIDDLEWARE_CONFIG"

    # Update PostgreSQL credentials in middleware config
    # Create temp file
    MIDDLEWARE_TEMP="${MIDDLEWARE_CONFIG}.tmp"
    > "$MIDDLEWARE_TEMP"

    while IFS= read -r line; do
        if [[ "$line" =~ ^POSTGRES_DB= ]]; then
            echo "POSTGRES_DB=labelstudio"
        elif [[ "$line" =~ ^POSTGRES_USER= ]]; then
            echo "POSTGRES_USER=labelstudio"
        elif [[ "$line" =~ ^POSTGRES_PASSWORD= ]]; then
            echo "POSTGRES_PASSWORD=$POSTGRES_PASSWORD"
        else
            echo "$line"
        fi
    done < "$MIDDLEWARE_CONFIG" > "$MIDDLEWARE_TEMP"

    # Replace original file
    mv "$MIDDLEWARE_TEMP" "$MIDDLEWARE_CONFIG"
    echo "✓ Synced PostgreSQL credentials to middleware config"
else
    echo "⚠️  Middleware config not found at $MIDDLEWARE_CONFIG"
    echo "   Run deployment script first, or manually update PostgreSQL credentials later"
fi

echo ""
echo "========================================"
echo "Configuration Summary:"
echo "========================================"
echo "Label Studio Host: $LABEL_STUDIO_HOST"
echo "PostgreSQL Password: [Generated and synced to middleware]"
echo "Secret Key: [Generated]"
echo ""
echo "✓ Environment configuration complete!"
echo ""
echo "Next steps:"
echo "  1. Review the .env file if needed: cat .env"
echo "  2. Start Label Studio: docker compose up -d"
echo "  3. Check logs: docker compose logs -f"
echo "  4. Access at: $LABEL_STUDIO_HOST"
echo "  5. If middleware is already deployed, restart it: sudo systemctl restart ls-middleware"
echo ""
