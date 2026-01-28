#!/usr/bin/env python3
"""
Script to add duration metadata to existing Label Studio tasks
This updates tasks that don't have duration information
"""

import os
import librosa
import soundfile as sf
from pathlib import Path
from label_studio_sdk import Client
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv('config.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
LS_URL = os.getenv("LABEL_STUDIO_URL", "http://localhost:8080")
LS_API_KEY = os.getenv("LABEL_STUDIO_API_KEY")
PROJECT_ID = int(os.getenv("LS_PROJECT_ID", "1"))
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

def update_tasks_with_duration():
    """Update all Label Studio tasks with audio duration metadata"""

    # Connect to Label Studio
    try:
        client = Client(url=LS_URL, api_key=LS_API_KEY)
        project = client.get_project(PROJECT_ID)
        logger.info("✅ Connected to Label Studio")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Label Studio: {e}")
        return False

    # Get all tasks
    try:
        tasks = project.get_tasks()
        logger.info(f"📋 Found {len(tasks)} tasks in project {PROJECT_ID}")
    except Exception as e:
        logger.error(f"❌ Failed to get tasks: {e}")
        return False

    # Process each task
    updated_count = 0
    skipped_count = 0
    error_count = 0

    for i, task in enumerate(tasks, 1):
        task_id = task['id']
        audio_path = task['data'].get('audio')

        # Check if duration already exists
        existing_duration = task['data'].get('duration')
        if existing_duration is not None:
            logger.info(f"[{i}/{len(tasks)}] Task {task_id}: Duration already exists ({existing_duration}s)")
            skipped_count += 1
            continue

        if not audio_path:
            logger.warning(f"[{i}/{len(tasks)}] Task {task_id}: No audio path found")
            error_count += 1
            continue

        # Convert Label Studio path to filesystem path
        # audio_path is like "/data/media/project_1/filename.wav"
        if audio_path.startswith('/data/media/'):
            file_path = audio_path.replace('/data/media/', '/opt/label-studio/media/')
        elif audio_path.startswith('/data/'):
            file_path = audio_path.replace('/data/', '/opt/label-studio/')
        else:
            file_path = f"/opt/label-studio/media/{audio_path}"

        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"[{i}/{len(tasks)}] Task {task_id}: Audio file not found: {file_path}")
            error_count += 1
            continue

        # Get audio duration
        duration = get_audio_duration(str(file_path))
        if duration is None:
            logger.error(f"[{i}/{len(tasks)}] Task {task_id}: Failed to extract duration")
            error_count += 1
            continue

        # Update task data
        try:
            # Preserve existing metadata
            existing_metadata = task['data'].get('metadata', {})

            updated_data = {
                **task['data'],
                'duration': duration,
                'metadata': {
                    **existing_metadata,
                    'duration_extracted_at': '2025-09-23T13:00:00',  # Current timestamp
                    'duration_extraction_method': 'librosa'
                }
            }

            # Update the task in Label Studio
            project.update_task(task_id, data=updated_data)
            updated_count += 1

            logger.info(f"[{i}/{len(tasks)}] Task {task_id}: ✅ Updated with duration {duration:.2f}s")

        except Exception as e:
            logger.error(f"[{i}/{len(tasks)}] Task {task_id}: Failed to update: {e}")
            error_count += 1

    # Summary
    logger.info("\n" + "="*50)
    logger.info("📊 DURATION UPDATE SUMMARY")
    logger.info("="*50)
    logger.info(f"✅ Updated: {updated_count} tasks")
    logger.info(f"⏭️  Skipped: {skipped_count} tasks (duration already exists)")
    logger.info(f"❌ Errors: {error_count} tasks")
    logger.info(f"📋 Total: {len(tasks)} tasks")

    success_rate = (updated_count / len(tasks)) * 100 if tasks else 0
    logger.info(f"🎯 Success rate: {success_rate:.1f}%")

    return updated_count > 0

if __name__ == "__main__":
    logger.info("🎵 Label Studio Duration Metadata Updater")
    logger.info("==========================================")

    if not LS_API_KEY:
        logger.error("❌ LABEL_STUDIO_API_KEY not configured")
        exit(1)

    success = update_tasks_with_duration()

    if success:
        logger.info("\n🎉 Duration metadata update completed successfully!")
        logger.info("💡 The compensation system can now calculate earnings based on actual audio duration.")
    else:
        logger.error("\n❌ Duration metadata update failed!")
        exit(1)