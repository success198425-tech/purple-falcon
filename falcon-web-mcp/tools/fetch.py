import httpx

from bs4 import BeautifulSoup

from config import (
    WEB_TIMEOUT,
    WEB_USER_AGENT
)


async def fetch_url(url: str):

    try:

        headers = {
            "User-Agent": WEB_USER_AGENT
        }

        async with httpx.AsyncClient(
            timeout=WEB_TIMEOUT
        ) as client:

            response = await client.get(
                url,
                headers=headers
            )

            response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        return {
            "success": True,
            "url": url,
            "content": text[:50000]
        }

    except Exception as e:

        return {
            "success": False,
            "url": url,
            "error": str(e)
        }
