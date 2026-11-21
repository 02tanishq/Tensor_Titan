"""
Direct Uvicorn Runner
Runs FastAPI with native WatchFiles auto-reload.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.server:app", host="0.0.0.0", port=8000, reload=True)
