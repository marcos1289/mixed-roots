import urllib.request,json,pathlib,re,concurrent.futures,html,time
root=pathlib.Path(__file__).parent;p=root/'recovery';assets=root/'dist/assets'
def fetch(job):
 name,url=job
 for attempt in range(2):
  try:
   data=urllib.request.urlopen(url,timeout=35).read();target=(assets if name.startswith('asset-') else p)/name;target.write_bytes(data);return {'file':name,'url':url,'bytes':len(data),'ok':True}
  except Exception as e:err=str(e)
 return {'file':name,'url':url,'ok':False,'error':err}
pages=['about.html','performances.html','contact.html','news','index.html']
jobs=[(x.replace('/','-')+'.html','https://web.archive.org/web/20260121062141id_/https://www.mixedrootsnewyork.com/'+x) for x in pages]
with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:results=list(ex.map(fetch,jobs))
print('pages',results,flush=True)
refs=set()
for f in p.glob('*.html'):
 h=f.read_text(errors='replace')
 for match in re.findall(r'(?:src|href)=[\"\']([^\"\']+)|url\([\"\']?([^\)\"\']+)',h):
  u=html.unescape(next(x for x in match if x))
  if '/uploads/' in u:refs.add('https://www.mixedrootsnewyork.com'+u if u.startswith('/') else u)
 # readable text
 clean=re.sub(r'<(script|style)\b[^>]*>.*?</\1>','',h,flags=re.S|re.I);clean=re.sub('<[^>]+>','\n',clean);clean=html.unescape(clean);clean='\n'.join(x.strip() for x in clean.splitlines() if x.strip());(p/(f.stem+'.txt')).write_text(clean)
for row in json.loads((p/'index.json').read_text())[1:]:
 if '/uploads/' in row[2]:refs.add(row[2])
jobs=[('asset-'+u.split('/')[-1].split('?')[0],'https://web.archive.org/web/20260121062141id_/'+u) for u in sorted(refs)]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 for r in ex.map(fetch,jobs):results.append(r);print(r['file'],r['ok'],flush=True)
(p/'manifest.json').write_text(json.dumps(results,indent=2));print('DONE',sum(x['ok'] for x in results),'/',len(results),flush=True)
