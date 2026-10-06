# Purple Falcon WebReason v14.0 - Verified Market Quote Mode
import os, re, json, logging, tempfile, time, csv, io
import requests
from html import unescape
from datetime import datetime, timezone
from urllib.parse import urlparse

APP_NAME='Purple Falcon PH'; VERSION='15.3.0'
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

_MARKET_RE=re.compile(r'\b(?:stock|share|shares|price|quote|market|trading|ticker|nasdaq|nyse|after[- ]hours|pre[- ]market|overnight)\b',re.I)
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

def classify_web_intent(q):
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
    pse=_pse_symbol_from_query(q)
    if pse:return pse
    intl=_resolve_international_alias(q)
    if intl:return intl
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
    if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',symbol): return None
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

def _history_yahoo(symbol,range_='1y',interval='1d'):
    """Fetch observed daily OHLCV history used only for deterministic indicators."""
    symbol=(symbol or '').upper().strip()
    if not re.fullmatch(r'[A-Z0-9.\-]{1,16}',symbol):return None
    try:
        r=requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}',params={'interval':interval,'range':range_,'includePrePost':'false'},headers={'User-Agent':'Mozilla/5.0 PurpleFalcon/14.9'},timeout=8)
        if r.status_code!=200:return None
        result=((r.json().get('chart') or {}).get('result') or [None])[0]
        if not isinstance(result,dict):return None
        ts=result.get('timestamp') or [];quote=(((result.get('indicators') or {}).get('quote') or [{}])[0]);closes=((((result.get('indicators') or {}).get('adjclose') or [{}])[0]).get('adjclose') or quote.get('close') or [])
        volumes=quote.get('volume') or []
        rows=[]
        for i,t in enumerate(ts):
            c=closes[i] if i<len(closes) else None;v=volumes[i] if i<len(volumes) else None
            if isinstance(c,(int,float)):rows.append({'timestamp':int(t),'close':float(c),'volume':float(v) if isinstance(v,(int,float)) else None})
        return rows or None
    except Exception as e:log.warning('Yahoo history failed: %s',e);return None

def _sma(values,n):
    return sum(values[-n:])/n if len(values)>=n else None

def _ema_series(values,n):
    if len(values)<n:return []
    k=2/(n+1);out=[];ema=sum(values[:n])/n
    for i,x in enumerate(values):
        if i<n-1:out.append(None)
        elif i==n-1:out.append(ema)
        else:ema=x*k+ema*(1-k);out.append(ema)
    return out

def _rsi14(values):
    if len(values)<15:return None
    changes=[values[i]-values[i-1] for i in range(1,len(values))][-14:];gain=sum(max(x,0) for x in changes)/14;loss=sum(max(-x,0) for x in changes)/14
    if loss==0:return 100.0
    rs=gain/loss;return 100-(100/(1+rs))

def _macd(values):
    e12=_ema_series(values,12);e26=_ema_series(values,26)
    pairs=[(a-b) for a,b in zip(e12,e26) if a is not None and b is not None]
    if len(pairs)<9:return (None,None,None)
    signal=_ema_series(pairs,9)[-1];macd=pairs[-1]
    return (macd,signal,macd-signal if signal is not None else None)

def _scenario_levels_from_closes(closes):
    if not closes or len(closes)<20:return None
    recent=[float(x) for x in closes[-20:]];price=recent[-1];support=min(recent);resistance=max(recent);range20=resistance-support
    sma20=sum(recent)/20;buffer=(range20*0.02) if range20>0 else price*0.005
    return {'Pullback reference':sma20 if sma20>support else support,'Breakout confirmation':resistance+buffer,'Invalidation / risk reference':support-buffer,'Upside reference 1':resistance+range20*0.5,'Upside reference 2':resistance+range20}

def _market_signal(symbol):
    rows=_history_yahoo(symbol)
    if not rows or len(rows)<50:return {'signal':'⚪ INSUFFICIENT DATA','risk':'Unknown','reason':'At least 50 daily closes are required','indicators':{}}
    closes=[r['close'] for r in rows];vols=[r['volume'] for r in rows if r['volume'] is not None];price=closes[-1]
    sma20=_sma(closes,20);sma50=_sma(closes,50);sma200=_sma(closes,200);rsi=_rsi14(closes);macd,macd_sig,hist=_macd(closes);v20=_sma(vols,20) if vols else None;vol=rows[-1]['volume'];support=min(closes[-20:]);resistance=max(closes[-20:])
    score=0;reasons=[]
    if sma20 is not None:score += 1 if price>sma20 else -1;reasons.append('price above SMA20' if price>sma20 else 'price below SMA20')
    if sma50 is not None:score += 1 if sma20 and sma20>sma50 else -1;reasons.append('SMA20 above SMA50' if sma20 and sma20>sma50 else 'SMA20 not above SMA50')
    if rsi is not None:
        if 50<=rsi<=70:score+=1;reasons.append('RSI supports positive momentum')
        elif rsi<40:score-=1;reasons.append('RSI shows weak momentum')
        elif rsi>75:reasons.append('RSI is elevated/overbought')
    if hist is not None:score += 1 if hist>0 else -1;reasons.append('MACD histogram positive' if hist>0 else 'MACD histogram negative')
    if vol is not None and v20 is not None and vol>v20*1.2:reasons.append('volume above 20-day average')
    signal='🟢 BULLISH' if score>=2 else '🔴 BEARISH' if score<=-2 else '🟡 NEUTRAL'
    risk='High' if (rsi is not None and (rsi>75 or rsi<30)) else 'Medium'
    # Technical scenario levels, not personalized buy/sell instructions.
    recent=closes[-20:]
    range20=max(recent)-min(recent) if recent else None
    buffer=(range20*0.02) if range20 and range20>0 else (price*0.005)
    breakout_entry=(resistance+buffer) if resistance is not None else None
    pullback_entry=(sma20 if sma20 is not None and sma20>support else support)
    invalidation=(support-buffer) if support is not None else None
    target1=(resistance + range20*0.5) if resistance is not None and range20 else None
    target2=(resistance + range20) if resistance is not None and range20 else None
    return {'signal':signal,'risk':risk,'reason':'; '.join(reasons[:4]),'indicators':{'SMA20':sma20,'SMA50':sma50,'SMA200':sma200,'RSI14':rsi,'MACD':macd,'MACD_signal':macd_sig,'MACD_hist':hist,'Volume':vol,'Volume20':v20,'Support20':support,'Resistance20':resistance},'scenario_levels':{'Pullback reference':pullback_entry,'Breakout confirmation':breakout_entry,'Invalidation / risk reference':invalidation,'Upside reference 1':target1,'Upside reference 2':target2}}

def _position_size_scenarios(sig,portfolio_values=(25000,50000,100000,250000,500000),risk_budgets=(0.25,0.50,1.00)):
    """Deterministic educational scenario matrix. Values are illustrative, not personalized sizing advice."""
    levels=(sig or {}).get('scenario_levels') or {}
    entry=levels.get('Pullback reference'); invalid=levels.get('Invalidation / risk reference')
    if not isinstance(entry,(int,float)) or not isinstance(invalid,(int,float)) or entry<=invalid:return None
    risk_per_unit=entry-invalid; rows=[]
    for portfolio in portfolio_values:
        row={'portfolio':float(portfolio),'units':{}}
        for pct in risk_budgets:
            risk_capital=float(portfolio)*(float(pct)/100.0)
            row['units'][float(pct)]=risk_capital/risk_per_unit
        rows.append(row)
    return {'entry':entry,'invalidation':invalid,'risk_per_unit':risk_per_unit,'portfolio_values':list(portfolio_values),'risk_budgets':list(risk_budgets),'rows':rows}

def _spark_bar(value,max_value,width=18):
    if not isinstance(value,(int,float)) or max_value<=0:return '—'
    n=max(1,min(width,int(round(value/max_value*width))))
    return '█'*n + '░'*(width-n)

def _position_size_csv(sig,symbol='MARKET'):
    """CSV export text for the same deterministic position-size scenarios shown in chat."""
    sc=_position_size_scenarios(sig)
    if not sc:return None
    buf=io.StringIO();w=csv.writer(buf,lineterminator='\n')
    w.writerow(['symbol','portfolio_value','risk_budget_percent','reference_entry','invalidation_reference','risk_per_unit','illustrative_units'])
    for row in sc['rows']:
        for pct in sc['risk_budgets']:
            w.writerow([symbol,f"{row['portfolio']:.2f}",f"{pct:.2f}",f"{sc['entry']:.4f}",f"{sc['invalidation']:.4f}",f"{sc['risk_per_unit']:.4f}",f"{row['units'][pct]:.4f}"])
    levels=(sig or {}).get('scenario_levels') or {}
    w.writerow([]);w.writerow(['technical_level','value'])
    for name in ('Pullback reference','Breakout confirmation','Invalidation / risk reference','Upside reference 1','Upside reference 2'):
        v=levels.get(name);w.writerow([name,'' if v is None else f'{v:.4f}'])
    return buf.getvalue()

def export_position_size_csv(sig,symbol='MARKET',directory=None):
    """Write a safe CSV artifact. Host/UI may expose the returned path as a download."""
    data=_position_size_csv(sig,symbol)
    if not data:return None
    directory=directory or os.getenv('PF_EXPORT_DIR','.')
    os.makedirs(directory,exist_ok=True)
    safe=re.sub(r'[^A-Z0-9._-]+','_',str(symbol or 'MARKET').upper())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    path=os.path.join(directory,f'purple_falcon_{safe}_position_scenarios_{stamp}.csv')
    with open(path,'w',encoding='utf-8',newline='') as f:f.write(data)
    return path

def _csv_export_preview(sig,symbol='MARKET'):
    data=_position_size_csv(sig,symbol)
    if not data:return ''
    return '\n'.join(['','**CSV export available:** position-size scenarios and technical levels are export-ready.','Use `export_position_size_csv(...)` from the host integration to create the downloadable `.csv` file.'])

def _position_size_plot(sig):
    """Portable Markdown/text plots render directly in chat without image-file plumbing."""
    sc=_position_size_scenarios(sig)
    if not sc:return '\n\n**Position-size scenarios:** Unavailable until valid entry/invalidation references exist.'
    all_units=[u for r in sc['rows'] for u in r['units'].values()]; mx=max(all_units) if all_units else 1
    lines=['','**Position-size scenarios (illustrative units)**','', '```text']
    for pct in sc['risk_budgets']:
        lines.append(f'Risk budget {pct:.2f}%')
        for row in sc['rows']:
            units=row['units'][pct]
            lines.append(f"{row['portfolio']:>9,.0f} | {_spark_bar(units,mx)} {units:,.2f} units")
        lines.append('')
    lines.append('```')
    levels=(sig or {}).get('scenario_levels') or {}
    plotted=[('Invalidation',levels.get('Invalidation / risk reference')),('Pullback',levels.get('Pullback reference')),('Breakout',levels.get('Breakout confirmation')),('Upside 1',levels.get('Upside reference 1')),('Upside 2',levels.get('Upside reference 2'))]
    vals=[v for _,v in plotted if isinstance(v,(int,float))]
    if vals:
        lo,hi=min(vals),max(vals);span=max(hi-lo,1e-9);width=36
        lines += ['','**Technical level map**','', '```text']
        for name,val in plotted:
            if not isinstance(val,(int,float)):continue
            pos=max(0,min(width,int(round((val-lo)/span*width))))
            lines.append(f"{name:<12} |"+' '*pos+'● '+f'{val:.2f}')
        lines.append('```')
    lines.append('Plots are educational scenario visualizations. They do not account for personal portfolio constraints or recommend a trade size.')
    return '\n'.join(lines)

def _position_sizing_guidance(sig):
    """Educational risk-budget examples only. Does not know the user's portfolio or recommend a trade size."""
    levels=(sig or {}).get('scenario_levels') or {}
    entry=levels.get('Pullback reference')
    invalid=levels.get('Invalidation / risk reference')
    if not isinstance(entry,(int,float)) or not isinstance(invalid,(int,float)) or entry<=invalid:
        return '\n'.join(['','| Position Sizing Guide | Value |','|---|---:|','| Risk per unit | Unavailable |','| Example risk budgets | 0.25% / 0.50% / 1.00% |','','Position sizing is unavailable until a valid technical reference and invalidation level exist.'])
    risk_per_unit=entry-invalid
    risk_pct=(risk_per_unit/entry*100) if entry else None
    lines=['','| Position Sizing Guide | Value |','|---|---:|',f'| Reference entry | {entry:.2f} |',f'| Invalidation reference | {invalid:.2f} |',f'| Risk per unit | {risk_per_unit:.2f} |',f'| Price risk | {risk_pct:.2f}% |' if risk_pct is not None else '| Price risk | Unavailable |','', '| Example Portfolio Risk Budget | Position Formula |','|---:|---|']
    for pct in (0.25,0.50,1.00):
        lines.append(f'| {pct:.2f}% | Units = (Portfolio Value × {pct/100:.4f}) ÷ {risk_per_unit:.2f} |')
    lines += ['', '**Worked example (illustrative only):** For a 100,000 portfolio and 0.50% risk budget, risk capital = 500.00; illustrative units = '+f'{500/risk_per_unit:.2f}'+'.', 'This is educational risk-budget math, not a personalized recommendation. Actual sizing must account for fees, slippage, lot sizes, currency conversion, liquidity, taxes, leverage, and the possibility of gaps beyond the invalidation level.']
    return '\n'.join(lines)

def _signal_table(symbol):
    sig=_market_signal(symbol);i=sig.get('indicators') or {}
    fmt=lambda x: f'{x:.2f}' if isinstance(x,(int,float)) else 'Unavailable'
    if sig['signal']=='⚪ INSUFFICIENT DATA':return '\n'.join(['','| Market Signal | Risk | Reason |','|---|---|---|',f"| {sig['signal']} | {sig['risk']} | {_md_cell(sig['reason'])} |"])
    levels=sig.get('scenario_levels') or {}
    technical='\n'.join(['','| Market Signal | Trend | Momentum | Risk |','|---|---|---|---|',f"| {sig['signal']} | {'Up' if (i.get('SMA20') and i.get('SMA50') and i['SMA20']>i['SMA50']) else 'Down / Mixed'} | RSI {fmt(i.get('RSI14'))}, MACD hist {fmt(i.get('MACD_hist'))} | {sig['risk']} |",'', '| Technical Reference | Value |','|---|---:|',f"| SMA20 | {fmt(i.get('SMA20'))} |",f"| SMA50 | {fmt(i.get('SMA50'))} |",f"| SMA200 | {fmt(i.get('SMA200'))} |",f"| 20-day support | {fmt(i.get('Support20'))} |",f"| 20-day resistance | {fmt(i.get('Resistance20'))} |",'', '| Technical Scenario Level | Value |','|---|---:|',f"| Pullback reference | {fmt(levels.get('Pullback reference'))} |",f"| Breakout confirmation | {fmt(levels.get('Breakout confirmation'))} |",f"| Invalidation / risk reference | {fmt(levels.get('Invalidation / risk reference'))} |",f"| Upside reference 1 | {fmt(levels.get('Upside reference 1'))} |",f"| Upside reference 2 | {fmt(levels.get('Upside reference 2'))} |",'',f"**Signal rationale:** {_md_cell(sig['reason'])}",'**Interpretation:** These are technical scenario references derived from observed price history, not personalized instructions to buy, sell, enter, exit, or set a stop.'])
    return technical + _position_sizing_guidance(sig) + _position_size_plot(sig) + _csv_export_preview(sig,symbol)

def _parse_utc_timestamp(value):
    if not value:return None
    try:return datetime.strptime(value,'%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
    except Exception:return None

def _quote_freshness(q,now=None):
    """Classify quote freshness from the market quote timestamp, never HTTP retrieval time."""
    now=now or datetime.now(timezone.utc)
    ts=_parse_utc_timestamp((q or {}).get('timestamp_utc'))
    if not ts:return {'label':'⚠️ UNKNOWN','age_seconds':None,'age_text':'timestamp unknown'}
    age=max(0,(now-ts).total_seconds())
    session=((q or {}).get('session') or '').lower()
    if age<=60: label='🟢 LIVE'
    elif age<=15*60: label='🟡 RECENT'
    elif age<=24*3600: label='🟠 DELAYED'
    else: label='⚪ LAST CLOSE' if ('close' in session or 'regular' in session) else '🟠 STALE'
    if age<60: text=f'{int(age)} sec ago'
    elif age<3600: text=f'{int(age//60)} min ago'
    elif age<86400: text=f'{age/3600:.1f} hr ago'
    else:text=f'{age/86400:.1f} d ago'
    return {'label':label,'age_seconds':age,'age_text':text}

def _md_cell(value):
    return str(value if value is not None else 'Unavailable').replace('|','\\|').replace('\n',' ')

def _format_direct_quote(q):
    """Compact market card: headline metrics first, supporting metadata second."""
    if not q:return None
    currency=q.get('currency') or 'USD'
    price=f"{q['price']:.2f} {currency}" if q.get('price') is not None else 'Unavailable'
    change=(f"{q['change']:+.2f} ({q['change_percent']:+.2f}%)" if q.get('change') is not None and q.get('change_percent') is not None else 'Unavailable')
    market_cap=_human_money(q.get('market_cap'),currency) if q.get('market_cap') is not None else 'Unavailable'
    dividend=(f"{q['dividend_rate']:.4g} {currency}" if q.get('dividend_rate') is not None else 'Unavailable')
    div_yield=_percent_value(q.get('dividend_yield')) if q.get('dividend_yield') is not None else 'Unavailable'
    previous=f"{q['previous_close']:.2f} {currency}" if q.get('previous_close') is not None else 'Unavailable'
    freshness=_quote_freshness(q)
    lines=[
      f"💜 **{_md_cell(q.get('symbol') or 'Market')} market update**",'',
      '| Price | Change | Market Cap | Dividend | Yield |',
      '|---:|---:|---:|---:|---:|',
      f"| {_md_cell(price)} | {_md_cell(change)} | {_md_cell(market_cap)} | {_md_cell(dividend)} | {_md_cell(div_yield)} |",'',
      '| Status | Session | Previous Close | Exchange | Currency |',
      '|---|---|---:|---|---|',
      f"| {_md_cell(freshness['label'])} | {_md_cell((q.get('session') or 'Unavailable').title())} | {_md_cell(previous)} | {_md_cell(q.get('exchange') or 'Unavailable')} | {_md_cell(currency)} |",'',
      f"**Quote time:** {_md_cell(q.get('timestamp_utc') or 'Unavailable')}",
      f"**Updated:** {_md_cell(freshness['age_text'])}",
      f"**Source:** {_md_cell(q.get('source') or 'Unavailable')}",
      q.get('source_url') or '',
      f"**Retrieved:** {_md_cell(q.get('observed_at') or 'Unavailable')}",
      'Market data may be delayed. Use the session and quote timestamp above.'
    ]
    base='\n'.join(x for x in lines if x!='')
    return base + _signal_table(q.get('symbol'))

def _market_quote_answer(query,items):
    q=_extract_market_quote(query,items)
    if q['price'] is None:
        return "💜 I searched current market sources, but I couldn't extract a reliable current quote from the retrieved evidence. I won't guess a price."
    price=f"{q['price']:.2f} USD"
    session=(q.get('session') or 'latest observed quote').title()
    lines=[f"💜 **{_md_cell(q.get('symbol') or 'Market')} market update**",'',
           '| Price | Change | Volume | Status | Session |','|---:|---:|---:|---|---|',
           f"| {_md_cell(price)} | {_md_cell(q.get('change_percent') or 'Unavailable')} | {_md_cell(q.get('volume') or 'Unavailable')} | ⚠️ SOURCE-TIMED | {_md_cell(session)} |",'',
           f"**Quote date/time:** {_md_cell(' '.join(x for x in (q.get('as_of_date'),q.get('as_of_time')) if x) or 'Unavailable')}",
           f"**Source:** {_md_cell(q.get('source') or 'Unavailable')}",q.get('source_url') or '',
           'Market data may be delayed. Use the quote date/time above.']
    return '\n'.join(x for x in lines if x!='')

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
        symbol=_symbol_from_query(query)
        direct=_direct_yahoo_quote(symbol) if symbol else None
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
    ans=_market_quote_answer('Tesla stock price now',[y]);assert '378.73 USD' in ans and '$185.12' not in ans and '| Price | Change | Volume | Status | Session |' in ans
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
    fixture='<table><tr><th>Company Name</th><th>Stock Symbol</th></tr><tr><td>Test Philippine Corp.</td><td>TPC</td></tr></table>'
    assert _parse_pse_directory_html(fixture).get('TPC')=='Test Philippine Corp.'
    assert _symbol_from_query('explain recursion') is None
    mock={'symbol':'TSLA','price':378.73,'session':'regular/latest','timestamp_utc':'2026-10-05 20:00:01 UTC','currency':'USD','exchange':'NasdaqGS','previous_close':370.59,'change':8.14,'change_percent':2.196,'market_cap':1200000000000,'dividend_rate':None,'dividend_yield':None,'source':'Yahoo Finance structured quote','source_url':'https://finance.yahoo.com/quote/TSLA/','observed_at':'2026-10-06 05:00:00 UTC'}
    formatted=_format_direct_quote(mock);assert '378.73 USD' in formatted and '$185.12' not in formatted and '| Price | Change | Market Cap | Dividend | Yield |' in formatted and '| Status | Session | Previous Close | Exchange | Currency |' in formatted and '1.20T USD' in formatted
    dividend_mock=dict(mock);dividend_mock.update({'symbol':'TEST','market_cap':15000000000,'dividend_rate':2.5,'dividend_yield':0.035})
    dividend_text=_format_direct_quote(dividend_mock);assert '15.00B USD' in dividend_text and '2.5 USD' in dividend_text and '3.50%' in dividend_text
    now=datetime(2026,10,6,5,0,0,tzinfo=timezone.utc)
    assert _quote_freshness({'timestamp_utc':'2026-10-06 04:59:30 UTC','session':'regular/latest'},now)['label']=='🟢 LIVE'
    assert _quote_freshness({'timestamp_utc':'2026-10-06 04:50:00 UTC','session':'regular/latest'},now)['label']=='🟡 RECENT'
    assert _quote_freshness({'timestamp_utc':'2026-10-06 03:00:00 UTC','session':'regular/latest'},now)['label']=='🟠 DELAYED'
    assert _quote_freshness({'timestamp_utc':'2026-10-04 20:00:00 UTC','session':'regular close'},now)['label']=='⚪ LAST CLOSE'
    up=[float(x) for x in range(1,61)];assert _sma(up,20)==sum(up[-20:])/20 and _rsi14(up)==100.0
    m,sig,h=_macd(up);assert m is not None and sig is not None and h is not None
    lv=_scenario_levels_from_closes(up);assert lv and lv['Breakout confirmation']>max(up[-20:]) and lv['Invalidation / risk reference']<min(up[-20:])
    mock_sig={'scenario_levels':lv}; sizing=_position_sizing_guidance(mock_sig);assert '0.25%' in sizing and '0.50%' in sizing and '1.00%' in sizing and 'Units = (Portfolio Value' in sizing
    sc=_position_size_scenarios(mock_sig);assert sc and len(sc['rows'])==5 and set(sc['risk_budgets'])=={0.25,0.5,1.0}
    plot=_position_size_plot(mock_sig);assert 'Position-size scenarios' in plot and 'Risk budget 0.25%' in plot and 'Technical level map' in plot and '█' in plot
    csv_text=_position_size_csv(mock_sig,'TEST');assert 'symbol,portfolio_value,risk_budget_percent' in csv_text and 'TEST,100000.00,0.50' in csv_text and 'technical_level,value' in csv_text
    return True

__all__=['ENABLED','WEBSEARCH_AVAILABLE','SEARCH_AVAILABLE','web_reply','reply_is_unsure','search_sources','self_test','_extract_candidates','normalize_result','classify_web_intent','analyze_prompt','verify_evidence','grounded_synthesis_messages','_extract_market_quote','_direct_yahoo_quote','_format_direct_quote','_fetch_pse_catalog','_pse_symbol_from_query','_parse_pse_directory_html','_human_money','_percent_value','_quote_freshness','_market_signal','_signal_table','_position_size_csv','export_position_size_csv']
if __name__=='__main__':print('self_test:','PASS' if self_test() else 'FAIL')
