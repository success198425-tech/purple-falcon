def brain_health(brain):
    checks={'decision_engine':callable(getattr(brain,'decide',None)),'router':getattr(brain,'router',None) is not None,'state_store':getattr(brain,'state',None) is not None}
    return {'status':'HEALTHY' if all(checks.values()) else 'DEGRADED','checks':checks}
