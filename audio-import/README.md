# Audio Import System

Import audio files into Label Studio for transcription tasks.

## Prerequisites

- Python 3.8+
- Label Studio and middleware services running
- Audio files in supported formats

## Setup

### 1. Create Python Virtual Environment

```bash
cd /opt/audio-import
python3 -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install label-studio-sdk
```

### 3. Verify Configuration

The script automatically reads configuration from `/opt/ls-middleware/config.env`:
- **LABEL_STUDIO_API_KEY**: API token from Label Studio
- **LABEL_STUDIO_URL**: Label Studio URL (default: `http://localhost:8080`)
- **LS_PROJECT_ID**: Project ID to import to (default: `1`)
- **Media Directory**: `/opt/label-studio/media`

To change the project ID, edit the config file:
```bash
sudo nano /opt/ls-middleware/config.env
# Change LS_PROJECT_ID=1 to LS_PROJECT_ID=2
sudo systemctl restart ls-middleware  # Restart middleware to use new project
```

## Usage

### Basic Import

```bash
# Activate virtual environment
cd /opt/audio-import
source venv/bin/activate

# Import audio files from a directory
python import_final.py /path/to/your/audio/files
```

### Example

```bash
# Create a test directory with audio files
mkdir -p ~/audio_samples
# Place your .wav files in ~/audio_samples

# Import them
cd /opt/audio-import
source venv/bin/activate
python import_audio.py ~/audio_samples
```

## How It Works

1. **Scans directory** for supported audio files
2. **Generates unique filenames** using MD5 hash to prevent duplicates
3. **Copies files** to Label Studio media directory with proper permissions
4. **Creates tasks** in Label Studio project via API
5. **Reports progress** and any errors

## Directory Structure

- `import_audio.py` - Main import script
- `venv/` - Python virtual environment (created during setup)

## Supported Audio Formats

- **WAV** - Uncompressed audio (recommended)
- **MP3** - Compressed audio
- **M4A** - AAC compressed audio
- **OGG** - Ogg Vorbis compressed audio
- **FLAC** - Lossless compressed audio
- **WEBM** - Web media format
- **OPUS** - Modern compressed audio

## Troubleshooting

### Permission Errors
```bash
# Ensure Label Studio media directory has correct permissions
sudo chown -R 1001:1001 /opt/label-studio/media
```

### API Connection Issues
```bash
# Verify middleware is running
curl http://localhost:8010/api/health

# Check Label Studio is accessible
curl http://localhost:8080
```

### Check Import Results
- Files are visible in Label Studio web interface under your project
- Tasks are created and ready for annotation
- Failed imports are logged in the console output

## Configuration Details

The script reads these settings automatically from `/opt/ls-middleware/config.env`:
- **LABEL_STUDIO_API_KEY**: API token for Label Studio access
- **LABEL_STUDIO_URL**: Label Studio URL (default: `http://localhost:8080`)
- **LS_PROJECT_ID**: Target project ID (default: `1`)
- **LABEL_STUDIO_MEDIA_ROOT**: Media storage path (`/opt/label-studio/media`)

**Note**: Both the import script and middleware use the same config file, so changing `LS_PROJECT_ID` will affect both. Make sure to restart the middleware after changing project ID:
```bash
sudo systemctl restart ls-middleware
```