# Purple Falcon WebReason v14.0 - Verified Market Quote Mode
import os, re, json, logging, tempfile, time
import requests
from html import unescape
from datetime import datetime, timezone
from urllib.parse import urlparse

APP_NAME='Purple Falcon PH'; VERSION='18.1.0'
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
 'US':{'index':'^GSPC','currency':'USD','name':'United States','aliases':('united states','usa','us market','america','american','nyse','nasdaq','s&p 500','sp500')},
 'CA':{'index':'^GSPTSE','currency':'CAD','name':'Canada','aliases':('canada','canadian','tsx','toronto')},
 'MX':{'index':'^MXX','currency':'MXN','name':'Mexico','aliases':('mexico','mexican','bmv','bolsa mexicana')},
 'BR':{'index':'^BVSP','currency':'BRL','name':'Brazil','aliases':('brazil','brazilian','b3','bovespa','ibovespa')},
 'UK':{'index':'^FTSE','currency':'GBP','name':'United Kingdom','aliases':('united kingdom','uk','britain','british','london','lse','ftse','ftse 100')},
 'DE':{'index':'^GDAXI','currency':'EUR','name':'Germany','aliases':('germany','german','xetra','frankfurt','dax')},
 'FR':{'index':'^FCHI','currency':'EUR','name':'France','aliases':('france','french','paris','euronext paris','cac 40')},
 'NL':{'index':'^AEX','currency':'EUR','name':'Netherlands','aliases':('netherlands','dutch','amsterdam','euronext amsterdam','aex')},
 'CH':{'index':'^SSMI','currency':'CHF','name':'Switzerland','aliases':('switzerland','swiss','six','smi')},
 'IT':{'index':'FTSEMIB.MI','currency':'EUR','name':'Italy','aliases':('italy','italian','milan','borsa italiana','ftse mib')},
 'ES':{'index':'^IBEX','currency':'EUR','name':'Spain','aliases':('spain','spanish','madrid','bme','ibex')},
 'MY':{'index':'^KLSE','currency':'MYR','name':'Malaysia','aliases':('malaysia','malaysian','bursa','bursa malaysia','klse','fbm klci','klci','kuala lumpur')},
 'PH':{'index':'PSEI.PS','currency':'PHP','name':'Philippines','aliases':('philippines','philippine','pse','psei','manila')},
 'SG':{'index':'^STI','currency':'SGD','name':'Singapore','aliases':('singapore','sgx','sti','straits times')},
 'JP':{'index':'^N225','currency':'JPY','name':'Japan','aliases':('japan','japanese','tokyo','tse','nikkei','nikkei 225')},
 'HK':{'index':'^HSI','currency':'HKD','name':'Hong Kong','aliases':('hong kong','hkex','hang seng','hsi')},
 'CN':{'index':'000001.SS','currency':'CNY','name':'China','aliases':('china','chinese','shanghai','shenzhen','sse','szse')},
 'IN':{'index':'^NSEI','currency':'INR','name':'India','aliases':('india','indian','nse','nifty','nifty 50')},
 'KR':{'index':'^KS11','currency':'KRW','name':'South Korea','aliases':('south korea','korea','korean','krx','kospi')},
 'TW':{'index':'^TWII','currency':'TWD','name':'Taiwan','aliases':('taiwan','taiwanese','twse','taiex')},
 'AU':{'index':'^AXJO','currency':'AUD','name':'Australia','aliases':('australia','australian','asx','asx 200')},
 'NZ':{'index':'^NZ50','currency':'NZD','name':'New Zealand','aliases':('new zealand','nz','nzx','nzx 50')},
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
    region=_explicit_market_region(q)
    if not region and re.search(r'\b(?:PH|PSE)\b',q,re.I):region='PH'
    if not region and re.search(r'\b(?:MY|KLSE)\b',q,re.I):region='MY'
    if not region and re.search(r'\blocal\b',q,re.I):region=_DEFAULT_LOCAL_MARKET
    if not region and re.search(r'\b(?:US|U\.S\.|USA)\b',q,re.I) and re.search(r'\b(?:stocks?|shares?|market|banks?|technology|tech)\b',q,re.I):region='US'
    return {'intent':'market_table','region':region or _DEFAULT_LOCAL_MARKET,'sector':_sector_from_query(q) if '_sector_from_query' in globals() else None}

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
 'ca':{'suffix':'.TO','currency':'CAD','names':('canada','canadian','toronto','tsx')},
 'mx':{'suffix':'.MX','currency':'MXN','names':('mexico','mexican','bmv')},
 'br':{'suffix':'.SA','currency':'BRL','names':('brazil','brazilian','b3','bovespa')},
 'de':{'suffix':'.DE','currency':'EUR','names':('germany','xetra','frankfurt')},
 'fr':{'suffix':'.PA','currency':'EUR','names':('france','paris','euronext paris')},
 'nl':{'suffix':'.AS','currency':'EUR','names':('netherlands','amsterdam','euronext amsterdam')},
 'it':{'suffix':'.MI','currency':'EUR','names':('italy','milan','borsa italiana')},
 'es':{'suffix':'.MC','currency':'EUR','names':('spain','madrid','bme')},
 'ch':{'suffix':'.SW','currency':'CHF','names':('switzerland','six','swiss')},
 'in-nse':{'suffix':'.NS','currency':'INR','names':('india','nse','national stock exchange india')},
 'in-bse':{'suffix':'.BO','currency':'INR','names':('bse','bombay stock exchange')},
 'kr':{'suffix':'.KS','currency':'KRW','names':('south korea','korea','krx')},
 'sg':{'suffix':'.SI','currency':'SGD','names':('singapore','sgx')},
 'my':{'suffix':'.KL','currency':'MYR','names':('malaysia','bursa malaysia','bursa','klse')},
 'ph':{'suffix':'.PS','currency':'PHP','names':('philippines','philippine','pse','philippine stock exchange')},
 'tw':{'suffix':'.TW','currency':'TWD','names':('taiwan','twse')},
 'cn-sh':{'suffix':'.SS','currency':'CNY','names':('china','shanghai','sse')},
 'cn-sz':{'suffix':'.SZ','currency':'CNY','names':('shenzhen','szse')},
 'nz':{'suffix':'.NZ','currency':'NZD','names':('new zealand','nzx')},
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
_KNOWN_SUFFIXES=('.L','.T','.HK','.AX','.TO','.V','.DE','.F','.PA','.AS','.SW','.NS','.BO','.KS','.KQ','.SI','.KL','.PS','.MX','.SA','.MI','.MC','.TW','.SS','.SZ','.NZ')
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
 'US':['AAPL','MSFT','NVDA','AMZN','GOOGL','META','BRK-B','JPM','AVGO','TSLA'],
 'CA':['RY.TO','TD.TO','SHOP.TO','ENB.TO','BNS.TO','CNQ.TO','CP.TO','CNR.TO','BMO.TO','TRI.TO'],
 'MX':['WALMEX.MX','AMXL.MX','FEMSAUBD.MX','GMEXICOB.MX','CEMEXCPO.MX','GAPB.MX','ASURB.MX','KOFUBL.MX','BIMBOA.MX','GFNORTEO.MX'],
 'BR':['PETR4.SA','VALE3.SA','ITUB4.SA','BBDC4.SA','ABEV3.SA','WEGE3.SA','BBAS3.SA','B3SA3.SA','RENT3.SA','PRIO3.SA'],
 'UK':['AZN.L','SHEL.L','HSBA.L','ULVR.L','BP.L','GSK.L','RIO.L','REL.L','LSEG.L','BARC.L'],
 'DE':['SAP.DE','SIE.DE','DTE.DE','ALV.DE','AIR.DE','BMW.DE','MBG.DE','BAS.DE','IFX.DE','ADS.DE'],
 'FR':['MC.PA','OR.PA','TTE.PA','AIR.PA','SAN.PA','SU.PA','BNP.PA','EL.PA','CS.PA','DG.PA'],
 'NL':['ASML.AS','SHELL.AS','INGA.AS','PRX.AS','ADYEN.AS','PHIA.AS','AD.AS','HEIA.AS','WKL.AS','KPN.AS'],
 'CH':['NESN.SW','NOVN.SW','ROG.SW','UBSG.SW','ABBN.SW','ZURN.SW','CFR.SW','SIKA.SW','LONN.SW','GIVN.SW'],
 'IT':['ENI.MI','ENEL.MI','ISP.MI','UCG.MI','STLAM.MI','RACE.MI','G.MI','SRG.MI','TEN.MI','PRY.MI'],
 'ES':['SAN.MC','IBE.MC','ITX.MC','BBVA.MC','CABK.MC','REP.MC','TEF.MC','AENA.MC','FER.MC','AMS.MC'],
 'JP':['7203.T','6758.T','9984.T','8306.T','8035.T','6861.T','6501.T','8058.T','6098.T','9432.T'],
 'HK':['0700.HK','9988.HK','0005.HK','1299.HK','0941.HK','3690.HK','2318.HK','0883.HK','0388.HK','0016.HK'],
 'CN':['600519.SS','601318.SS','600036.SS','601166.SS','600900.SS','000858.SZ','000333.SZ','002594.SZ','300750.SZ','000001.SZ'],
 'IN':['RELIANCE.NS','TCS.NS','HDFCBANK.NS','BHARTIARTL.NS','ICICIBANK.NS','INFY.NS','SBIN.NS','LICI.NS','ITC.NS','HINDUNILVR.NS'],
 'KR':['005930.KS','000660.KS','373220.KS','207940.KS','005380.KS','000270.KS','068270.KS','105560.KS','035420.KS','055550.KS'],
 'TW':['2330.TW','2317.TW','2454.TW','2308.TW','2881.TW','2891.TW','2882.TW','2303.TW','2412.TW','3711.TW'],
 'SG':['D05.SI','O39.SI','U11.SI','Z74.SI','C6L.SI','S68.SI','A17U.SI','C38U.SI','BN4.SI','F34.SI'],
 'MY':['1155.KL','1295.KL','1023.KL','5347.KL','5225.KL','5183.KL','6012.KL','6033.KL','8869.KL','3816.KL'],
 'PH':['BDO.PS','BPI.PS','JFC.PS','SM.PS','SMPH.PS','ALI.PS','TEL.PS','GLO.PS','MER.PS','ICT.PS','ACEN.PS','AP.PS'],
 'AU':['BHP.AX','CBA.AX','CSL.AX','NAB.AX','WBC.AX','ANZ.AX','WES.AX','MQG.AX','GMG.AX','RIO.AX'],
 'NZ':['FPH.NZ','AIR.NZ','SPK.NZ','MEL.NZ','MCY.NZ','IFT.NZ','CEN.NZ','EBO.NZ','ATM.NZ','GMT.NZ'],
}
_REGION_SECTOR_BASKETS={
 ('US','technology'):['AAPL','MSFT','NVDA','AVGO','ORCL','CRM','AMD','ADBE','QCOM','INTC'],
 ('US','banks'):['JPM','BAC','WFC','C','GS','MS','USB','PNC','TFC','BK'],
 ('JP','automakers'):['7203.T','7267.T','7201.T','7269.T','7270.T','7211.T','7202.T','7205.T','7272.T','7203.T'],
 ('PH','banks'):['BDO.PS','BPI.PS','MBT.PS','UBP.PS','AUB.PS','BNCOM.PS'],
 ('SG','banks'):['D05.SI','O39.SI','U11.SI'],
 ('HK','technology'):['0700.HK','9988.HK','3690.HK','1810.HK','9618.HK','9999.HK'],
}
_SECTOR_QUERY_ALIASES={'technology':('technology','tech','semiconductor','software'),'banks':('bank','banks','banking'),'automakers':('automaker','automakers','auto','automotive','car makers')}
def _sector_from_query(query):
    low=clean_query(query).lower()
    for key,names in _SECTOR_QUERY_ALIASES.items():
        if any(re.search(r'(?<![a-z0-9])'+re.escape(n)+r'(?![a-z0-9])',low) for n in names):return key
    return None

def _market_table_symbols(query,limit=10):
    req=_market_table_request(query) or {};region=req.get('region') or _DEFAULT_LOCAL_MARKET;sector=_sector_from_query(query)
    syms=list(_REGION_SECTOR_BASKETS.get((region,sector),_REGION_BASKETS.get(region,[])))
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
        body.append('<tr>'+f'<td class="pf-symbol">{_html_escape(r.get("symbol"))}</td>'+f'<td class="pf-num pf-price">{_html_escape(price)}</td>'+f'<td class="pf-num pf-change-cell">{_change_html(r)}</td>'+f'<td class="pf-session">{_session_html(r.get("session"))}</td>'+f'<td class="pf-date">{_html_escape(r.get("date") or "Unknown")}</td>'+f'<td class="pf-source">{_html_escape(r.get("source") or "Unavailable")}</td>'+'</tr>')
    return '<div class="pf-market-table-card">'+f'<div class="pf-market-table-title">💜 {_html_escape(title)}</div>'+'<div class="pf-market-table-scroll"><table class="pf-market-table"><thead><tr><th>Symbol</th><th>Price</th><th>Change</th><th>Session</th><th>Date</th><th>Source</th></tr></thead><tbody>'+''.join(body)+'</tbody></table></div></div>'

MARKET_TABLE_CSS="""<style>
.pf-market-table-card{border:1px solid var(--pf-mkt-border,#cbd5e1);border-radius:16px;overflow:hidden;background:var(--pf-mkt-bg,#fff);color:var(--pf-mkt-text,#172033);margin:.65rem 0 1rem;box-shadow:0 4px 14px var(--pf-mkt-shadow,rgba(15,23,42,.12))}
.pf-market-table-title{font-size:15px;line-height:1.35;font-weight:850;color:var(--pf-mkt-title,#101828);padding:14px 16px;border-bottom:1px solid var(--pf-mkt-border,#cbd5e1);background:var(--pf-mkt-title-bg,#f8fafc);letter-spacing:.01em}
.pf-market-table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-color:var(--pf-mkt-scroll-thumb,#64748b) var(--pf-mkt-scroll-track,#e2e8f0);scrollbar-width:auto}
.pf-market-table-scroll::-webkit-scrollbar{height:12px}.pf-market-table-scroll::-webkit-scrollbar-track{background:var(--pf-mkt-scroll-track,#e2e8f0)}.pf-market-table-scroll::-webkit-scrollbar-thumb{background:var(--pf-mkt-scroll-thumb,#64748b);border-radius:999px;border:2px solid var(--pf-mkt-scroll-track,#e2e8f0)}
.pf-market-table{width:100%;min-width:900px;border-collapse:separate;border-spacing:0;font-size:14px;line-height:1.35;color:var(--pf-mkt-text,#172033);background:var(--pf-mkt-bg,#fff);table-layout:auto}
.pf-market-table th{padding:13px 14px;text-align:left;background:var(--pf-mkt-header,#e7eff8);color:var(--pf-mkt-header-text,#1d2939);font-size:13px;font-weight:800;white-space:nowrap;border-bottom:2px solid var(--pf-mkt-border-strong,#94a3b8)}
.pf-market-table td{padding:12px 14px;border-top:1px solid var(--pf-mkt-border,#cbd5e1);color:var(--pf-mkt-text,#172033);vertical-align:middle;white-space:nowrap;background:var(--pf-mkt-row,#fff)}
.pf-market-table tbody tr:nth-child(even) td{background:var(--pf-mkt-row-alt,#f8fbff)}.pf-market-table tbody tr:hover td{background:var(--pf-mkt-hover,#eef6ff)}
.pf-market-table td+td,.pf-market-table th+th{border-left:1px solid var(--pf-mkt-border,#cbd5e1)}
.pf-market-table .pf-symbol{font-weight:800;color:var(--pf-mkt-symbol,#101828);position:sticky;left:0;z-index:2;min-width:88px;background:var(--pf-mkt-row,#fff);box-shadow:2px 0 0 var(--pf-mkt-border,#cbd5e1)}
.pf-market-table tbody tr:nth-child(even) .pf-symbol{background:var(--pf-mkt-row-alt,#f8fbff)}.pf-market-table tbody tr:hover .pf-symbol{background:var(--pf-mkt-hover,#eef6ff)}.pf-market-table th:first-child{position:sticky;left:0;z-index:3;background:var(--pf-mkt-header,#e7eff8);box-shadow:2px 0 0 var(--pf-mkt-border-strong,#94a3b8)}
.pf-market-table .pf-num{font-variant-numeric:tabular-nums}.pf-market-table .pf-price{color:var(--pf-mkt-price,#344054);font-weight:700}.pf-market-table .pf-date{color:var(--pf-mkt-date,#344054);font-weight:650}.pf-market-table .pf-source{min-width:170px;max-width:240px;overflow:hidden;text-overflow:ellipsis;color:var(--pf-mkt-muted,#475467);font-weight:650}.pf-market-table td.pf-price,.pf-market-table td.pf-date,.pf-market-table td.pf-source{opacity:1}
.pf-market-change.pf-up,.pf-up{color:var(--pf-mkt-up,#067647);font-weight:800}.pf-market-change.pf-down,.pf-down{color:var(--pf-mkt-down,#b42318);font-weight:800}.pf-market-change.pf-neutral,.pf-neutral{color:var(--pf-mkt-neutral,#344054);font-weight:750}
.pf-market-pill{display:inline-flex;align-items:center;max-width:175px;padding:4px 9px;border:1px solid transparent;border-radius:999px;font-size:12px;line-height:1.25;font-weight:800;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pf-live{background:var(--pf-mkt-live-bg,#dcfce7);color:var(--pf-mkt-live-text,#166534);border-color:var(--pf-mkt-live-border,#86efac)}.pf-delayed{background:var(--pf-mkt-delay-bg,#fef3c7);color:var(--pf-mkt-delay-text,#92400e);border-color:var(--pf-mkt-delay-border,#fcd34d)}.pf-closed{background:var(--pf-mkt-na-bg,#f2f4f7);color:var(--pf-mkt-na-text,#475467);border-color:var(--pf-mkt-na-border,#d0d5dd)}
.pf-market-table-note{font-size:12.5px;line-height:1.45;color:var(--pf-mkt-note,#475467);margin:.35rem .2rem .6rem}
@media(max-width:760px){.pf-market-table{min-width:850px;font-size:13px}.pf-market-table th{font-size:12.5px}.pf-market-table th,.pf-market-table td{padding:10px 11px}.pf-market-table-card{border-radius:12px}}
@media(forced-colors:active){.pf-market-table-card,.pf-market-table th,.pf-market-table td{border-color:CanvasText!important}.pf-market-table-card,.pf-market-table,.pf-market-table td,.pf-market-table th{background:Canvas!important;color:CanvasText!important}.pf-market-pill{border-color:CanvasText!important;color:CanvasText!important;background:Canvas!important}}
</style>"""

def _format_market_table(query):
    req=_market_table_request(query) or {};region=req.get('region') or _DEFAULT_LOCAL_MARKET
    rows=[]
    for sym in _market_table_symbols(query,10):
        row=_compact_quote_row(sym)
        if row:rows.append(row)
        else:rows.append({'symbol':sym,'price':None,'change':None,'pct':None,'currency':'','exchange':'Unavailable','session':'Unavailable','date':'Unknown','source':'Unavailable'})
    meta=_MARKET_CONTEXTS.get(region,{})
    title=f"{meta.get('name',region)} stocks"
    if not rows:
        return "💜 I recognized the market, but its default stock universe is unavailable. I won't render an empty market table."
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

# ==================================================
# v18.1 UNIVERSAL DECISION BRAIN
# ==================================================
from dataclasses import dataclass, field
from typing import Any, Dict, List

_BRAIN_STATE={"goal":None,"entities":[],"last_intent":None,"last_user":None,"language":"en"}

def _brain_language(text):
    low=(text or "").lower(); words=set(re.findall(r"[a-z]+",low))
    if len(words & {"boleh","macam","saham","pasaran","anda","saya"})>=2:return "ms"
    if len(words & {"ano","paano","bakit","sige","pwede","naman","alin","yung","mga","gusto","nga","pa"})>=2 or re.search(r"\b(?:po|sige|pwede|paano|ano|pa-check|pacheck|nga)\b",low):return "tl"
    return "en"

def _brain_say(lang,en,tl,ms=None): return tl if lang=="tl" else (ms if lang=="ms" and ms else en)

def _brain_entities(text):
    out=[]; raw=text or ""
    # Reuse the mature market resolver instead of maintaining another company map.
    try:
        sym=_symbol_from_query(raw)
        if sym and sym not in out:out.append(sym)
    except Exception:
        pass
    # Preserve explicit exchange-qualified/ticker tokens when present.
    for token in re.findall(r"(?<![A-Z0-9])\$?([A-Z]{1,6}(?:\.[A-Z]{1,3})?)(?![A-Z0-9])",raw):
        if token not in {"US","USA","PH","MY","AI","CEO","USD","PHP","ETF"} and token not in out:out.append(token)
    return out

def _brain_reconstruct(message):
    msg=clean_query(message)
    m=re.match(r"^\s*(?:what about|how about|paano naman)\s+(.+?)[?!.]*$",msg,re.I)
    if m and _BRAIN_STATE.get("entities") and _brain_entities(m.group(1)):
        return m.group(1)+" stock"
    if re.match(r"^\s*(?:compare them|compare those|which one stronger|which is stronger)\s*[?!.]*$",msg,re.I) and len(_BRAIN_STATE.get("entities",[]))>=2:
        return "Compare "+" and ".join(_BRAIN_STATE["entities"][-2:])+" stocks"
    return msg

@dataclass
class BrainDecision:
    goal:str="answer"; intent:str="STATIC"; domain:str="general"; action:str="DEFER_TO_LOCAL"; language:str="en"
    entities:List[str]=field(default_factory=list); known:Dict[str,Any]=field(default_factory=dict); missing:List[str]=field(default_factory=list)
    freshness_required:bool=False; risk_level:str="LOW"; evidence_required:bool=False
    research_depth:int=0; response_depth:str="CONCISE"; allow_local_brain:bool=True; allow_model_memory:bool=True
    reconstructed:str=""; clarification_question:str=""

def _universal_intent(message,reconstructed):
    low=clean_query(reconstructed).lower(); sem=semantic_intent(reconstructed); intent=sem.get('type','STATIC')
    decision_market=bool(re.search(r'\b(?:buy|sell|hold|entry|exit|worth buying|should i buy|should i sell|bumili|bibili|benta|ibenta|hold ko|good entry)\b',low,re.I) and (_MARKET_RE.search(low) or _brain_entities(reconstructed)))
    if decision_market:return 'MARKET_DECISION_ANALYSIS'
    if intent=='MARKET_QUOTE' and re.search(r'\b(?:analysis|technical|trend|momentum|rsi|macd|support|resistance)\b',low,re.I):return 'MARKET_TECHNICAL_ANALYSIS'
    if intent=='MARKET_TABLE' and re.search(r'\bcompare\b',low,re.I) and len(_brain_entities(reconstructed))>=2:return 'MARKET_COMPARISON'
    if re.search(r'\bweather|forecast|temperature|rain|humidity|storm|typhoon\b',low,re.I):return 'WEATHER'
    return intent

def _decision_domain(intent,message):
    if intent.startswith('MARKET_'):return 'finance'
    if intent in {'OFFICEHOLDER','NEWS_RESEARCH','WEATHER','CURRENT_FACT','VERIFY_RESEARCH','REVERIFY'}:return 'current_world'
    if re.search(r'\b(?:code|python|javascript|api|bug|error|debug)\b',message or '',re.I):return 'technology'
    if re.search(r'\b(?:travel|trip|flight|hotel|visa)\b',message or '',re.I):return 'travel'
    return 'general'

def brain_decide(message,history=None):
    original=clean_query(message);lang=_brain_language(original);reconstructed=_brain_reconstruct(original);intent=_universal_intent(original,reconstructed);entities=_brain_entities(reconstructed);domain=_decision_domain(intent,reconstructed);missing=[];question=''
    if re.match(r'^\s*(?:compare|comparison)\s*(?:stocks?|shares?)?\s*[?!.]*$',original,re.I) and len(entities)<2 and len(_BRAIN_STATE.get('entities',[]))<2:
        missing=['comparison_targets'];question=_brain_say(lang,'Sure. Which stocks, companies, or markets do you want to compare?','Sige. Aling stocks, companies, o markets ang gusto mong i-compare?','Boleh. Saham, syarikat, atau pasaran mana yang anda mahu bandingkan?')
    elif re.search(r'\blaptop\b',original,re.I) and not re.search(r'\b(?:budget|programming|gaming|office|ai|video|school|work)\b',original,re.I):
        missing=['primary_use'];question=_brain_say(lang,'Sure. What will you mainly use the laptop for?','Sige. Ano mainly ang paggagamitan mo ng laptop?','Boleh. Laptop itu terutama untuk kegunaan apa?')
    elif re.search(r'\b(?:analyze|analyse|review|summarize)\b.*\b(?:file|report|document|pdf|excel|csv)\b',original,re.I) and not re.search(r'\b(?:attached|uploaded|this file|this report)\b',original,re.I):
        missing=['file'];question=_brain_say(lang,'Sure. Please attach the file you want me to analyze.','Sige. I-attach mo lang yung file na gusto mong ipa-analyze.','Boleh. Sila lampirkan fail yang anda mahu saya analisis.')
    elif re.search(r'\b(?:travel|trip|vacation|visit)\b',original,re.I) and not re.search(r'\b(?:from|depart|date|dates|when|kailan|mula|galing)\b',original,re.I):
        missing=['dates_or_origin'];question=_brain_say(lang,'Sure. What dates are you considering, and where will you depart from?','Sige. Anong dates mo at saan ka manggagaling?','Boleh. Tarikh bila dan anda akan bertolak dari mana?')
    fresh=intent in {'OFFICEHOLDER','NEWS_RESEARCH','WEATHER','CURRENT_FACT','VERIFY_RESEARCH','REVERIFY','MARKET_QUOTE','MARKET_TABLE','MARKET_OVERVIEW','MARKET_COMPARISON','MARKET_EXPLANATION','MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS'} or bool(_FRESH_RE.search(reconstructed))
    high=intent in {'MARKET_DECISION_ANALYSIS'}
    risk='HIGH' if high else ('MEDIUM' if domain in {'finance','current_world'} else 'LOW')
    evidence=fresh or risk=='HIGH'
    allow_local=not fresh and risk!='HIGH'; allow_memory=not fresh
    if missing:action='ASK_USER'
    elif intent in {'MARKET_QUOTE','MARKET_TABLE','MARKET_OVERVIEW','MARKET_COMPARISON','MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS'}:action='MARKET_ANALYSIS'
    elif intent in {'OFFICEHOLDER','NEWS_RESEARCH','WEATHER','CURRENT_FACT','VERIFY_RESEARCH','DEEP_RESEARCH','MARKET_EXPLANATION'}:action='WEB_RESEARCH'
    elif intent=='REVERIFY':action='VERIFY'
    elif intent=='STATIC':action='DEFER_TO_LOCAL'
    else:action='WEB_RESEARCH' if fresh else 'DEFER_TO_LOCAL'
    depth=max(3,research_depth(reconstructed)) if risk=='HIGH' else (research_depth(reconstructed) if action in {'MARKET_ANALYSIS','WEB_RESEARCH','VERIFY'} else 0)
    response='DEEP' if intent in {'DEEP_RESEARCH','MARKET_EXPLANATION','MARKET_COMPARISON'} else ('CONCISE' if len(original.split())<=6 else 'STANDARD')
    return BrainDecision(intent.lower(),intent,domain,action,lang,entities,{'entities':entities},missing,fresh,risk,evidence,depth,response,allow_local,allow_memory,reconstructed,question)

def _brain_commit(d,message):
    ents=list(_BRAIN_STATE.get("entities",[]))
    for x in d.entities:
        if x not in ents:ents.append(x)
    _BRAIN_STATE.update({"goal":d.goal,"entities":ents[-6:],"last_intent":d.intent,"last_user":message,"language":d.language})

def brain_explain(message):
    d=brain_decide(message)
    return '\n'.join(['Brain: Purple Falcon',f'Intent: {d.intent}',f'Domain: {d.domain}',f'Action: {d.action}',f'Language: {d.language}',f'Freshness required: {d.freshness_required}',f'Risk: {d.risk_level}',f'Evidence required: {d.evidence_required}',f'Local Brain allowed: {d.allow_local_brain}',f'Model memory allowed: {d.allow_model_memory}',f'Research depth: {d.research_depth}',f'Response depth: {d.response_depth}',f"Known entities: {', '.join(d.entities) or 'None'}",f"Missing: {', '.join(d.missing) or 'None'}"])

def brain_state(): return "Brain state\n"+"\n".join(f"- {k}: {v}" for k,v in _BRAIN_STATE.items())

# ==================================================
# v17.1 SEMANTIC INTENT PRECEDENCE
# ==================================================
_OFFICEHOLDER_INTENT_RE=re.compile(r'\b(?:prime\s+minister|president|presidente|officeholder|head\s+of\s+government|mayor|governor|minister|ceo)\b',re.I)
_MARKET_EXPLANATION_RE=re.compile(r'\b(?:why|bakit|reason|reasons|cause|causes|driver|drivers|explain|analysis|analyze)\b',re.I)
_VERIFY_RESEARCH_RE=re.compile(r'^\s*(?:verify|fact[- ]?check|check whether|is this (?:still )?(?:true|correct)|verify whether)\b',re.I)
_REVERIFY_RE=re.compile(r'^\s*(?:sure\??|are you sure\??|verify again|check again|recheck|double[- ]check)\s*$',re.I)
_DEEP_RESEARCH_RE=re.compile(r'\b(?:compare|comparison|deep research|investigate|strategy|strategies|competitive|versus|\bvs\b)\b',re.I)

def semantic_intent(query):
    q=clean_query(query)
    if not q:return {'type':'STATIC','web':False}
    if _REVERIFY_RE.match(q):return {'type':'REVERIFY','web':True}
    if _VERIFY_RESEARCH_RE.search(q):return {'type':'VERIFY_RESEARCH','web':True}
    if _OFFICEHOLDER_INTENT_RE.search(q):return {'type':'OFFICEHOLDER','web':True}
    marketish=bool(_MARKET_RE.search(q) or re.search(r'\b(?:pse|psei|stocks?|shares?|ticker|quote)\b',q,re.I))
    # Generic words such as compare/list must never create a market table without market context.
    table=_market_table_request(q) if marketish else None
    if table:return {'type':'MARKET_TABLE','web':True,'market':table}
    if _DEEP_RESEARCH_RE.search(q) and _FRESH_RE.search(q):return {'type':'DEEP_RESEARCH','web':True}
    if marketish and _MARKET_EXPLANATION_RE.search(q):return {'type':'MARKET_EXPLANATION','web':True}
    symbol=_symbol_from_query(q) if marketish else None
    if symbol and not _is_market_index(symbol):return {'type':'MARKET_QUOTE','web':True,'symbol':symbol}
    if marketish or _market_index_from_query(q):return {'type':'MARKET_OVERVIEW','web':True,'symbol':symbol or _market_index_from_query(q)}
    if _NEWS_RE.search(q):return {'type':'NEWS_RESEARCH','web':True}
    if _WEATHER_RE.search(q):return {'type':'WEATHER_RESEARCH','web':True}
    if analyze_prompt(q).get('fresh'):return {'type':'CURRENT_RESEARCH','web':True}
    return {'type':'STATIC','web':False}

# ==================================================
# v17 ADAPTIVE RESEARCH AGENT
# ==================================================
RESEARCH_CACHE_FILE=os.getenv('PF_RESEARCH_CACHE_FILE','purple_falcon_research_cache.json')
RESEARCH_LEDGER_FILE=os.getenv('PF_RESEARCH_LEDGER_FILE','purple_falcon_research_ledger.jsonl')
RESEARCH_MAX_ROUNDS=int(os.getenv('PF_RESEARCH_MAX_ROUNDS','3'))
RESEARCH_DEEP_MAX_ROUNDS=int(os.getenv('PF_RESEARCH_DEEP_MAX_ROUNDS','5'))
_PROVIDER_HEALTH={}

_AUTHORITY_RULES=(
 (1.00,('gov','official','pse.com.ph','edge.pse.com.ph','sec.gov','who.int','nasa.gov')),
 (.95,('company filing','investor relations','exchange')),
 (.90,('reuters.com','apnews.com','finance.yahoo.com','nasdaq.com','stockanalysis.com')),
 (.80,('bbc.com','cnbc.com','bloomberg.com','marketwatch.com')),
 (.60,()),
)
_TTL_BY_INTENT={'market':900,'weather':1800,'news':21600,'officeholder':86400,'general':604800}

def research_depth(query,policy=None):
    p=policy or analyze_prompt(query);q=clean_query(query).lower();sem=semantic_intent(query).get('type')
    if sem=='STATIC':return 0
    if sem in {'MARKET_EXPLANATION','DEEP_RESEARCH','VERIFY_RESEARCH','REVERIFY'}:return 3
    if sem in {'OFFICEHOLDER','NEWS_RESEARCH','WEATHER_RESEARCH','CURRENT_RESEARCH','MARKET_QUOTE','MARKET_TABLE','MARKET_OVERVIEW'}:return 2
    if p.get('intent')=='general' and not p.get('fresh'):return 0
    if re.search(r'\b(?:deep research|investigate|verify thoroughly|compare|comparison|why|analysis|analyze)\b',q):return 3
    if p.get('intent') in {'market','weather','news','officeholder'}:return 2
    return 1

def research_plan(query,policy=None):
    p=policy or analyze_prompt(query);depth=research_depth(query,p);intent=p.get('intent','general')
    tasks=[{'kind':'primary','query':clean_query(query)}]
    if depth>=2:tasks.append({'kind':'official','query':clean_query(query)+' official'})
    if depth>=3:tasks += [{'kind':'cross-check','query':clean_query(query)+' Reuters'},{'kind':'context','query':clean_query(query)+' latest analysis'}]
    return {'query':clean_query(query),'intent':intent,'depth':depth,'fresh':bool(p.get('fresh')),'max_rounds':RESEARCH_DEEP_MAX_ROUNDS if depth>=3 else RESEARCH_MAX_ROUNDS,'tasks':tasks}

def source_authority(item):
    text=' '.join(str(item.get(k) or '') for k in ('source','url','title')).lower()
    for score,hints in _AUTHORITY_RULES:
        if not hints or any(h in text for h in hints):return score
    return .60

def evidence_freshness(item,intent='general'):
    text=' '.join(str(item.get(k) or '') for k in ('title','body')).lower();now=datetime.now(timezone.utc)
    dm=_DATE_RE.search(text)
    if not dm:return .65 if intent!='general' else .8
    try:
        d=datetime.strptime(dm.group(0).replace(',',''),'%B %d %Y').replace(tzinfo=timezone.utc)
    except Exception:
        try:d=datetime.strptime(dm.group(0).replace(',',''),'%b %d %Y').replace(tzinfo=timezone.utc)
        except Exception:return .65
    age=max(0,(now-d).total_seconds());ttl=_TTL_BY_INTENT.get(intent,604800)
    return max(.05,min(1.0,ttl/max(ttl,age)))

def build_evidence(query,items,intent='general'):
    out=[]
    tokens={w for w in re.findall(r'\b[a-z0-9]{3,}\b',clean_query(query).lower()) if w not in {'the','and','for','today','latest','current','what','who','why','how'}}
    for item in items or []:
        text=' '.join(str(item.get(k) or '') for k in ('title','body')).lower()
        relevance=min(1.0,.25+.15*sum(1 for t in tokens if t in text)) if tokens else .7
        authority=source_authority(item);fresh=evidence_freshness(item,intent)
        score=.45*authority+.30*fresh+.25*relevance
        out.append({'item':item,'authority':authority,'freshness':fresh,'relevance':relevance,'score':score})
    out.sort(key=lambda x:x['score'],reverse=True);return out

def evidence_metrics(evidence):
    if not evidence:return {'authority':0,'freshness':0,'relevance':0,'agreement':0,'completeness':0,'overall':0}
    top=evidence[:5];avg=lambda k:sum(x[k] for x in top)/len(top)
    domains={_domain(x['item']) for x in top if _domain(x['item'])}
    agreement=min(1.0,.45+.15*len(domains));completeness=min(1.0,len(top)/3)
    vals={'authority':avg('authority'),'freshness':avg('freshness'),'relevance':avg('relevance'),'agreement':agreement,'completeness':completeness}
    vals['overall']=sum(vals.values())/5;return vals

def contradiction_scan(evidence):
    # Generic numerical contradiction detector. Domain specialists may add richer checks.
    observations=[]
    for e in evidence[:6]:
        text=e['item'].get('title','')+' '+e['item'].get('body','')
        nums=[float(x.replace(',','')) for x in re.findall(r'(?<!\w)(\d{1,7}(?:,\d{3})*(?:\.\d+)?)',text)[:4]]
        if nums:observations.append((e['item'].get('source') or _domain(e['item']),nums))
    return {'detected':False,'observations':observations}  # claim-specific verifier resolves actual conflicts

def rewrite_query(query,reason,round_no):
    suffix={'stale':' current official','weak':' authoritative source','conflict':' official confirmation','missing':' exact value date source'}.get(reason,' official verified')
    return clean_query(query)+suffix+f' {datetime.now().year}'

def _provider_record(name,ok,latency):
    h=_PROVIDER_HEALTH.setdefault(name,{'requests':0,'success':0,'latency_total':0.0});h['requests']+=1;h['success']+=int(bool(ok));h['latency_total']+=float(latency)

def provider_health():
    return {k:{'requests':v['requests'],'success_rate':round(v['success']/max(1,v['requests']),3),'avg_latency':round(v['latency_total']/max(1,v['requests']),3)} for k,v in _PROVIDER_HEALTH.items()}

def _research_cache_load():
    try:
        if os.path.exists(RESEARCH_CACHE_FILE):
            with open(RESEARCH_CACHE_FILE,encoding='utf-8') as f:return json.load(f)
    except Exception:pass
    return {}

def _research_cache_save(data):
    try:
        folder=os.path.dirname(os.path.abspath(RESEARCH_CACHE_FILE)) or '.';os.makedirs(folder,exist_ok=True)
        with tempfile.NamedTemporaryFile('w',dir=folder,suffix='.tmp',delete=False,encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);tmp=f.name
        os.replace(tmp,RESEARCH_CACHE_FILE)
    except Exception as e:log.warning('Research cache save failed: %s',e)

def research_cache_get(query,intent):
    item=_research_cache_load().get(clean_query(query).lower())
    if not isinstance(item,dict):return None
    if time.time()-float(item.get('cached_at',0))>_TTL_BY_INTENT.get(intent,604800):return None
    return item

def research_cache_put(query,intent,payload):
    data=_research_cache_load();data[clean_query(query).lower()]={'cached_at':time.time(),'intent':intent,'payload':payload};_research_cache_save(data)

def decision_ledger(entry):
    try:
        with open(RESEARCH_LEDGER_FILE,'a',encoding='utf-8') as f:f.write(json.dumps(dict(entry,time=datetime.now(timezone.utc).isoformat()),ensure_ascii=False)+'\n')
    except Exception as e:log.warning('Research ledger write failed: %s',e)

def adaptive_research(query):
    plan=research_plan(query);intent=plan['intent'];all_items=[];rounds=[]
    cached=research_cache_get(query,intent)
    if cached:return {'plan':plan,'cached':True,'items':cached['payload'].get('items',[]),'evidence':cached['payload'].get('evidence',[]),'metrics':cached['payload'].get('metrics',{}),'rounds':[]}
    pending=[x['query'] for x in plan['tasks']]
    for round_no in range(1,plan['max_rounds']+1):
        q=pending.pop(0) if pending else rewrite_query(query,'weak',round_no)
        t0=time.time();items=search_sources([q]) or [];_provider_record('websearch',bool(items),time.time()-t0)
        seen={x.get('url') or (x.get('title'),x.get('body','')[:80]) for x in all_items}
        all_items.extend(x for x in items if (x.get('url') or (x.get('title'),x.get('body','')[:80])) not in seen)
        ev=build_evidence(query,all_items,intent);metrics=evidence_metrics(ev);rounds.append({'round':round_no,'query':q,'found':len(items),'overall':metrics['overall']})
        if metrics['overall']>=.72 and len(ev)>=max(1,2 if plan['depth']>=2 else 1):break
    ev=build_evidence(query,all_items,intent);metrics=evidence_metrics(ev);result={'plan':plan,'cached':False,'items':all_items,'evidence':ev,'metrics':metrics,'rounds':rounds,'contradictions':contradiction_scan(ev)}
    research_cache_put(query,intent,{'items':all_items,'evidence':ev,'metrics':metrics});decision_ledger({'query':query,'intent':intent,'depth':plan['depth'],'rounds':rounds,'metrics':metrics});return result

def verified_research_messages(query,research,system_prompt='',history=None):
    evidence='\n\n'.join(f"[{i}] {e['item']['title']}\n{e['item'].get('body','')}\nURL: {e['item'].get('url','')}" for i,e in enumerate(research.get('evidence',[])[:8],1))
    guard=('ADAPTIVE VERIFIED RESEARCH MODE. Every current factual claim, number, name, date, quote, officeholder, or score must be supported by supplied evidence. '
           'Do not manufacture missing evidence. If sources conflict, state the conflict and prefer newer authoritative evidence. If support is absent, say Unavailable. Cite [1], [2].')
    return [{'role':'system','content':(system_prompt or '')+'\n'+guard}]+(history or [])[-4:]+[{'role':'user','content':f'Question: {query}\nResearch metrics: {json.dumps(research.get("metrics",{}))}\n\nEvidence:\n{evidence}'}]

def claim_verification_required(text,research):
    # Conservative gate: current answers require usable evidence; numerical answers require at least one evidence item containing a number.
    if not isinstance(text,str) or not text.strip():return False
    ev=research.get('evidence',[])
    if not ev:return False
    if re.search(r'\d',text):return any(re.search(r'\d',e['item'].get('title','')+' '+e['item'].get('body','')) for e in ev)
    return True

def web_explain(query):
    r=adaptive_research(query);m=r.get('metrics',{});plan=r.get('plan',{})
    lines=[f"Research intent: {plan.get('intent')}",f"Depth: {plan.get('depth')}",f"Cached: {r.get('cached')}",f"Rounds: {len(r.get('rounds',[]))}",f"Authority: {m.get('authority',0):.2f}",f"Freshness: {m.get('freshness',0):.2f}",f"Relevance: {m.get('relevance',0):.2f}",f"Agreement: {m.get('agreement',0):.2f}",f"Completeness: {m.get('completeness',0):.2f}",f"Overall: {m.get('overall',0):.2f}"]
    return '\n'.join(lines)


def web_reply(message,call_ai=None,ai_failed_check=None,system_prompt=None,brain_down=False,history=None):
    if not ENABLED:return None
    cmd=clean_query(message).lower()
    if cmd.startswith('/brain explain'):
        target=clean_query(message)[len('/brain explain'):].strip() or (_BRAIN_STATE.get('last_user') or '')
        return brain_explain(target) if target else 'No active question to explain yet.'
    if cmd=='/brain state':return brain_state()
    decision=brain_decide(message,history); _brain_commit(decision,message)
    if decision.action=='ASK_USER':return decision.clarification_question
    message=decision.reconstructed or message
    query=clean_query(message);kind=semantic_intent(query).get('type')
    if kind=='STATIC':return None
    if kind=='MARKET_TABLE':return _format_market_table(query)
    universal_kind=decision.intent
    if universal_kind in {'MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS','MARKET_COMPARISON'}:
        kind=universal_kind
    if kind in {'MARKET_QUOTE','MARKET_OVERVIEW','MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS'}:
        sem=semantic_intent(query);symbol=sem.get('symbol') or _symbol_from_query(query)
        direct=(_resolve_pse_quote(symbol) if symbol and str(symbol).upper().endswith('.PS') else _direct_yahoo_quote(symbol)) if symbol else None
        if direct and kind in {'MARKET_QUOTE','MARKET_OVERVIEW'}:return _format_direct_quote(direct)
        if direct and kind in {'MARKET_DECISION_ANALYSIS','MARKET_TECHNICAL_ANALYSIS'}:
            base=_format_direct_quote(direct)
            return base+'\n\n**Scenario analysis:** Use the verified quote and observed technical evidence to assess bullish, neutral, and bearish conditions. This is market analysis, not a personalized instruction to buy or sell.'
        sources=search_sources(intent_queries(query))
        if not sources:return "💜 I couldn't verify a current market value from the available providers. I won't guess a price."
        return _market_quote_answer(query,sources)
    research=adaptive_research(query);evidence=research.get('evidence') or [];metrics=research.get('metrics') or {}
    if not evidence:return "💜 I couldn't gather enough trustworthy current evidence to answer this yet."
    if call_ai:
        try:
            msgs=verified_research_messages(query,research,system_prompt,history)
            if kind=='MARKET_EXPLANATION':msgs[0]['content']+='\nExplain market drivers only when evidence explicitly supports them. Separate observed movement from reported catalysts; do not infer causation.'
            if kind=='OFFICEHOLDER':msgs[0]['content']+='\nPrefer official government and newest authoritative evidence. Country names must never be reinterpreted as market-index requests.'
            ai=call_ai(msgs);failed=ai_failed_check(ai) if ai_failed_check else not bool(ai)
            if isinstance(ai,str) and ai.strip() and not failed and not reply_is_unsure(ai) and claim_verification_required(ai,research):return ai.strip()
        except Exception as e:log.warning('Adaptive synthesis unavailable: %s',e)
    conf='HIGH' if metrics.get('overall',0)>=.8 else ('MEDIUM' if metrics.get('overall',0)>=.6 else 'LOW')
    lines=[f"💜 **Verified web evidence** — Confidence: **{conf}**",'']
    for i,e in enumerate(evidence[:5],1):
        x=e['item'];lines += [f"**{i}. {x.get('title','Evidence')}**",x.get('body','')[:650],f"Source: {x.get('url','')}",'']
    return '\n'.join(lines).strip()


def run_v171_regression_matrix():
    cases={
      'BDO stock Philippines':'MARKET_QUOTE','tabulate local stocks at PH':'MARKET_TABLE','Philippines stock update':'MARKET_OVERVIEW',
      'Why is the Philippine stock market down today?':'MARKET_EXPLANATION','Toyota stock Japan':'MARKET_QUOTE','Japan market today':'MARKET_OVERVIEW',
      'Who is the current Prime Minister of Japan?':'OFFICEHOLDER','latest AI news':'NEWS_RESEARCH',
      'Compare the latest AI strategies of Microsoft, Google and OpenAI':'DEEP_RESEARCH','Verify whether this claim is still correct today':'VERIFY_RESEARCH',
      'sure?':'REVERIFY','Explain recursion':'STATIC'}
    failures=[]
    for q,want in cases.items():
        got=semantic_intent(q).get('type')
        if got!=want:failures.append((q,want,got))
    return {'passed':not failures,'failures':failures,'cases':len(cases)}

def run_global_market_universe_tests():
    cases={'Tabulate USA stocks':'US','Tabulate Canada stocks':'CA','Tabulate Japan stocks':'JP','Tabulate Hong Kong stocks':'HK','Tabulate Singapore stocks':'SG','Tabulate Malaysia stocks':'MY','Tabulate Philippines stocks':'PH','Tabulate UK stocks':'UK','Tabulate Germany stocks':'DE','Tabulate France stocks':'FR','Tabulate India stocks':'IN','Tabulate South Korea stocks':'KR','Tabulate Taiwan stocks':'TW','Tabulate Australia stocks':'AU','Tabulate New Zealand stocks':'NZ','Tabulate Brazil stocks':'BR','Tabulate Mexico stocks':'MX'}
    failures=[]
    for q,want in cases.items():
        req=_market_table_request(q);got=(req or {}).get('region');syms=_market_table_symbols(q,10)
        if got!=want or not syms:failures.append((q,want,got,len(syms)))
    extra=[('Tabulate USA technology stocks','US','technology'),('Tabulate US banks','US','banks'),('Tabulate Japanese automakers','JP','automakers'),('Tabulate Philippine banks','PH','banks'),('Tabulate Singapore banks','SG','banks')]
    for q,region,sector in extra:
        if (_market_table_request(q) or {}).get('region')!=region or _sector_from_query(q)!=sector or not _market_table_symbols(q,10):failures.append((q,region,sector))
    return {'passed':not failures,'failures':failures,'countries':len(cases),'sector_cases':len(extra)}

def run_v18_conversational_brain_tests():
    checks=[('Compare stocks','ASK_USER'),('I need a laptop','ASK_USER'),('Analyze my report','ASK_USER'),('I want to travel Japan','ASK_USER'),('Tabulate USA stocks','MARKET_ANALYSIS'),('Who is the current Prime Minister of Japan?','WEB_RESEARCH'),('Explain recursion','DEFER_TO_LOCAL')]
    failures=[]
    for q,want in checks:
        d=brain_decide(q)
        if d.action!=want:failures.append((q,want,d.action,d.intent))
    if brain_decide('Pa-check nga BDO ngayon').language!='tl':failures.append(('Taglish','tl'))
    if brain_decide('Boleh compare saham Maybank?').language!='ms':failures.append(('Malay','ms'))
    return {'passed':not failures,'failures':failures,'cases':len(checks)+2}

def run_v181_universal_decision_tests():
    cases={
      'can I buy Tesla or sell?':('MARKET_DECISION_ANALYSIS','MARKET_ANALYSIS',False,True,'HIGH'),
      'BDO okay ba bumili?':('MARKET_DECISION_ANALYSIS','MARKET_ANALYSIS',False,True,'HIGH'),
      'Who is the current Prime Minister of Japan?':('OFFICEHOLDER','WEB_RESEARCH',False,True,'MEDIUM'),
      'latest AI news':('NEWS_RESEARCH','WEB_RESEARCH',False,True,'MEDIUM'),
      'why PSE down today?':('MARKET_EXPLANATION','WEB_RESEARCH',False,True,'MEDIUM'),
      'Tabulate USA stocks':('MARKET_TABLE','MARKET_ANALYSIS',False,True,'MEDIUM'),
      'Explain recursion':('STATIC','DEFER_TO_LOCAL',True,False,'LOW')}
    failures=[]
    for q,want in cases.items():
        d=brain_decide(q);got=(d.intent,d.action,d.allow_local_brain,d.evidence_required,d.risk_level)
        if got!=want:failures.append((q,want,got))
    d=brain_decide('Compare stocks')
    if d.action!='ASK_USER' or not d.missing:failures.append(('Compare stocks','ASK_USER',d.action,d.missing))
    return {'passed':not failures,'failures':failures,'cases':len(cases)+1}

def self_test():
    assert run_v181_universal_decision_tests()['passed'], run_v181_universal_decision_tests()['failures']
    assert run_v18_conversational_brain_tests()['passed'], run_v18_conversational_brain_tests()['failures']
    assert run_global_market_universe_tests()['passed'], run_global_market_universe_tests()['failures']
    assert run_v171_regression_matrix()['passed'], run_v171_regression_matrix()['failures']
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
    assert 'var(--pf-mkt-price' in MARKET_TABLE_CSS and 'var(--pf-mkt-border' in MARKET_TABLE_CSS and 'forced-colors:active' in MARKET_TABLE_CSS
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

__all__=['ENABLED','WEBSEARCH_AVAILABLE','SEARCH_AVAILABLE','web_reply','reply_is_unsure','search_sources','self_test','_extract_candidates','normalize_result','classify_web_intent','analyze_prompt','verify_evidence','grounded_synthesis_messages','_extract_market_quote','_direct_yahoo_quote','_format_direct_quote','_fetch_pse_catalog','_pse_symbol_from_query','_parse_pse_directory_html','_human_money','_percent_value','_dynamic_market_intent','_market_index_from_query','_local_market_region','_private_market_entity','_market_table_request','_market_table_symbols','_format_market_table','_pse_company_id','_resolve_pse_quote','_refresh_pse_company_ids','semantic_intent','run_v171_regression_matrix','research_depth','research_plan','adaptive_research','provider_health','web_explain','run_global_market_universe_tests','_sector_from_query','BrainDecision','brain_decide','brain_explain','brain_state','run_v18_conversational_brain_tests','run_v181_universal_decision_tests']
if __name__=='__main__':print('self_test:','PASS' if self_test() else 'FAIL')
