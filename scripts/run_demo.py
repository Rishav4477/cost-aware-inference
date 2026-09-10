"""Run all mock regions and gateway locally. Ctrl-C shuts down every child."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.chdir(root)
env = {
    **os.environ,
    "DEMO_API_KEY": os.getenv("DEMO_API_KEY", "local-demo-key-change-me"),
    "CONFIG_PATH": "config/demo.yaml",
}
children = []


def stop(*_):
    for child in children:
        child.terminate()
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
try:
    for port in (8101, 8102, 8103):
        children.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "inference.mock_provider:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                env=env,
            )
        )
    children.append(
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "inference.app:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            env=env,
        )
    )
    print("Demo: http://127.0.0.1:8000/docs | Uses local mock providers only.", flush=True)
    while all(c.poll() is None for c in children):
        time.sleep(0.5)
except KeyboardInterrupt:
    pass
finally:
    stop()
