from duckduckgo_search import DDGS
from config import WEB_MAX_RESULTS


def web_search(
    query: str,
    limit: int = WEB_MAX_RESULTS
):
    results = []

    try:
        with DDGS() as ddgs:

            for row in ddgs.text(
                query,
                max_results=limit
            ):

                results.append(
                    {
                        "title": row.get("title", ""),
                        "url": row.get("href", ""),
                        "snippet": row.get("body", "")
                    }
                )

    except Exception as e:

        return {
            "success": False,
            "error": str(e),
            "results": []
        }

    return {
        "success": True,
        "query": query,
        "count": len(results),
        "results": results
    }
