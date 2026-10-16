from fastapi import FastAPI
from tools.health import health

app = FastAPI(title="Falcon Memory MCP", version="1.0.0")

@app.get("/")
def root():
    return {"service":"Falcon Memory MCP","version":"1.0.0","status":"running"}

@app.get("/health")
def health_check():
    return health()
