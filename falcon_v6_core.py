"""Purple Falcon v6 Lightweight Cognitive Core.
Single-process, dependency-free orchestration primitives for integration with the existing Gradio app.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Any
import re

@dataclass
class MemoryContext:
    active_topic: str = ""
    current_goal: str = ""
    pending_task: str = ""
    recent_messages: list[dict] = field(default_factory=list)

@dataclass
class IntentResult:
    name: str
    requires_ai: bool = False
    requires_web: bool = False
    requires_memory: bool = True
    confidence: str = "medium"

@dataclass
class AgentResult:
    success: bool
    content: str = ""
    route: str = ""
    evidence: list[dict] = field(default_factory=list)
    error: str = ""

@dataclass
class ValidationResult:
    passed: bool
    reason: str = ""
    retry: bool = False

@dataclass
class TurnResult:
    text: str
    intent: str
    route: str
    confidence: str
    web_used: bool = False

class V6IntentRouter:
    ACK = re.compile(r"^\s*(?:cool|nice|great|good|awesome|okay|ok|sige|salamat|thanks?|thank you|haha+|hehe+|lol|oh(?:\s+talaga)?|talaga|really|i see|gets|got it|understood|yes|yup|yep|no|nope|sure)[!?. \t]*$", re.I)
    MEMORY = re.compile(r"\b(?:memory|remember|remembering|naalala|natatandaan|conversation|previous|earlier|kanina|pinag.?uusapan|discussing|previous topic|last topic)\b", re.I)
    FOLLOWUP = re.compile(r"\b(?:bakit|why|ano(?:ng)? nangyari|what happened|tuloy|continue|ulit|again|last answer|sagot|answer|ito|iyan|yan|yun|yung|that|this|it)\b", re.I)
    SELFQ = re.compile(r"\b(?:your skills|your capabilities|what can you do|what will you learn|what did you learn|your status|system status|your tools|about yourself|what is enabled)\b", re.I)
    CURRENT = re.compile(r"\b(?:latest|current|today|recent|news|weather|price|cost|srp|rrp|rate|version|release|schedule|availability|updated?|now|right now)\b", re.I)
    RESEARCH = re.compile(r"\b(?:search|research|look ?up|find online|web|internet|source|citation|verify|confirm|compare|pricing|who is|what is|when is|where is|how much)\b", re.I)
    CODE = re.compile(r"```|\b(?:code|coding|script|program|function|class|algorithm)\b|\b(?:write|create|make|build|generate|give me|show me|provide)\b.{0,60}\b(?:sample|example|code|program|script|function|algorithm)\b", re.I)
    MATH = re.compile(r"\b(?:calculate|compute|solve|equation|algebra|calculus|derivative|integral|matrix|probability|statistics?|fft|rms|oee|mtbf|mttr)\b|\d\s*[+*/^%-]\s*\d", re.I)
    INDUSTRIAL = re.compile(r"\b(?:machine|motor|pump|bearing|vibration|rms|fft|temperature|downtime|oee|alarm|plc|vfd|servo|maintenance)\b", re.I)

    def classify(self, message: str, memory: MemoryContext, has_image: bool=False, has_file: bool=False) -> IntentResult:
        text=(message or "").strip()
        live_intent = bool(
            text and (
                self.CURRENT.search(text)
                or self.RESEARCH.search(text)
                or re.search(r"\b(?:what|who|where|when|why|how|which)\b.*\b(?:now|price|cost|srp|rrp|rate|release|latest|current|today|weather|news)\b", text, re.I)
            )
        )
        if self.ACK.match(text):
            return IntentResult("acknowledgement", False, False, True, "high")
        if self.SELFQ.search(text):
            return IntentResult("self_system", False, False, True, "high")
        if len(text.split()) <= 24 and self.MEMORY.search(text):
            return IntentResult("memory", False, False, True, "high")
        if len(text.split()) <= 24 and self.FOLLOWUP.search(text):
            return IntentResult("conversation_followup", False, False, True, "high")
        if has_image:
            return IntentResult("vision", True, False, True, "high")
        if self.CODE.search(text):
            return IntentResult("coding", True, False, True, "high")
        if self.MATH.search(text):
            return IntentResult("math", False, False, True, "high")
        if self.INDUSTRIAL.search(text):
            return IntentResult("industrial", True, False, True, "high")
        if live_intent:
            return IntentResult("external_current", True, True, True, "high")
        if has_file:
            return IntentResult("file", True, False, True, "high")
        return IntentResult("general_reasoning", True, False, True, "medium")

class V6Validator:
    LOCAL = {"acknowledgement", "self_system", "memory", "conversation_followup"}
    def validate(self, intent: IntentResult, result: AgentResult) -> ValidationResult:
        if not result.success or not result.content.strip():
            return ValidationResult(False, result.error or "empty result", True)
        if intent.name in self.LOCAL and result.route == "web":
            return ValidationResult(False, "web result cannot satisfy a local conversation intent", True)
        return ValidationResult(True, "route compatible with intent", False)

class V6ConversationAgent:
    def execute(self, intent: IntentResult, memory: MemoryContext) -> AgentResult:
        topic=memory.active_topic.strip()
        if intent.name == "acknowledgement":
            msg = "👍 Sige. " + (f"Tuloy natin ang **{topic}** kapag ready ka." if topic else "Ready ako sa next step mo.")
            return AgentResult(True, msg, "local")
        if intent.name in {"memory", "conversation_followup"}:
            msg = (f"🧠 Nasa memory pa ang context. Ang active topic natin ay **{topic}**." if topic
                   else "🧠 Available ang conversation memory, pero wala pa akong sapat na earlier substantive topic sa session.")
            return AgentResult(True, msg, "memory")
        if intent.name == "self_system":
            return AgentResult(True, "🧠 Purple Falcon v6 uses memory-first intent routing, reasoning/provider routing, coding, math, vision/files when available, local knowledge, validation, and selective web research. Web is a specialist tool, not the default fallback brain.", "local")
        return AgentResult(False, route="local", error="not a local intent")

class V6Orchestrator:
    """Lightweight coordinator. Existing Falcon functions are injected as callbacks."""
    def __init__(self, brain: Callable[[str, MemoryContext], AgentResult], web: Callable[[str, MemoryContext], AgentResult],
                 code: Callable[[str, MemoryContext], AgentResult] | None=None,
                 math: Callable[[str, MemoryContext], AgentResult] | None=None,
                 vision: Callable[[str, MemoryContext], AgentResult] | None=None):
        self.router=V6IntentRouter(); self.validator=V6Validator(); self.local=V6ConversationAgent()
        self.brain=brain; self.web=web; self.code=code or brain; self.math=math or brain; self.vision=vision or brain

    def _looks_live(self, message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False
        return bool(
            self.router.CURRENT.search(text)
            or self.router.RESEARCH.search(text)
            or re.search(r"\b(?:what|who|where|when|why|how|which)\b.*\b(?:now|price|cost|srp|rrp|rate|release|latest|current|today|weather|news)\b", text, re.I)
        )

    def handle(self, message: str, memory: MemoryContext, *, has_image=False, has_file=False) -> TurnResult:
        intent=self.router.classify(message, memory, has_image, has_file)
        if intent.name in self.validator.LOCAL:
            candidate=self.local.execute(intent, memory)
        elif intent.name == "external_current":
            candidate=self.web(message, memory)
        elif intent.name == "coding":
            candidate=self.code(message, memory)
        elif intent.name == "math":
            candidate=self.math(message, memory)
        elif intent.name == "vision":
            candidate=self.vision(message, memory)
        else:
            candidate=self.brain(message, memory)
        check=self.validator.validate(intent, candidate)
        if not check.passed:
            if intent.name in self.validator.LOCAL:
                candidate=self.local.execute(intent, memory)
            elif self._looks_live(message) and callable(self.web):
                web_candidate=self.web(message, memory)
                if web_candidate.success and web_candidate.content.strip():
                    return TurnResult(web_candidate.content, intent.name, "web", intent.confidence, True)
                candidate = web_candidate if web_candidate.success else self.brain(message, memory)
            elif intent.requires_web and callable(self.web):
                web_candidate=self.web(message, memory)
                if web_candidate.success and web_candidate.content.strip():
                    return TurnResult(web_candidate.content, intent.name, "web", intent.confidence, True)
                candidate = web_candidate if web_candidate.success else self.brain(message, memory)
            else:
                return TurnResult("🧠 The selected capability is unavailable for this turn.", intent.name, candidate.route or "unavailable", "low", False)
        return TurnResult(candidate.content, intent.name, candidate.route, intent.confidence, candidate.route == "web")
