# run_prod_windows.ps1 — Start SR15 Analytics in production mode (Windows)
# Prerequisites: pip install gunicorn  (works via WSL or Git Bash on Windows)
# For native Windows use waitress instead — see README_RUN.md

$env:ENV = "prod"
$env:SECRET_KEY = "GANTI-INI-DENGAN-SECRET-YANG-AMAN"   # <-- change this

Write-Host "Starting SR15 Analytics (prod) on 0.0.0.0:8050 ..."
gunicorn app:server -c gunicorn.conf.py
