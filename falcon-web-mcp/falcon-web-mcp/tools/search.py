from duckduckgo_search import DDGS

def web_search(query:str, limit:int=5):
    results=[]
    with DDGS() as ddgs:
        for item in ddgs.text(query,max_results=limit):
            results.append({"title":item.get("title"),"url":item.get("href"),"snippet":item.get("body")})
    return results
