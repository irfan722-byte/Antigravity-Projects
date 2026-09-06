import os
import sys
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_aurumguard.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-1234")
os.environ.setdefault("ANALYSIS_ENABLED", "false")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
