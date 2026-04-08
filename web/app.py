"""FastAPI web application for bikini preview."""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .routes import router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
GENERATED_DIR = os.path.join(BASE_DIR, "generated")

app = FastAPI(title="3D Bikini Generator", version="0.1.0")

# API routes
app.include_router(router, prefix="/api")

# Serve generated files (OBJ, MTL, textures)
os.makedirs(GENERATED_DIR, exist_ok=True)
app.mount("/generated", StaticFiles(directory=GENERATED_DIR), name="generated")

# Serve static frontend
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


def main():
    uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
