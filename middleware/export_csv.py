#!/usr/bin/env python3
"""
Export agent data to CSV files for spreadsheet analysis
"""

import csv
from models import SessionLocal, TranscriptionSession, AgentStats
from datetime import datetime

def export_to_csv():
    """Export agent data to CSV files"""

    db = SessionLocal()

    try:
        # Export agent summary
        print("📄 Exporting agent summary to agent_summary.csv...")
        with open('agent_summary.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Agent_ID', 'Tasks_Completed', 'Tasks_Skipped', 'Total_Duration_Minutes', 'Total_Earnings', 'Last_Active'])

            agents = db.query(AgentStats).all()
            for agent in agents:
                writer.writerow([
                    agent.agent_id,
                    agent.total_tasks_completed,
                    agent.total_tasks_skipped,
                    round(agent.total_duration_seconds / 60, 2),
                    round(agent.total_earnings, 2),
                    agent.last_active.strftime('%Y-%m-%d %H:%M:%S') if agent.last_active else ''
                ])

        # Export detailed sessions
        print("📄 Exporting detailed sessions to session_details.csv...")
        with open('session_details.csv', 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Session_ID', 'Agent_ID', 'Task_ID', 'Status', 'Duration_Seconds', 'Transcription_Length', 'Assigned_At', 'Completed_At', 'Skip_Reason'])

            sessions = db.query(TranscriptionSession).order_by(TranscriptionSession.assigned_at.desc()).all()
            for session in sessions:
                writer.writerow([
                    session.id,
                    session.agent_id,
                    session.task_id,
                    session.status,
                    session.duration_seconds or '',
                    session.transcription_length or '',
                    session.assigned_at.strftime('%Y-%m-%d %H:%M:%S') if session.assigned_at else '',
                    session.completed_at.strftime('%Y-%m-%d %H:%M:%S') if session.completed_at else '',
                    session.skip_reason or ''
                ])

        print("✅ CSV files exported:")
        print("   - agent_summary.csv (agent overview)")
        print("   - session_details.csv (detailed session history)")

    finally:
        db.close()

if __name__ == "__main__":
    export_to_csv()