#!/usr/bin/env python3

from models import SessionLocal, AgentStats, TranscriptionSession
from datetime import datetime

db = SessionLocal()

try:
    # Recalculate agent stats with the new duration data
    agent_ids = db.query(TranscriptionSession.agent_id).distinct().all()

    print("🎯 Agent Earnings Report:")
    print("=" * 50)

    for (agent_id,) in agent_ids:
        agent_stats = db.query(AgentStats).filter(AgentStats.agent_id == agent_id).first()
        if not agent_stats:
            continue

        # Get completed sessions
        completed_sessions = db.query(TranscriptionSession).filter(
            TranscriptionSession.agent_id == agent_id,
            TranscriptionSession.status == 'completed',
            TranscriptionSession.duration_seconds != None
        ).all()

        # Calculate totals
        total_duration = sum(s.duration_seconds for s in completed_sessions)
        total_minutes = total_duration / 60

        # Update stats
        agent_stats.total_duration_seconds = total_duration

        # Calculate earnings (example: $0.10 per minute)
        earnings_per_minute = 0.10
        agent_stats.total_earnings = total_minutes * earnings_per_minute

        print(f"Agent {agent_id}: {len(completed_sessions)} tasks, {total_duration:.1f}s ({total_minutes:.1f} min), ${agent_stats.total_earnings:.2f}")

    db.commit()
    print("\n✅ Agent statistics updated with duration-based earnings")

finally:
    db.close()