# Docker Container Health Monitoring & Auto-Recovery Tool

A Docker container can still be running while its CPU or memory usage is high.
Developed by Ronali Jayasekera as a final-year BSc project, this Python tool
monitors one container on a standalone Docker host and decides when to restart it.

## How it decides when to act

- **Brief spike:** If CPU usage exceeds 80% or memory usage exceeds 75%, the
  monitor records a strike. If usage returns to normal on the next check,
  it clears the count and the container keeps running.
- **Sustained pressure:** If either threshold is exceeded for three consecutive
  checks, the monitor restarts the container and checks whether it is running again.
- **Stopped container:** If the monitor finds that the container has exited,
  it attempts a restart on that check, without waiting for three strikes.

This design addresses two different reliability problems. Restarting a busy
container too early can interrupt work that would have finished normally.
Waiting after a container has already stopped can prolong an outage.
The tool uses a different recovery rule for each situation.

Readings, warnings, restart attempts, and outcomes are recorded in SQLite.
The project report explains the design and how it was tested under CPU and
memory stress.

[Read the final project report (PDF)](docs/final-project-report.pdf)
