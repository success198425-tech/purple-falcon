import platform
import datetime


def web_health():

    return {
        "service": "Falcon-Web-MCP",
        "status": "healthy",
        "python": platform.python_version(),
        "timestamp":
        datetime.datetime.utcnow().isoformat()
    }
