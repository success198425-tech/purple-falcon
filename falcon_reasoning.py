# ==================================================
# Purple Falcon Local Brain v2.0
# Evidence reasoning + relevance-gated persistent local learning
# ==================================================
import os, re, json, time, tempfile, hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

BRAIN_VERSION='2.0.0'
KNOWLEDGE_FILE=os.getenv('PF_LOCAL_BRAIN_FILE','purple_falcon_local_brain.json')
MIN_RELEVANCE=float(os.getenv('PF_LOCAL_RELEVANCE','0.42'))
AUTO_CANDIDATES=os.getenv('PF_LOCAL_AUTO_CANDIDATES','1').lower() not in ('0','false','no','off')

@dataclass
class ReasoningLayer:
    name:str; confidence:float; evidence:str; applicable:bool=True

_STOP={'the','a','an','is','are','was','were','of','to','for','and','or','in','on','at','what','who','how','my','your','this','that','ang','ng','sa','ay','ano','sino','paano','ba','po'}
_FRESH=re.compile(r'\b(?:current|latest|today|now|ngayon|recent|news|weather|price|stock|score|schedule|election|president|prime minister|ceo)\b',re.I)

def _tokens(text):
    return {w for w in re.findall(r'\b[a-z0-9]{3,}\b',(text or '').lower()) if w not in _STOP}

def _load():
    default={'version':BRAIN_VERSION,'verified':[],'candidates':[],'memories':[]}
    try:
        if os.path.exists(KNOWLEDGE_FILE):
            with open(KNOWLEDGE_FILE,encoding='utf-8') as f:d=json.load(f)
            if isinstance(d,dict):
                for k,v in default.items():d.setdefault(k,v)
                return d
    except Exception as e: print(f'Local Brain read warning: {e}')
    return default

def _save(db):
    try:
        folder=os.path.dirname(os.path.abspath(KNOWLEDGE_FILE)) or '.';os.makedirs(folder,exist_ok=True)
        with tempfile.NamedTemporaryFile('w',dir=folder,suffix='.tmp',delete=False,encoding='utf-8') as f:
            json.dump(db,f,ensure_ascii=False,indent=2);tmp=f.name
        os.replace(tmp,KNOWLEDGE_FILE);return True
    except Exception as e: print(f'Local Brain save warning: {e}');return False

def _id(content,kind='knowledge'):
    return hashlib.sha256((kind+'|'+content.strip().lower()).encode()).hexdigest()[:16]

def relevance_score(query,item):
    qt=_tokens(query); content=(item.get('content') or '')+' '+(item.get('title') or '')+' '+ ' '.join(item.get('tags') or [])
    kt=_tokens(content)
    if not qt or not kt:return 0.0
    overlap=len(qt & kt); coverage=overlap/max(len(qt),1); precision=overlap/max(len(kt),1)
    phrase=0.18 if (query or '').lower().strip() in content.lower() else 0
    return min(1.0,0.72*coverage+0.28*precision+phrase)

def retrieve_local(query,limit=5,min_score=MIN_RELEVANCE,include_candidates=False):
    # Current-world questions never accept persistent local facts as authoritative current truth.
    if _FRESH.search(query or ''):return []
    db=_load(); pools=list(db['verified'])+list(db['memories'])
    if include_candidates:pools+=list(db['candidates'])
    ranked=[]
    for item in pools:
        score=relevance_score(query,item)
        if score>=min_score:ranked.append((score,item))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return [{'score':round(s,3),**i} for s,i in ranked[:limit]]

def learn(content,source='user',verified=True,tags=None,title=''):
    content=(content or '').strip()
    if not content:return {'ok':False,'reason':'empty'}
    db=_load(); kind='verified' if verified else 'candidate'; target=db[kind]
    iid=_id(content,kind)
    for x in db['verified']+db['candidates']:
        if x.get('id')==iid or x.get('content','').strip().lower()==content.lower():return {'ok':True,'duplicate':True,'item':x}
    row={'id':iid,'title':title,'content':content,'source':source,'verified':verified,'confidence':1.0 if verified else 0.5,'tags':tags or [],'created_at':datetime.now(timezone.utc).isoformat(),'updated_at':datetime.now(timezone.utc).isoformat(),'uses':0}
    target.append(row);_save(db);return {'ok':True,'duplicate':False,'item':row}

def remember(content,tags=None):
    content=(content or '').strip();db=_load();iid=_id(content,'memory')
    for x in db['memories']:
        if x.get('content','').lower()==content.lower():return {'ok':True,'duplicate':True,'item':x}
    row={'id':iid,'content':content,'source':'user_memory','verified':True,'confidence':1.0,'tags':tags or [],'created_at':datetime.now(timezone.utc).isoformat(),'uses':0};db['memories'].append(row);_save(db);return {'ok':True,'duplicate':False,'item':row}

def forget(term):
    db=_load();term=(term or '').strip().lower();removed=[]
    for bucket in ('verified','candidates','memories'):
        keep=[]
        for x in db[bucket]:
            if term and (term==x.get('id','').lower() or term in x.get('content','').lower()):removed.append(x)
            else:keep.append(x)
        db[bucket]=keep
    _save(db);return {'ok':True,'removed':len(removed)}

def knowledge_status():
    db=_load();return {'verified':len(db['verified']),'candidates':len(db['candidates']),'memories':len(db['memories']),'file':KNOWLEDGE_FILE,'threshold':MIN_RELEVANCE}

def propose_candidate(content,source='conversation',tags=None):
    if not AUTO_CANDIDATES:return {'ok':False,'reason':'disabled'}
    # candidates are never retrieved by default and need promotion/approval
    return learn(content,source=source,verified=False,tags=tags)

def promote_candidate(item_id):
    db=_load()
    for i,x in enumerate(db['candidates']):
        if x.get('id')==item_id:
            row=db['candidates'].pop(i);row['verified']=True;row['confidence']=1.0;row['updated_at']=datetime.now(timezone.utc).isoformat();db['verified'].append(row);_save(db);return {'ok':True,'item':row}
    return {'ok':False,'reason':'not_found'}

def local_answer(question):
    hits=retrieve_local(question)
    if not hits:return None
    top=hits[0]
    return {'answer':top.get('content',''),'confidence':top['score'],'source':top.get('source','local'),'id':top.get('id'),'hits':hits}

# Existing DOLA-style evidence reasoning retained and hardened.
def analyze_source_alignment(evidence_list):
    if len(evidence_list)<2:return ReasoningLayer('source_alignment',.5,'Only one source available',False)
    domains={getattr(e,'source','unknown') for e in evidence_list};return ReasoningLayer('source_alignment',min(.95,.55+.1*len(domains)),f'{len(evidence_list)} evidence items across {len(domains)} source labels')
def analyze_temporal_consistency(evidence_list):
    if not evidence_list:return ReasoningLayer('temporal_consistency',.5,'No evidence',False)
    now=time.time();ages=[max(0,(now-getattr(e,'fetched',now))/3600) for e in evidence_list];avg=sum(ages)/len(ages)
    return ReasoningLayer('temporal_consistency',.95 if avg<1 else .85 if avg<24 else .65 if avg<168 else .4,f'Average evidence age {avg:.1f} hours')
def analyze_specificity(question,evidence_list):
    if not evidence_list:return ReasoningLayer('specificity',.5,'No evidence',False)
    q=_tokens(question);scores=[]
    for e in evidence_list:
        et=_tokens(getattr(e,'text',''));scores.append(len(q&et)/max(len(q),1))
    v=sum(scores)/len(scores);return ReasoningLayer('specificity',min(.95,.45+.5*v),f'Query/evidence lexical coverage {v:.0%}')
def analyze_contradiction_risk(evidence_list):
    if len(evidence_list)<2:return ReasoningLayer('contradiction_risk',.8,'Single source',False)
    neg={'not','never','no','false','wrong','denied','rejected'};count=0
    for i,a in enumerate(evidence_list):
        aw=set(getattr(a,'text','').lower().split())
        for b in evidence_list[i+1:]:
            bw=set(getattr(b,'text','').lower().split())
            if bool(aw&neg)!=bool(bw&neg):count+=1
    return ReasoningLayer('contradiction_risk',max(.4,1-.2*count),f'{count} potential polarity conflict(s)')
def fallback_reasoning(question,evidence_list,max_layers=4):
    layers=[analyze_source_alignment(evidence_list),analyze_temporal_consistency(evidence_list),analyze_specificity(question,evidence_list),analyze_contradiction_risk(evidence_list)]
    active=[x for x in layers if x.applicable][:max_layers];confidence=sum(x.confidence for x in active)/len(active) if active else .5
    explanation=f'**Reasoning ({confidence*100:.0f}% confidence)**:\n'+''.join(f"• {'✓' if x.confidence>.7 else '◐' if x.confidence>.4 else '✗'} {x.name}: {x.evidence}\n" for x in active)
    return confidence,explanation,active

def compose_with_reasoning(res,intro=None,show_reasoning=True):
    if not getattr(res,'evidence',None):
        try:
            from falcon_skills import friendly_fallback;return friendly_fallback(res.question)
        except Exception:return None
    from falcon_skills import _GENERIC_SKILLS,sources_footer
    specific=[e for e in res.evidence if e.skill not in _GENERIC_SKILLS];chosen=specific[:2] if specific else res.evidence[:3]
    L=[intro or "🔎 Here's what I found live:"]
    for e in chosen:L += ['',f'**{e.title}**' if e.title else '',e.text]
    if show_reasoning and len(chosen)>1:
        confidence,text,_=fallback_reasoning(res.question,chosen);L+=['',text]
        if confidence<.6:L.append(f'⚠️ **Confidence is {confidence*100:.0f}%** — verify with another independent source')
    foot=sources_footer(type(res)(res.question,chosen))
    if foot:L+=['',foot]
    return '\n'.join(x for x in L if x is not None)

def handle_local_command(message):
    m=(message or '').strip()
    x=re.match(r'^/(learn|remember|forget|knowledge)\b\s*:?[ ]*(.*)$',m,re.I)
    if not x:return None
    cmd,arg=x.group(1).lower(),x.group(2).strip()
    if cmd=='learn':
        r=learn(arg,source='user',verified=True);return '🧠 Knowledge already exists.' if r.get('duplicate') else '🧠 Knowledge learned and verified from user instruction.'
    if cmd=='remember':
        r=remember(arg);return '🧠 Memory already exists.' if r.get('duplicate') else '🧠 Memory saved.'
    if cmd=='forget':
        r=forget(arg);return f"🧠 Removed {r['removed']} matching local item(s)."
    st=knowledge_status();return f"🧠 Local Brain — verified: {st['verified']}, candidates: {st['candidates']}, memories: {st['memories']}, relevance threshold: {st['threshold']:.2f}"

def self_test():
    assert relevance_score('Purple Falcon local first',{'content':'Purple Falcon uses a local first architecture','tags':[]})>MIN_RELEVANCE
    assert relevance_score('Tesla stock now',{'content':'Philippine Tech Vision','tags':[]})<MIN_RELEVANCE
    assert retrieve_local('Tesla stock now')==[] # freshness gate
    return True

__all__=['ReasoningLayer','fallback_reasoning','compose_with_reasoning','relevance_score','retrieve_local','learn','remember','forget','knowledge_status','propose_candidate','promote_candidate','local_answer','handle_local_command','self_test']
if __name__=='__main__':print('self_test:','PASS' if self_test() else 'FAIL')
