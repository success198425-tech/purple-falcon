import re

def reconstruct(message,state):
    msg=(message or '').strip()
    m=re.match(r'^\s*(?:compare them|compare those|which one stronger|which is stronger)\s*[?!.]*$',msg,re.I)
    if m and len(state.entities)>=2:return 'Compare '+' and '.join(state.entities[-2:])+' stocks'
    return msg
