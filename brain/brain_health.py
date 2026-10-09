def brain_health(brain):

    checks = {

        "decision_engine":
            callable(
                getattr(
                    brain,
                    "decide",
                    None
                )
            ),

        "router":
            getattr(
                brain,
                "router",
                None
            ) is not None,

        "state_store":
            getattr(
                brain,
                "state",
                None
            ) is not None,

        "webreason":
            getattr(
                brain,
                "webreason",
                None
            ) is not None,
    }

    score = sum(
        1 for v in checks.values()
        if v
    )

    status = (
        "HEALTHY"
        if score == len(checks)
        else "DEGRADED"
    )

    return {
        "status": status,
        "score": score,
        "checks": checks
    }
