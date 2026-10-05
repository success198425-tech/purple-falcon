# Purple Falcon WebReason v11.1 - WebResults adapter fix
# Drop-in replacement for the user's v10.9.4 WebReason retrieval boundary.
import os, re, json, logging, tempfile
from datetime import datetime
from urllib.parse import urlparse

APP_NAME='Purple Falcon PH'; VERSION='11.1.0'
ENABLED=os.getenv('PF_WEBREASON','1').strip().lower() not in ('0','false','no','off')
MEMORY_FILE=os.getenv('PF_MEMORY_FILE','purple_falcon_memory.json')
MAX_CONTEXT=8; MAX_RESULTS=8; MIN_SOURCES=2
CONFIDENCE_HIGH=.90; CONFIDENCE_MEDIUM=.65; CONFIDENCE_LOW=.40
logging.basicConfig(level=logging.INFO); log=logging.getLogger('falcon.webreason')

try:
    import falcon_websearch as websearch
    WEBSEARCH_AVAILABLE=bool(getattr(websearch,'ENABLED',True))
except Exception as e:
    websearch=None; WEBSEARCH_AVAILABLE=False; log.warning('WebSearch unavailable: %s',e)

try:
    from ddgs import DDGS
    DDGS_AVAILABLE=True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_AVAILABLE=True
    except ImportError:
        DDGS=None; DDGS_AVAILABLE=False
SEARCH_AVAILABLE=WEBSEARCH_AVAILABLE or DDGS_AVAILABLE

def clean_query(text):
    if not isinstance(text,str): return ''
    v=re.sub(r'\s+',' ',text.strip()); v=re.sub(r'\s*[?!.:;]+\s*$','',v)
    return v if len(v)>1 else ''

def load_memory():
    d={'conversations':[],'topics':[],'last_subject':None,'user_language':'tl','context_chain':[]}
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE,encoding='utf-8') as f: x=json.load(f)
            if isinstance(x,dict):
                for k,v in d.items(): x.setdefault(k,v)
                return x
    except Exception as e: log.warning('Memory read skipped: %s',e)
    return d

def save_memory(memory):
    try:
        directory=os.path.dirname(os.path.abspath(MEMORY_FILE)) or '.'
        with tempfile.NamedTemporaryFile('w',dir=directory,suffix='.tmp',delete=False,encoding='utf-8') as f:
            json.dump(memory,f,ensure_ascii=False,indent=2); tmp=f.name
        os.replace(tmp,MEMORY_FILE)
    except Exception as e: log.warning('Memory save skipped: %s',e)

def update_context_chain(memory,user_msg,assistant_reply):
    r=str(assistant_reply or '')
    memory['context_chain'].append({'user':user_msg,'reply':r[:150],'time':datetime.now().isoformat()}); memory['context_chain']=memory['context_chain'][-MAX_CONTEXT:]
    memory['conversations'].append({'user':user_msg,'reply':r[:200],'time':datetime.now().isoformat()}); memory['conversations']=memory['conversations'][-20:]
    return memory

def reply_is_unsure(text):
    if not isinstance(text,str) or not text.strip(): return True
    return bool(re.search(r"hindi.*alam|hindi.*sigurado|i don't know|not sure|cannot find|couldn't find|no information|no results|quota|rate limit|forbidden",text,re.I))

def normalize_result(r):
    if not isinstance(r,dict): return None
    title=str(r.get('title') or r.get('name') or '').strip()
    body=str(r.get('body') or r.get('snippet') or r.get('text') or r.get('extract') or r.get('content') or '').strip()[:2200]
    url=str(r.get('url') or r.get('href') or r.get('link') or '').strip()
    source=str(r.get('source') or (urlparse(url).netloc.replace('www.','') if url else 'web'))
    if not title and not body:return None
    return {'title':title or 'Untitled','body':body,'source':source,'url':url}

def _extract_candidates(result):
    """Understands the actual falcon_websearch.WebResults object plus legacy shapes."""
    if result is None:return []
    if isinstance(result,list):return result
    if isinstance(result,dict):
        for key in ('results','items','sources','data','pages'):
            if isinstance(result.get(key),list):return result[key]
        return [result] if any(k in result for k in ('title','body','snippet','text','url','href')) else []
    # THE FIX: falcon_websearch.search() returns WebResults(query, items, provider, trace)
    items=getattr(result,'items',None)
    if isinstance(items,list):return items
    try:return list(result)
    except (TypeError,AttributeError):return []

def search_via_websearch(query):
    if not WEBSEARCH_AVAILABLE or not websearch:return None
    try: raw=websearch.search(clean_query(query))
    except Exception as e: log.warning('WebSearch failed: %s',e); return None
    out=[]
    for item in _extract_candidates(raw):
        n=normalize_result(item)
        if n:out.append(n)
    return out or None

def search_web_fallback(query_list):
    if not DDGS_AVAILABLE:return None
    out=[]
    for q in query_list:
        try: rows=DDGS().text(clean_query(q),max_results=4) or []
        except Exception as e: log.warning('DDGS fallback failed: %s',e); continue
        for r in rows:
            n=normalize_result(r)
            if n:out.append(n)
        if len(out)>=MAX_RESULTS:break
    return out[:MAX_RESULTS] or None

def search_sources(query_list):
    out=[]; seen=set()
    for q in query_list:
        batch=search_via_websearch(q) or search_web_fallback([q]) or []
        for item in batch:
            key=item.get('url') or (item.get('title'),item.get('body','')[:100])
            if key in seen:continue
            seen.add(key);out.append(item)
            if len(out)>=MAX_RESULTS:return out
    return out or None

class ResearchAgent:
    def __init__(self,lang='tl'):
        self.lang=lang;self.plan={};self.sources=[];self.confirmed_facts=[];self.unverified=[];self.confidence_score=0.0
    def plan_search_strategy(self,q):
        y=datetime.now().year; low=q.lower(); self.plan={'primary_query':q,'cross_check_queries':[],'note':'Standard research'}
        if re.search(r'\b(latest|current|today|now|ngayon|news|update)\b',low):self.plan.update(cross_check_queries=[q+' official',f'{q} {y}'],note='Checking recency and official/current sources')
        elif re.search(r'\b(who|sino|what|ano|fact)\b',low):self.plan.update(cross_check_queries=[q+' official'],note='Cross-referencing independent sources')
        return self.plan
    def add_source(self,r):
        n=normalize_result(r)
        if not n:return
        n['domain']=urlparse(n['url']).netloc.replace('www.','') if n['url'] else n['source'];self.sources.append(n)
    def cross_check_facts(self):
        domains={s['domain'] for s in self.sources if s.get('domain') not in ('','unknown','web')}
        if len(self.sources)<2:self.confidence_score=CONFIDENCE_LOW;self.unverified.append('Insufficient retrieved evidence');return
        # WebSearch already returns full/snippet evidence. Keep synthesis honest: confidence depends on independent domains.
        if len(domains)>=3:self.confidence_score=CONFIDENCE_HIGH
        elif len(domains)>=2:self.confidence_score=CONFIDENCE_MEDIUM
        else:self.confidence_score=CONFIDENCE_LOW
    def evidence_answer(self,question):
        label='HIGH' if self.confidence_score>=CONFIDENCE_HIGH else ('MEDIUM' if self.confidence_score>=CONFIDENCE_MEDIUM else 'LOW')
        lines=[f'💜 **Web-verified research** — Confidence: **{label}**','']
        for i,s in enumerate(self.sources[:5],1):
            body=(s['body'] or '').strip()
            lines.append(f"**{i}. {s['title']}**")
            if body:lines.append(body[:650])
            if s['url']:lines.append(f"Source: {s['url']}")
            lines.append('')
        return '\n'.join(lines).strip()

def detect_intent(message,reconstructed=None):
    q=clean_query(reconstructed or message); low=q.lower()
    if not q:return {'type':'clarify','search':False}
    if re.search(r'^(hi|hello|kamusta)$',low):return {'type':'greeting','search':False}
    if re.search(r'\b(current|latest|now|ngayon|today|news|weather|price|stock|prime minister|president|ceo)\b',low):return {'type':'research_request','search':True,'query':q}
    return {'type':'chat','search':False}

def web_reply(message,call_ai=None,ai_failed_check=None,system_prompt=None,brain_down=False,history=None):
    if not ENABLED:return None
    intent=detect_intent(message)
    if not intent['search']:return None
    query=intent['query'];agent=ResearchAgent('en');plan=agent.plan_search_strategy(query)
    sources=search_sources([plan['primary_query']]+plan['cross_check_queries'])
    if not sources:return None
    for x in sources:agent.add_source(x)
    agent.cross_check_facts()
    # Preferred synthesis: use the main brain only if available. If absent, provide structured evidence, not failure.
    if call_ai:
        try:
            evidence='\n\n'.join(f"[{i}] {s['title']}\n{s['body']}\nURL: {s['url']}" for i,s in enumerate(agent.sources[:6],1))
            msgs=[{'role':'system','content':(system_prompt or '')+'\nUse ONLY the supplied current web evidence for current facts. Answer naturally, cite [1], [2]. If evidence is insufficient, say so.'}]
            msgs+=(history or [])[-4:];msgs.append({'role':'user','content':f'Question: {query}\n\nCurrent web evidence:\n{evidence}'})
            ai=call_ai(msgs)
            failed=ai_failed_check(ai) if ai_failed_check else not bool(ai)
            if isinstance(ai,str) and ai.strip() and not failed:return ai.strip()
        except Exception as e:log.warning('Main-brain synthesis unavailable: %s',e)
    return agent.evidence_answer(query)

def self_test():
    class WR:
        def __init__(self):
            self.items=[{'title':'Japan PM','url':'https://example.jp/a','snippet':'Current prime minister evidence','text':''}]
            self.ok=True;self.provider='test';self.trace=[]
    assert len(_extract_candidates(WR()))==1
    n=normalize_result(_extract_candidates(WR())[0]);assert n['body']=='Current prime minister evidence'
    return True

__all__=['ENABLED','WEBSEARCH_AVAILABLE','SEARCH_AVAILABLE','web_reply','reply_is_unsure','search_sources','ResearchAgent','self_test','_extract_candidates','normalize_result']
if __name__=='__main__':print('self_test:','PASS' if self_test() else 'FAIL')
