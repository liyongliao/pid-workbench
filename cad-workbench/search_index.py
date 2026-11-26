"""Normalize CAD search fields once for each published catalog."""
from functools import lru_cache
import re
from rapidfuzz import fuzz

def normalized(value):
    return re.sub(r'[^A-Z0-9\u4e00-\u9fff]','',value.upper())

class SearchIndex:
    def __init__(self,catalog):
        self.rows=[]
        for d in catalog:
            team=d.get("team","工艺")
            identity={k:d[k] for k in ("id","title","code","platform","entityCount")}
            identity["team"]=team
            equipment=[]
            for e in d.get("equipment",[]):
                tag=normalized(e["tag"])
                short=normalized(re.sub(r'^(CEPD?|WHP[A-Z]|WP[A-Z]|PRP)-','',e["tag"].upper()))
                equipment.append((tag,short,normalized(e["tag"]+e["name"]+e.get("search","")),
                                  dict(e,drawingId=d["id"],drawingTitle=d["title"],team=team,platform=d["platform"])))
            self.rows.append((identity,normalized(d["title"]+d["code"]),normalized(d.get("search","")),equipment))
        self.search=lru_cache(maxsize=128)(self._search)

    def _search(self,term,platform,team):
        needle=normalized(term)
        drawings,items=[],[]
        for d,title,body,equipment in self.rows:
            if (platform and d["platform"]!=platform) or (team and team!=d["team"]):continue
            score=100 if not needle or needle in body else fuzz.partial_ratio(needle,title)
            if needle and needle in title:score+=30
            for tag,short,search,e in equipment:
                if needle and needle in search:
                    rank=0 if needle in (tag,short) else 1 if needle in tag else 2
                    items.append((rank,e))
                    score=max(score,(230,210,200)[rank])
            if score>=65:drawings.append(dict(d,score=score))
        items.sort(key=lambda row:(row[0],row[1]["tag"],row[1]["drawingId"]))
        drawings.sort(key=lambda row:-row["score"])
        return {"drawings":drawings,"equipment":[e for _,e in items[:100]],"total":len(drawings),"equipmentTotal":len(items)}
