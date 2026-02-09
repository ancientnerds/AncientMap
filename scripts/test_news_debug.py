import sys, os
sys.path.insert(0, '/app')
os.environ.setdefault('QDRANT_HOST', 'qdrant')
from api.services.lyra_agent import _auto_retrieve, _get_related_news
ctx, sites, rel, vt = _auto_retrieve('Recent discoveries about Karahantepe', 'site')
print(f'Sites: {len(sites)}')
for s in sites[:3]:
    print(f'  {s.get("name")} id={s.get("id","NONE")[:8]}')
ids = [s['id'] for s in sites if s.get('id')]
names = [s['name'] for s in sites if s.get('name')]
news = _get_related_news(site_ids=ids, site_names=names) if (ids or names) else []
print(f'News: {len(news)}')
for n in news[:3]:
    print(f'  {n["headline"][:60]}')
