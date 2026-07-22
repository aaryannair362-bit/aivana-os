import sys
import os
from pathlib import Path

# Add the backend folder to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.main import app
from mangum import Mangum

# Vercel expects a handler named 'handler'
handler = Mangum(app)