#!/bin/sh
# usage: getall.sh jobs.txt outdir   (jobs: timestamp url filename)
cd "$2" || exit 1
while read t u f; do
  [ -s "$f" ] && continue
  for i in 1 2 3 4; do
    code=$(curl -s -m 90 -o "$f.part" -w '%{http_code}' "https://web.archive.org/web/${t}id_/$u")
    if [ "$code" = 200 ]; then mv "$f.part" "$f"; echo "ok $f"; break; fi
    echo "http $code $f (try $i)"; rm -f "$f.part"; sleep $((i*10))
  done
  sleep 3
done < "$1"
echo DONE
