# Purple Falcon WebReason v14.0 - Verified Market Quote Mode
import os, re, json, logging, tempfile, time
import requests
from html import unescape
from datetime import datetime, timezone
from urllib.parse import urlparse

APP_NAME='Purple Falcon PH'; VERSION='16.8.3'
ENABLED=os.getenv('PF_WEBREASON','1').strip().lower() not in ('0','false','no','off')
MEMORY_FILE=os.getenv('PF_MEMORY_FILE','purple_falcon_memory.json')
MAX_RESULTS=10; MIN_SOURCES=2
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
    v=re.sub(r'\s+',' ',text.strip());return re.sub(r'\s*[?!.:;]+\s*$','',v)

def reply_is_unsure(text):
    return not isinstance(text,str) or not text.strip() or bool(re.search(r"i don't know|not sure|cannot find|no information|no results|quota|rate limit|forbidden",text,re.I))

def normalize_result(r):
    if not isinstance(r,dict):return None
    title=str(r.get('title') or r.get('name') or '').strip()
    body=str(r.get('body') or r.get('snippet') or r.get('text') or r.get('extract') or r.get('content') or '').strip()[:3000]
    url=str(r.get('url') or r.get('href') or r.get('link') or '').strip()
    source=str(r.get('source') or (urlparse(url).netloc.replace('www.','') if url else 'web'))
    if not title and not body:return None
    return {'title':title or 'Untitled','body':body,'source':source,'url':url}

def _extract_candidates(result):
    if result is None:return []
    if isinstance(result,list):return result
    if isinstance(result,dict):
        for k in ('results','items','sources','data','pages'):
            if isinstance(result.get(k),list):return result[k]
        return [result]
    items=getattr(result,'items',None)
    return items if isinstance(items,list) else []

def search_via_websearch(q):
    if not WEBSEARCH_AVAILABLE:return []
    try:raw=websearch.search(q)
    except Exception as e:log.warning('WebSearch failed: %s',e);return []
    return [n for n in (normalize_result(x) for x in _extract_candidates(raw)) if n]

def search_fallback(q):
    if not DDGS_AVAILABLE:return []
    try:rows=DDGS().text(q,max_results=6) or []
    except Exception as e:log.warning('DDGS failed: %s',e);return []
    return [n for n in (normalize_result(x) for x in rows) if n]

_MARKET_RE=re.compile(r'\b(?:stock|stocks|share|shares|price|quote|market|trading|ticker|index|indices|nasdaq|nyse|pse|psei|after[- ]hours|pre[- ]market|overnight)\b',re.I)
_FRESH_RE=re.compile(r'\b(?:current|latest|today|now|ngayon|recent|updated?|as of)\b',re.I)
_WEATHER_RE=re.compile(r'\b(?:weather|forecast|temperature|rain|storm|typhoon)\b',re.I)
_NEWS_RE=re.compile(r'\b(?:news|balita|headline|breaking)\b',re.I)
_OFFICE_RE=re.compile(r'\b(?:president|prime\s+minister|pm|ceo|mayor|governor|minister|leader)\b',re.I)
_TESLA_RE=re.compile(r'\b(?:tesla|tsla)\b',re.I)
_STOCK_ALIASES={
 'tesla':'TSLA','tsla':'TSLA',
 'apple':'AAPL','aapl':'AAPL',
 'microsoft':'MSFT','msft':'MSFT',
 'nvidia':'NVDA','nvda':'NVDA',
 'amazon':'AMZN','amzn':'AMZN',
 'alphabet':'GOOGL','google':'GOOGL','googl':'GOOGL','goog':'GOOG',
 'meta':'META','facebook':'META',
 'netflix':'NFLX','nflx':'NFLX',
 'amd':'AMD','advanced micro devices':'AMD',
 'intel':'INTC','intc':'INTC',
 'broadcom':'AVGO','avgo':'AVGO',
 'oracle':'ORCL','orcl':'ORCL',
 'salesforce':'CRM','crm':'CRM',
 'palantir':'PLTR','pltr':'PLTR',
 'coinbase':'COIN','coin':'COIN',
 'berkshire hathaway':'BRK-B','berkshire':'BRK-B','brk-b':'BRK-B','brk.b':'BRK-B',
 'jpmorgan':'JPM','jp morgan':'JPM','jpm':'JPM',
 'visa':'V','mastercard':'MA',
 'walmart':'WMT','wmt':'WMT',
 'disney':'DIS','dis':'DIS',
 'boeing':'BA','ba':'BA',
 'coca cola':'KO','coca-cola':'KO',
 'nike':'NKE','nke':'NKE',
 'spotify':'SPOT','spot':'SPOT',
 'uber':'UBER','airbnb':'ABNB',
 'shopify':'SHOP','shop':'SHOP',
 'spy':'SPY','s&p 500 etf':'SPY',
 'qqq':'QQQ','nasdaq 100 etf':'QQQ',
 'dia':'DIA','dow etf':'DIA',
}
_PRICE_RE=re.compile(r'(?<!\w)\$\s*(\d{1,5}(?:\.\d{1,4})?)\b')
_PCT_RE=re.compile(r'([+-]?\d+(?:\.\d+)?)\s*%')
_VOLUME_RE=re.compile(r'\b(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*[KMB])\s*(?:shares?\s*)?(?:volume)?\b',re.I)
_DATE_RE=re.compile(r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+20\d{2}\b',re.I)
_TIME_RE=re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\s*(?:EDT|EST|ET|UTC|GMT)?\b',re.I)
_FINANCE_DOMAINS=('finance.yahoo.com','nasdaq.com','reuters.com','bloomberg.com','marketwatch.com','cnbc.com','investing.com','google.com')

_LOCAL_MARKET_RE=re.compile(r'\b(?:local|domestic|home)\b.*\b(?:stock|stocks|market|shares?|index|update)\b|\b(?:stock|stocks|market|shares?|index)\b.*\b(?:local|domestic|home)\b',re.I)
_MARKET_CONTEXTS={
 'MY':{'index':'^KLSE','currency':'MYR','aliases':('malaysia','malaysian','bursa','bursa malaysia','klse','fbm klci','klci','kuala lumpur')},
 'PH':{'index':'PSEI.PS','currency':'PHP','aliases':('philippines','philippine','pse','psei','manila')},
 'SG':{'index':'^STI','currency':'SGD','aliases':('singapore','sgx','sti','straits times')},
 'JP':{'index':'^N225','currency':'JPY','aliases':('japan','tokyo','nikkei','nikkei 225')},
 'HK':{'index':'^HSI','currency':'HKD','aliases':('hong kong','hkex','hang seng','hsi')},
 'AU':{'index':'^AXJO','currency':'AUD','aliases':('australia','asx','asx 200')},
 'IN':{'index':'^NSEI','currency':'INR','aliases':('india','nse','nifty','nifty 50')},
 'UK':{'index':'^FTSE','currency':'GBP','aliases':('united kingdom','uk','london','ftse','ftse 100')},
 'US':{'index':'^GSPC','currency':'USD','aliases':('united states','usa','us market','s&p 500','sp500')},
}
_INDEX_SYMBOLS={meta['index'] for meta in _MARKET_CONTEXTS.values()}
_DEFAULT_LOCAL_MARKET=os.getenv('PF_LOCAL_MARKET','MY').strip().upper() or 'MY'

def _explicit_market_region(query):
    low=clean_query(query).lower()
    for code,meta in _MARKET_CONTEXTS.items():
        if any(re.search(r'(?<![a-z0-9])'+re.escape(a)+r'(?![a-z0-9])',low) for a in meta['aliases']):return code
    return None

def _local_market_region(query):
    explicit=_explicit_market_region(query)
    if explicit:return explicit
    if _LOCAL_MARKET_RE.search(clean_query(query)):
        return _DEFAULT_LOCAL_MARKET if _DEFAULT_LOCAL_MARKET in _MARKET_CONTEXTS else 'MY'
    return None

def _market_index_from_query(query):
    q=clean_query(query);low=q.lower()
    # Named companies/tickers must beat broad local-market overview routing.
    company_hints=('bdo','bpi','jollibee','ayala','acen','aboitiz','pldt','globe','meralco','ictsi','san miguel','puregold','metrobank','unionbank','maynilad','maybank','public bank','tenaga','cimb','maxis','petronas','airasia')
    if any(re.search(r'(?<![a-z0-9])'+re.escape(x)+r'(?![a-z0-9])',low) for x in company_hints):return None
    if re.search(r'\b[A-Z0-9]{1,12}(?:\.[A-Z]{1,4}|\^[A-Z0-9]+)\b',q):return None
    region=_local_market_region(q)
    if region:return _MARKET_CONTEXTS[region]['index']
    return None

def _is_market_index(symbol):return (symbol or '').upper() in {x.upper() for x in _INDEX_SYMBOLS}

_MARKET_TABLE_RE=re.compile(r'\b(?:table|tabulate|list|compare|comparison|watchlist|basket|top|other|several|multiple)\b',re.I)

def _market_table_request(query):
    q=clean_query(query);low=q.lower()
    if not _MARKET_TABLE_RE.search(q):return None
    region=_explicit_market_region(q) or (_DEFAULT_LOCAL_MARKET if re.search(r'\blocal\b',q,re.I) else None)
    if re.search(r'\b(?:ph|philippines|philippine|pse)\b',q,re.I):region='PH'
    if re.search(r'\b(?:my|malaysia|malaysian|bursa|klse)\b',q,re.I):region='MY'
    return {'intent':'market_table','region':region or _DEFAULT_LOCAL_MARKET}

def _dynamic_market_intent(query):
    q=clean_query(query)
    table=_market_table_request(q)
    if table:return table
    idx=_market_index_from_query(q)
    if idx:
        region=next((code for code,m in _MARKET_CONTEXTS.items() if m['index']==idx),None)
        return {'intent':'market','symbol':idx,'kind':'index','region':region}
    if _MARKET_RE.search(q):
        return {'intent':'market','symbol':None,'kind':'security','region':_explicit_market_region(q)}
    return None

# Optional entity state for well-known private/unlisted names. This avoids treating a company name as a ticker.
_PRIVATE_MARKET_ENTITIES={
 'gcash':{'company':'GCash / Mynt','region':'PH','kind':'private_or_unlisted'},
 'mynt':{'company':'Globe Fintech Innovations (Mynt)','region':'PH','kind':'private_or_unlisted'},
}
def _private_market_entity(query):
    low=clean_query(query).lower()
    for key,meta in _PRIVATE_MARKET_ENTITIES.items():
        if re.search(r'(?<![a-z0-9])'+re.escape(key)+r'(?![a-z0-9])',low):return dict(meta,key=key)
    return None

def _private_market_reply(query):
    ent=_private_market_entity(query)
    if not ent:return None
    return (f"💜 **{ent['company']} market check**\n\n"
            "I could not resolve this name to a verified publicly traded ticker in the market resolver, so I won't invent a live share price.\n\n"
            "I can research its current IPO/listing status, or you can ask for a related listed security or local market benchmark.")

def classify_web_intent(q):
    if _dynamic_market_intent(q):return 'market'
    if _MARKET_RE.search(q or ''):return 'market'
    if _WEATHER_RE.search(q or ''):return 'weather'
    if _NEWS_RE.search(q or ''):return 'news'
    if _OFFICE_RE.search(q or ''):return 'officeholder'
    return 'general'

def analyze_prompt(q):
    q=clean_query(q);intent=classify_web_intent(q)
    return {'query':q,'intent':intent,'fresh':bool(_FRESH_RE.search(q) or intent in {'market','weather','news','officeholder'}) }

_EXCHANGE_ALIASES={
 'us':{'suffix':'','currency':'USD','names':('nasdaq','nyse','united states','usa','us')},
 'uk':{'suffix':'.L','currency':'GBP','names':('london','lse','united kingdom','uk')},
 'jp':{'suffix':'.T','currency':'JPY','names':('tokyo','tse','japan')},
 'hk':{'suffix':'.HK','currency':'HKD','names':('hong kong','hkex','hk')},
 'au':{'suffix':'.AX','currency':'AUD','names':('australia','asx')},
 'ca':{'suffix':'.TO','currency':'CAD','names':('canada','toronto','tsx')},
 'de':{'suffix':'.DE','currency':'EUR','names':('germany','xetra','frankfurt')},
 'fr':{'suffix':'.PA','currency':'EUR','names':('france','paris','euronext paris')},
 'nl':{'suffix':'.AS','currency':'EUR','names':('netherlands','amsterdam','euronext amsterdam')},
 'ch':{'suffix':'.SW','currency':'CHF','names':('switzerland','six','swiss')},
 'in-nse':{'suffix':'.NS','currency':'INR','names':('india','nse','national stock exchange india')},
 'in-bse':{'suffix':'.BO','currency':'INR','names':('bse','bombay stock exchange')},
 'kr':{'suffix':'.KS','currency':'KRW','names':('south korea','korea','krx')},
 'sg':{'suffix':'.SI','currency':'SGD','names':('singapore','sgx')},
 'my':{'suffix':'.KL','currency':'MYR','names':('malaysia','bursa malaysia','bursa','klse')},
 'ph':{'suffix':'.PS','currency':'PHP','names':('philippines','philippine','pse','philippine stock exchange')},
}
_INTERNATIONAL_ALIASES={
 'toyota':{'jp':'7203.T'},'sony':{'jp':'6758.T'},'softbank group':{'jp':'9984.T'},
 'tencent':{'hk':'0700.HK'},'alibaba':{'hk':'9988.HK'},'meituan':{'hk':'3690.HK'},
 'bhp':{'au':'BHP.AX'},'commonwealth bank':{'au':'CBA.AX'},'cba':{'au':'CBA.AX'},'csl':{'au':'CSL.AX'},
 'royal bank of canada':{'ca':'RY.TO'},'rbc':{'ca':'RY.TO'},'td bank':{'ca':'TD.TO'},
 'sap':{'de':'SAP.DE'},'bmw':{'de':'BMW.DE'},'mercedes benz':{'de':'MBG.DE'},
 'loreal':{'fr':'OR.PA'},"l'oreal":{'fr':'OR.PA'},'lvmh':{'fr':'MC.PA'},'airbus':{'fr':'AIR.PA'},
 'asml':{'nl':'ASML.AS'},
 'nestle':{'ch':'NESN.SW'},'novartis':{'ch':'NOVN.SW'},
 'reliance':{'in-nse':'RELIANCE.NS'},'tcs':{'in-nse':'TCS.NS'},'infosys':{'in-nse':'INFY.NS'},
 'samsung electronics':{'kr':'005930.KS'},'samsung':{'kr':'005930.KS'},
 'dbs':{'sg':'D05.SI'},'ocbc':{'sg':'O39.SI'},'uob':{'sg':'U11.SI'},
 'maybank':{'my':'1155.KL'},'public bank':{'my':'1295.KL'},'tenaga nasional':{'my':'5347.KL'},'tenaga':{'my':'5347.KL'},
 'vodafone':{'uk':'VOD.L'},'shell':{'uk':'SHEL.L'},'hsbc':{'uk':'HSBA.L'},
}
_KNOWN_SUFFIXES=('.L','.T','.HK','.AX','.TO','.DE','.PA','.AS','.SW','.NS','.BO','.KS','.SI','.KL','.PS')
_PSE_SUFFIX='.PS'
_PSE_DIRECTORY_URL='https://edge.pse.com.ph/companyDirectory/form.do'
_PSE_CACHE_FILE=os.getenv('PF_PSE_CATALOG_FILE','purple_falcon_pse_catalog.json')
_PSE_CACHE_SECONDS=int(os.getenv('PF_PSE_CATALOG_TTL','86400'))
_PSE_ID_CACHE_FILE=os.getenv('PF_PSE_ID_CACHE_FILE','purple_falcon_pse_company_ids.json')
_PSE_ID_CACHE_SECONDS=int(os.getenv('PF_PSE_ID_CACHE_TTL','604800'))
_PSE_EDGE_SEARCH_URL='https://edge.pse.com.ph/companyDirectory/search.ax'

def _load_pse_id_cache():
    try:
        if not os.path.exists(_PSE_ID_CACHE_FILE):return {}
        with open(_PSE_ID_CACHE_FILE,encoding='utf-8') as f:data=json.load(f)
        if not isinstance(data,dict):return {}
        if time.time()-float(data.get('fetched_at',0))>_PSE_ID_CACHE_SECONDS:return {}
        return data.get('ids') if isinstance(data.get('ids'),dict) else {}
    except Exception:return {}

def _save_pse_id_cache(ids):
    try:
        folder=os.path.dirname(os.path.abspath(_PSE_ID_CACHE_FILE)) or '.';os.makedirs(folder,exist_ok=True)
        payload={'fetched_at':time.time(),'ids':ids}
        with tempfile.NamedTemporaryFile('w',dir=folder,suffix='.tmp',delete=False,encoding='utf-8') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2);tmp=f.name
        os.replace(tmp,_PSE_ID_CACHE_FILE)
    except Exception as e:log.warning('PSE company-id cache save failed: %s',e)

def _parse_pse_company_ids(html):
    """Extract symbol -> cmpy_id from PSE EDGE company-directory/company links."""
    out={}
    rows=re.findall(r'(?is)<tr[^>]*>(.*?)</tr>',html or '')
    for row in rows:
        idm=re.search(r'(?:cmpy_id=|companyId[=:]["\']?)(\d+)',row,re.I)
        if not idm:continue
        text=re.sub(r'(?is)<[^>]+>',' ',row);text=re.sub(r'\s+',' ',unescape(text)).strip()
        # Prefer a known PSE symbol present in the row.
        tokens=re.findall(r'\b[A-Z][A-Z0-9]{0,9}\b',text.upper())
        for tok in tokens:
            if tok in _PSE_BUILTINS:
                out[tok]=idm.group(1);break
    return out

def _refresh_pse_company_ids():
    ids=_load_pse_id_cache()
    if ids:return ids
    # Seed known verified mapping and discover the rest from directory HTML.
    ids={'BDO':'260'}
    try:
        r=requests.get(_PSE_DIRECTORY_URL,headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/16.8.1'},timeout=10)
        if r.status_code==200:ids.update(_parse_pse_company_ids(r.text))
    except Exception as e:log.warning('PSE company-id discovery failed: %s',e)
    _save_pse_id_cache(ids);return ids

def _pse_company_id(symbol):
    base=(symbol or '').upper().removesuffix('.PS')
    return _refresh_pse_company_ids().get(base)

def _pse_edge_quote(symbol):
    base=(symbol or '').upper().removesuffix('.PS');cmpy_id=_pse_company_id(symbol)
    if not base or not cmpy_id:return None
    url=f'https://edge.pse.com.ph/companyPage/stockData.do?cmpy_id={cmpy_id}'
    try:
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/16.8.1'},timeout=9)
        if r.status_code!=200:return None
        text=unescape(re.sub(r'(?is)<[^>]+>',' ',r.text));text=re.sub(r'\s+',' ',text)
        m=re.search(r'Last Traded Price\s*([0-9][0-9,]*(?:\.\d+)?)',text,re.I)
        if not m:return None
        price=float(m.group(1).replace(',',''))
        pm=re.search(r'Previous Close(?: and Date)?\s*([0-9][0-9,]*(?:\.\d+)?)',text,re.I);prev=float(pm.group(1).replace(',','')) if pm else None
        change=price-prev if prev is not None else None;pct=(change/prev*100) if change is not None and prev else None
        dm=re.search(r'As of\s+([A-Z][a-z]{2}\s+\d{1,2},\s+20\d{2})(?:\s+([0-9:]+\s+[AP]M))?',text)
        timestamp=' '.join(x for x in dm.groups() if x) if dm else None
        return {'symbol':base+'.PS','price':price,'session':'PSE official / source-timed','timestamp_utc':timestamp,'currency':'PHP','exchange':'PSE','previous_close':prev,'change':change,'change_percent':pct,'source':'PSE EDGE','source_url':url,'observed_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    except Exception as e:log.warning('PSE EDGE quote failed for %s: %s',symbol,e);return None

_PSE_BUILTINS={
 'BDO':'BDO Unibank, Inc.','BPI':'Bank of the Philippine Islands','AC':'Ayala Corporation','ALI':'Ayala Land, Inc.',
 'ACEN':'ACEN CORPORATION','AEV':'Aboitiz Equity Ventures, Inc.','AP':'Aboitiz Power Corporation','AREIT':'AREIT, Inc.',
 'JFC':'Jollibee Foods Corporation','SM':'SM Investments Corporation','SMPH':'SM Prime Holdings, Inc.','TEL':'PLDT Inc.',
 'GLO':'Globe Telecom, Inc.','MER':'Manila Electric Company','ICT':'International Container Terminal Services, Inc.',
 'SMC':'San Miguel Corporation','PGOLD':'Puregold Price Club, Inc.','MBT':'Metropolitan Bank & Trust Company','UBP':'Union Bank of the Philippines',
 'MYNLD':'Maynilad Water Services, Inc.','LTL':'PNB Holdings Corporation','BLOOM':'Bloomberry Resorts Corporation',
 'AUB':'Asia United Bank Corporation','BNCOM':'Bank of Commerce','AGI':'Alliance Global Group, Inc.','ALLDY':'AllDay Marts, Inc.',
 'ALLHC':'AyalaLand Logistics Holdings Corp.','ALTER':'Alternergy Holdings Corporation','APX':'Apex Mining Co., Inc.','ASLAG':'Raslag Corp.'
}

def _pse_normalize_name(name):
    x=unescape(name or '').lower();x=re.sub(r'[^a-z0-9]+',' ',x);return re.sub(r'\s+',' ',x).strip()

def _load_pse_cache():
    try:
        if not os.path.exists(_PSE_CACHE_FILE):return None
        with open(_PSE_CACHE_FILE,encoding='utf-8') as f:data=json.load(f)
        if not isinstance(data,dict) or not isinstance(data.get('symbols'),dict):return None
        if time.time()-float(data.get('fetched_at',0))>_PSE_CACHE_SECONDS:return None
        return data
    except Exception:return None

def _save_pse_cache(symbols):
    try:
        folder=os.path.dirname(os.path.abspath(_PSE_CACHE_FILE)) or '.';os.makedirs(folder,exist_ok=True)
        payload={'fetched_at':time.time(),'count':len(symbols),'symbols':symbols}
        with tempfile.NamedTemporaryFile('w',dir=folder,suffix='.tmp',delete=False,encoding='utf-8') as f:
            json.dump(payload,f,ensure_ascii=False,indent=2);tmp=f.name
        os.replace(tmp,_PSE_CACHE_FILE)
    except Exception as e:log.warning('PSE cache save failed: %s',e)

def _parse_pse_directory_html(html):
    """Parse PSE EDGE company-directory rows into {PSE_SYMBOL: company_name}."""
    symbols={}
    # The directory exposes company links followed by symbol links. Keep parsing tolerant to markup changes.
    rows=re.findall(r'(?is)<tr[^>]*>(.*?)</tr>',html or '')
    for row in rows:
        cells=[re.sub(r'(?is)<[^>]+>',' ',c) for c in re.findall(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>',row)]
        cells=[re.sub(r'\s+',' ',unescape(c)).strip() for c in cells]
        if len(cells)<2:continue
        company,symbol=cells[0],cells[1].upper().strip()
        if re.fullmatch(r'[A-Z][A-Z0-9]{0,9}',symbol) and company and 'company name' not in company.lower():symbols[symbol]=company
    return symbols

def _fetch_pse_catalog():
    cached=_load_pse_cache()
    if cached:return cached['symbols']
    symbols=dict(_PSE_BUILTINS)
    try:
        r=requests.get(_PSE_DIRECTORY_URL,headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/14.4'},timeout=10)
        if r.status_code==200:
            live=_parse_pse_directory_html(r.text)
            if live:symbols.update(live)
        else:log.warning('PSE directory HTTP %s',r.status_code)
    except Exception as e:log.warning('PSE directory refresh failed: %s',e)
    _save_pse_cache(symbols)
    return symbols

def _pse_context(query):
    return bool(re.search(r'\b(?:pse|philippine stock exchange|philippines|philippine|ph stock|bursa pilipinas)\b',query or '',re.I))

def _pse_symbol_from_query(query):
    q=(query or '').strip();low=_pse_normalize_name(q);catalog=_fetch_pse_catalog()
    # Explicit Yahoo PSE symbol always wins.
    m=re.search(r'\b([A-Z][A-Z0-9]{0,9})\.PS\b',q,re.I)
    if m:return m.group(1).upper()+'.PS'
    # Company-name matching can resolve even without explicit PH context when sufficiently distinctive.
    by_name=sorted((( _pse_normalize_name(name),sym) for sym,name in catalog.items()),key=lambda x:len(x[0]),reverse=True)
    for name,sym in by_name:
        if len(name)>=5 and re.search(r'(?<![a-z0-9])'+re.escape(name)+r'(?![a-z0-9])',low):return sym+'.PS'
    # Common natural short names.
    common={'bdo':'BDO','bpi':'BPI','ayala land':'ALI','ayala corporation':'AC','jollibee':'JFC','sm prime':'SMPH','sm investments':'SM','pldt':'TEL','globe telecom':'GLO','meralco':'MER','ictsi':'ICT','san miguel':'SMC','puregold':'PGOLD','metrobank':'MBT','unionbank':'UBP','maynilad':'MYNLD','acen':'ACEN','aboitiz power':'AP'}
    for name,sym in sorted(common.items(),key=lambda x:len(x[0]),reverse=True):
        if re.search(r'(?<![a-z0-9])'+re.escape(name)+r'(?![a-z0-9])',low):return sym+'.PS'
    # Bare PSE symbols require explicit Philippine/PSE context to avoid C/V/P-style global collisions.
    if _pse_context(q):
        tokens=re.findall(r'\b[A-Za-z][A-Za-z0-9]{0,9}\b',q)
        for token in tokens:
            sym=token.upper()
            if sym in catalog:return sym+'.PS'
    return None

def _exchange_from_query(query):
    low=(query or '').lower()
    hits=[]
    for code,meta in _EXCHANGE_ALIASES.items():
        if any(re.search(r'(?<![a-z0-9])'+re.escape(name)+r'(?![a-z0-9])',low) for name in meta['names']): hits.append(code)
    # NSE wins generic India; BSE only when explicitly stated.
    if 'in-bse' in hits:return 'in-bse'
    if 'in-nse' in hits:return 'in-nse'
    return hits[0] if hits else None

_REGION_BASKETS={
 'PH':['BDO.PS','BPI.PS','JFC.PS','SM.PS','SMPH.PS','ALI.PS','TEL.PS','GLO.PS','MER.PS','ICT.PS','ACEN.PS','AP.PS'],
 'MY':['1155.KL','1295.KL','1023.KL','5347.KL','5225.KL','5183.KL','6012.KL','6033.KL','8869.KL','3816.KL'],
}

def _market_table_symbols(query,limit=10):
    req=_market_table_request(query) or {};region=req.get('region') or _DEFAULT_LOCAL_MARKET
    syms=list(_REGION_BASKETS.get(region,[]))
    return syms[:max(1,min(int(limit or 10),15))]

def _pse_search_quote(symbol):
    base=(symbol or '').upper().removesuffix('.PS')
    if not base:return None
    qs=[f'PSE {base} stock price today',f'{base} PSE Last Traded Price',f'site:stockanalysis.com/quote/pse/{base} {base}']
    for q in qs:
        for item in (search_via_websearch(q) or search_fallback(q)):
            text=' '.join(str(item.get(k) or '') for k in ('title','body'))
            if not re.search(rf'\b{re.escape(base)}\b',text,re.I):continue
            m=re.search(r'Last Traded Price\s*([0-9][0-9,]*(?:\.\d+)?)',text,re.I)
            if m:
                price=float(m.group(1).replace(',',''));pm=re.search(r'Previous Close(?: and Date)?\s*([0-9][0-9,]*(?:\.\d+)?)',text,re.I);prev=float(pm.group(1).replace(',','')) if pm else None
                return {'symbol':base+'.PS','price':price,'currency':'PHP','exchange':'PSE','previous_close':prev,'change':price-prev if prev is not None else None,'change_percent':((price-prev)/prev*100) if prev else None,'session':'PSE source-timed','timestamp_utc':None,'source':item.get('source') or urlparse(item.get('url','')).netloc,'source_url':item.get('url','')}
            m=re.search(r'\b([0-9]{1,5}(?:\.\d{1,4})?)\s+([+\-]?[0-9]{1,5}(?:\.\d{1,4})?)\s*\(([+\-]?[0-9]+(?:\.\d+)?)%\)',text)
            if m:
                price=float(m.group(1));chg=float(m.group(2));pct=float(m.group(3))
                return {'symbol':base+'.PS','price':price,'currency':'PHP','exchange':'PSE','previous_close':price-chg,'change':chg,'change_percent':pct,'session':'Delayed/Last close','timestamp_utc':None,'source':item.get('source') or urlparse(item.get('url','')).netloc,'source_url':item.get('url','')}
    return None

def _stockanalysis_pse_quote(symbol):
    """Secondary PSE provider retained from the successful 8/10 pipeline."""
    base=(symbol or '').upper().removesuffix('.PS')
    if not base:return None
    url=f'https://stockanalysis.com/quote/pse/{base}/'
    try:
        r=requests.get(url,headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/16.8.2','Accept':'text/html,application/xhtml+xml'},timeout=9)
        if r.status_code!=200:return None
        text=unescape(re.sub(r'(?is)<[^>]+>',' ',r.text));text=re.sub(r'\s+',' ',text).strip()
        patterns=[rf'\b{re.escape(base)}\b[^0-9]{{0,120}}([0-9]{{1,5}}(?:\.[0-9]{{1,4}})?)\s+([+\-]?[0-9]{{1,5}}(?:\.[0-9]{{1,4}})?)\s*\(([+\-]?[0-9]+(?:\.[0-9]+)?)%\)',r'At close:\s*[^0-9]{0,40}([0-9]{1,5}(?:\.[0-9]{1,4})?)\s+([+\-]?[0-9]{1,5}(?:\.[0-9]{1,4})?)\s*\(([+\-]?[0-9]+(?:\.[0-9]+)?)%\)']
        m=next((x for pat in patterns if (x:=re.search(pat,text,re.I))),None)
        if not m:return None
        price=float(m.group(1));chg=float(m.group(2));pct=float(m.group(3));prev=price-chg
        dm=re.search(r'(?:At close:\s*)?([A-Z][a-z]{2}\s+\d{1,2},\s+20\d{2})',text)
        return {'symbol':base+'.PS','price':price,'currency':'PHP','exchange':'PSE','previous_close':prev,'change':chg,'change_percent':pct,'session':'Delayed/Last close','timestamp_utc':dm.group(1) if dm else None,'source':'StockAnalysis PSE quote','source_url':url}
    except Exception as e:log.warning('StockAnalysis PSE failed for %s: %s',symbol,e);return None

def _verified_pse_cache_file():return os.getenv('PF_QUOTE_CACHE_FILE','purple_falcon_verified_quotes.json')
def _verified_pse_cache_quote(symbol):
    try:
        path=_verified_pse_cache_file()
        if not os.path.exists(path):return None
        data=json.load(open(path,encoding='utf-8'));item=data.get((symbol or '').upper()) if isinstance(data,dict) else None
        if not isinstance(item,dict) or not isinstance(item.get('price'),(int,float)):return None
        age=int(time.time())-int(item.get('cached_at') or item.get('verified_at_epoch') or 0)
        max_age=int(os.getenv('PF_QUOTE_CACHE_HARD_MAX_AGE','259200'))
        if age<0 or age>max_age:return None
        out=dict(item);out['session']='Cached verified';out['source']=f"{item.get('source') or 'verified source'} (cached)";return out
    except Exception:return None

def _resolve_pse_quote(symbol):
    # Coverage merge: official ID discovery enhances the prior provider stack rather than replacing it.
    return (_pse_edge_quote(symbol) or _stockanalysis_pse_quote(symbol) or _pse_search_quote(symbol) or _direct_yahoo_quote(symbol) or _verified_pse_cache_quote(symbol))

def _compact_quote_row(symbol):
    q=_resolve_pse_quote(symbol) if str(symbol).upper().endswith('.PS') else _direct_yahoo_quote(symbol)
    if not q:return None
    price=q.get('price');prev=q.get('previous_close');currency=q.get('currency') or ''
    change=(price-prev) if isinstance(price,(int,float)) and isinstance(prev,(int,float)) else None
    pct=(change/prev*100) if isinstance(change,(int,float)) and isinstance(prev,(int,float)) and prev else None
    return {'symbol':symbol,'price':price,'change':change,'pct':pct,'currency':currency,'exchange':q.get('exchange') or 'Unavailable','session':q.get('session') or 'Unavailable','timestamp':q.get('timestamp'),'timestamp_utc':q.get('timestamp_utc'),'observed_at':q.get('observed_at'),'date':_quote_date_from_row(q),'source':q.get('source') or (urlparse(q.get('source_url','')).netloc.removeprefix('www.') if q.get('source_url') else 'Unavailable')}

def _quote_date_from_row(row):
    if not isinstance(row,dict):return 'Unknown'
    ts=row.get('timestamp')
    if isinstance(ts,(int,float)):return datetime.fromtimestamp(ts,timezone.utc).strftime('%b %d, %Y')
    text=str(row.get('timestamp_utc') or row.get('observed_at') or '')
    for pat in (r'\b(20\d{2}-\d{2}-\d{2})\b',r'\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2})\b'):
        m=re.search(pat,text,re.I)
        if m:return m.group(1)
    return 'Unknown'

def _html_escape(v):
    import html
    return html.escape(str(v if v is not None else ''))

def _change_html(row):
    a=row.get('change');p=row.get('pct')
    if not isinstance(a,(int,float)) or not isinstance(p,(int,float)):return '<span class="pf-market-change pf-neutral">Unavailable</span>'
    cls,arrow=('pf-up','▲') if a>0 else (('pf-down','▼') if a<0 else ('pf-neutral','•'))
    return f'<span class="pf-market-change {cls}">{arrow} {a:+.2f} ({p:+.2f}%)</span>'

def _session_html(v):
    text=str(v or 'Unavailable');low=text.lower()
    cls='pf-live' if any(x in low for x in ('official','regular','open','live')) else ('pf-delayed' if any(x in low for x in ('delay','source-timed','last close','cached')) else 'pf-closed')
    return f'<span class="pf-market-pill {cls}">{_html_escape(text)}</span>'

def _market_table_html(title,rows):
    body=[]
    for r in rows:
        price=f"{r['price']:.2f} {r.get('currency','')}" if isinstance(r.get('price'),(int,float)) else 'Unavailable'
        body.append('<tr>'+f'<td class="pf-symbol">{_html_escape(r.get("symbol"))}</td>'+f'<td class="pf-num">{_html_escape(price)}</td>'+f'<td class="pf-num">{_change_html(r)}</td>'+f'<td>{_session_html(r.get("session"))}</td>'+f'<td>{_html_escape(r.get("date") or "Unknown")}</td>'+f'<td class="pf-source">{_html_escape(r.get("source") or "Unavailable")}</td>'+'</tr>')
    return '<div class="pf-market-table-card">'+f'<div class="pf-market-table-title">💜 {_html_escape(title)}</div>'+'<div class="pf-market-table-scroll"><table class="pf-market-table"><thead><tr><th>Symbol</th><th>Price</th><th>Change</th><th>Session</th><th>Date</th><th>Source</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div></div>'

MARKET_TABLE_CSS="""<style>
.pf-market-table-card{border:1px solid rgba(127,127,127,.25);border-radius:14px;overflow:hidden;background:var(--pf-panel,#fff);margin:.55rem 0 1rem}.pf-market-table-title{font-weight:700;padding:12px 16px;border-bottom:1px solid rgba(127,127,127,.18)}.pf-market-table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}.pf-market-table{width:100%;min-width:760px;border-collapse:separate;border-spacing:0;font-size:.94rem}.pf-market-table th{padding:12px 16px;text-align:left;background:rgba(120,120,120,.07);white-space:nowrap}.pf-market-table td{padding:12px 16px;border-top:1px solid rgba(127,127,127,.18);white-space:nowrap}.pf-market-table td+td,.pf-market-table th+th{border-left:1px solid rgba(127,127,127,.12)}.pf-symbol{font-weight:700}.pf-num{font-variant-numeric:tabular-nums}.pf-source{max-width:220px;overflow:hidden;text-overflow:ellipsis}.pf-up{color:#16803c;font-weight:700}.pf-down{color:#b42318;font-weight:700}.pf-neutral{color:#667085}.pf-market-pill{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:.78rem;font-weight:700}.pf-live{background:#dcfce7;color:#166534}.pf-delayed{background:#fef3c7;color:#92400e}.pf-closed{background:#eef2f7;color:#475569}.pf-market-table-note{font-size:.78rem;opacity:.72;margin:.25rem .15rem .5rem}@media(max-width:640px){.pf-market-table{font-size:.88rem}.pf-market-table th,.pf-market-table td{padding:10px 12px}}
</style>"""

def _format_market_table(query):
    req=_market_table_request(query) or {};region=req.get('region') or _DEFAULT_LOCAL_MARKET
    rows=[]
    for sym in _market_table_symbols(query,10):
        row=_compact_quote_row(sym)
        if row:rows.append(row)
        else:rows.append({'symbol':sym,'price':None,'change':None,'pct':None,'currency':'','exchange':'Unavailable','session':'Unavailable','date':'Unknown','source':'Unavailable'})
    title='Philippine local stocks' if region=='PH' else ('Malaysia local stocks' if region=='MY' else f'{region} local stocks')
    verified=sum(1 for r in rows if isinstance(r.get('price'),(int,float)))
    unavailable=len(rows)-verified
    result=MARKET_TABLE_CSS+_market_table_html(f'{title} — current market quotes',rows)
    result+=f"<div class='pf-market-table-note'>Requested: {len(rows)} · Verified: {verified} · Unavailable: {unavailable}. Failed symbols do not cancel the table.</div>"
    result+="<div class='pf-market-table-note'>Provider metadata is preserved per row. Missing values remain unavailable and are never guessed.</div>"
    return '<!--PF_MARKET_TABLE-->'+result


def _normalize_symbol(symbol):
    value=(symbol or '').strip().upper().replace(' ', '')
    if not value:return None
    # Yahoo-style international symbols preserve the suffix separator.
    return value

def _resolve_international_alias(query):
    low=(query or '').lower(); exchange=_exchange_from_query(query)
    for alias,listings in sorted(_INTERNATIONAL_ALIASES.items(),key=lambda kv:len(kv[0]),reverse=True):
        if not re.search(r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])',low):continue
        if exchange and exchange in listings:return listings[exchange]
        if len(listings)==1:return next(iter(listings.values()))
        return None
    return None

def _symbol_from_query(query):
    q=(query or '').strip(); low=q.lower()
    if _private_market_entity(q):return None
    # Explicit/named securities outrank broad regional market-overview routing.
    pse=_pse_symbol_from_query(q)
    if pse:return pse
    intl=_resolve_international_alias(q)
    if intl:return intl
    index_symbol=_market_index_from_query(q)
    if index_symbol:return index_symbol
    # Explicit Yahoo/exchange-qualified symbol such as 7203.T / 0700.HK / 1155.KL / ASML.AS.
    m=re.search(r'(?<![A-Za-z0-9])([A-Za-z0-9]{1,12}(?:\.[A-Za-z]{1,4}|-[A-Za-z]))\b',q)
    if m:
        sym=_normalize_symbol(m.group(1))
        if any(sym.endswith(suf) for suf in _KNOWN_SUFFIXES) or '-' in sym:return sym
    for alias,symbol in sorted(_STOCK_ALIASES.items(),key=lambda kv:len(kv[0]),reverse=True):
        if re.search(r'(?<![a-z0-9])'+re.escape(alias)+r'(?![a-z0-9])',low): return symbol
    m=re.search(r'\$(?P<t>[A-Za-z][A-Za-z0-9.\-]{0,12})\b',q)
    if m:return _normalize_symbol(m.group('t'))
    m=re.search(r'\b(?:ticker|symbol)\s*[:=]?\s*(?P<t>[A-Za-z0-9][A-Za-z0-9.\-]{0,12})\b',q,re.I)
    if m:return _normalize_symbol(m.group('t'))
    if _MARKET_RE.search(q):
        toks=re.findall(r'\b[A-Z]{2,6}(?:[.\-][A-Z]{1,4})?\b',q);ignored={'USD','NYSE','NASDAQ','ETF','CEO','LSE','TSE','HKEX','ASX','TSX','SGX','KRX','NSE','BSE'}
        for t in toks:
            if t not in ignored:return _normalize_symbol(t)
    return None

def intent_queries(q):
    q=clean_query(q);intent=classify_web_intent(q)
    if intent=='market':
        sym=_symbol_from_query(q)
        if sym:
            venue='international exchange' if any(sym.endswith(x) for x in _KNOWN_SUFFIXES) else 'NASDAQ NYSE'
            return [f'{sym} stock quote today Yahoo Finance',f'{sym} quote today {venue}',f'{sym} stock price Reuters']
        return [q+' quote today Yahoo Finance',q+' market price Reuters']
    if intent=='officeholder':return [q+' official government',q+' Reuters']
    if intent=='news':return [q+' Reuters',q+' AP']
    if intent=='weather':return [q+' official forecast']
    return [q,q+' official']

def _domain(item):return urlparse(item.get('url','')).netloc.lower().removeprefix('www.')
def _market_relevant(item,query=''):
    text=(item.get('title','')+' '+item.get('body','')+' '+item.get('url','')).lower();d=_domain(item)
    if 'wikipedia.org' in d:return False
    if any(x in text for x in ('nikola tesla','autopilot','history of tesla')):return False
    sym=_symbol_from_query(query)
    symbol_ok=(sym.lower() in text) if sym else True
    market_ok=any(x in text for x in ('stock','quote','nasdaq','nyse','share','market','trading','price'))
    return symbol_ok and market_ok

def search_sources(queries):
    out=[];seen=set()
    for q in queries:
        for x in (search_via_websearch(q) or search_fallback(q)):
            key=x.get('url') or (x['title'],x['body'][:100])
            if key in seen:continue
            seen.add(key);out.append(x)
        if len(out)>=MAX_RESULTS:break
    return out[:MAX_RESULTS]

def _extract_market_quote(query,items):
    """Extract structured quote values only from observed evidence. Never invent numeric fields."""
    accepted=[x for x in items if _market_relevant(x,query)]
    accepted.sort(key=lambda x:(0 if any(fd in _domain(x) for fd in _FINANCE_DOMAINS) else 1))
    quote={'symbol':_symbol_from_query(query),'price':None,'session':None,'as_of_date':None,'as_of_time':None,'change_percent':None,'volume':None,'source':None,'source_url':None,'evidence':accepted}
    for item in accepted:
        text=item['title']+' '+item['body']; low=text.lower(); prices=[float(x) for x in _PRICE_RE.findall(text)]
        if prices and quote['price'] is None:
            # Prefer explicit current/close/trading price vicinity; otherwise first observed dollar value from a finance result.
            quote['price']=prices[0];quote['source']=item.get('source') or _domain(item);quote['source_url']=item.get('url')
            if 'overnight' in low:quote['session']='overnight'
            elif 'after hours' in low or 'after-hours' in low:quote['session']='after-hours'
            elif 'pre-market' in low or 'premarket' in low:quote['session']='pre-market'
            elif 'at close' in low or 'close' in low:quote['session']='regular close'
            else:quote['session']='latest observed quote'
            dm=_DATE_RE.search(text);tm=_TIME_RE.search(text)
            if dm:quote['as_of_date']=dm.group(0)
            if tm:quote['as_of_time']=tm.group(0)
            pm=_PCT_RE.search(text)
            if pm:quote['change_percent']=pm.group(1)+'%'
            vm=_VOLUME_RE.search(text)
            if vm:quote['volume']=vm.group(1)
    return quote

def _direct_yahoo_quote(symbol):
    """Direct structured quote provider. Returns only observed Yahoo chart metadata, never model-generated values."""
    symbol=(symbol or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9.^\-]{1,16}',symbol): return None
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
    try:
        r=requests.get(url,params={'interval':'1m','range':'1d','includePrePost':'true'},headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/14.1'},timeout=8)
        if r.status_code!=200:
            log.warning('Yahoo structured quote HTTP %s',r.status_code);return None
        data=r.json(); result=((data.get('chart') or {}).get('result') or [None])[0]
        if not isinstance(result,dict): return None
        meta=result.get('meta') or {}; now=int(time.time())
        candidates=[]
        for key,label,tkey in [('postMarketPrice','after-hours','postMarketTime'),('preMarketPrice','pre-market','preMarketTime'),('regularMarketPrice','regular/latest','regularMarketTime')]:
            val=meta.get(key);ts=meta.get(tkey)
            if isinstance(val,(int,float)):
                candidates.append((int(ts or 0),label,float(val),key))
        if not candidates:return None
        candidates.sort(key=lambda x:x[0],reverse=True);ts,label,price,key=candidates[0]
        if not ts: ts=int(meta.get('regularMarketTime') or now)
        dt=datetime.fromtimestamp(ts,timezone.utc)
        prev=meta.get('chartPreviousClose') or meta.get('previousClose')
        change=price-float(prev) if isinstance(prev,(int,float)) else None
        pct=(change/float(prev)*100) if change is not None and float(prev)!=0 else None
        market_cap=meta.get('marketCap')
        trailing_dividend_rate=meta.get('trailingAnnualDividendRate')
        trailing_dividend_yield=meta.get('trailingAnnualDividendYield')
        return {'symbol':symbol,'price':price,'session':label,'timestamp_utc':dt.strftime('%Y-%m-%d %H:%M:%S UTC'),'currency':meta.get('currency') or 'USD','exchange':meta.get('exchangeName') or meta.get('fullExchangeName'),'previous_close':float(prev) if isinstance(prev,(int,float)) else None,'change':change,'change_percent':pct,'market_cap':float(market_cap) if isinstance(market_cap,(int,float)) else None,'dividend_rate':float(trailing_dividend_rate) if isinstance(trailing_dividend_rate,(int,float)) else None,'dividend_yield':float(trailing_dividend_yield) if isinstance(trailing_dividend_yield,(int,float)) else None,'source':'Yahoo Finance structured quote','source_url':f'https://finance.yahoo.com/quote/{symbol}/','observed_at':datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
    except Exception as e:
        log.warning('Yahoo structured quote failed: %s',e);return None

def _human_money(value,currency='USD'):
    if value is None:return None
    n=float(value);sign='-' if n<0 else '';n=abs(n)
    for size,suffix in ((1e12,'T'),(1e9,'B'),(1e6,'M'),(1e3,'K')):
        if n>=size:return f"{sign}{n/size:.2f}{suffix} {currency}"
    return f"{sign}{n:.2f} {currency}"

def _percent_value(value):
    if value is None:return None
    v=float(value)
    # Yahoo metadata commonly represents yield as a decimal fraction; tolerate already-percent values too.
    if abs(v)<=1:v*=100
    return f"{v:.2f}%"

def _md_cell(value):
    return str(value if value is not None else 'Unavailable').replace('|','\\|').replace('\n',' ')

def _format_direct_quote(q):
    if not q:return None
    currency=q.get('currency') or 'USD'
    rows=[]
    rows.append(('Symbol',q.get('symbol') or 'Unavailable'))
    rows.append(('Price',f"{q['price']:.2f} {currency}" if q.get('price') is not None else 'Unavailable'))
    rows.append(('Session',(q.get('session') or 'Unavailable').title()))
    rows.append(('Quote timestamp',q.get('timestamp_utc') or 'Unavailable'))
    if q.get('change') is not None and q.get('change_percent') is not None:
        rows.append(('Change vs previous close',f"{q['change']:+.2f} {currency} ({q['change_percent']:+.2f}%)"))
    else: rows.append(('Change vs previous close','Unavailable'))
    rows.append(('Previous close',f"{q['previous_close']:.2f} {currency}" if q.get('previous_close') is not None else 'Unavailable'))
    if not _is_market_index(q.get('symbol')):
        rows.append(('Market cap',_human_money(q.get('market_cap'),currency) if q.get('market_cap') is not None else 'Unavailable'))
        rows.append(('Trailing annual dividend',f"{q['dividend_rate']:.4g} {currency} / share" if q.get('dividend_rate') is not None else 'Unavailable'))
        rows.append(('Trailing dividend yield',_percent_value(q.get('dividend_yield')) if q.get('dividend_yield') is not None else 'Unavailable'))
    rows.append(('Exchange',q.get('exchange') or 'Unavailable'))
    rows.append(('Currency',currency))
    lines=[f"💜 **{_md_cell(q.get('symbol') or 'Market')} market update**",'', '| Item | Value |','|---|---|']
    lines.extend(f"| {_md_cell(k)} | {_md_cell(v)} |" for k,v in rows)
    lines += ['',f"**Source:** {_md_cell(q.get('source') or 'Unavailable')}",q.get('source_url') or '',f"**Retrieved:** {_md_cell(q.get('observed_at') or 'Unavailable')}",'Market data can change quickly and may be delayed depending on exchange/source coverage. Use the session and quote timestamp above.']
    return '\n'.join(lines)

def _market_quote_answer(query,items):
    q=_extract_market_quote(query,items)
    if q['price'] is None:
        return "💜 I searched current market sources, but I couldn't extract a reliable current quote from the retrieved evidence. I won't guess a price."
    rows=[
      ('Symbol',q.get('symbol') or 'Unavailable'),
      ('Price',f"{q['price']:.2f} USD"),
      ('Session',(q.get('session') or 'latest observed quote').title()),
      ('Quote date',q.get('as_of_date') or 'Unavailable'),
      ('Quote time',q.get('as_of_time') or 'Unavailable'),
      ('Change',q.get('change_percent') or 'Unavailable'),
      ('Volume',q.get('volume') or 'Unavailable'),
    ]
    lines=[f"💜 **{_md_cell(q.get('symbol') or 'Market')} market update**",'', '| Item | Value |','|---|---|']
    lines.extend(f"| {_md_cell(k)} | {_md_cell(v)} |" for k,v in rows)
    lines += ['',f"**Source:** {_md_cell(q.get('source') or 'Unavailable')}",q.get('source_url') or '','Market data can change quickly; the session/date/time above describes the retrieved quote.']
    return '\n'.join(lines)

def grounded_synthesis_messages(query,verification,system_prompt='',history=None):
    evidence='\n\n'.join(f"[{i}] {x['title']}\n{x['body']}\nURL: {x['url']}" for i,x in enumerate(verification['accepted'][:6],1))
    locked='VERIFIED-WEB MODE. Use only supplied evidence for current facts. Never introduce a number, name, date, price, score, or officeholder not present in evidence. If evidence is insufficient, say so. Do not claim Purple Falcon lacks web access.'
    return [{'role':'system','content':(system_prompt or '')+'\n'+locked}]+(history or [])[-4:]+[{'role':'user','content':f'Question: {query}\n\nVerified evidence:\n{evidence}'}]

def verify_evidence(query,items):
    intent=classify_web_intent(query);accepted=[];domains=set()
    for x in items:
        ok=_market_relevant(x,query) if intent=='market' else True
        if ok:accepted.append(x);domains.add(_domain(x))
    return {'accepted':accepted,'domains':domains,'sufficient':bool(accepted),'confidence':'HIGH' if len(domains)>=3 else 'MEDIUM' if len(domains)>=2 else 'LOW'}

def web_reply(message,call_ai=None,ai_failed_check=None,system_prompt=None,brain_down=False,history=None):
    if not ENABLED:return None
    policy=analyze_prompt(message)
    if not policy['fresh'] and policy['intent']=='general':return None
    query=policy['query']
    if policy['intent']=='market':
        if _market_table_request(query):return _format_market_table(query)
        private_reply=_private_market_reply(query)
        if private_reply:return private_reply
        symbol=_symbol_from_query(query)
        direct=(_resolve_pse_quote(symbol) if symbol and str(symbol).upper().endswith('.PS') else _direct_yahoo_quote(symbol)) if symbol else None
        if direct:return _format_direct_quote(direct)
        sources=search_sources(intent_queries(query))
        if not sources:return "💜 I couldn't retrieve a current structured market quote or trustworthy market evidence right now. I won't guess a price."
        return _market_quote_answer(query,sources)
    sources=search_sources(intent_queries(query))
    if not sources:return None
    verification=verify_evidence(query,sources)
    if not verification['sufficient']:return "💜 I searched the live web, but the retrieved evidence is not strong enough to verify the requested current fact."
    if call_ai:
        try:
            ai=call_ai(grounded_synthesis_messages(query,verification,system_prompt,history));failed=ai_failed_check(ai) if ai_failed_check else not bool(ai)
            if isinstance(ai,str) and ai.strip() and not failed and not reply_is_unsure(ai):return ai.strip()
        except Exception as e:log.warning('Grounded synthesis unavailable: %s',e)
    lines=[f"💜 **Verified web evidence** — Confidence: **{verification['confidence']}**",'']
    for i,x in enumerate(verification['accepted'][:5],1):lines += [f"**{i}. {x['title']}**",x['body'][:650],f"Source: {x['url']}",'']
    return '\n'.join(lines).strip()

def self_test():
    # Regression: never reproduce an invented $185.12 when evidence says $378.73.
    y={'title':'Tesla, Inc. (TSLA) Historical Prices','body':'At close: October 5 at 4:00:01 PM EDT. Oct 5, 2026 close $378.73, volume 42,112,900.','source':'finance.yahoo.com','url':'https://finance.yahoo.com/quote/TSLA/history/'}
    q=_extract_market_quote('Tesla stock price now',[y]);assert q['price']==378.73 and q['session']=='regular close'
    ans=_market_quote_answer('Tesla stock price now',[y]);assert '| Price | 378.73 USD |' in ans and '$185.12' not in ans and '| Item | Value |' in ans
    bad={'title':'Tesla Autopilot','body':'Tesla vehicle feature $185.12 unrelated number','source':'wikipedia','url':'https://en.wikipedia.org/wiki/Tesla_Autopilot'}
    assert _extract_market_quote('Tesla stock price now',[bad])['price'] is None
    assert classify_web_intent('Tesla stock price now')=='market'
    assert _symbol_from_query('Tesla stock price now')=='TSLA'
    assert _symbol_from_query('Apple stock price now')=='AAPL'
    assert _symbol_from_query('Microsoft stock today')=='MSFT'
    assert _symbol_from_query('NVIDIA shares now')=='NVDA'
    assert _symbol_from_query('$AMZN stock price')=='AMZN'
    assert _symbol_from_query('ticker PLTR price')=='PLTR'
    assert _symbol_from_query('QQQ stock quote')=='QQQ'
    assert _symbol_from_query('Toyota stock Japan')=='7203.T'
    assert _symbol_from_query('Tencent stock HKEX')=='0700.HK'
    assert _symbol_from_query('Maybank stock Malaysia')=='1155.KL'
    assert _symbol_from_query('ASML stock Amsterdam')=='ASML.AS'
    assert _symbol_from_query('Reliance NSE price')=='RELIANCE.NS'
    assert _symbol_from_query('Samsung stock South Korea')=='005930.KS'
    assert _symbol_from_query('DBS stock Singapore')=='D05.SI'
    assert _symbol_from_query('7203.T stock price')=='7203.T'
    assert _symbol_from_query('0700.HK price now')=='0700.HK'
    assert _symbol_from_query('1155.KL stock')=='1155.KL'
    assert _symbol_from_query('BDO stock Philippines')=='BDO.PS'
    assert _symbol_from_query('BPI PSE price')=='BPI.PS'
    assert _symbol_from_query('Jollibee stock Philippines')=='JFC.PS'
    assert _symbol_from_query('Maynilad PSE stock')=='MYNLD.PS'
    assert _symbol_from_query('ACEN PSE price now')=='ACEN.PS'
    assert _symbol_from_query('BDO.PS price')=='BDO.PS'
    assert _pse_company_id('BDO.PS')=='260'
    assert callable(_resolve_pse_quote)
    assert len(_market_table_symbols('tabulate local stocks at PH',10))==10
    assert callable(_stockanalysis_pse_quote) and callable(_verified_pse_cache_quote)
    demo={'timestamp_utc':'Oct 06, 2026','source':'PSE EDGE'}
    assert _quote_date_from_row(demo)=='Oct 06, 2026'
    assert '<!--PF_MARKET_TABLE-->' in _format_market_table.__code__.co_consts
    # Dynamic local-market tests. Default local market is controlled by PF_LOCAL_MARKET.
    expected_local=_MARKET_CONTEXTS.get(_DEFAULT_LOCAL_MARKET,_MARKET_CONTEXTS['MY'])['index']
    assert _symbol_from_query('local stock update today?')==expected_local
    assert _symbol_from_query('what I mean Philippines stock update')=='PSEI.PS'
    assert _symbol_from_query('how is the local market now')==expected_local
    assert _symbol_from_query('PSEi today')=='PSEI.PS'
    assert _dynamic_market_intent('local stocks today')['kind']=='index'
    assert _market_table_request('can you tabulate result for other local stocks at PH?')['region']=='PH'
    assert _dynamic_market_intent('can you tabulate result for other local stocks at PH?')['intent']=='market_table'
    assert _market_table_symbols('tabulate local stocks PH',3)==['BDO.PS','BPI.PS','JFC.PS']
    assert _market_table_symbols('compare local stocks Malaysia',2)==['1155.KL','1295.KL']
    assert _symbol_from_query('Malaysia stock update today')=='^KLSE'
    assert _symbol_from_query('Philippines stock update')=='PSEI.PS'
    assert _symbol_from_query('Singapore stock market today')=='^STI'
    assert _symbol_from_query('Japan market update')=='^N225'
    assert _symbol_from_query('Hong Kong market now')=='^HSI'
    assert _symbol_from_query('Maybank stock Malaysia')=='1155.KL'
    assert _symbol_from_query('BDO stock Philippines')=='BDO.PS'
    assert _symbol_from_query('gcash stock now?') is None
    assert _private_market_entity('gcash stock now?')['kind']=='private_or_unlisted'
    fixture='<table><tr><th>Company Name</th><th>Stock Symbol</th></tr><tr><td>Test Philippine Corp.</td><td>TPC</td></tr></table>'
    assert _parse_pse_directory_html(fixture).get('TPC')=='Test Philippine Corp.'
    assert _symbol_from_query('explain recursion') is None
    mock={'symbol':'TSLA','price':378.73,'session':'regular/latest','timestamp_utc':'2026-10-05 20:00:01 UTC','currency':'USD','exchange':'NasdaqGS','previous_close':370.59,'change':8.14,'change_percent':2.196,'market_cap':1200000000000,'dividend_rate':None,'dividend_yield':None,'source':'Yahoo Finance structured quote','source_url':'https://finance.yahoo.com/quote/TSLA/','observed_at':'2026-10-06 05:00:00 UTC'}
    formatted=_format_direct_quote(mock);assert '378.73 USD' in formatted and '$185.12' not in formatted and '| Item | Value |' in formatted and '| Market cap | 1.20T USD |' in formatted and '| Trailing annual dividend | Unavailable |' in formatted
    dividend_mock=dict(mock);dividend_mock.update({'symbol':'TEST','market_cap':15000000000,'dividend_rate':2.5,'dividend_yield':0.035})
    dividend_text=_format_direct_quote(dividend_mock);assert '| Market cap | 15.00B USD |' in dividend_text and '| Trailing annual dividend | 2.5 USD / share |' in dividend_text and '| Trailing dividend yield | 3.50% |' in dividend_text
    return True

__all__=['ENABLED','WEBSEARCH_AVAILABLE','SEARCH_AVAILABLE','web_reply','reply_is_unsure','search_sources','self_test','_extract_candidates','normalize_result','classify_web_intent','analyze_prompt','verify_evidence','grounded_synthesis_messages','_extract_market_quote','_direct_yahoo_quote','_format_direct_quote','_fetch_pse_catalog','_pse_symbol_from_query','_parse_pse_directory_html','_human_money','_percent_value','_dynamic_market_intent','_market_index_from_query','_local_market_region','_private_market_entity','_market_table_request','_market_table_symbols','_format_market_table','_pse_company_id','_resolve_pse_quote','_refresh_pse_company_ids']
if __name__=='__main__':print('self_test:','PASS' if self_test() else 'FAIL')
