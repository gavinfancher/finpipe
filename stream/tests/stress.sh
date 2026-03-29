#!/bin/bash
# Usage: ./stress.sh [requests_per_wave] [delay_between_waves_seconds]
# Defaults: 50 requests per wave, 2s delay

WAVE=${1:-50}
DELAY=${2:-2}
API="http://localhost:8080"

echo "logging in..."
TOKEN=$(curl -s -X POST $API/external/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"gavin","password":"password"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "login failed — is the server running?"
  exit 1
fi

echo "token ok — firing $WAVE requests per wave every ${DELAY}s (ctrl+c to stop)"
echo ""

WAVE_NUM=0
while true; do
  WAVE_NUM=$((WAVE_NUM + 1))
  echo "wave $WAVE_NUM..."

  for i in $(seq 1 $WAVE); do
    (
      # normal traffic
      curl -s $API/external/tickers/list -H "Authorization: Bearer $TOKEN" > /dev/null
      curl -s $API/internal/health > /dev/null
      curl -s $API/external/tickers/AAPL -X POST -H "Authorization: Bearer $TOKEN" > /dev/null
      curl -s $API/external/tickers/MSFT -X POST -H "Authorization: Bearer $TOKEN" > /dev/null

      # sprinkle in some errors (~20% of waves)
      if [ $((i % 5)) -eq 0 ]; then
        curl -s $API/external/tickers/list -H "Authorization: Bearer badtoken" > /dev/null
        curl -s $API/external/doesnotexist > /dev/null
      fi
    ) &
  done
  wait

  sleep $DELAY
done
