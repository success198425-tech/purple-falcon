from .brain_types import BrainAction, BrainDecision, RiskLevel

FRESH_INTENTS={'MARKET_QUOTE','MARKET_TABLE','MARKET_OVERVIEW','MARKET_COMPARISON','MARKET_EXPLANATION','MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS','WEATHER','OFFICEHOLDER','NEWS_RESEARCH','CURRENT_FACT','VERIFY_RESEARCH','REVERIFY'}
HIGH_RISK_INTENTS={'MARKET_DECISION_ANALYSIS'}

def apply_policy(d:BrainDecision)->BrainDecision:
    d.freshness_required=d.freshness_required or d.intent in FRESH_INTENTS
    if d.intent in HIGH_RISK_INTENTS:d.risk_level=RiskLevel.HIGH.value
    elif d.freshness_required and d.risk_level==RiskLevel.LOW.value:d.risk_level=RiskLevel.MEDIUM.value
    d.evidence_required=d.evidence_required or d.freshness_required or d.risk_level==RiskLevel.HIGH.value
    if d.freshness_required or d.risk_level==RiskLevel.HIGH.value:
        d.allow_local_brain=False;d.allow_model_memory=False
    if d.risk_level==RiskLevel.HIGH.value:d.research_depth=max(3,d.research_depth)
    return d
