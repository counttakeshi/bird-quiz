#!/usr/bin/env bash
# Wait for Macaulay's rate limit to lift, then harvest.
#
# The harvest itself is a heavy process - it holds every species' photographs in
# memory - and this machine kills the biggest expendable thing whenever it runs
# short of RAM. Having that process do the waiting meant it was killed mid-sleep
# over and over. So the waiting is done here instead, by a shell loop and a
# single curl, and the heavy work only starts once there is work to do.
#
# One probe every ten minutes is six an hour, which cannot plausibly be the
# thing the rate limit exists to stop.
set -u

# Run from anywhere: the paths below are relative to the project root.
cd "$(dirname "$0")/../.." || exit 1

# Not the `python` on PATH - that one is a bare 3.14 without `requests`.
PY="C:/Users/52967/anaconda3/python.exe"
URL="https://search.macaulaylibrary.org/api/v2/search?taxonCode=bubfly&mediaType=photo&count=5&sort=rating_rank_desc"
UA="BirdQuiz/1.0 (personal study tool; github.com/counttakeshi/bird-quiz)"
INTERVAL=600

while :; do
  ct=$(curl -s -m 45 -o /dev/null -w '%{content_type}' -A "$UA" "$URL" 2>/dev/null || echo "error")
  stamp=$(date '+%H:%M:%S')
  case "$ct" in
    *json*)
      echo "[$stamp] clear - starting harvest"
      "$PY" -u quiz/pipeline/fetch_photos.py
      echo "[$stamp] harvest returned; checking whether anything is left"
      # If it finished, stop. If it exited because it was blocked again, loop.
      left=$("$PY" -c "
import json,pathlib
cache=json.loads(pathlib.Path('quiz/data/raw/photos_ml.json').read_text(encoding='utf-8'))
idx=json.loads(pathlib.Path('src/lib/data/quiz/index.json').read_text(encoding='utf-8'))
def want(v): return v.get('w',0) if isinstance(v,dict) else 0
print(sum(1 for e in idx if e['c'] not in cache or want(cache[e['c']])<50))
")
      echo "[$stamp] $left species still to fetch"
      [ "$left" = "0" ] && { echo "ALL DONE"; exit 0; }
      ;;
    *) echo "[$stamp] blocked ($ct) - next probe in $((INTERVAL/60)) min" ;;
  esac
  sleep "$INTERVAL"
done
