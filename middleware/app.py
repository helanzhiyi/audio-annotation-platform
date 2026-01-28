from fastapi import FastAPI, HTTPException, Header, Security, Depends, Request
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import os
from label_studio_sdk import Client
import redis
import redis.asyncio as aioredis
import httpx
import json
import logging
from dotenv import load_dotenv
import asyncio
import csv
import io
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from models_async import (
    TranscriptionSession,
    AgentStats,
    get_async_db,
    create_tables,
    test_connection
)

# Load environment variables
load_dotenv('config.env')

app = FastAPI(title="Label Studio ASR Middleware")

# Configuration
LS_URL = os.getenv("LABEL_STUDIO_URL", "http://localhost:8080")
LS_API_KEY = os.getenv("LABEL_STUDIO_API_KEY")
PROJECT_ID = int(os.getenv("LS_PROJECT_ID", "1"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
TZ_SYSTEM_API_KEY = os.getenv("TZ_SYSTEM_API_KEY")

# Initialize Label Studio client
ls_client = Client(url=LS_URL, api_key=LS_API_KEY)
redis_client = redis.from_url(REDIS_URL, decode_responses=True)
project = None  # Will be initialized on startup

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Async clients and separated caches - will be initialized on startup
async_redis_client = None
httpx_client = None

# Fast assignment queue - real-time task distribution
assignment_queue = {
    "tasks": [],  # List of task IDs ready for assignment
    "last_sync": None,
    "syncing": False,
    "completed_tasks": set()  # Track completed tasks to prevent re-addition
}

# Stats cache - eventual consistency for dashboard
stats_cache = {
    "total_unlabeled": 0,
    "total_locked": 0,
    "available": 0,
    "last_updated": None
}

async def sync_assignment_queue():
    """Sync assignment queue with Label Studio in background"""
    global assignment_queue, stats_cache
    if assignment_queue["syncing"]:
        return  # Already syncing

    assignment_queue["syncing"] = True
    try:
        if project:
            loop = asyncio.get_event_loop()
            # Get fresh task list from Label Studio
            tasks = await loop.run_in_executor(None, project.get_unlabeled_tasks)
            logger.info(f"Label Studio returned {len(tasks)} unlabeled tasks")

            # Extract just the IDs for the assignment queue, excluding completed tasks
            fresh_task_ids = [
                task['id'] for task in tasks
                if task['id'] not in assignment_queue["completed_tasks"]
            ]

            logger.info(f"After filtering completed tasks: {len(fresh_task_ids)} available")

            # Debug: Check if we're getting limited results
            if len(tasks) > 0:
                logger.info(f"Task ID range: {min(task['id'] for task in tasks)} to {max(task['id'] for task in tasks)}")
                sample_tasks = tasks[:3]
                logger.info(f"Sample tasks: {[t.get('id') for t in sample_tasks]}")

            # Clear and repopulate Redis assignment queue atomically
            pipe = async_redis_client.pipeline()
            pipe.delete("assignment_queue")
            for task_id in fresh_task_ids:
                pipe.rpush("assignment_queue", task_id)
            await pipe.execute()

            # Update memory queue for stats/monitoring
            assignment_queue["tasks"] = fresh_task_ids
            assignment_queue["last_sync"] = datetime.utcnow()

            # Update stats cache
            stats_cache["total_unlabeled"] = len(fresh_task_ids)
            stats_cache["last_updated"] = datetime.utcnow()

            # Count locked tasks for accurate stats
            locked_count = 0
            for task_id in fresh_task_ids:
                if await async_redis_client.exists(f"task:locked:{task_id}"):
                    locked_count += 1

            stats_cache["total_locked"] = locked_count
            stats_cache["available"] = len(fresh_task_ids) - locked_count

            logger.info(f"Assignment queue synced: {len(fresh_task_ids)} tasks available")
    except Exception as e:
        logger.error(f"Failed to sync assignment queue: {e}")
    finally:
        assignment_queue["syncing"] = False

async def sync_assignment_queue_periodically():
    """Background task to sync assignment queue every 30 seconds"""
    while True:
        try:
            await sync_assignment_queue()
            await asyncio.sleep(30)  # Sync every 30 seconds
        except Exception as e:
            logger.error(f"Error in periodic assignment queue sync: {e}")
            await asyncio.sleep(60)  # Wait longer on error

def get_available_task_ids():
    """Get available task IDs from assignment queue"""
    return assignment_queue["tasks"].copy()

async def remove_task_from_queue(task_id):
    """Immediately remove task from assignment queue and mark as completed"""
    # Remove from memory queue
    if task_id in assignment_queue["tasks"]:
        assignment_queue["tasks"].remove(task_id)

    # Remove from Redis queue (LREM removes all occurrences)
    await async_redis_client.lrem("assignment_queue", 0, task_id)

    # Mark as completed to prevent future re-addition
    assignment_queue["completed_tasks"].add(task_id)

    # Update stats immediately
    stats_cache["total_unlabeled"] = max(0, stats_cache["total_unlabeled"] - 1)
    stats_cache["available"] = len(assignment_queue["tasks"])
    logger.info(f"Task {task_id} removed from assignment queue and marked as completed")
    return True

@app.on_event("startup")
async def startup_event():
    """Initialize async clients on startup"""
    global async_redis_client, httpx_client, project
    async_redis_client = await aioredis.from_url(REDIS_URL, decode_responses=True)
    httpx_client = httpx.AsyncClient(timeout=30.0)
    await create_tables()

    # Initialize Label Studio project
    try:
        project = ls_client.get_project(PROJECT_ID)
        logger.info(f"✅ Label Studio project {PROJECT_ID} initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Label Studio project {PROJECT_ID}: {e}")
        project = None

    logger.info("Async clients initialized")

    # Perform initial sync to populate assignment queue
    await sync_assignment_queue()

    # Start background task to sync assignment queue periodically
    asyncio.create_task(sync_assignment_queue_periodically())

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if async_redis_client:
        await async_redis_client.close()
    if httpx_client:
        await httpx_client.aclose()
    logger.info("Async clients closed")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    # Log the incoming request
    logger.info(f"📨 {request.method} {request.url.path} - Client: {request.client.host if request.client else 'unknown'}")

    response = await call_next(request)

    # Log the response
    process_time = time.time() - start_time
    logger.info(f"📤 {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")

    return response

# Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_tz_system(api_key: str = Security(api_key_header)):
    """Verify the request is from TZ system"""
    if api_key != TZ_SYSTEM_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return True

# Models
class TaskRequest(BaseModel):
    agent_id: int
    limit: int = 1

class TranscriptionSubmit(BaseModel):
    agent_id: int
    transcription: str

class TaskSkip(BaseModel):
    agent_id: int
    reason: Optional[str] = None

class TaskResponse(BaseModel):
    task_id: int
    audio_url: str
    duration: Optional[float]
    metadata: dict

# Core endpoints
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis
        await async_redis_client.ping()
        
        # Check database
        db_ok = await test_connection()
        
        return {
            "status": "healthy",
            "redis": "connected",
            "database": "connected" if db_ok else "error",
            "project_id": PROJECT_ID
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/api/tasks/request", response_model=TaskResponse)
async def request_task_for_agent(
    request: TaskRequest,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Request a task for a specific agent"""
    
    # Check if agent already has an active task
    active_task_key = f"agent:active:{request.agent_id}"
    active_task = await async_redis_client.get(active_task_key)
    
    if active_task:
        task_data = json.loads(active_task)
        logger.info(f"Agent {request.agent_id} already has task {task_data['task_id']}")
        return TaskResponse(**task_data)
    
    try:
        # Get available task IDs from fast assignment queue
        available_task_ids = get_available_task_ids()

        if not available_task_ids:
            # Queue is empty - immediately sync instead of returning 404
            logger.info("Assignment queue empty, performing immediate sync...")
            await sync_assignment_queue()
            available_task_ids = get_available_task_ids()

            if not available_task_ids:
                # Still empty after sync - fallback to direct Label Studio query
                logger.info("Queue still empty after sync, checking Label Studio directly...")
                try:
                    tasks = project.get_unlabeled_tasks()
                    if tasks:
                        # Found tasks in Label Studio but not in our queue - force full resync
                        logger.warning(f"Found {len(tasks)} unlabeled tasks in Label Studio but queue is empty - forcing resync")
                        await sync_assignment_queue()
                        available_task_ids = get_available_task_ids()
                except Exception as e:
                    logger.error(f"Error checking Label Studio for tasks: {e}")

                if not available_task_ids:
                    # Truly no tasks available anywhere
                    raise HTTPException(status_code=404, detail="No tasks available in assignment queue")

        # Try to get a task using Redis atomic transactions for concurrency safety
        max_attempts = 50  # Limit attempts to prevent infinite loops

        # Debugging counters
        debug_results = {"SKIPPED": 0, "LOCKED": 0, "DISABLED": 0, "None": 0}

        for attempt in range(max_attempts):
            # First, ensure Redis queue has tasks from memory queue
            if await async_redis_client.llen("assignment_queue") == 0:
                # Atomically batch transfer tasks from memory to Redis
                pipeline = async_redis_client.pipeline()
                transferred_count = 0

                for memory_task_id in available_task_ids[:10]:  # Batch transfer
                    pipeline.rpush("assignment_queue", memory_task_id)
                    assignment_queue["tasks"].remove(memory_task_id)
                    transferred_count += 1

                if transferred_count > 0:
                    await pipeline.execute()

            # Atomic task assignment using Lua script for consistency
            lua_script = """
                -- Get a task from queue
                local task_id = redis.call('LPOP', 'assignment_queue')
                if not task_id then
                    return nil
                end

                local agent_id = ARGV[1]
                local skip_key = 'task:skipped:' .. task_id .. ':' .. agent_id
                local lock_key = 'task:locked:' .. task_id
                local global_skip_key = 'task:global_skips:' .. task_id

                -- Check if this task has been skipped by 5+ people (permanently disabled)
                local global_skip_count = tonumber(redis.call('GET', global_skip_key) or 0)
                if global_skip_count >= 5 then
                    -- Task is permanently disabled, don't put back in queue
                    return 'DISABLED'
                end

                -- Check if agent recently skipped this task
                if redis.call('EXISTS', skip_key) == 1 then
                    -- Put task back at end of queue for other agents
                    redis.call('RPUSH', 'assignment_queue', task_id)
                    return 'SKIPPED'
                end

                -- Try to acquire lock atomically
                local lock_result = redis.call('SET', lock_key, agent_id, 'NX', 'EX', 3600)
                if lock_result then
                    return task_id
                else
                    -- Someone else locked it, put back in queue
                    redis.call('RPUSH', 'assignment_queue', task_id)
                    return 'LOCKED'
                end
            """

            result = await async_redis_client.eval(lua_script, 0, str(request.agent_id))

            if result is None:
                debug_results["None"] += 1
                break  # No more tasks available
            elif result == b'SKIPPED' or result == 'SKIPPED':
                debug_results["SKIPPED"] += 1
                continue  # This agent skipped this task, try next
            elif result == b'LOCKED' or result == 'LOCKED':
                debug_results["LOCKED"] += 1
                continue  # Task was locked by another agent, try next
            elif result == b'DISABLED' or result == 'DISABLED':
                debug_results["DISABLED"] += 1
                continue  # Task was skipped by 2+ agents, permanently disabled
            else:
                # Successfully got and locked a task
                task_id = int(result)
                task_lock_key = f"task:locked:{task_id}"

                # Get task details from Label Studio for metadata
                try:
                    response = await httpx_client.get(
                        f"{LS_URL}/api/tasks/{task_id}",
                        headers={"Authorization": f"Token {LS_API_KEY}"}
                    )
                    task_details = response.json() if response.status_code == 200 else {}
                except Exception:
                    task_details = {}

                task_data = {
                    "task_id": task_id,
                    "audio_url": f"/api/audio/stream/{task_id}/{request.agent_id}",
                    "duration": task_details.get('data', {}).get('duration'),
                    "metadata": task_details.get('data', {}).get('metadata', {})
                }
                
                # Store agent's active task
                await async_redis_client.setex(
                    active_task_key,
                    3600,  # 1 hour to complete
                    json.dumps(task_data)
                )
                
                # Store in PostgreSQL
                transcription_session = TranscriptionSession(
                    agent_id=request.agent_id,
                    task_id=task_id,
                    assigned_at=datetime.utcnow(),
                    duration_seconds=task_details.get('data', {}).get('duration'),
                    status='assigned'
                )
                db.add(transcription_session)
                await db.commit()

                # Update agent stats
                result = await db.execute(
                    select(AgentStats).filter(AgentStats.agent_id == request.agent_id)
                )
                agent_stats = result.scalar_one_or_none()
                
                if not agent_stats:
                    agent_stats = AgentStats(agent_id=request.agent_id)
                    db.add(agent_stats)
                    
                agent_stats.last_active = datetime.utcnow()
                await db.commit()

                # Audit log
                await async_redis_client.lpush(
                    "audit:assignments",
                    json.dumps({
                        "agent_id": request.agent_id,
                        "task_id": task_id,
                        "assigned_at": datetime.utcnow().isoformat()
                    })
                )

                logger.info(f"Assigned task {task_id} to agent {request.agent_id}")
                return TaskResponse(**task_data)
        
        # No available tasks for this agent (all locked or skipped)
        logger.warning(f"Agent {request.agent_id} exhausted {max_attempts} attempts. Debug results: {debug_results}")
        logger.warning(f"Redis queue length: {await async_redis_client.llen('assignment_queue')}")
        logger.warning(f"Memory queue length: {len(available_task_ids)}")

        raise HTTPException(status_code=404, detail=f"No available tasks for agent {request.agent_id} - all tasks are locked or recently skipped")
        
    except HTTPException:
        # Re-raise HTTPException as-is (404, 403, etc.)
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error requesting task: {str(e)}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio/stream/{task_id}/{agent_id}")
async def stream_audio(
    task_id: int,
    agent_id: int,
    authorized: bool = Security(verify_tz_system)
):
    """Stream audio file directly from filesystem"""
    task_lock_key = f"task:locked:{task_id}"
    locked_by = await async_redis_client.get(task_lock_key)

    if locked_by is None or int(locked_by) != agent_id:
        logger.warning(f"Agent {agent_id} tried to access task {task_id} locked by {locked_by}")
        raise HTTPException(status_code=403, detail="Access denied to this audio")

    try:
        # Get task from Label Studio using async HTTP
        headers = {"Authorization": f"Token {LS_API_KEY}"}
        response = await httpx_client.get(
            f"{LS_URL}/api/tasks/{task_id}",
            headers=headers
        )

        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Task not found")

        task = response.json()
        audio_path = task['data'].get('audio')

        if not audio_path:
            raise HTTPException(status_code=404, detail="No audio found")

        logger.info(f"Task {task_id}: Raw audio_path from Label Studio: {audio_path}")

        # Convert Label Studio path to filesystem path
        if audio_path.startswith('/data/media/'):
            file_path = audio_path.replace('/data/media/', '/opt/label-studio/media/')
        elif audio_path.startswith('/data/'):
            file_path = audio_path.replace('/data/', '/opt/label-studio/')
        else:
            file_path = f"/opt/label-studio/media/{audio_path}"

        logger.info(f"Task {task_id}: Converted file_path: {file_path}")

        if not os.path.exists(file_path):
            logger.error(f"Audio file not found: {file_path}")
            raise HTTPException(status_code=404, detail="Audio file not found on disk")

        # Determine content type from file extension
        file_ext = os.path.splitext(file_path)[1].lower()
        content_type_map = {
            '.wav': 'audio/wav',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac',
            '.webm': 'audio/webm',
            '.opus': 'audio/opus'
        }
        media_type = content_type_map.get(file_ext, 'audio/mpeg')

        # Audit log
        await async_redis_client.lpush(
            "audit:audio_access",
            json.dumps({
                "agent_id": agent_id,
                "task_id": task_id,
                "accessed_at": datetime.utcnow().isoformat(),
                "file_path": file_path
            })
        )

        logger.info(f"Serving audio file: {file_path} to agent {agent_id}")

        return FileResponse(
            file_path,
            media_type=media_type,
            filename=f"task_{task_id}{file_ext}",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Accept-Ranges": "bytes"
            }
        )

    except httpx.HTTPError as e:
        logger.error(f"Error fetching task from Label Studio: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch task data")
    except Exception as e:
        logger.error(f"Error streaming audio: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/{task_id}/submit")
async def submit_transcription(
    task_id: int,
    submission: TranscriptionSubmit,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Submit transcription for a task"""
    
    # Verify agent has this task locked
    task_lock_key = f"task:locked:{task_id}"
    locked_by = await async_redis_client.get(task_lock_key)
    
    if locked_by is None or int(locked_by) != submission.agent_id:
        logger.warning(f"Agent {submission.agent_id} tried to submit for task {task_id}")
        raise HTTPException(status_code=403, detail="Cannot submit for this task")
    
    try:
        # Create annotation in Label Studio
        annotation_result = [{
            "value": {
                "text": [submission.transcription]
            },
            "from_name": "transcription",
            "to_name": "audio",
            "type": "textarea"
        }]
        
        # Submit annotation via API
        response = await httpx_client.post(
            f"{LS_URL}/api/tasks/{task_id}/annotations",
            headers={"Authorization": f"Token {LS_API_KEY}"},
            json={"result": annotation_result}
        )
        
        if response.status_code not in [200, 201]:
            raise HTTPException(status_code=500, detail="Failed to create annotation")
        
        # Update PostgreSQL transcription session
        result = await db.execute(
            select(TranscriptionSession).filter(
                TranscriptionSession.agent_id == submission.agent_id,
                TranscriptionSession.task_id == task_id,
                TranscriptionSession.status == 'assigned'
            )
        )
        sessions = result.scalars().all()

        if len(sessions) > 1:
            logger.warning(f"Found {len(sessions)} duplicate sessions for agent {submission.agent_id}, task {task_id}")

        if sessions:
            # Update all sessions (in case of duplicates)
            for session in sessions:
                session.completed_at = datetime.utcnow()
                session.status = 'completed'
                session.transcription_length = len(submission.transcription)

            # Update agent stats
            stats_result = await db.execute(
                select(AgentStats).filter(AgentStats.agent_id == submission.agent_id)
            )
            agent_stats = stats_result.scalar_one_or_none()
            
            if agent_stats and session.duration_seconds:
                agent_stats.total_duration_seconds += session.duration_seconds
                agent_stats.total_tasks_completed += 1
                agent_stats.last_active = datetime.utcnow()
                session_earnings = (session.duration_seconds / 60) * 0.45
                agent_stats.total_earnings += session_earnings

            await db.commit()

        # Clean up Redis
        await async_redis_client.delete(task_lock_key)
        await async_redis_client.delete(f"agent:active:{submission.agent_id}")

        # Audit log
        await async_redis_client.lpush(
            "audit:completions",
            json.dumps({
                "agent_id": submission.agent_id,
                "task_id": task_id,
                "completed_at": datetime.utcnow().isoformat(),
                "transcription_length": len(submission.transcription)
            })
        )
        
        logger.info(f"Agent {submission.agent_id} completed task {task_id}")

        # Immediately remove task from assignment queue - no more reassignments!
        await remove_task_from_queue(task_id)

        return {
            "status": "success",
            "message": "Transcription submitted successfully"
        }

    except Exception as e:
        logger.error(f"Error submitting transcription: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tasks/{task_id}/skip")
async def skip_task(
    task_id: int,
    skip_data: TaskSkip,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Skip a task and release it for other agents"""

    task_lock_key = f"task:locked:{task_id}"
    locked_by = await async_redis_client.get(task_lock_key)

    if locked_by is None or int(locked_by) != skip_data.agent_id:
        logger.warning(f"Agent {skip_data.agent_id} tried to skip task {task_id} locked by {locked_by}")
        raise HTTPException(status_code=403, detail="Cannot skip task not assigned to you")

    try:
        # Mark task as skipped by this agent
        skip_key = f"task:skipped:{task_id}:{skip_data.agent_id}"
        await async_redis_client.setex(skip_key, 1800, "skipped")

        # Increment global skip count for this task
        global_skip_key = f"task:global_skips:{task_id}"
        global_skip_count = await async_redis_client.incr(global_skip_key)

        # Set expiration on global skip counter (24 hours)
        if global_skip_count == 1:
            await async_redis_client.expire(global_skip_key, 86400)

        # Log if task becomes permanently disabled
        if global_skip_count >= 5:
            logger.warning(f"Task {task_id} permanently disabled after {global_skip_count} skips")

        # Update PostgreSQL transcription session
        result = await db.execute(
            select(TranscriptionSession).filter(
                TranscriptionSession.agent_id == skip_data.agent_id,
                TranscriptionSession.task_id == task_id,
                TranscriptionSession.status == 'assigned'
            )
        )
        sessions = result.scalars().all()

        if len(sessions) > 1:
            logger.warning(f"Found {len(sessions)} duplicate sessions for agent {skip_data.agent_id}, task {task_id}")

        session = sessions[0] if sessions else None

        if sessions:
            # Update all sessions (in case of duplicates)
            for session in sessions:
                session.status = 'skipped'
                session.skip_reason = skip_data.reason or "No reason provided"

            # Update agent stats (only once regardless of duplicate sessions)
            stats_result = await db.execute(
                select(AgentStats).filter(AgentStats.agent_id == skip_data.agent_id)
            )
            agent_stats = stats_result.scalar_one_or_none()

            if agent_stats:
                agent_stats.total_tasks_skipped += 1
                agent_stats.last_active = datetime.utcnow()

            await db.commit()

        # Clean up Redis locks
        await async_redis_client.delete(task_lock_key)
        await async_redis_client.delete(f"agent:active:{skip_data.agent_id}")

        # Audit log
        await async_redis_client.lpush(
            "audit:skips",
            json.dumps({
                "agent_id": skip_data.agent_id,
                "task_id": task_id,
                "skipped_at": datetime.utcnow().isoformat(),
                "reason": skip_data.reason or "No reason provided"
            })
        )

        logger.info(f"Agent {skip_data.agent_id} skipped task {task_id}: {skip_data.reason}")

        # Note: We don't invalidate cache for skips since task is still available to other agents
        # Only completion actually removes a task from the available pool

        return {
            "status": "success",
            "message": "Task skipped successfully"
        }

    except Exception as e:
        logger.error(f"Error skipping task: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/available/count")
async def get_available_task_count(
    agent_id: Optional[int] = None,
    authorized: bool = Security(verify_tz_system)
):
    """Get count of available unassigned tasks"""
    try:
        # Use fast stats cache for immediate response
        if stats_cache["last_updated"] is None:
            # Trigger sync and return basic stats
            asyncio.create_task(sync_assignment_queue())
            return {
                "available_tasks": len(assignment_queue["tasks"]),
                "total_unlabeled": len(assignment_queue["tasks"]),
                "note": "Stats syncing"
            }

        result = {
            "available_tasks": stats_cache["available"],
            "total_unlabeled": stats_cache["total_unlabeled"]
        }

        # If agent_id provided, count tasks available for that specific agent
        if agent_id:
            available_for_agent = 0
            for task_id in assignment_queue["tasks"]:
                skip_key = f"task:skipped:{task_id}:{agent_id}"
                lock_key = f"task:locked:{task_id}"
                if not await async_redis_client.exists(skip_key) and not await async_redis_client.exists(lock_key):
                    available_for_agent += 1
            result["available_for_agent"] = available_for_agent

        return result

    except Exception as e:
        logger.error(f"Error counting tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tasks/disabled")
async def get_disabled_tasks(
    authorized: bool = Security(verify_tz_system)
):
    """Get list of tasks that have been permanently disabled due to 5+ skips"""
    disabled_tasks = []

    # Scan for all global skip keys
    keys = await async_redis_client.keys("task:global_skips:*")

    for key in keys:
        skip_count = await async_redis_client.get(key)
        if skip_count and int(skip_count) >= 5:
            task_id = key.decode('utf-8').split(':')[-1] if isinstance(key, bytes) else key.split(':')[-1]
            disabled_tasks.append({
                "task_id": int(task_id),
                "skip_count": int(skip_count)
            })

    disabled_tasks.sort(key=lambda x: x['task_id'])

    return {
        "disabled_tasks": disabled_tasks,
        "total_disabled": len(disabled_tasks)
    }

@app.post("/api/tasks/reset-disabled")
async def reset_disabled_tasks(
    authorized: bool = Security(verify_tz_system)
):
    """Reset all disabled tasks to make them available again"""
    try:
        # Get all global skip keys
        keys = await async_redis_client.keys("task:global_skips:*")

        reset_count = 0
        restored_tasks = []

        for key in keys:
            skip_count = await async_redis_client.get(key)
            if skip_count and int(skip_count) >= 2:  # Tasks with 2+ skips that were disabled
                task_id = key.decode('utf-8').split(':')[-1] if isinstance(key, bytes) else key.split(':')[-1]

                # Delete the global skip counter to reset the task
                await async_redis_client.delete(key)
                reset_count += 1
                restored_tasks.append(int(task_id))

        # Trigger assignment queue sync to pick up restored tasks
        if reset_count > 0:
            asyncio.create_task(sync_assignment_queue())

        logger.info(f"Reset {reset_count} disabled tasks: {restored_tasks[:10]}{'...' if len(restored_tasks) > 10 else ''}")

        return {
            "status": "success",
            "reset_count": reset_count,
            "restored_tasks": restored_tasks,
            "message": f"Reset {reset_count} disabled tasks"
        }

    except Exception as e:
        logger.error(f"Error resetting disabled tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/{agent_id}/stats")
async def get_agent_stats(
    agent_id: int,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get statistics for a specific agent"""

    # Get agent stats from PostgreSQL
    result = await db.execute(
        select(AgentStats).filter(AgentStats.agent_id == agent_id)
    )
    agent_stats = result.scalar_one_or_none()
    
    if not agent_stats:
        agent_stats = AgentStats(agent_id=agent_id)
        db.add(agent_stats)
        await db.commit()

    # Get today's completions
    today = datetime.utcnow().date()
    today_result = await db.execute(
        select(func.count(TranscriptionSession.id)).filter(
            TranscriptionSession.agent_id == agent_id,
            TranscriptionSession.status == 'completed',
            TranscriptionSession.completed_at >= datetime.combine(today, datetime.min.time())
        )
    )
    today_completions = today_result.scalar()

    # Check current task from Redis
    active_task = await async_redis_client.get(f"agent:active:{agent_id}")
    current_task_id = None
    if active_task:
        current_task_id = json.loads(active_task)['task_id']

    return {
        "agent_id": agent_id,
        "current_task_id": current_task_id,
        "tasks_completed_today": today_completions,
        "total_tasks_completed": agent_stats.total_tasks_completed,
        "total_tasks_skipped": agent_stats.total_tasks_skipped,
        "total_duration_seconds": agent_stats.total_duration_seconds,
        "total_earnings": round(agent_stats.total_earnings, 2),
        "last_active": agent_stats.last_active.isoformat() if agent_stats.last_active else None
    }

@app.get("/api/agents/{agent_id}/earnings")
async def get_agent_earnings(
    agent_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get detailed earnings report for a specific agent"""
    # Parse date parameters
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = datetime.fromisoformat(start_date)
    if end_date:
        end_dt = datetime.fromisoformat(end_date)

    # Get agent stats
    result = await db.execute(select(AgentStats).filter(AgentStats.agent_id == agent_id))
    agent_stats = result.scalar_one_or_none()
    if not agent_stats:
        agent_stats = AgentStats(agent_id=agent_id)
        db.add(agent_stats)
        await db.commit()

    # Build query for sessions
    sessions_query = select(TranscriptionSession).filter(
        TranscriptionSession.agent_id == agent_id,
        TranscriptionSession.status == 'completed'
    )

    if start_dt:
        sessions_query = sessions_query.filter(TranscriptionSession.completed_at >= start_dt)
    if end_dt:
        sessions_query = sessions_query.filter(TranscriptionSession.completed_at <= end_dt)

    result = await db.execute(sessions_query)
    sessions = result.scalars().all()

    # Calculate earnings
    total_earnings = 0.0
    total_duration = 0.0
    daily_earnings = {}

    for session in sessions:
        duration = session.duration_seconds or 0
        earnings = duration / 60 * 0.45  # $0.45 per minute
        total_earnings += earnings
        total_duration += duration

        # Group by day
        day_key = session.completed_at.date().isoformat()
        if day_key not in daily_earnings:
            daily_earnings[day_key] = {"earnings": 0.0, "duration": 0.0, "tasks": 0}
        daily_earnings[day_key]["earnings"] += earnings
        daily_earnings[day_key]["duration"] += duration
        daily_earnings[day_key]["tasks"] += 1

    return {
        "agent_id": agent_id,
        "total_earnings": round(total_earnings, 2),
        "total_duration_seconds": total_duration,
        "total_tasks": len(sessions),
        "daily_breakdown": daily_earnings,
        "period": {
            "start_date": start_date,
            "end_date": end_date
        }
    }

@app.get("/api/leaderboard/top-performers")
async def get_top_performers_leaderboard(
    limit: int = 10,
    period_days: Optional[int] = None,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get leaderboard of top performing agents by tasks completed"""
    # Get agent stats
    agents_query = select(AgentStats).filter(AgentStats.total_tasks_completed > 0)

    # If period specified, also filter by recent activity
    if period_days:
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        agents_query = agents_query.filter(AgentStats.last_active >= cutoff_date)

    agents_query = agents_query.order_by(AgentStats.total_tasks_completed.desc()).limit(limit)
    result = await db.execute(agents_query)
    agents = result.scalars().all()

    leaderboard = []
    for rank, agent in enumerate(agents, 1):
        total_tasks = agent.total_tasks_completed + agent.total_tasks_skipped
        completion_rate = (agent.total_tasks_completed / total_tasks * 100) if total_tasks > 0 else 0
        avg_duration = agent.total_duration_seconds / agent.total_tasks_completed if agent.total_tasks_completed > 0 else 0

        leaderboard.append({
            "rank": rank,
            "agent_id": agent.agent_id,
            "tasks_completed": agent.total_tasks_completed,
            "tasks_skipped": agent.total_tasks_skipped,
            "completion_rate": round(completion_rate, 2),
            "total_duration_seconds": agent.total_duration_seconds,
            "avg_duration_per_task": round(avg_duration, 2),
            "total_earnings": round(agent.total_earnings, 2),
            "last_active": agent.last_active.isoformat() if agent.last_active else None
        })

    return {
        "leaderboard": leaderboard,
        "period_days": period_days,
        "total_agents": len(leaderboard)
    }

@app.get("/api/leaderboard/earnings")
async def get_earnings_leaderboard(
    limit: int = 10,
    period_days: Optional[int] = None,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get leaderboard of top earning agents"""
    if period_days:
        # Period-based earnings leaderboard
        cutoff_date = datetime.utcnow() - timedelta(days=period_days)
        result = await db.execute(
            select(TranscriptionSession).filter(
                TranscriptionSession.status == 'completed',
                TranscriptionSession.completed_at >= cutoff_date
            )
        )
        sessions = result.scalars().all()

        # Group by agent and calculate earnings
        agent_earnings = {}
        for session in sessions:
            if session.agent_id not in agent_earnings:
                agent_earnings[session.agent_id] = {
                    "tasks_completed": 0,
                    "duration_seconds": 0,
                    "earnings": 0.0
                }
            agent_earnings[session.agent_id]["tasks_completed"] += 1
            agent_earnings[session.agent_id]["duration_seconds"] += session.duration_seconds or 0
            agent_earnings[session.agent_id]["earnings"] += (session.duration_seconds or 0) / 60 * 0.45

        # Sort by earnings and create leaderboard
        sorted_agents = sorted(agent_earnings.items(), key=lambda x: x[1]["earnings"], reverse=True)[:limit]
        leaderboard = []
        for rank, (agent_id, stats) in enumerate(sorted_agents, 1):
            leaderboard.append({
                "rank": rank,
                "agent_id": agent_id,
                "earnings": round(stats["earnings"], 2),
                "tasks_completed": stats["tasks_completed"],
                "duration_seconds": stats["duration_seconds"]
            })
    else:
        # All-time earnings leaderboard
        result = await db.execute(
            select(AgentStats).filter(AgentStats.total_earnings > 0)
            .order_by(AgentStats.total_earnings.desc()).limit(limit)
        )
        agents = result.scalars().all()

        leaderboard = []
        for rank, agent in enumerate(agents, 1):
            leaderboard.append({
                "rank": rank,
                "agent_id": agent.agent_id,
                "earnings": round(agent.total_earnings, 2),
                "tasks_completed": agent.total_tasks_completed,
                "duration_seconds": agent.total_duration_seconds,
                "last_active": agent.last_active.isoformat() if agent.last_active else None
            })

    return {
        "leaderboard": leaderboard,
        "period_days": period_days,
        "total_agents": len(leaderboard)
    }

@app.get("/api/leaderboard/productivity")
async def get_productivity_leaderboard(
    limit: int = 10,
    min_tasks: int = 5,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get leaderboard of most productive agents (by avg time per task)"""
    result = await db.execute(
        select(AgentStats).filter(AgentStats.total_tasks_completed >= min_tasks)
    )
    agents = result.scalars().all()

    # Calculate productivity (lower avg time = higher productivity)
    agent_productivity = []
    for agent in agents:
        avg_time = agent.total_duration_seconds / agent.total_tasks_completed
        agent_productivity.append({
            "agent_id": agent.agent_id,
            "avg_time_per_task": avg_time,
            "tasks_completed": agent.total_tasks_completed,
            "total_duration": agent.total_duration_seconds,
            "total_earnings": agent.total_earnings,
            "last_active": agent.last_active
        })

    # Sort by avg time (ascending = most productive first)
    sorted_agents = sorted(agent_productivity, key=lambda x: x["avg_time_per_task"])[:limit]

    leaderboard = []
    for rank, agent in enumerate(sorted_agents, 1):
        leaderboard.append({
            "rank": rank,
            "agent_id": agent["agent_id"],
            "avg_time_per_task": round(agent["avg_time_per_task"], 2),
            "tasks_completed": agent["tasks_completed"],
            "total_duration_seconds": agent["total_duration"],
            "total_earnings": round(agent["total_earnings"], 2),
            "last_active": agent["last_active"].isoformat() if agent["last_active"] else None
        })

    return {
        "leaderboard": leaderboard,
        "min_tasks_threshold": min_tasks,
        "total_agents": len(leaderboard)
    }

@app.get("/api/stats/live")
async def get_live_stats(
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get real-time system status"""

    # Get currently active sessions from Redis
    active_sessions = []
    async for key in async_redis_client.scan_iter(match="agent:active:*"):
        agent_id = key.split(":")[-1]
        task_data = await async_redis_client.get(key)
        if task_data:
            try:
                task_info = json.loads(task_data)
                active_sessions.append({
                    "agent_id": int(agent_id),
                    "task_id": task_info["task_id"]
                })
            except:
                continue

    # Get today's statistics
    today = datetime.utcnow().date()
    today_result = await db.execute(
        select(TranscriptionSession).filter(
            TranscriptionSession.assigned_at >= datetime.combine(today, datetime.min.time())
        )
    )
    today_sessions = today_result.scalars().all()

    today_completed = [s for s in today_sessions if s.status == 'completed']
    today_skipped = [s for s in today_sessions if s.status == 'skipped']
    today_duration = sum(s.duration_seconds or 0 for s in today_completed)

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "active_sessions": {
            "count": len(active_sessions),
            "sessions": active_sessions
        },
        "today_activity": {
            "assigned": len(today_sessions),
            "completed": len(today_completed),
            "skipped": len(today_skipped),
            "duration_minutes": round(today_duration / 60, 2),
            "earnings": round((today_duration / 60) * 0.45, 2),
            "unique_agents": len(set(s.agent_id for s in today_sessions))
        }
    }

@app.get("/api/stats/system/overview")
async def get_system_overview(
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get overall system statistics and overview"""
    # Get all agents
    result = await db.execute(select(AgentStats))
    all_agents = result.scalars().all()
    total_agents = len(all_agents)

    # Calculate totals
    total_completed = sum(a.total_tasks_completed for a in all_agents)
    total_skipped = sum(a.total_tasks_skipped for a in all_agents)
    total_duration = sum(a.total_duration_seconds for a in all_agents)
    total_earnings = sum(a.total_earnings for a in all_agents)

    # Get active agents (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    result = await db.execute(
        select(AgentStats).filter(AgentStats.last_active >= yesterday)
    )
    active_agents_24h = len(result.scalars().all())

    # Get current task counts from fast stats cache
    try:
        if stats_cache["last_updated"] is None:
            # Trigger sync if no data available
            asyncio.create_task(sync_assignment_queue())
            total_unlabeled = len(assignment_queue["tasks"])
            locked_tasks = 0
            available_tasks = total_unlabeled
        else:
            total_unlabeled = stats_cache["total_unlabeled"]
            locked_tasks = stats_cache["total_locked"]
            available_tasks = stats_cache["available"]
    except Exception as e:
        logger.warning(f"Error getting task counts: {e}")
        total_unlabeled = 0
        locked_tasks = 0
        available_tasks = 0

    # Recent activity (last 7 days)
    week_ago = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(TranscriptionSession).filter(
            TranscriptionSession.assigned_at >= week_ago
        )
    )
    recent_sessions = result.scalars().all()

    return {
        "system_totals": {
            "total_agents": total_agents,
            "total_tasks_completed": total_completed,
            "total_tasks_skipped": total_skipped,
            "total_duration_seconds": total_duration,
            "total_earnings": round(total_earnings, 2)
        },
        "current_activity": {
            "active_agents_24h": active_agents_24h,
            "total_unlabeled_tasks": total_unlabeled,
            "locked_tasks": locked_tasks,
            "available_tasks": available_tasks
        },
        "recent_activity_7d": {
            "total_sessions": len(recent_sessions),
            "completed_sessions": len([s for s in recent_sessions if s.status == 'completed']),
            "skipped_sessions": len([s for s in recent_sessions if s.status == 'skipped'])
        }
    }

@app.get("/api/stats/daily")
async def get_daily_stats(
    days: int = 7,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get daily statistics for the past N days"""
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(TranscriptionSession).filter(
            TranscriptionSession.assigned_at >= cutoff_date
        )
    )
    sessions = result.scalars().all()

    # Group by day
    daily_stats = {}
    for session in sessions:
        day_key = session.assigned_at.date().isoformat()
        if day_key not in daily_stats:
            daily_stats[day_key] = {
                "completed": 0,
                "skipped": 0,
                "duration_seconds": 0,
                "earnings": 0.0,
                "unique_agents": set()
            }

        daily_stats[day_key]["unique_agents"].add(session.agent_id)
        if session.status == 'completed':
            daily_stats[day_key]["completed"] += 1
            duration = session.duration_seconds or 0
            daily_stats[day_key]["duration_seconds"] += duration
            daily_stats[day_key]["earnings"] += duration / 60 * 0.45
        elif session.status == 'skipped':
            daily_stats[day_key]["skipped"] += 1

    # Convert sets to counts and format
    formatted_stats = []
    for day, stats in sorted(daily_stats.items()):
        formatted_stats.append({
            "date": day,
            "tasks_completed": stats["completed"],
            "tasks_skipped": stats["skipped"],
            "total_tasks": stats["completed"] + stats["skipped"],
            "duration_seconds": stats["duration_seconds"],
            "earnings": round(stats["earnings"], 2),
            "unique_agents": len(stats["unique_agents"])
        })

    return {
        "daily_stats": formatted_stats,
        "period_days": days
    }

@app.get("/api/stats/agents/active")
async def get_active_agents_stats(
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Get statistics about currently active agents"""
    # Get currently active sessions from Redis
    current_sessions = {}
    async for key in async_redis_client.scan_iter(match="agent:active:*"):
        agent_id = int(key.split(":")[-1])
        task_data = await async_redis_client.get(key)
        if task_data:
            try:
                task_info = json.loads(task_data)
                current_sessions[agent_id] = task_info["task_id"]
            except:
                pass

    # Get active agents from the database (last 24 hours)
    yesterday = datetime.utcnow() - timedelta(days=1)
    result = await db.execute(
        select(AgentStats).filter(
            AgentStats.last_active >= yesterday
        ).order_by(AgentStats.last_active.desc())
    )
    active_agents = result.scalars().all()

    # Get today's sessions
    today = datetime.utcnow().date()
    result = await db.execute(
        select(TranscriptionSession).filter(
            func.date(TranscriptionSession.assigned_at) == today
        )
    )
    today_sessions = result.scalars().all()

    # Calculate agent activity
    agent_activity = []
    for agent in active_agents:
        # Count today's activity
        agent_today_sessions = [s for s in today_sessions if s.agent_id == agent.agent_id]
        today_completed = len([s for s in agent_today_sessions if s.status == 'completed'])
        today_skipped = len([s for s in agent_today_sessions if s.status == 'skipped'])

        agent_activity.append({
            "agent_id": agent.agent_id,
            "currently_active": agent.agent_id in current_sessions,
            "current_task_id": current_sessions.get(agent.agent_id),
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
            "today_completed": today_completed,
            "today_skipped": today_skipped,
            "total_completed": agent.total_tasks_completed,
            "total_earnings": round(agent.total_earnings, 2)
        })

    return {
        "currently_active_count": len(current_sessions),
        "active_24h_count": len(active_agents),
        "agents": agent_activity
    }

@app.get("/api/reports/agents/summary/csv")
async def download_agent_summary_csv(
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Download agent summary report as CSV file"""
    # Generate CSV content in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Agent_ID', 'Tasks_Completed', 'Tasks_Skipped', 'Total_Duration_Seconds', 'Total_Duration_Minutes',
        'Total_Earnings', 'Completion_Rate_%', 'Avg_Duration_Seconds', 'Last_Active'
    ])

    # Get all agents with stats
    result = await db.execute(
        select(AgentStats).order_by(AgentStats.total_tasks_completed.desc())
    )
    agents = result.scalars().all()

    for agent in agents:
        total_tasks = agent.total_tasks_completed + agent.total_tasks_skipped
        completion_rate = (agent.total_tasks_completed / total_tasks * 100) if total_tasks > 0 else 0
        avg_duration = agent.total_duration_seconds / agent.total_tasks_completed if agent.total_tasks_completed > 0 else 0

        writer.writerow([
            agent.agent_id,
            agent.total_tasks_completed,
            agent.total_tasks_skipped,
            round(agent.total_duration_seconds, 1),
            round(agent.total_duration_seconds / 60, 2),
            f'${agent.total_earnings:.2f}',
            round(completion_rate, 2),
            round(avg_duration, 1),
            agent.last_active.isoformat() if agent.last_active else 'Never'
        ])

    # Prepare response
    output.seek(0)
    filename = f"agent_summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    # Create a proper async generator for StreamingResponse
    def generate_csv():
        yield output.getvalue().encode('utf-8')

    return StreamingResponse(
        generate_csv(),
        media_type='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/reports/sessions/detailed/csv")
async def download_session_details_csv(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Download detailed session report as CSV file with optional date filtering"""
    # Parse date parameters
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = datetime.fromisoformat(start_date)
    if end_date:
        end_dt = datetime.fromisoformat(end_date)

    # Generate CSV content in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Session_ID', 'Agent_ID', 'Task_ID', 'Status', 'Duration_Seconds',
        'Transcription_Length', 'Assigned_At', 'Completed_At', 'Skip_Reason'
    ])

    # Build query for sessions
    query = select(TranscriptionSession).order_by(TranscriptionSession.assigned_at.desc())
    if start_dt:
        query = query.filter(TranscriptionSession.assigned_at >= start_dt)
    if end_dt:
        query = query.filter(TranscriptionSession.assigned_at <= end_dt)

    result = await db.execute(query)
    sessions = result.scalars().all()

    for session in sessions:
        writer.writerow([
            session.id,
            session.agent_id,
            session.task_id,
            session.status,
            session.duration_seconds or 0,
            session.transcription_length or 0,
            session.assigned_at.isoformat() if session.assigned_at else '',
            session.completed_at.isoformat() if session.completed_at else '',
            session.skip_reason or ''
        ])

    # Prepare response
    output.seek(0)
    date_suffix = f"_{start_date}_to_{end_date}" if start_date and end_date else ""
    filename = f"session_details{date_suffix}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    # Create a proper async generator for StreamingResponse
    def generate_csv():
        yield output.getvalue().encode('utf-8')

    return StreamingResponse(
        generate_csv(),
        media_type='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/reports/complete/csv")
async def download_complete_report_csv(
    authorized: bool = Security(verify_tz_system),
    db: AsyncSession = Depends(get_async_db)
):
    """Download complete agent performance report as CSV file"""
    # Generate CSV content in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write summary header
    writer.writerow(['AGENT PERFORMANCE SUMMARY'])
    writer.writerow([])

    # Calculate overall stats
    result = await db.execute(select(AgentStats))
    agents = result.scalars().all()

    total_agents = len(agents)
    total_completed = sum(a.total_tasks_completed for a in agents)
    total_skipped = sum(a.total_tasks_skipped for a in agents)
    total_duration = sum(a.total_duration_seconds for a in agents)
    total_earnings = sum(a.total_earnings for a in agents)

    writer.writerow(['Total_Agents', total_agents])
    writer.writerow(['Total_Completed_Tasks', total_completed])
    writer.writerow(['Total_Skipped_Tasks', total_skipped])
    writer.writerow(['Total_Duration_Seconds', round(total_duration, 1)])
    writer.writerow(['Total_Duration_Minutes', round(total_duration / 60, 2)])
    writer.writerow(['Total_Earnings', f'${total_earnings:.2f}'])
    writer.writerow([])

    # Write agent details header
    writer.writerow(['AGENT DETAILS'])
    writer.writerow([
        'Agent_ID', 'Tasks_Completed', 'Tasks_Skipped', 'Total_Duration_Minutes',
        'Total_Earnings', 'Completion_Rate_%', 'Avg_Duration_Seconds', 'Last_Active'
    ])

    # Write agent details
    for agent in sorted(agents, key=lambda x: x.total_tasks_completed, reverse=True):
        total_tasks = agent.total_tasks_completed + agent.total_tasks_skipped
        completion_rate = (agent.total_tasks_completed / total_tasks * 100) if total_tasks > 0 else 0
        avg_duration = agent.total_duration_seconds / agent.total_tasks_completed if agent.total_tasks_completed > 0 else 0

        writer.writerow([
            agent.agent_id,
            agent.total_tasks_completed,
            agent.total_tasks_skipped,
            round(agent.total_duration_seconds / 60, 2),
            f'${agent.total_earnings:.2f}',
            round(completion_rate, 2),
            round(avg_duration, 1),
            agent.last_active.isoformat() if agent.last_active else 'Never'
        ])

    # Prepare response
    output.seek(0)
    filename = f"complete_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"

    # Create a proper async generator for StreamingResponse
    def generate_csv():
        yield output.getvalue().encode('utf-8')

    return StreamingResponse(
        generate_csv(),
        media_type='text/csv',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/dashboard")
async def serve_dashboard():
    """Serve the dashboard HTML page"""
    dashboard_path = os.path.join(os.path.dirname(__file__), "web", "dashboard.html")

    if not os.path.exists(dashboard_path):
        raise HTTPException(status_code=404, detail="Dashboard not found")

    with open(dashboard_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    html_content = html_content.replace(
        "const API_KEY = 'tqvdCM+/Bkm1rRZOGuMHByXYEtNqXCVy1kOGrh3umVQ=';",
        f"const API_KEY = '{TZ_SYSTEM_API_KEY}';"
    )

    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    import signal
    import sys

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Starting Label Studio ASR Middleware service...")

    try:
        logger.info("✅ Configuration validated for project " + str(PROJECT_ID))
    except Exception as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        sys.exit(1)

    logger.info(f"🚀 Server will be available at http://0.0.0.0:8010")

    try:
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8010,
            log_level="info",
            access_log=True
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)
