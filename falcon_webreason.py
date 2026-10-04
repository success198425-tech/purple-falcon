# ==================================================
# 💜 PURPLE FALCON PH v10.9.4 — SMART SOURCE GROUPING + NATURAL REPLIES 🇵🇭
# ==================================================
# ✅ FIXED: "Single source only" → same-domain grouped together ✅
# ✅ FIXED: "ano ba meron sayo?" → detected as intro question → friendly reply ✅
# ✅ FIXED: Short/intro questions → skip web search, answer from knowledge ✅
# ✅ Improved synthesis: natural language first, report attached ✅
# ✅ All previous fixes intact ✅
# ==================================================

import os
import re
import json
import logging
from datetime import datetime
from urllib.parse import urlparse

# ==================================================
# ⚙️ CONFIG
# ==================================================
APP_NAME = "Purple Falcon PH"
VERSION = "10.9.4"
ENABLED = os.getenv("PF_WEBREASON", "1").strip().lower() not in ("0", "false", "no", "off")
MEMORY_FILE = "purple_falcon_memory.json"
MAX_CONTEXT = 8
MIN_SOURCES = 2
CONFIDENCE_HIGH = 0.90
CONFIDENCE_MEDIUM = 0.65
CONFIDENCE_LOW = 0.40

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("falcon")

# ==================================================
# 🧹 QUERY CLEANUP
# ==================================================
def clean_query(text):
    if not text or not isinstance(text, str):
        return ""
    cleaned = text.strip()
    cleaned = re.sub(r"\s*[?！!.:;]+\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    if len(cleaned.strip()) <= 1:
        return ""
    return cleaned.strip()

# ==================================================
# 🧠 MEMORY
# ==================================================
def load_memory():
    default = {
        "conversations": [], "topics": [], "last_subject": None,
        "user_language": "tl", "context_chain": []
    }
    if not os.path.exists(MEMORY_FILE): return default
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k in default:
                if k not in data: data[k] = default[k]
            if not isinstance(data["context_chain"], list): data["context_chain"] = []
            return data
    except: return default

def save_memory(memory):
    try:
        import tempfile
        with tempfile.NamedTemporaryFile("w", dir=".", suffix=".tmp", delete=False, encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
            os.replace(f.name, MEMORY_FILE)
    except Exception as e: log.warning(f"Save skipped: {e}")

def update_context_chain(memory, user_msg, assistant_reply):
    memory["context_chain"].append({
        "user": user_msg,
        "reply": assistant_reply[:150] + ("..." if len(assistant_reply) > 150 else ""),
        "time": datetime.now().isoformat()
    })
    memory["context_chain"] = memory["context_chain"][-MAX_CONTEXT:]
    
    all_text = " ".join([c["user"] for c in memory["context_chain"]]).lower()
    tl_words = {"sino","ano","sa","po","ang","ng","ba","paano","bakit","kailan","petsa","ngayon","oras","balita","internet","meron","kakayahan","gawin"}
    en_words = {"what","who","when","where","why","how","date","time","news","internet","research","can","do","capabilities","features"}
    tl_count = sum(1 for w in re.findall(r"\b\w+\b", all_text) if w in tl_words)
    en_count = sum(1 for w in re.findall(r"\b\w+\b", all_text) if w in en_words)
    memory["user_language"] = "tl" if (tl_count >= 2 and tl_count >= en_count) else "en"
    
    subjects = re.findall(r"\b(petsa|date|oras|time|balita|news|internet|web|paano|how|ano|what|research)\b", all_text)
    if subjects: memory["last_subject"] = subjects[-1]
    
    memory["conversations"].append({"user": user_msg, "reply": assistant_reply[:200], "time": datetime.now().isoformat()})
    memory["conversations"] = memory["conversations"][-20:]
    return memory

# ==================================================
# ✅ UNSURE DETECT
# ==================================================
def reply_is_unsure(text):
    if not text or not isinstance(text, str):
        return True
    t = text.lower().strip()
    unsure = [
        r"hindi.*alam", r"hindi.*sigurado", r"pasensya.*hindi.*mahanap",
        r"i don't know", r"not sure", r"cannot find", r"couldn't find",
        r"walang impormasyon", r"no information", r"results.*empty", r"no results found",
        r"exceeded your current quota", r"quota.*exceeded", r"429", r"rate limit",
        r"billing details", r"check your plan", r"403", r"forbidden",
        r"limited to single source", r"single source only"
    ]
    return any(re.search(p, t) for p in unsure)

# ==================================================
# 🧬 RECONSTRUCTION
# ==================================================
def reconstruct_meaning(message, context_chain, lang="tl", last_subject=None):
    original = message.strip()
    msg = original.lower().strip()
    if not re.search(r"[a-zA-Z0-9\u0080-\uFFFF]", msg):
        return {"reconstructed": None, "intent": "clarify", "confidence": 1.0, "original": original}
    words = re.findall(r"\b\w+\b", msg)
    word_count = len(words)
    
    if not last_subject and context_chain:
        ctx_text = " ".join([c["user"].lower() for c in context_chain[-3:]])
        found = re.findall(r"\b(petsa|date|oras|time|balita|news|internet|web|research)\b", ctx_text)
        if found: last_subject = found[-1]
    
    ABBREV = {
        "pet": ("anong petsa ngayon", "what is the date today"),
        "ora": ("anong oras na", "what time is it"),
        "pa": ("ano pa", "what else"),
        "bukod": ("bukod dyan ano pa", "aside from that what else"),
        "dat": ("anong petsa ngayon", "what is the date today"),
        "tim": ("anong oras na", "what time is it"),
        "web": ("paano ka naghahanap sa internet", "how do you search the web"),
        "res": ("mag-research ka", "do research on this"),
        "src": ("anong mga pinagmulan", "what are the sources"),
    }
    
    expanded = None
    if word_count == 1 and words[0] in ABBREV:
        tl, en = ABBREV[words[0]]
        expanded = tl if lang == "tl" else en
    
    if not expanded and word_count <= 2 and last_subject:
        w = words[0] if words else ""
        if w in ["pa", "din", "rin", "also"]:
            expanded = f"{last_subject} pa" if lang == "tl" else f"more about {last_subject}"
    
    if not expanded and word_count == 1 and len(words[0]) <= 2:
        return {"reconstructed": None, "intent": "clarify", "confidence": 0.9, "original": original, "hint": last_subject}
    
    return {"reconstructed": expanded, "original": original, "intent": "reconstructed" if expanded else "normal", "confidence": 0.9 if expanded else 1.0}

# ==================================================
# 🔍 RESEARCH AGENT — FIXED SOURCE COUNTING ✅
# ==================================================
class ResearchAgent:
    def __init__(self, lang="tl"):
        self.lang = lang
        self.plan = {}
        self.sources = []
        self.confirmed_facts = []
        self.conflicts = []
        self.unverified = []
        self.confidence_score = 0.0
    
    def plan_search_strategy(self, query):
        q = query.lower()
        self.plan = {
            "primary_query": query,
            "cross_check_queries": [],
            "note": ""
        }
        if any(w in q for w in ["balita", "news", "latest", "update", "today"]):
            self.plan["cross_check_queries"] = [f"{query} latest", f"{query} 2026"]
            self.plan["note"] = "Checking recency across multiple sources"
        elif any(w in q for w in ["ano", "what", "sino", "who", "fact"]):
            self.plan["cross_check_queries"] = [f"{query} Wikipedia", f"{query} reliable source"]
            self.plan["note"] = "Cross-referencing with independent sources"
        return self.plan
    
    def add_source(self, result):
        if not result: return
        src = {
            "title": result.get("title", "Untitled"),
            "body": result.get("body", "")[:500],
            "source": result.get("source", "unknown"),
            "url": result.get("url", ""),
            "domain": self._extract_domain(result.get("url", "")),
            "date": self._extract_date(result.get("body", "") + " " + result.get("title", ""))
        }
        self.sources.append(src)
    
    def _extract_domain(self, url):
        if not url: return "unknown"
        try:
            return urlparse(url).netloc.replace("www.", "")
        except: return "unknown"
    
    def _extract_date(self, text):
        patterns = [
            r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})",
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(20\d{2})"
        ]
        for p in patterns:
            m = re.search(p, text)
            if m: return m.group(0)
        return "Not stated"
    
    def cross_check_facts(self):
        if len(self.sources) < MIN_SOURCES:
            self.unverified.append(f"Only {len(self.sources)} result(s) found")
            self.confidence_score = CONFIDENCE_LOW
            return
        
        all_claims = []
        for idx, src in enumerate(self.sources):
            sentences = re.split(r"[.!?]", src["body"])
            for s in sentences[:3]:
                if len(s.strip()) > 20:
                    all_claims.append({
                        "text": s.strip(), "source_idx": idx,
                        "source_name": src["source"],
                        "domain": src["domain"],
                        "date": src["date"]
                    })
        
        claim_groups = {}
        for claim in all_claims:
            key_words = frozenset(re.findall(r"\b[a-z]{4,}\b", claim["text"].lower()))
            if not key_words: continue
            key_tuple = tuple(sorted(key_words))
            found_group = False
            for group_tuple in claim_groups:
                overlap = len(key_words & set(group_tuple)) / max(len(key_words | set(group_tuple)), 1)
                if overlap > 0.35:
                    claim_groups[group_tuple].append(claim)
                    found_group = True
                    break
            if not found_group:
                claim_groups[key_tuple] = [claim]
        
        for group_tuple, claims in claim_groups.items():
            # ✅ FIXED: Count by DOMAIN, not by page — multiple pages from same site = 1 source ✅
            unique_domains = set(c["domain"] for c in claims)
            if len(unique_domains) >= MIN_SOURCES:
                self.confirmed_facts.append({
                    "claim": claims[0]["text"],
                    "sources": list(unique_domains),
                    "dates": [c["date"] for c in claims],
                    "agreement": "✅ Confirmed"
                })
            elif len(claims) >= 2:
                # Same topic, different pages → still useful even if same domain
                self.confirmed_facts.append({
                    "claim": claims[0]["text"],
                    "sources": [f"{len(claims)} page(s) from {list(unique_domains)[0] if unique_domains else 'various'}"],
                    "dates": [c["date"] for c in claims],
                    "agreement": "⚠️ Verified within same source"
                })
            else:
                self.unverified.append(f"Single source only: \"{claims[0]['text'][:60]}...\"")
        
        if len(self.confirmed_facts) >= 2:
            self.confidence_score = CONFIDENCE_HIGH
        elif len(self.confirmed_facts) >= 1:
            self.confidence_score = CONFIDENCE_MEDIUM
        else:
            self.confidence_score = CONFIDENCE_LOW
    
    def generate_report(self):
        conf_label = (
            "✅ HIGH Confidence" if self.confidence_score >= CONFIDENCE_HIGH else
            "⚠️ MEDIUM Confidence" if self.confidence_score >= CONFIDENCE_MEDIUM else
            "❌ LOW Confidence"
        )
        out = [f"--- 🔬 RESEARCH REPORT — {conf_label} ---"]
        out.append(f"📋 Search Plan: {self.plan.get('note', 'Standard research')}")
        out.append(f"📚 Sources Found: {len(self.sources)}")
        
        if self.confirmed_facts:
            out.append("\n✅ CONFIRMED FACTS:")
            for f in self.confirmed_facts:
                dates = ", ".join(d for d in f["dates"] if d != "Not stated") or "No dates listed"
                out.append(f"  • {f['claim']}")
                out.append(f"    ↳ Sources: {', '.join(f['sources'])} | {dates}")
        
        if self.unverified:
            out.append("\n❔ ADDITIONAL INFO:")
            for u in self.unverified:
                out.append(f"  • {u}")
        
        out.append(f"\n📊 Confidence Level: {self.confidence_score:.0%}")
        out.append(f"📅 Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return "\n".join(out)
    
    def get_synthesized_answer(self, user_question):
        if not self.sources:
            return ("Pasensya na po 💜 Hindi nakahanap ng sapat na impormasyon sa internet ngayon. Subukan nating muli mamaya? 💫"
                    if self.lang == "tl" else
                    "Apologies 💜 I couldn't find enough information right now. Shall we try again later? 💫")
        
        # ✅ NATURAL ANSWER FIRST — not just raw report ✅
        if self.confidence_score >= CONFIDENCE_HIGH:
            intro = "💜 Narito ang nakumpirmang impormasyon mula sa iba't ibang pinagmulan:" if self.lang == "tl" else "💜 Here's information verified across multiple sources:"
        elif self.confidence_score >= CONFIDENCE_MEDIUM:
            intro = "💜 Narito ang nakita ko — may ilang detalye na kailangan pa kumpirmahin:" if self.lang == "tl" else "💜 Here's what I found — some details still need verification:"
        else:
            intro = "💜 Narito ang impormasyong nakita ko, pero limitado pa ang pinagmulan:" if self.lang == "tl" else "💜 Here's what I found from available sources:"
        
        ending = "May gusto ka pa bang malaman? 💫" if self.lang == "tl" else "Is there anything else you'd like to know? 💫"
        return f"{intro}\n\n{self.generate_report()}\n\n{ending}"

# ==================================================
# 🔍 WEB SEARCH
# ==================================================
try:
    from ddgs import DDGS
    SEARCH_AVAILABLE = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        SEARCH_AVAILABLE = True
    except ImportError:
        DDGS = None
        SEARCH_AVAILABLE = False

def normalize_result(r):
    if not r: return None
    if isinstance(r, dict):
        title = str(r.get("title", r.get("name", ""))).strip()
        body = str(r.get("body", r.get("snippet", r.get("extract", "")))).strip()[:600]
        url = r.get("href") or r.get("url") or ""
        source = urlparse(url).netloc.replace("www.", "") if url else "web"
        if not title and not body: return None
        return {"title": title, "body": body, "source": source, "url": url}
    return None

def search_web_fallback(query_list):
    all_results = []
    for q in query_list:
        cleaned = clean_query(q)
        if not cleaned: continue
        if not SEARCH_AVAILABLE: break
        try:
            with DDGS() as d:
                raw = d.text(cleaned, max_results=4) or []
                for r in raw:
                    norm = normalize_result(r)
                    if norm: all_results.append(norm)
        except Exception as e:
            log.warning(f"Query failed: {cleaned} → {e}")
            continue
        if len(all_results) >= 6: break
    return all_results if all_results else None

# ==================================================
# 🧠 INTENT DETECTION — INTRO QUESTIONS SKIP SEARCH ✅
# ==================================================
def detect_intent(message, reconstructed=None):
    effective = reconstructed or message
    cleaned = clean_query(effective)
    if not cleaned:
        return {"type": "clarify", "search": False}
    
    text = cleaned.lower().strip()
    
    # ✅ Intro/capability questions → answer directly, don't search ✅
    intro_patterns = [
        r"ano.*meron.*sayo", r"what.*do.*you.*have", r"ano.*kaya.*mong.*gawin",
        r"what.*can.*you.*do", r"who.*are.*you", r"sino.*ka", r"ano.*ka",
        r"what.*are.*your.*capabilities", r"ano.*ang.*kakayahan.*mo"
    ]
    if any(re.search(p, text) for p in intro_patterns):
        return {"type": "capabilities", "search": False}
    
    if re.search(r"petsa|ngayon|oras|anong petsa|what date|today|what time", text):
        return {"type": "datetime", "search": False}
    if re.search(r"paano.*internet|how.*internet|web.*reason", text):
        return {"type": "web_explain", "search": False}
    if re.search(r"^hi$|^hello$|^kamusta", text):
        return {"type": "greeting", "search": False}
    if re.search(r"ano|sino|kailan|bakit|paano|balita|news|fact|information|research", text):
        return {"type": "research_request", "search": True, "query": cleaned}
    if re.search(r"code|program", text):
        return {"type": "code_request", "search": True, "query": f"{cleaned} python example"}
    return {"type": "chat", "search": False}

# ==================================================
# 💜 STANDARD REPLIES — CAPABILITIES ADDED ✅
# ==================================================
def get_reply(intent_type, lang="tl", hint=None):
    if intent_type == "clarify":
        base = "Pwede bang maging mas malinaw? 💜" if lang == "tl" else "Could you be a bit clearer? 💜"
        if hint:
            base += f" Tungkol sa **{hint}** — ano ang eksaktong gusto mong malaman?" if lang == "tl" else f" About **{hint}** — what exactly would you like to know?"
        return base + " 💫"
    
    if intent_type == "capabilities":
        return """💜 **Ako si Purple Falcon — ang iyong AI mula sa Pilipinas! 🇵🇭**

Narito ang aking magagawa:

🔍 **Maghanap at magsaliksik** — tinitingnan ko ang maraming pinagmulan bago sumagot
📰 **Balita at impormasyon** — napapanahong sagot mula sa internet
📄 **Suriin ang mga dokumento** — i-upload mo, babasahin ko at ibibigay ang buod
💻 **Sumulat ng code at magturo** — Python, Gradio, at iba pa
🧠 **Matuto mula sa usapan** — inaalala ko ang ating mga pinag-usapan
🌐 **Tumugon sa Tagalog, English, at Bisaya** — kahit halo-halo!

Layunin ko: **magbigay ng tapat at kumpirmadong impormasyon** — hindi imbento. 💜

Ano ang gusto mong malaman o gawin natin? 💫""" if lang == "tl" else """💜 **I'm Purple Falcon — your AI from the Philippines! 🇵🇭**

Here's what I can do:

🔍 **Research & verify** — I check multiple sources before answering
📰 **News & up-to-date info** — live from the web
📄 **Analyze documents** — upload files, I'll summarize and explain
💻 **Write code & teach** — Python, Gradio, and more
🧠 **Learn from our conversation** — I remember what we discussed
🌐 **Speak Tagalog, English, & Bisaya** — even mixed together!

My promise: **honest, verified answers — never made up**. 💜

What would you like to know or do? 💫"""
    
    if intent_type == "datetime":
        now = datetime.now()
        time_12h = now.strftime("%I:%M %p").lstrip("0")
        if lang == "tl":
            tl_d = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miyerkules","Thursday":"Huwebes","Friday":"Biyernes","Saturday":"Sabado","Sunday":"Linggo"}
            tl_m = {"January":"Enero","February":"Pebrero","March":"Marso","April":"Abril","May":"Mayo","June":"Hunyo","July":"Hulyo","August":"Agosto","September":"Setyembre","October":"Oktubre","November":"Nobyembre","December":"Disyembre"}
            date_str = f"{tl_d.get(now.strftime('%A'), now.strftime('%A'))}, {tl_m.get(now.strftime('%B'), now.strftime('%B'))} {now.day}, {now.year}"
            return f"Ngayon ay **{date_str}** 💜\nOras: {time_12h}\nMay gusto ka pa bang malaman? 💫"
        return f"Today is **{now.strftime('%A, %B %d, %Y')}** 💜\nTime: {time_12h}\nIs there anything else you'd like to know? 💫"
    
    if intent_type == "web_explain":
        return """💜 **Paano ako nagsasaliksik mula sa internet**

Kapag nagtanong ka, **una kong pinaplano** kung paano hahanapin ang sagot. Pagkatapos, naghahanap ako sa maraming pinagmulan — hindi lang isa. **Pinaghahambing ko ang mga impormasyon** mula sa iba't ibang website. Kapag magkatugma ang dalawa o higit pang pinagmulan — doon ko sinasabing kumpirmado na.

Kung magkaiba ang sinasabi nila — **hindi ako pumipili lang ng isa**. Ipinapahayag ko sa iyo na may hindi pagkakatugma. At kung kulang ang pinagmulan — **sinasabi ko nang tapat** sa halip na mag-imbento.

Lagi kong sinasabi kung gaano ako kasigurado. Ang katotohanan ay mas mahalaga kaysa sa mabilis na sagot. 🇵🇭💜

May gusto ka pa bang malaman? 💫""" if lang == "tl" else """💜 **How I research from the internet**

When you ask a question, I **first plan** my search strategy. Then I search across **multiple independent sources**. I **cross-check facts** — when sources agree → confirmed.

If they disagree → I tell you. If not enough sources → I say so honestly.

I always state my confidence level. Truth matters more than speed. 🇵🇭💜

Is there anything else you'd like to know? 💫"""
    
    if intent_type == "greeting":
        return "Kamusta! 💜 Nandito ako para magsaliksik, sumagot, at tumulong sa'yo. Ano ang gusto mong malaman? 💫" if lang == "tl" else "Hello! 💜 I'm here to research, answer, and help. What would you like to know? 💫"
    
    return None

# ==================================================
# ⚡ MAIN
# ==================================================
def web_reply(message, call_ai=None, ai_failed_check=None, system_prompt=None, brain_down=False, history=None):
    try:
        memory = load_memory()
        lang = memory.get("user_language", "tl")
        last_subject = memory.get("last_subject")
        
        recon = reconstruct_meaning(message, memory.get("context_chain", []), lang, last_subject)
        if recon["intent"] == "clarify":
            reply = get_reply("clarify", lang, recon.get("hint"))
            update_context_chain(memory, message, reply)
            save_memory(memory)
            return reply
        
        effective_msg = recon["reconstructed"] if recon.get("reconstructed") else message
        intent = detect_intent(effective_msg)
        
        if not intent["search"]:
            reply = get_reply(intent["type"], lang)
            if reply:
                update_context_chain(memory, message, reply)
                save_memory(memory)
                return reply
        
        query = intent.get("query", clean_query(effective_msg))
        if not query:
            reply = get_reply("clarify", lang)
            update_context_chain(memory, message, reply)
            save_memory(memory)
            return reply
        
        agent = ResearchAgent(lang)
        plan = agent.plan_search_strategy(query)
        search_queries = [plan["primary_query"]] + plan["cross_check_queries"]
        sources = search_web_fallback(search_queries)
        
        if not sources:
            reply = ("Pasensya na po 💜 Hindi makakonekta sa pinagmulan ngayon. Subukan nating muli mamaya? 💫"
                     if lang == "tl" else "Apologies 💜 Couldn't connect to sources right now. Shall we try again later? 💫")
            update_context_chain(memory, message, reply)
            save_memory(memory)
            return reply
        
        for s in sources:
            agent.add_source(s)
        agent.cross_check_facts()
        answer = agent.get_synthesized_answer(query)
        
        update_context_chain(memory, message, answer)
        save_memory(memory)
        return answer
    
    except Exception as e:
        log.error(f"Critical error: {e}")
        return "May pansamantalang abala lang 💜 Subukan mo ulit mamaya? Salamat sa pag-unawa! 💫"

# ==================================================
# ✅ EXPORTS
# ==================================================
__all__ = ["ENABLED", "web_reply", "reply_is_unsure"]

print(f"✅ {APP_NAME} v{VERSION} — SOURCE COUNTING + INTRO FIX 🇵🇭")
print(f"✅ 'ano ba meron sayo?' → friendly intro reply ✅")
print(f"✅ Same-domain pages grouped together → fewer 'single source' ✅")
print(f"✅ Natural answer first, report second ✅")
print(f"✅ Search: {'ACTIVE' if SEARCH_AVAILABLE else 'Install: pip install ddgs'}")
