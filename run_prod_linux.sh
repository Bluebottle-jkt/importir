#!/usr/bin/env bash
# run_prod_linux.sh — Start SR15 Analytics in production mode (Linux / WSL)

export ENV=prod
export SECRET_KEY="GANTI-INI-DENGAN-SECRET-YANG-AMAN"   # <-- change this

echo "Starting SR15 Analytics (prod) on 0.0.0.0:8050 ..."
gunicorn app:server -c gunicorn.conf.py
