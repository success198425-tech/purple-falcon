import requests

def web_search(query: str, limit: int = 5):

    try:
        url = "https://api.duckduckgo.com/"

        r = requests.get(
            url,
            params={
                "q": query,
                "format": "json"
            },
            timeout=15
        )

        data = r.json()

        results = []

        for item in data.get("RelatedTopics", [])[:limit]:

            if isinstance(item, dict):

                results.append({
                    "title": item.get("Text", ""),
                    "url": item.get("FirstURL", ""),
                    "snippet": item.get("Text", "")
                })

        return results

    except Exception as e:

        return [{
            "error": str(e)
        }]
