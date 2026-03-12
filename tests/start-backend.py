#!/usr/bin/env python3
"""
Simple script to start the backend server
"""
import subprocess
import sys
import time
import os

os.chdir(r"I:\code\miniclaw\backend")

# Create venv if not exists
if not os.path.exists("venv"):
    print("Creating virtual environment...")
    subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)

# Activate venv and install
if os.name == "nt":
    pip = os.path.join("venv", "Scripts", "pip")
    python = os.path.join("venv", "Scripts", "python")
else:
    pip = os.path.join("venv", "bin", "pip")
    python = os.path.join("venv", "bin", "python")

print("Installing dependencies...")
subprocess.run([pip, "install", "-q", "-r", "requirements.txt"])

print("Starting backend server...")
subprocess.run([python, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"])
