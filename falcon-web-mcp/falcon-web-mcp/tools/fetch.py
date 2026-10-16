import requests
from bs4 import BeautifulSoup

def fetch_url(url:str):
    r=requests.get(url,timeout=20,headers={"User-Agent":"Falcon-Web-MCP/1.0"})
    r.raise_for_status()
    soup=BeautifulSoup(r.text,"html.parser")
    for tag in soup(["script","style","noscript"]):
        tag.decompose()
    text=soup.get_text(separator=" ",strip=True)
    return {"url":url,"title":soup.title.string if soup.title else "","content":text[:10000]}
