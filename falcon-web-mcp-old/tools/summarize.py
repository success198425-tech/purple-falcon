def summarize_content(content: str):

    if not content:

        return {
            "success": True,
            "summary": ""
        }

    clean = content.strip()

    summary = clean[:1200]

    return {
        "success": True,
        "summary": summary,
        "characters": len(summary)
    }
