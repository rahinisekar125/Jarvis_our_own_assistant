#!/usr/bin/env python
"""Download Vosk model for wake-word detection."""
import os
from pathlib import Path
import urllib.request
import zipfile

MODEL_NAME = "vosk-model-small-en-us-0.15"
MODEL_ZIP = f"{MODEL_NAME}.zip"
MODEL_URL = f"https://alphacephei.com/vosk/{MODEL_ZIP}"
MODEL_DIR = Path("models")

print(f"Downloading {MODEL_NAME}...")
MODEL_DIR.mkdir(exist_ok=True)
zip_path = MODEL_DIR / MODEL_ZIP

# Download
urllib.request.urlretrieve(MODEL_URL, str(zip_path))
print(f"Downloaded to {zip_path}")

# Extract
print(f"Extracting {MODEL_ZIP}...")
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(str(MODEL_DIR))

# Clean up zip
zip_path.unlink()
print(f"Model ready at {MODEL_DIR / MODEL_NAME}")
