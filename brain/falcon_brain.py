import re
from .brain_types import BrainAction, BrainDecision, RiskLevel, ResponseDepth
from .brain_policy import apply_policy
from .brain_language import detect_language, say
from .brain_state import BrainStateStore
from .brain_context import reconstruct
from .brain_router import CapabilityRouter
from .brain_ledger import record

class FalconBrain:
    def __init__(self,webreason=None,local=None,tools=None,main=None,ledger_path='purple_falcon_brain_ledger.jsonl'):
        self.webreason=webreason;self.state=BrainStateStore();self.ledger_path=ledger_path
        self.router=CapabilityRouter(local=local,web=self._web,tools=tools,main=main)
    def _web(self,message,history=None):
        if not self.webreason:return None
        return self.webreason.web_reply(message,history=history)
    def decide(self,message,history=None,conversation_id='default'):
        st=self.state.get(conversation_id);q=reconstruct(message,st);lang=detect_language(q);low=q.lower()
        d=BrainDecision(language=lang,reconstructed_query=q)
        if self.webreason and hasattr(self.webreason,'brain_decide'):
            wd=self.webreason.brain_decide(q,history)
            for name in ('goal','intent','domain','action','language','entities','known','missing','freshness_required','risk_level','evidence_required','research_depth','response_depth','allow_local_brain','allow_model_memory'):
                if hasattr(wd,name):setattr(d,name,getattr(wd,name))
            if hasattr(wd,'clarification_question'):d.clarification_question=wd.clarification_question
            elif hasattr(wd,'question'):d.clarification_question=wd.question
            if d.action=='DEFER_TO_LOCAL':d.action=BrainAction.ANSWER_LOCAL.value
        else:
            if re.search(r'\b(?:current|latest|today|now|news|weather|stock|market)\b',low):d.intent='CURRENT_FACT';d.domain='current_world';d.action=BrainAction.WEB_RESEARCH.value;d.freshness_required=True
            else:d.action=BrainAction.ANSWER_LOCAL.value
        d=apply_policy(d)
        if d.missing and not d.clarification_question:d.action=BrainAction.ASK_USER.value;d.clarification_question=say(lang,'What information should I use to continue?','Anong information ang gusto mong gamitin ko para magpatuloy?','Maklumat apa yang perlu saya gunakan untuk teruskan?')
        st.active_goal=d.goal;st.entities=(st.entities+d.entities)[-10:];st.last_intent=d.intent;st.last_domain=d.domain;st.last_user_message=message;st.language=lang;st.pending_question=d.clarification_question
        record(d,self.ledger_path);return d
    def execute(self,decision,message,history=None):return self.router.execute(decision,decision.reconstructed_query or message,history)
    def respond(self,message,history=None,conversation_id='default'):
        d=self.decide(message,history,conversation_id);return self.execute(d,message,history)
