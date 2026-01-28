#!/usr/bin/env python3
"""
Generate comprehensive report of all agent transcription activity
"""

from models import SessionLocal, TranscriptionSession, AgentStats
from datetime import datetime, timedelta
import json

def generate_full_agent_report():
    """Generate complete report of all agent activity"""

    db = SessionLocal()

    try:
        print("📋 COMPLETE AGENT TRANSCRIPTION REPORT")
        print("=" * 60)

        # Get all agents with activity
        agents = db.query(AgentStats).order_by(AgentStats.total_tasks_completed.desc()).all()

        total_agents = len(agents)
        total_completed_tasks = sum(a.total_tasks_completed for a in agents)
        total_skipped_tasks = sum(a.total_tasks_skipped for a in agents)
        total_duration = sum(a.total_duration_seconds for a in agents)
        total_earnings = sum(a.total_earnings for a in agents)

        print(f"📊 SUMMARY:")
        print(f"   Total Agents: {total_agents}")
        print(f"   Tasks Completed: {total_completed_tasks}")
        print(f"   Tasks Skipped: {total_skipped_tasks}")
        print(f"   Total Duration: {total_duration/60:.1f} minutes ({total_duration/3600:.1f} hours)")
        print(f"   Total Earnings: ${total_earnings:.2f}")
        print()

        print("👥 INDIVIDUAL AGENT PERFORMANCE:")
        print("-" * 60)
        print(f"{'Agent ID':<8} {'Completed':<10} {'Skipped':<8} {'Duration':<12} {'Earnings':<10} {'Last Active'}")
        print("-" * 60)

        for agent in agents:
            last_active = agent.last_active.strftime('%Y-%m-%d') if agent.last_active else 'Never'
            duration_min = agent.total_duration_seconds / 60

            print(f"{agent.agent_id:<8} {agent.total_tasks_completed:<10} {agent.total_tasks_skipped:<8} "
                  f"{duration_min:>8.1f} min {agent.total_earnings:>8.2f} {last_active}")

        print("\n" + "=" * 60)
        print("📝 DETAILED SESSION HISTORY:")
        print("-" * 60)

        # Get all sessions with details
        sessions = db.query(TranscriptionSession).order_by(
            TranscriptionSession.assigned_at.desc()
        ).all()

        print(f"{'Agent':<6} {'Task':<6} {'Status':<10} {'Duration':<10} {'Assigned':<12} {'Completed':<12}")
        print("-" * 60)

        for session in sessions[:50]:  # Show last 50 sessions
            assigned = session.assigned_at.strftime('%m-%d %H:%M') if session.assigned_at else 'Unknown'
            completed = session.completed_at.strftime('%m-%d %H:%M') if session.completed_at else '-'
            duration = f"{session.duration_seconds:.1f}s" if session.duration_seconds else '-'

            print(f"{session.agent_id:<6} {session.task_id:<6} {session.status:<10} "
                  f"{duration:<10} {assigned:<12} {completed}")

        if len(sessions) > 50:
            print(f"\n... and {len(sessions) - 50} more sessions (showing latest 50)")

        print("\n" + "=" * 60)
        print("📈 PERFORMANCE ANALYTICS:")
        print("-" * 60)

        # Calculate completion rate by agent
        for agent in agents[:10]:  # Top 10 agents
            completed = agent.total_tasks_completed
            skipped = agent.total_tasks_skipped
            total = completed + skipped
            completion_rate = (completed / total * 100) if total > 0 else 0
            avg_duration = agent.total_duration_seconds / completed if completed > 0 else 0

            print(f"Agent {agent.agent_id}: {completion_rate:.1f}% completion rate, "
                  f"avg {avg_duration:.1f}s per task")

        # Recent activity (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        recent_sessions = db.query(TranscriptionSession).filter(
            TranscriptionSession.assigned_at >= week_ago
        ).all()

        print(f"\n🕐 RECENT ACTIVITY (Last 7 days):")
        print(f"   Sessions: {len(recent_sessions)}")
        print(f"   Active Agents: {len(set(s.agent_id for s in recent_sessions))}")

        recent_completed = [s for s in recent_sessions if s.status == 'completed']
        if recent_completed:
            recent_duration = sum(s.duration_seconds or 0 for s in recent_completed)
            print(f"   Completed: {len(recent_completed)} tasks")
            print(f"   Duration: {recent_duration/60:.1f} minutes")
            print(f"   Earnings: ${(recent_duration/60) * 0.10:.2f}")

    finally:
        db.close()

if __name__ == "__main__":
    generate_full_agent_report()