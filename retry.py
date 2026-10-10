import pathlib,json,urllib.request,concurrent.futures
r=pathlib.Path(__file__).parent;p=r/'recovery';m=json.loads((p/'manifest.json').read_text());jobs=[]
for item in m:
 if item['ok']:continue
 u=item['url'].split('id_/',1)[1]
 if u.startswith('"'):u='https://www.mixedrootsnewyork.com'+u.strip('"')
 elif 'com//www.weebly.com' in u:u='https://www.weebly.com'+u.split('www.weebly.com')[1]
 else:continue
 jobs.append((u,'asset-'+u.split('/')[-1]))
def get(job):
 u,name=job
 try:
  data=urllib.request.urlopen('https://web.archive.org/web/20260121062141id_/'+u,timeout=25).read();(r/'dist/assets'/name).write_bytes(data);return {'url':u,'file':name,'bytes':len(data),'ok':True}
 except Exception as e:return {'url':u,'file':name,'ok':False,'error':str(e)}
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as ex:
 out=list(ex.map(get,jobs))
m.extend(out);(p/'manifest.json').write_text(json.dumps(m,indent=2));print(out)
