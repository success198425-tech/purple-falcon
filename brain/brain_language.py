import re

def detect_language(text:str)->str:
    low=(text or '').lower(); words=set(re.findall(r'[a-z]+',low))
    if len(words & {'boleh','macam','saham','pasaran','anda','saya'})>=2:return 'ms'
    if len(words & {'ano','paano','bakit','sige','pwede','naman','alin','yung','mga','gusto','nga','pa'})>=2 or re.search(r'\b(?:po|sige|pwede|paano|ano|pa-check|pacheck|nga)\b',low):return 'tl'
    return 'en'

def say(lang,en,tl,ms=None):return tl if lang=='tl' else (ms if lang=='ms' and ms else en)
