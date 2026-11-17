"""Sends "slot closes soon" reminders. Run from cron every 10 minutes (see README in chat).
Safe to run as often as you like: each reminder is sent at most once per player per slot."""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))   # database.db is a relative path
import app

if __name__ == "__main__":
    n = app.send_closing_reminders()
    print(f"[push_cron] sent {n} notification(s)")