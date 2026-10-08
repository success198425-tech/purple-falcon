from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ConversationState:
    conversation_id:str='default'; active_goal:Optional[str]=None; entities:List[str]=field(default_factory=list)
    last_intent:Optional[str]=None; last_domain:Optional[str]=None; last_user_message:Optional[str]=None
    language:str='en'; pending_question:Optional[str]=None

class BrainStateStore:
    def __init__(self):self._states={}
    def get(self,cid='default'):
        if cid not in self._states:self._states[cid]=ConversationState(conversation_id=cid)
        return self._states[cid]
    def reset(self,cid='default'):self._states.pop(cid,None)
