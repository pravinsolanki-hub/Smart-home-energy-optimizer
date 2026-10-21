import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api.routes import router as api_router
from app.alexa_mcp.server import get_mcp_streamable_app

app = FastAPI(
    title="Smart Home Energy Optimizer API",
    description=(
        "Residential energy management system: forecasts demand, evaluates cost-effective "
        "actions against dynamic tariffs, and provides a self-hosted Model Context Protocol (MCP) server."
    ),
    version="1.0.0"
)

# Enable CORS for dashboard and external clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register REST API Router
app.include_router(api_router, prefix="/api")

# Mount Official MCP Server over Streamable HTTP (Spec 2025-11-25)
try:
    mcp_streamable_asgi = get_mcp_streamable_app()
    app.mount("/mcp", mcp_streamable_asgi)
except Exception as e:
    print(f"[WARN] Could not mount Streamable HTTP MCP server: {e}")

# Static files directory for frontend dashboard
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def serve_dashboard():
    """Serves the interactive single-page dashboard."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {
        "service": "Smart Home Energy Optimizer API",
        "status": "online",
        "docs_url": "/docs",
        "mcp_streamable_endpoint": "/mcp"
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "smart-home-energy-optimizer",
        "mcp_spec": "2025-11-25",
        "mcp_transport": "Streamable HTTP"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
