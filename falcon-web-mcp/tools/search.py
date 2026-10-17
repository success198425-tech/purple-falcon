import re
import requests

try:
    from duckduckgo_search import DDGS
except Exception:
    DDGS = None


def clean_html(text: str) -> str:

    if not text:
        return ""

    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    return text.strip()


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
                "snippet": clean_html(
                    r.get("body", "")
                )
            }
            for r in results
        ]

    except Exception as e:

        print("DuckDuckGo Error:", str(e))
        return []


def search_wikipedia(query, limit):

    try:

        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json"
            },
            headers={
                "User-Agent": "PurpleFalconMCP/1.0"
            },
            timeout=15
        )

        data = response.json()

        results = []

        for item in data.get("query", {}).get("search", [])[:limit]:

            title = item.get("title", "")

            results.append({
                "source": "wikipedia",
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "snippet": clean_html(
                    item.get("snippet", "")
                )
            })

        return results

    except Exception as e:

        print("Wikipedia Error:", str(e))
        return []


def search_google_news(query, limit):

    try:

        import xml.etree.ElementTree as ET

        url = f"https://news.google.com/rss/search?q={query}"

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=15
        )

        root = ET.fromstring(response.text)

        results = []

        for item in root.findall(".//item")[:limit]:

            results.append({
                "source": "google_news",
                "title": clean_html(
                    item.findtext("title", "")
                ),
                "url": item.findtext("link", ""),
                "snippet": clean_html(
                    item.findtext("description", "")
                )
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
        print(f"Provider: DuckDuckGo ({len(results)} results)")
        return results

    #
    # Provider 2
    #
    results = search_wikipedia(query, limit)

    if results:
        print(f"Provider: Wikipedia ({len(results)} results)")
        return results

    #
    # Provider 3
    #
    results = search_google_news(query, limit)

    if results:
        print(f"Provider: Google News ({len(results)} results)")
        return results

    #
    # Fallback
    #
    return [
        {
            "source": "fallback",
            "title": f'No results found for "{query}"',
            "url": "",
            "snippet": "All search providers returned empty results."
        }
    ]
