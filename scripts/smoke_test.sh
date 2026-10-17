#!/usr/bin/env bash
# Проверка API как это сделает жюри: ./scripts/smoke_test.sh path/to/video.mov [http://localhost:8000]
set -e
VIDEO="$1"; URL="${2:-http://localhost:8000}"
KEY="${API_KEY:-$(grep ^API_KEY .env | cut -d= -f2)}"
JOB=$(curl -sf -X POST "$URL/api/v1/analyze" -H "X-API-Key: $KEY" -F "file=@$VIDEO" | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB"
while true; do
  R=$(curl -sf "$URL/api/v1/jobs/$JOB" -H "X-API-Key: $KEY")
  S=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
  [ "$S" != "processing" ] && break
  sleep 2
done
echo "$R" | python3 -c "
import sys,json; r=json.load(sys.stdin)
for v in r.get('violations',[]): v['evidence_frames']=[{'timestamp_sec':f['timestamp_sec'],'image_base64':f['image_base64'][:20]+'...'} for f in v['evidence_frames']]
print(json.dumps(r,ensure_ascii=False,indent=2))"
