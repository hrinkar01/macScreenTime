import os
import sqlite3
import subprocess
import re
from datetime import datetime, timedelta

def get_last_unplug_time():
    """Allows manual entry of the unplugged time string."""
    print("Enter the exact time you unplugged your charger.")
    print("Formats allowed: '10:30 AM', '4:15 PM', or '14:15' (24-hour style)")
    user_input = input("Unplugged time: ").strip()
    
    # Common potential time input layouts
    formats = ["%I:%M %p", "%I:%M%p", "%H:%M"]
    
    parsed_time = None
    for fmt in formats:
        try:
            parsed_time = datetime.strptime(user_input, fmt)
            break
        except ValueError:
            continue
            
    if not parsed_time:
        print("Error: Invalid time format. Defaulting to 12 hours ago.")
        return datetime.now() - timedelta(hours=12)
        
    # Combine the parsed hour/minute entry with today's calendar date
    now = datetime.now()
    unplugged_time = now.replace(hour=parsed_time.hour, minute=parsed_time.minute, second=0, microsecond=0)
    
    # If the calculated timestamp falls into the future, it happened yesterday evening
    if unplugged_time > now:
        unplugged_time -= timedelta(days=1)
        
    return unplugged_time

def calculate_exact_screen_time():
    unplugged_at = get_last_unplug_time()
    if not unplugged_at:
        return

    now = datetime.now()
    print(f"\nTracking battery discharge since: {unplugged_at.strftime('%Y-%m-%d %I:%M %p')}")
    
    # 1. Calculate Full Elapsed Time (Wall clock time including Sleep and Standby)
    elapsed_delta = now - unplugged_at
    elapsed_hours, remainder = divmod(elapsed_delta.total_seconds(), 3600)
    elapsed_minutes, _ = divmod(remainder, 60)
    
    # Target database location
    db_path = os.path.expanduser("~/Library/Application Support/Knowledge/knowledgeC.db")
    
    if not os.path.exists(db_path):
        print("\nError: Core tracking database not found or blocked.")
        print("Fix: Go to System Settings > Privacy & Security > Full Disk Access, and ensure Terminal is turned ON.")
        return

    # Convert timestamp to Apple Core Data Epoch time scale offset
    apple_epoch_offset = 978307200
    start_epoch = unplugged_at.timestamp() - apple_epoch_offset

    # Structured SQL query targeting active foreground apps
    query = """
    SELECT ZSTARTDATE, ZENDDATE 
    FROM ZOBJECT 
    WHERE ZSTREAMNAME = '/app/usage' 
    AND ZSTARTDATE > ?
    """
    
    try:
        # Connect directly to the database via URI in read-only immutable mode 
        db_uri = f"file:{db_path}?mode=ro&immutable=1"
        conn = sqlite3.connect(db_uri, uri=True)
        cursor = conn.cursor()
        cursor.execute(query, (start_epoch,))
        
        intervals = cursor.fetchall()
        conn.close()
        
        print("\n=== TOTAL BATTERY BACKUP STATS ===")
        print(f"Total Time Since Unplugged : {int(elapsed_hours)}h {int(elapsed_minutes)}m (Includes Sleep & Standby)")
        
        if not intervals:
            print("Actual Active Screen Time   : 0h 0m")
            print("\nReason: No active system events found since the specified timestamp.")
            return

        # Sort and merge overlapping active time blocks
        intervals.sort(key=lambda x: x[0])
        merged_total_seconds = 0
        current_start, current_end = intervals[0]

        for start, end in intervals[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                merged_total_seconds += (current_end - current_start)
                current_start, current_end = start, end
        merged_total_seconds += (current_end - current_start)

        # Format active duration
        active_hours = int(merged_total_seconds // 3600)
        active_minutes = int((merged_total_seconds % 3600) // 60)
        
        print(f"Actual Active Screen Time   : {active_hours}h {active_minutes}m (Screen On)")
        
        # Calculate background standby time
        standby_seconds = max(0, elapsed_delta.total_seconds() - merged_total_seconds)
        standby_hours = int(standby_seconds // 3600)
        standby_minutes = int((standby_seconds % 3600) // 60)
        print(f"Lid Closed / Standby Time   : {standby_hours}h {standby_minutes}m")
        
    except sqlite3.OperationalError:
        print("\n[Permissions Alert]")
        print("To read screen data, your Python environment needs Full Disk Access permission.")
        print("1. Open System Settings > Privacy & Security > Full Disk Access.")
        print("2. Click the '+' button and add your Terminal app.")
        print("3. Restart Terminal and run the script again.")

if __name__ == "__main__":
    calculate_exact_screen_time()

