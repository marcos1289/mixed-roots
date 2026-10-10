import re,html,sys,pathlib,collections
src=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(exist_ok=True)
def text(h):
    h=re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>','',h)
    h=re.sub(r'(?i)<br\s*/?>|</(p|div|h\d|li|tr)>','\n',h)
    h=re.sub(r'<[^>]+>','\n',h);h=html.unescape(h)
    return '\n'.join(x.strip() for x in h.splitlines() if x.strip() and x.strip()!='​')
groups=collections.defaultdict(list)
for f in sorted(src.glob('*.html')):
    page,ts=f.stem.rsplit('__',1)
    t=text(f.read_text(errors='replace')); (out/(f.stem+'.txt')).write_text(t)
    groups[page].append((ts,t))
allines=collections.defaultdict(dict)
for page,vs in groups.items():
    uniq=[];prev=None
    for ts,t in vs:
        if t!=prev: uniq.append(ts); prev=t
        for l in t.splitlines(): allines[page].setdefault(l,ts)
    print(page,len(vs),'versions,',len(uniq),'distinct texts:',' '.join(uniq))
import json;json.dump({p:v for p,v in allines.items()},open(out/'_firstseen.json','w'),indent=0)
