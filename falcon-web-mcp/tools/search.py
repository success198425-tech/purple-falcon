from duckduckgo_search import DDGS


def web_search(query: str, limit: int = 5):

    results = []

    try:

        ddgs = DDGS()

        for item in ddgs.text(
            query,
            max_results=limit
        ):
            results.append({
                "title": item.get("title"),
                "url": item.get("href"),
                "snippet": item.get("body")
            })

    except Exception as e:

        return [
            {
                "error": str(e)
            }
        ]

    return results
