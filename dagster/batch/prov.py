"""
Provision EC2, wait for SSH, upload code, install deps, run backfill.

Usage:
    uv run python prov.py --year 2025 --months 1 2 3 4 5 6 7 8 9 10 11 12
    uv run python prov.py --year 2026 --months 3
"""

import argparse
import subprocess
import sys
import time

from infra.ec2.backfill.instance import create as launch_backfill, terminate

FILES_TO_UPLOAD = ["main.py", "pyproject.toml", ".python-version", ".env"]
SSH_USER = "ubuntu"
SSH_OPTS = ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=5"]


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def ssh(host, cmd):
    full = ["ssh", *SSH_OPTS, f"{SSH_USER}@{host}", cmd]
    log(f"$ {cmd}")
    result = subprocess.run(full, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0 and result.stderr.strip():
        print(result.stderr.strip())
    return result.returncode


def scp(host, local, remote):
    full = ["scp", *SSH_OPTS, local, f"{SSH_USER}@{host}:{remote}"]
    log(f"scp {local} → {remote}")
    return subprocess.run(full, capture_output=True, text=True).returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--months", type=int, nargs="+", default=list(range(1, 13)))
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    months_str = " ".join(str(m) for m in args.months)

    # --- launch ---
    t0 = time.monotonic()
    instance_id, host = launch_backfill()
    log(f"total provision time: {time.monotonic() - t0:.0f}s")

    # --- wait for SSH ---
    log("waiting for SSH to become available...")
    ssh_start = time.monotonic()
    for _ in range(30):
        if ssh(host, "echo ready") == 0:
            log(f"SSH ready ({time.monotonic() - ssh_start:.0f}s)")
            break
        time.sleep(5)
    else:
        log("SSH never came up after 150s, exiting")
        sys.exit(1)

    # --- upload files ---
    log(f"uploading {len(FILES_TO_UPLOAD)} files...")
    ssh(host, "mkdir -p ~/backfill")
    for f in FILES_TO_UPLOAD:
        scp(host, f, "~/backfill/")

    # --- install uv + deps ---
    log("installing uv...")
    ssh(host, "curl -LsSf https://astral.sh/uv/install.sh | sh")
    log("running uv sync...")
    ssh(host, "cd ~/backfill && ~/.local/bin/uv sync")
    log(f"setup complete ({time.monotonic() - t0:.0f}s total)")

    # --- run backfill (stream output live) ---
    log(f"running backfill: year={args.year} months={months_str} workers={args.workers}")
    cmd = f"cd ~/backfill && ~/.local/bin/uv run main.py --year {args.year} --months {months_str} --mode concurrent --workers {args.workers}"
    full = ["ssh", *SSH_OPTS, f"{SSH_USER}@{host}", cmd]
    proc = subprocess.run(full)
    rc = proc.returncode

    print()
    if rc == 0:
        log(f"backfill succeeded in {time.monotonic() - t0:.0f}s total, terminating {instance_id}...")
        terminate(instance_id)
        log("done!")
    else:
        log(f"backfill failed (exit {rc}), instance left running for debugging")
        print(f"  ssh {SSH_USER}@{host}")
        print(f"  aws ec2 terminate-instances --instance-ids {instance_id}")


if __name__ == "__main__":
    main()
