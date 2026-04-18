import docker
import time
import sqlite3
from datetime import datetime

# The constants
CONTAINER_NAME = "target-app"  
CHECK_INTERVAL = 5             
CPU_THRESHOLD = 80.0           
MEM_THRESHOLD = 75.0           
MAX_STRIKES = 3                
DB_NAME = "sre_logs.db"        

# 1. DATABASE SETUP
def init_db():
    """Creates the SQLite database and table if they don't exist."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                container_name TEXT,
                message TEXT,
                cpu_usage REAL,
                mem_usage REAL,
                status TEXT
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Critical Error: Could not initialize database. {e}")
        exit()

# Connecting to the docker engine
try:
    client = docker.from_env()
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Connection established to Docker Engine.")
except Exception as e:
    print(f"Critical Error: Could not connect to Docker. {e}")
    exit()
    
def log_event(level, message, cpu=0.0, mem=0.0, status="UNKNOWN"):
    """Logs to both the terminal and the SQLite Database"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Print to Terminal (Standard Output)
    print(f"[{timestamp}] {level}: {message}")
    
    # 2. Persist to Database (Objective iv)
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO metrics_log (timestamp, level, container_name, message, cpu_usage, mem_usage, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (timestamp, level, CONTAINER_NAME, message, cpu, mem, status)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[{timestamp}] ERROR: Database write failed - {e}")

def monitor_loop(): 
    log_event("INFO", f"SRE Monitor active for container: {CONTAINER_NAME}")
    log_event("INFO", f"Active Thresholds: CPU > {CPU_THRESHOLD}% | RAM > {MEM_THRESHOLD}% | Strikes: {MAX_STRIKES}")
    print("-" * 65)
    
    strike_count = 0  # Initialize the strike counter

    while True:
        try:
            container = client.containers.get(CONTAINER_NAME)
            status = container.status
            
            if status == "running":
                stats = container.stats(stream=False)
                
                # RAM Calculation
                mem_usage = stats['memory_stats']['usage']
                mem_limit = stats['memory_stats']['limit']
                mem_percent = (mem_usage / mem_limit) * 100.0
                
                # CPU Calculation (Delta-based SRE Formula)
                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - stats['precpu_stats']['system_cpu_usage']
                
                if system_delta > 0 and cpu_delta > 0:
                    online_cpus = stats['cpu_stats'].get('online_cpus', 1)
                    cpu_percent = (cpu_delta / system_delta) * online_cpus * 100.0
                else:
                    cpu_percent = 0.0

                # IDENTIFY HAZARDOUS STATES & THREE-STRIKE LOGIC
                is_healthy = True 
                
                if cpu_percent > CPU_THRESHOLD or mem_percent > MEM_THRESHOLD:
                    is_healthy = False
                    strike_count += 1
                    
                    reason = "CPU" if cpu_percent > CPU_THRESHOLD else "RAM"
                    val = cpu_percent if cpu_percent > CPU_THRESHOLD else mem_percent
                    
                    log_event("WARNING", f"HAZARDOUS: High {reason} detected ({val:.2f}%). Strike {strike_count}/{MAX_STRIKES}", cpu_percent, mem_percent, status)
                    
                    # Proactive Auto-Recovery if strikes reach limit
                    if strike_count >= MAX_STRIKES:
                        log_event("CRITICAL", "Maximum strikes reached! Resource exhaustion imminent.", cpu_percent, mem_percent, status)
                        log_event("ACTION", f"Initiating Proactive Auto-Recovery for {CONTAINER_NAME}...", cpu_percent, mem_percent, status)
                        
                        container.restart()
                        time.sleep(2)
                        
                        container.reload()
                        if container.status == "running":
                            log_event("SUCCESS", "Proactive recovery complete. Container is stable.", 0.0, 0.0, container.status)
                        else:
                            log_event("ERROR", "Auto-Recovery failed. Manual intervention required.", 0.0, 0.0, container.status)
                        
                        strike_count = 0 # Reset strikes after restart action

                # Normal Telemetry Output
                if is_healthy:
                    if strike_count > 0:
                        # If it was unhealthy but recovered naturally before 3 strikes
                        log_event("INFO", "Resource usage normalized. Resetting strike count.", cpu_percent, mem_percent, status)
                        strike_count = 0
                        
                    log_event("HEALTHY", f"CPU: {cpu_percent:.2f}% | RAM: {mem_percent:.2f}%", cpu_percent, mem_percent, status)
            
            else:
                # Immediate Recovery for Crash States (EXITED)
                strike_count = 0 # Reset strikes
                log_event("CRITICAL", f"FATAL: Status '{status.upper()}' detected.", 0.0, 0.0, status)
                log_event("ACTION", f"Initiating Crash Auto-Recovery for {CONTAINER_NAME}...")
                
                container.restart()
                time.sleep(2) 
                
                container.reload()
                if container.status == "running":
                    log_event("SUCCESS", "Crash recovery complete. Container is stable.", 0.0, 0.0, container.status)
                else:
                    log_event("ERROR", "Auto-Recovery failed. Manual intervention required.", 0.0, 0.0, container.status)

        except docker.errors.NotFound:
            log_event("ERROR", f"Target container '{CONTAINER_NAME}' not found.")
        except Exception as e:
            log_event("ERROR", f"Unexpected monitoring failure: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    init_db() # Run database setup before starting the loop
    monitor_loop()