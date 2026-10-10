import re,html,pathlib,sys,json
snap=pathlib.Path(sys.argv[1]);out={}
def clean(s):
    s=re.sub(r'(?is)<(script|style)\b.*?</\1>','',s);s=re.sub(r'<[^>]+>',' ',s);s=html.unescape(s)
    return re.sub(r'\s+',' ',s).replace('​','').strip()
for f in sorted(snap.glob('*.html')):
    page,ts=f.stem.rsplit('__',1)
    if page in('home','index.html'):continue
    h=f.read_text(errors='replace')
    body=h[h.find('<body'):]
    for m in re.finditer(r'(?:/uploads/1/0/2/1/102180450/|video=b/102180450-\d+/)((?:background-images/)?[\w.-]+?)(?:_orig)?\.(?:jpe?g|png|mp4)',body):
        k=m.group(1)
        before=clean(body[max(0,m.start()-1500):m.start()])[-220:]
        after=clean(body[m.end():m.end()+2500])[:260]
        e=out.setdefault(k,{'page':page,'first':ts[:8],'last':ts[:8],'before':before,'after':after})
        e['last']=ts[:8]
json.dump(out,open(sys.argv[2],'w'),indent=1)
for k,e in sorted(out.items(),key=lambda x:x[1]['first']):
    print(f"\n[{k}] {e['page']} {e['first']}..{e['last']}\n   BEFORE: ...{e['before'][-150:]}\n   AFTER:  {e['after'][:200]}")
