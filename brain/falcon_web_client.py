import requests

WEB_MCP_URL = "https://falcon-web-mcp.onrender.com"


def search(query, limit=5):
    return requests.post(
        f"{WEB_MCP_URL}/search",
        json={
            "query": query,
            "limit": limit
        },
        timeout=30
    ).json()


def fetch(url):
    return requests.post(
        f"{WEB_MCP_URL}/fetch",
        json={
            "url": url
        },
        timeout=30
    ).json()
