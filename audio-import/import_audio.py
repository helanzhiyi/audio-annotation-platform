#!/usr/bin/env python3
"""
Enhanced audio import script that includes duration metadata extraction
This ensures future imports automatically include duration for compensation tracking
"""

import os
import sys
import subprocess
import hashlib
import librosa
import soundfile as sf
from pathlib import Path
from label_studio_sdk import Client
from datetime import datetime
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get configuration from middleware config file
config_file = "/opt/ls-middleware/config.env"

def get_config_value(key, default=None):
    """Read a value from the config file"""
    try:
        cmd = f"grep '^{key}=' {config_file} | cut -d'=' -f2"
        result = subprocess.check_output(cmd, shell=True).decode().strip()
        return result if result else default
    except subprocess.CalledProcessError:
        return default

LS_API_KEY = get_config_value("LABEL_STUDIO_API_KEY")
LS_URL = get_config_value("LABEL_STUDIO_URL", "http://localhost:8080")
PROJECT_ID = int(get_config_value("LS_PROJECT_ID", "1"))

# Configuration
LABEL_STUDIO_MEDIA_ROOT = "/opt/label-studio/media"

def get_audio_duration(file_path):
    """Get audio duration in seconds using librosa"""
    try:
        # First try with librosa (more reliable)
        y, sr = librosa.load(file_path, sr=None)
        duration = len(y) / sr
        return float(duration)
    except Exception as e:
        logger.warning(f"Librosa failed for {file_path}: {e}")
        try:
            # Fallback to soundfile
            with sf.SoundFile(file_path) as audio_file:
                duration = len(audio_file) / audio_file.samplerate
                return float(duration)
        except Exception as e2:
            logger.error(f"Both librosa and soundfile failed for {file_path}: {e2}")
            return None

def import_audio_directory(source_directory):
    """Import all audio files from a directory with duration metadata"""

    print(f"🎵 Enhanced Audio Import with Duration Extraction")
    print(f"Using API token: {LS_API_KEY[:20]}...")

    # Connect to Label Studio
    client = Client(url=LS_URL, api_key=LS_API_KEY)
    project = client.get_project(PROJECT_ID)

    # Create project media directory
    project_media = Path(LABEL_STUDIO_MEDIA_ROOT) / f"project_{PROJECT_ID}"
    subprocess.run(['sudo', 'mkdir', '-p', str(project_media)], check=True)

    # Find audio files
    source_path = Path(source_directory)
    audio_extensions = ['*.wav', '*.mp3', '*.m4a', '*.ogg', '*.flac', '*.webm', '*.opus']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(source_path.glob(ext))

    print(f"Found {len(audio_files)} audio files")

    # Process each audio file
    tasks = []
    successful_copies = 0
    duration_extracted = 0

    for i, audio_file in enumerate(audio_files, 1):
        try:
            # Extract duration BEFORE copying
            logger.info(f"[{i}/{len(audio_files)}] Extracting duration for {audio_file.name}")
            duration = get_audio_duration(str(audio_file))

            if duration is not None:
                duration_extracted += 1
                logger.info(f"  ✅ Duration: {duration:.2f}s")
            else:
                logger.warning(f"  ⚠️  Could not extract duration")

            # Generate unique filename
            with open(audio_file, 'rb') as f:
                content = f.read()
                file_hash = hashlib.md5(content).hexdigest()[:16]

            new_filename = f"{file_hash}_{audio_file.name}"
            dest_path = project_media / new_filename

            # Copy with sudo and set permissions in one go
            cmds = [
                ['sudo', 'cp', str(audio_file), str(dest_path)],
                ['sudo', 'chown', '1001:1001', str(dest_path)],
                ['sudo', 'chmod', '644', str(dest_path)]
            ]

            all_success = True
            for cmd in cmds:
                result = subprocess.run(cmd, capture_output=True)
                if result.returncode != 0:
                    all_success = False
                    break

            if all_success and dest_path.exists():
                successful_copies += 1
                print(f"  [{i}/{len(audio_files)}] ✓ {audio_file.name}")

                # Create task with duration metadata
                audio_url = f"/data/media/project_{PROJECT_ID}/{new_filename}"
                task_data = {
                    "data": {
                        "audio": audio_url,
                        "duration": duration,  # Add duration to main data
                        "metadata": {
                            "original_filename": audio_file.name,
                            "file_size": audio_file.stat().st_size,
                            "duration_seconds": duration,
                            "duration_extraction_method": "librosa" if duration else "failed",
                            "imported_at": datetime.now().isoformat(),
                            "import_version": "enhanced_v1.0"
                        }
                    }
                }
                tasks.append(task_data)
            else:
                print(f"  [{i}/{len(audio_files)}] ✗ Failed: {audio_file.name}")

        except Exception as e:
            print(f"  Error processing {audio_file.name}: {e}")

    print(f"\n✓ Successfully copied {successful_copies}/{len(audio_files)} files")
    print(f"🎵 Duration extracted for {duration_extracted}/{len(audio_files)} files")

    # Set final permissions for entire directory
    subprocess.run(['sudo', 'chown', '-R', '1001:1001', str(project_media)], check=True)
    subprocess.run(['sudo', 'chmod', '-R', '755', str(project_media)], check=True)

    # Import tasks to Label Studio
    if tasks:
        try:
            print(f"\nImporting {len(tasks)} tasks to Label Studio...")

            # Import in batches of 50 to avoid timeouts
            batch_size = 50
            total_imported = 0

            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i+batch_size]
                imported = project.import_tasks(batch)
                total_imported += len(batch)
                print(f"  Imported batch {i//batch_size + 1}: {len(batch)} tasks")

            print(f"\n✓ Successfully imported {total_imported} tasks")
            print(f"🎵 All tasks include duration metadata for compensation tracking")

            # Verify
            all_tasks = project.get_tasks()
            print(f"✓ Total tasks in project: {len(all_tasks)}")

        except Exception as e:
            print(f"✗ Error importing tasks: {e}")
            # Save tasks for retry
            with open('/tmp/failed_tasks.json', 'w') as f:
                json.dump(tasks, f)
            print("  Tasks saved to /tmp/failed_tasks.json for retry")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ./import_audio.py <source_directory>")
        print()
        print("Configuration is read from: /opt/ls-middleware/config.env")
        print(f"  - LABEL_STUDIO_API_KEY: {LS_API_KEY[:20] if LS_API_KEY else 'NOT SET'}...")
        print(f"  - LABEL_STUDIO_URL: {LS_URL}")
        print(f"  - LS_PROJECT_ID: {PROJECT_ID}")
        print()
        print("To import to a different project, update LS_PROJECT_ID in config.env:")
        print("  sudo nano /opt/ls-middleware/config.env")
        print()
        print("Example: ./import_audio.py /path/to/audio/files")
        sys.exit(1)

    source_dir = sys.argv[1]

    if not os.path.exists(source_dir):
        print(f"❌ Source directory does not exist: {source_dir}")
        sys.exit(1)

    print(f"🎯 Importing to Project ID: {PROJECT_ID}")
    import_audio_directory(source_dir)