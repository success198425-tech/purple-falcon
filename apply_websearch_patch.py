#!/usr/bin/env python3
"""
Integrates live web search into falcon_ultimate.py automatically.

Usage (put this file + falcon_websearch.py next to falcon_ultimate.py):
    python apply_websearch_patch.py                 # patches ./falcon_ultimate.py
    python apply_websearch_patch.py path/to/file.py

Safe by design: makes a .bak backup first, checks every anchor matches exactly once,
verifies the patched file compiles, and only then writes. Running it twice does nothing.
"""
import os, re, shutil, sys

target = sys.argv[1] if len(sys.argv) > 1 else "falcon_ultimate.py"
if not os.path.isfile(target):
    sys.exit(f"❌ Can't find {target}. Run this from the folder that contains it, or pass the path.")

raw = open(target, "r", encoding="utf-8", newline="").read()
crlf = "\r\n" in raw
src = raw.replace("\r\n", "\n")

if "import falcon_websearch" in src:
    sys.exit("✅ Already patched — nothing to do.")

if not os.path.isfile(os.path.join(os.path.dirname(os.path.abspath(target)), "falcon_websearch.py")):
    print("⚠️  falcon_websearch.py is not next to this file yet — copy it there before launching the app.")

problems = []

def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        problems.append(f"{label}: expected 1 match, found {n}")
        return text
    return text.replace(old, new)

# 1) import + status line ------------------------------------------------------
src = replace_once(src,
'''    skills, SKILLS_STATUS = None, "⚠️ falcon_skills.py not found next to this script"
''',
'''    skills, SKILLS_STATUS = None, "⚠️ falcon_skills.py not found next to this script"

# ==================================================
# 🌐 LIVE WEB SEARCH  (falcon_websearch.py sits next to this script)
# ==================================================
try:
    import falcon_websearch as websearch
    WEB_STATUS = "✅ live web search" if websearch.ENABLED else "◻ off (PF_WEBSEARCH=0)"
except ImportError:
    websearch, WEB_STATUS = None, "⚠️ falcon_websearch.py not found next to this script"
''', "import block")

src = replace_once(src,
'''print(f"   Live skills:   {SKILLS_STATUS}")
''',
'''print(f"   Live skills:   {SKILLS_STATUS}")
print(f"   Web search:    {WEB_STATUS}")
''', "status print")

# 2) helper above chat_reply ---------------------------------------------------
src = replace_once(src,
'''def chat_reply(message, paths, request=None):
''',
'''def web_answer(message, request=None, use_ai=True):
    """Search the web, then answer from the sources (AI-written if possible, plain summary if not)."""
    if not websearch or not websearch.ENABLED:
        return None
    try:
        res = websearch.search(message)
    except Exception as e:
        print(f"⚠️ (kept out of chat) web search crashed — {e.__class__.__name__}: {e}")
        return None
    if not res.ok:
        return None
    if use_ai:
        reply = call_ai(websearch.grounded_messages(message, res, get_system_prompt()))
        if not ai_failed(reply):
            return f"{reply.strip()}\\n\\n{websearch.sources_footer(res)}"
    return websearch.compose(res)

def chat_reply(message, paths, request=None):
''', "helper")

# 3) web_ok flag + proactive search --------------------------------------------
src = replace_once(src,
'''    live_ok = bool(skills) and not paths and bool(message) and not coding_request
''',
'''    live_ok = bool(skills) and not paths and bool(message) and not coding_request
    web_ok = bool(websearch) and websearch.ENABLED and not paths and bool(message) and not coding_request
''', "web_ok flag")

src = replace_once(src,
'''    # 2) ordinary conversation
''',
'''    # 1b) needs fresh / verifiable info (or the user said "search…") → answer from the live web
    if web_ok and websearch.should_search(message):
        ans = web_answer(message, request)
        if ans:
            return ans, []
    # 2) ordinary conversation
''', "proactive search")

# 4) fallbacks around the AI reply ---------------------------------------------
src = replace_once(src,
'''    if reply == CHAT_PROVIDER_FALLBACK:
        local_reply = offline_reasoning_reply(message)
        return (local_reply or reply), []
    if not ai_failed(reply):
        return reply, []
''',
'''    if reply == CHAT_PROVIDER_FALLBACK:
        if web_ok:                                   # every AI provider is down → answer from the web
            ans = web_answer(message, request, use_ai=False)
            if ans:
                return ans, []
        local_reply = offline_reasoning_reply(message)
        return (local_reply or reply), []
    if not ai_failed(reply):
        if web_ok and websearch.reply_is_unsure(reply):   # the model admits it doesn't know → check the web
            ans = web_answer(message, request)
            if ans:
                return ans, []
        return reply, []
    if web_ok:                                       # AI returned an error string → web before other fallbacks
        ans = web_answer(message, request, use_ai=False)
        if ans:
            return ans, []
''', "AI reply fallbacks")

# 5) bottom of file: launch code must live inside `if __name__ == "__main__":` --
marker = '\nPUBLIC_HOST = os.getenv("PF_PUBLIC_HOST", "127.0.0.1")'
if src.count(marker) == 1:
    head, tail = src.split(marker)
    tail = marker + tail
    lines = tail.split("\n")
    lines = [("    " + l if l.strip() else l) for l in lines]
    src = head + "\n".join(lines).rstrip() + "\n"
else:
    print("ℹ️  Skipped the launch-indent fix (already indented or not found).")

if problems:
    sys.exit("❌ Nothing was changed. Your file differs from what I expected:\n  - " + "\n  - ".join(problems))

try:
    compile(src, target, "exec")
except SyntaxError as e:
    sys.exit(f"❌ Patched file failed the syntax check (line {e.lineno}: {e.msg}). Nothing was changed.")

shutil.copy2(target, target + ".bak")
with open(target, "w", encoding="utf-8", newline="") as f:
    f.write(src.replace("\n", "\r\n") if crlf else src)
print(f"✅ Web search integrated into {target}  (backup: {target}.bak)")
print("   Next: pip install ddgs   (optional keys: TAVILY_API_KEY / BRAVE_API_KEY / SERPER_API_KEY in .env)")
print("   Then restart:  python falcon_ultimate.py")
