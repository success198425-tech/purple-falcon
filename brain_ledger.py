import json, os
from datetime import datetime, timezone

def record(decision,path='purple_falcon_brain_ledger.jsonl'):
    try:
        row={'time':datetime.now(timezone.utc).isoformat(),'goal':decision.goal,'intent':decision.intent,'domain':decision.domain,'action':decision.action,'freshness_required':decision.freshness_required,'risk_level':decision.risk_level,'research_depth':decision.research_depth,'allow_local_brain':decision.allow_local_brain,'allow_model_memory':decision.allow_model_memory}
        with open(path,'a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    except Exception:pass
