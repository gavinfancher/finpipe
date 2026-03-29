"""
Starts all three services:
  ingestion  — connects to Massive API          (port 9000)
  api        — serves data to the UI            (port 8080)
  ui         — vite dev server                  (port 5173)

Run: uv run python main.py
"""

import signal
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).parent

RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"

SERVICES = [
    {
        "name": "ingestion",
        "label": f"\033[36m{BOLD}ingestion{RESET}",   # cyan
        "cmd": ["uv", "run", "uvicorn", "server.ingestion.massive:app", "--port", "9000"],
        "cwd": ROOT,
    },
    {
        "name": "api",
        "label": f"\033[33m{BOLD}      api{RESET}",   # yellow
        "cmd": ["uv", "run", "uvicorn", "server.api.app:app", "--port", "8080", "--host", "0.0.0.0"],
        "cwd": ROOT,
    },
    {
        "name": "ui",
        "label": f"\033[35m{BOLD}       ui{RESET}",   # magenta
        "cmd": ["npm", "run", "dev"],
        "cwd": ROOT / "ui",
    },
]

processes: list[subprocess.Popen] = []


def pipe_output(label: str, stream):
    for raw in stream:
        line = raw.decode(errors="replace").rstrip()
        if line:
            print(f"  {label}  {DIM}│{RESET}  {line}")
    stream.close()


def shutdown():
    for p in processes:
        if p.poll() is None:
            p.terminate()
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()


def handle_signal(*_):
    print("\nshutting down...")
    shutdown()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

for svc in SERVICES:
    p = subprocess.Popen(
        svc["cmd"],
        cwd=svc["cwd"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    processes.append(p)
    threading.Thread(target=pipe_output, args=(svc["label"], p.stdout), daemon=True).start()
    print(f"  {svc['label']}  {DIM}│{RESET}  starting...")

while True:
    for p, svc in zip(processes, SERVICES):
        if p.poll() is not None:
            print(f"  {svc['label']}  {DIM}│{RESET}  exited (code {p.returncode}), shutting down")
            shutdown()
            sys.exit(1)
    try:
        processes[0].wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
