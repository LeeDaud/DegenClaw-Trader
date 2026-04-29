#!/bin/bash
# DegenClaw 后端启动脚本
cd "$(dirname "$0")/../backend"
PYTHONPATH=. python -m uvicorn main:app --host 0.0.0.0 --port 8000
