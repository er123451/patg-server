#!/bin/bash
. ./venv/bin/activate
setsid fastapi run ./main.py > ./logs.log 2>&1 < /dev/null
