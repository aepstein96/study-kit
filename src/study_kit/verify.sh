#!/usr/bin/env bash
# Verify one study end-to-end: analysis -> typecheck -> build -> serve -> screenshot -> checks.
# Every step uses absolute paths and the study's own toolchain. Hand-rolled versions kept failing
# on things unrelated to the study: `npx tsc` resolving to an unrelated registry package, a preview
# server curl'd before it was listening.
set -euo pipefail
ROOT="$1"; NAME="$2"; shift 2
STUDY="$ROOT/$NAME"; APP="$STUDY/app"; SHOT="$STUDY/verification.png"
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== 1/5 analysis =========================================================="
if [ "${1:-}" = "--skip-analysis" ]; then
  echo "   skipped (--skip-analysis)"
else
  ( cd "$STUDY" && uv run python analysis/analyze.py ) || fail "analysis/analyze.py"
fi
DATA="$APP/public/data.json"
[ -s "$DATA" ] || fail "$DATA missing or empty"
python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$DATA" || fail "data.json is not valid JSON"
echo "   data.json OK ($(wc -c < "$DATA" | tr -d ' ') bytes)"
# Malformed SVG still serves 200, and browsers render invalid XML as blank with no error.
COVER="$APP/public/cover.svg"
if [ -s "$COVER" ]; then
  python3 -c "import xml.etree.ElementTree as ET,sys; ET.parse(sys.argv[1])" "$COVER" \
    || fail "cover.svg is not well-formed XML"
  echo "   cover.svg OK (well-formed XML)"
else
  echo "   WARNING: no cover.svg yet"
fi

echo "== 2/5 install ==========================================================="
[ -d "$APP/node_modules" ] || ( cd "$APP" && npm install --no-audit --no-fund )

echo "== 3/5 typecheck ========================================================="
[ -x "$APP/node_modules/.bin/tsc" ] || fail "no local tsc: run npm install in $APP"
( cd "$APP" && ./node_modules/.bin/tsc --noEmit ) || fail "tsc --noEmit"
echo "   tsc --noEmit clean"

echo "== 4/5 build ============================================================="
( cd "$APP" && npm run build ) || fail "npm run build"

echo "== 5/5 serve + screenshot ================================================"
# localhost, not 127.0.0.1: `vite preview` can bind IPv6 only.
PORT=$(python3 -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1]);s.close()")
( cd "$APP" && exec ./node_modules/.bin/vite preview --port "$PORT" --strictPort >/dev/null 2>&1 ) &
SRV=$!
trap 'kill $SRV 2>/dev/null || true' EXIT
CODE=""
for _ in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$PORT/" || true)
  [ "$CODE" = "200" ] && break
  sleep 0.5
done
[ "$CODE" = "200" ] || fail "preview server never returned 200 (last: ${CODE:-none})"
curl -sf "http://localhost:$PORT/data.json" >/dev/null || fail "data.json not served with the app"
echo "   served 200 on :$PORT (index + data.json)"

CHROME=""
for c in "${CHROME_BIN:-}" "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         google-chrome chromium chromium-browser chrome; do
  [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { CHROME="$c"; break; }
done
if [ -n "$CHROME" ]; then
  "$CHROME" --headless --no-sandbox --disable-gpu --hide-scrollbars --window-size=1280,1600 \
    --virtual-time-budget=6000 --screenshot="$SHOT" "http://localhost:$PORT/" >/dev/null 2>&1 || true
  if [ -s "$SHOT" ]; then
    BYTES=$(wc -c < "$SHOT" | tr -d ' ')
    echo "   screenshot: $SHOT ($BYTES bytes)"
    # A React app that throws on mount serves 200 and screenshots a flat background. Measured: a
    # blank render came out at 9,343 bytes against 293,099 for the same page working.
    [ "$BYTES" -ge 40000 ] || fail "screenshot is only $BYTES bytes: the page almost certainly rendered blank"
  else
    echo "   WARNING: Chrome produced no screenshot"
  fi
else
  echo "   WARNING: no Chrome found (set CHROME_BIN): skipped the screenshot, so a blank page would pass"
fi

echo "== checks ================================================================"
"$STUDY_KIT_PY" -c "import sys; from pathlib import Path; from study_kit import checks; sys.exit(checks.run(Path(sys.argv[1])))" "$STUDY" \
  || fail "a check failed (see above)"

echo
echo "PASS: $NAME: analysis, types, build, serve OK."
echo "Still required: confirm report/report.md figures against data.json, and look at the app."
