from duckduckgo_search import DDGS

def web_search(query: str, limit: int = 5):

    try:

        print(f"Searching: {query}")

        with DDGS() as ddgs:

            results = list(
                ddgs.text(
                    query,
                    max_results=limit
                )
            )

        print(f"Results found: {len(results)}")

        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in results
        ]

    except Exception as e:

        print("SEARCH ERROR:", str(e))

        return [{
            "error": str(e)
        }]
