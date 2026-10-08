from .brain_types import BrainAction, BrainResult

class CapabilityRouter:
    def __init__(self,local=None,web=None,tools=None,main=None):self.local=local;self.web=web;self.tools=tools;self.main=main
    def execute(self,d,message,history=None):
        if d.action==BrainAction.ASK_USER.value:return BrainResult(d,d.clarification_question,True)
        if d.action in {BrainAction.WEB_RESEARCH.value,BrainAction.MARKET_ANALYSIS.value,BrainAction.VERIFY.value} and self.web:
            text=self.web(message,history=history);return BrainResult(d,text,bool(text))
        if d.action==BrainAction.ANSWER_LOCAL.value and self.local:
            text=self.local(message);return BrainResult(d,text,bool(text))
        if d.action==BrainAction.TOOL_ACTION.value and self.tools:
            text=self.tools(message);return BrainResult(d,text,bool(text))
        if self.main:
            text=self.main(message,history=history);return BrainResult(d,text,bool(text))
        return BrainResult(d,None,False)
