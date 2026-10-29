#!/bin/bash
export PYTHONPATH=.
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
