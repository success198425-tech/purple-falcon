import os
import re
import json
import requests

WEB_MCP_URL=os.getenv("WEB_MCP_URL","https://falcon-web-mcp.onrender.com")
MEMORY_MCP_URL=os.getenv("MEMORY_MCP_URL","https://falcon-memory-mcp.onrender.com")

URL_RE=re.compile(r"https?://\S+",re.I)

def mcp_web_search(query, limit=5):

    try:

        r = requests.post(
            f"{WEB_MCP_URL}/search",
            json={
                "query": query,
                "limit": limit
            },
            timeout=30
        )

        if r.status_code == 200:
            return r.json()

        return {
            "error": f"HTTP {r.status_code}",
            "body": r.text[:1000]
        }

    except Exception as e:

        return {
            "error": str(e)
        }
def mcp_web_fetch(url):

    try:

        r = requests.post(
            f"{WEB_MCP_URL}/fetch",
            json={
                "url": url
            },
            timeout=30
        )

        if r.status_code == 200:
            return r.json()

        return {
            "error": f"HTTP {r.status_code}",
            "body": r.text[:1000]
        }

    except Exception as e:

        return {
            "error": str(e)
        }
def mcp_can_handle(message):
    m=message.lower()
    kws=["search","web","internet","website","research","google","look up","find online"]
    return bool(URL_RE.search(message)) or any(k in m for k in kws)

def mcp_process(message):
    match=URL_RE.search(message)
    if match:
        return {"type":"fetch","data":mcp_web_fetch(match.group(0))}
    return {"type":"search","data":mcp_web_search(message,5)}
