from __future__ import annotations
import os, subprocess, sys, threading
import uvicorn
from monitor import run_forever
from persistence import init_db
from tv_store import init_tv_tables
from intelligence_store import init_intelligence_tables

def run_api():
    uvicorn.run("webhook_receiver:app", host="0.0.0.0", port=int(os.getenv("WEBHOOK_PORT", "8000")), log_level="info")

def main():
    init_db(); init_tv_tables()
    threading.Thread(target=run_forever, daemon=True, name="trade-monitor").start()
    threading.Thread(target=run_api, daemon=True, name="webhook-api").start()
    port = os.getenv("PORT", "8501")
    return subprocess.call([sys.executable, "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", f"--server.port={port}", "--server.headless=true"])
if __name__ == "__main__":
    raise SystemExit(main())
