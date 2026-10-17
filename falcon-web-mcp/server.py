from fastapi import FastAPI
from pydantic import BaseModel
from tools.health import health
from tools.search import web_search
from tools.fetch import fetch_url

app=FastAPI(title="Falcon Web MCP",version="1.0.0")

class SearchRequest(BaseModel):
    query:str
    limit:int=5

class FetchRequest(BaseModel):
    url:str

@app.get("/")
def root():
    return {"service":"Falcon Web MCP","version":"1.0.0","status":"running"}

@app.get("/health")
def health_check():
    return health()

@app.post("/search")
def search(req: SearchRequest):

    results = web_search(
        req.query,
        req.limit
    )

    return {
        "success": True,
        "count": len(results),
        "results": results
    }

@app.post("/fetch")
def fetch(req:FetchRequest):
    return fetch_url(req.url)
