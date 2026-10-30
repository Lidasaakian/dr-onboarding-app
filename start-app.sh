#!/usr/bin/env bash
# Entry point for the DataRobot custom application. The web server must listen on port 8080.
cd "$(dirname "$(readlink -f "$0")")" || exit 1
exec python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips='*'
