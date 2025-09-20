
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent  # <project>
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(parents=True, exist_ok=True)

def _default_sqlite_uri():
    return f"sqlite:///{(INSTANCE_DIR / 'colizeum.db').as_posix()}"

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _default_sqlite_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

def ensure_instance(app):
    # Flask instance path
    os.makedirs(app.instance_path, exist_ok=True)
