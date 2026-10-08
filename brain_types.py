from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class BrainAction(str, Enum):
    DETERMINISTIC='DETERMINISTIC'; ASK_USER='ASK_USER'; ANSWER_LOCAL='ANSWER_LOCAL'
    WEB_RESEARCH='WEB_RESEARCH'; MARKET_ANALYSIS='MARKET_ANALYSIS'; TOOL_ACTION='TOOL_ACTION'
    VERIFY='VERIFY'; MAIN_REASONING='MAIN_REASONING'

class RiskLevel(str, Enum): LOW='LOW'; MEDIUM='MEDIUM'; HIGH='HIGH'
class ResponseDepth(str, Enum): CONCISE='CONCISE'; STANDARD='STANDARD'; DEEP='DEEP'

@dataclass
class BrainDecision:
    goal:str='answer'; intent:str='STATIC'; domain:str='general'; action:str=BrainAction.ANSWER_LOCAL.value
    language:str='en'; entities:List[str]=field(default_factory=list); known:Dict[str,Any]=field(default_factory=dict)
    missing:List[str]=field(default_factory=list); freshness_required:bool=False; evidence_required:bool=False
    risk_level:str=RiskLevel.LOW.value; research_depth:int=0; response_depth:str=ResponseDepth.CONCISE.value
    allow_local_brain:bool=True; allow_model_memory:bool=True; reconstructed_query:Optional[str]=None
    clarification_question:Optional[str]=None

@dataclass
class BrainResult:
    decision:BrainDecision; text:Optional[str]=None; handled:bool=False; metadata:Dict[str,Any]=field(default_factory=dict)
