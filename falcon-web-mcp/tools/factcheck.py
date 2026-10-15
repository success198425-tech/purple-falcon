from tools.search import web_search


def fact_check(claim: str):

    results = web_search(
        claim,
        limit=5
    )

    return {
        "claim": claim,
        "sources_found": results.get(
            "count",
            0
        ),
        "results": results.get(
            "results",
            []
        )
    }
