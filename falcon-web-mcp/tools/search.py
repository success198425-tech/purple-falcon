import requests

try:
    from duckduckgo_search import DDGS
except Exception:
    DDGS = None


def search_duckduckgo(query, limit):

    if DDGS is None:
        return []

    try:

        with DDGS() as ddgs:

            results = list(
                ddgs.text(
                    query,
                    max_results=limit
                )
            )

        return [
            {
                "source": "duckduckgo",
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")
            }
            for r in results
        ]

    except Exception as e:

        print("DuckDuckGo Error:", str(e))
        return []


def search_wikipedia(query, limit):

    try:

        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json"
            },
            timeout=15
        )

        data = r.json()

        results = []

        for item in data.get("query", {}).get("search", [])[:limit]:

            title = item.get("title", "")

            results.append({
                "source": "wikipedia",
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "snippet": item.get("snippet", "")
            })

        return results

    except Exception as e:

        print("Wikipedia Error:", str(e))
        return []


def search_google_news(query, limit):

    try:

        import xml.etree.ElementTree as ET

        url = f"https://news.google.com/rss/search?q={query}"

        xml_data = requests.get(
            url,
            timeout=15
        ).text

        root = ET.fromstring(xml_data)

        results = []

        for item in root.findall(".//item")[:limit]:

            results.append({
                "source": "google_news",
                "title": item.findtext("title", ""),
                "url": item.findtext("link", ""),
                "snippet": item.findtext("description", "")
            })

        return results

    except Exception as e:

        print("Google News Error:", str(e))
        return []


def web_search(query: str, limit: int = 5):

    print(f"Searching: {query}")

    #
    # Provider 1
    #
    results = search_duckduckgo(query, limit)

    if results:
        print("Provider: DuckDuckGo")
        return results

    #
    # Provider 2
    #
    results = search_wikipedia(query, limit)

    if results:
        print("Provider: Wikipedia")
        return results

    #
    # Provider 3
    #
    results = search_google_news(query, limit)

    if results:
        print("Provider: Google News")
        return results

    #
    # Fallback Result
    #
    return [
        {
            "source": "fallback",
            "title": "No results found",
            "url": "",
            "snippet": f'No search provider returned results for "{query}"'
        }
    ]
