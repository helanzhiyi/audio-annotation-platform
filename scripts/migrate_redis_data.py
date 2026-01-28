#!/usr/bin/env python3
"""
Migration script to transfer existing Redis audit data to PostgreSQL
Run this once to migrate historical data from Redis to the new PostgreSQL schema
"""

import redis
import json
from datetime import datetime
from sqlalchemy.orm import Session
from models import TranscriptionSession, AgentStats, SessionLocal, test_connection
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config.env')

def migrate_redis_to_postgresql():
    """Migrate existing Redis audit data to PostgreSQL"""

    # Test database connection first
    if not test_connection():
        print("❌ PostgreSQL connection failed - aborting migration")
        return False

    # Connect to Redis
    redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)

    try:
        redis_client.ping()
        print("✅ Redis connection successful")
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

    db = SessionLocal()

    try:
        print("🔄 Starting migration from Redis to PostgreSQL...")

        # Migrate assignments
        print("📋 Migrating assignments...")
        assignments = redis_client.lrange("audit:assignments", 0, -1)
        print(f"Found {len(assignments)} assignment records")

        assignment_count = 0
        for assignment_data in assignments:
            try:
                data = json.loads(assignment_data)
                agent_id = int(data['agent_id'])  # Convert to int
                task_id = data['task_id']
                assigned_at = datetime.fromisoformat(data['assigned_at'])

                # Check if this session already exists
                existing = db.query(TranscriptionSession).filter(
                    TranscriptionSession.agent_id == agent_id,
                    TranscriptionSession.task_id == task_id,
                    TranscriptionSession.assigned_at == assigned_at
                ).first()

                if not existing:
                    session = TranscriptionSession(
                        agent_id=agent_id,
                        task_id=task_id,
                        assigned_at=assigned_at,
                        status='assigned'
                    )
                    db.add(session)
                    assignment_count += 1

            except Exception as e:
                print(f"⚠️  Error processing assignment: {e}")
                continue

        # Migrate completions
        print("✅ Migrating completions...")
        completions = redis_client.lrange("audit:completions", 0, -1)
        print(f"Found {len(completions)} completion records")

        completion_count = 0
        for completion_data in completions:
            try:
                data = json.loads(completion_data)
                agent_id = int(data['agent_id'])  # Convert to int
                task_id = data['task_id']
                completed_at = datetime.fromisoformat(data['completed_at'])
                transcription_length = data.get('transcription_length', 0)

                # Find the corresponding assignment session
                session = db.query(TranscriptionSession).filter(
                    TranscriptionSession.agent_id == agent_id,
                    TranscriptionSession.task_id == task_id
                ).first()

                if session:
                    session.completed_at = completed_at
                    session.status = 'completed'
                    session.transcription_length = transcription_length
                else:
                    # Create a new session if assignment wasn't found
                    session = TranscriptionSession(
                        agent_id=agent_id,
                        task_id=task_id,
                        assigned_at=completed_at,  # Use completion time as fallback
                        completed_at=completed_at,
                        status='completed',
                        transcription_length=transcription_length
                    )
                    db.add(session)

                completion_count += 1

            except Exception as e:
                print(f"⚠️  Error processing completion: {e}")
                continue

        # Migrate skips
        print("⏭️  Migrating skips...")
        skips = redis_client.lrange("audit:skips", 0, -1)
        print(f"Found {len(skips)} skip records")

        skip_count = 0
        for skip_data in skips:
            try:
                data = json.loads(skip_data)
                agent_id = int(data['agent_id'])  # Convert to int
                task_id = data['task_id']
                skipped_at = datetime.fromisoformat(data['skipped_at'])
                reason = data.get('reason', 'No reason provided')

                # Find the corresponding assignment session
                session = db.query(TranscriptionSession).filter(
                    TranscriptionSession.agent_id == agent_id,
                    TranscriptionSession.task_id == task_id
                ).first()

                if session:
                    session.status = 'skipped'
                    session.skip_reason = reason
                else:
                    # Create a new session if assignment wasn't found
                    session = TranscriptionSession(
                        agent_id=agent_id,
                        task_id=task_id,
                        assigned_at=skipped_at,  # Use skip time as fallback
                        status='skipped',
                        skip_reason=reason
                    )
                    db.add(session)

                skip_count += 1

            except Exception as e:
                print(f"⚠️  Error processing skip: {e}")
                continue

        # Commit all session data
        db.commit()
        print(f"✅ Migrated {assignment_count} assignments, {completion_count} completions, {skip_count} skips")

        # Calculate and update agent stats
        print("📊 Calculating agent statistics...")
        agent_ids = db.query(TranscriptionSession.agent_id).distinct().all()
        agent_count = 0

        for (agent_id,) in agent_ids:
            # Get or create agent stats
            agent_stats = db.query(AgentStats).filter(AgentStats.agent_id == agent_id).first()
            if not agent_stats:
                agent_stats = AgentStats(agent_id=agent_id)
                db.add(agent_stats)

            # Calculate totals from sessions
            completed_sessions = db.query(TranscriptionSession).filter(
                TranscriptionSession.agent_id == agent_id,
                TranscriptionSession.status == 'completed'
            ).all()

            skipped_sessions = db.query(TranscriptionSession).filter(
                TranscriptionSession.agent_id == agent_id,
                TranscriptionSession.status == 'skipped'
            ).all()

            total_duration = sum(s.duration_seconds or 0 for s in completed_sessions)

            # Update stats
            agent_stats.total_tasks_completed = len(completed_sessions)
            agent_stats.total_tasks_skipped = len(skipped_sessions)
            agent_stats.total_duration_seconds = total_duration

            # Calculate earnings (example: $0.10 per minute)
            earnings_per_minute = 0.10
            agent_stats.total_earnings = (total_duration / 60) * earnings_per_minute

            # Set last active from most recent session
            if completed_sessions or skipped_sessions:
                all_sessions = completed_sessions + skipped_sessions
                most_recent = max(all_sessions, key=lambda s: s.completed_at or s.assigned_at)
                agent_stats.last_active = most_recent.completed_at or most_recent.assigned_at

            agent_count += 1

        db.commit()
        print(f"✅ Updated statistics for {agent_count} agents")

        print("🎉 Migration completed successfully!")
        print("\n📋 Summary:")
        print(f"   - {assignment_count} assignments migrated")
        print(f"   - {completion_count} completions migrated")
        print(f"   - {skip_count} skips migrated")
        print(f"   - {agent_count} agent statistics calculated")
        print("\n💡 The Redis audit logs are still preserved for reference")

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        return False

    finally:
        db.close()

if __name__ == "__main__":
    print("🚀 Redis to PostgreSQL Migration Tool")
    print("=====================================")

    migrate_redis_to_postgresql()