#!/usr/bin/env python3
"""
Update all existing agent earnings to use new rate of $0.45 per minute
"""

from models import SessionLocal, AgentStats
from datetime import datetime

def update_earnings_rate():
    """Update all agent earnings to $0.45 per minute rate"""

    db = SessionLocal()

    try:
        print("🔄 Updating all agent earnings to $0.45 per minute...")

        # Get all agents
        agents = db.query(AgentStats).all()

        new_rate = 0.45  # $0.45 per minute
        old_rate = 0.10  # Previous rate

        updated_count = 0

        for agent in agents:
            if agent.total_duration_seconds > 0:
                # Recalculate earnings based on duration
                total_minutes = agent.total_duration_seconds / 60
                new_earnings = total_minutes * new_rate
                old_earnings = agent.total_earnings

                agent.total_earnings = new_earnings
                updated_count += 1

                print(f"Agent {agent.agent_id}: {total_minutes:.2f} min - "
                      f"Old: ${old_earnings:.2f} → New: ${new_earnings:.2f} "
                      f"(+${new_earnings - old_earnings:.2f})")

        db.commit()

        print(f"\n✅ Updated earnings for {updated_count} agents")
        print(f"💰 Rate changed from ${old_rate:.2f} to ${new_rate:.2f} per minute")

        # Show totals
        total_new_earnings = sum(a.total_earnings for a in agents)
        total_duration = sum(a.total_duration_seconds for a in agents)

        print(f"\n📊 SUMMARY:")
        print(f"   Total Duration: {total_duration/60:.2f} minutes")
        print(f"   Total Earnings: ${total_new_earnings:.2f}")
        print(f"   Average Rate: ${(total_new_earnings / (total_duration/60)):.2f} per minute")

    except Exception as e:
        print(f"❌ Error updating earnings: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("💰 Earnings Rate Update Tool")
    print("=" * 30)
    update_earnings_rate()