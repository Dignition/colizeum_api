from flask_sqlalchemy import SQLAlchemy

# Flask-Migrate может отсутствовать — работаем без него
try:
    from flask_migrate import Migrate
except Exception:
    class Migrate:  # заглушка
        def __init__(self, *a, **k): pass
        def init_app(self, *a, **k): pass

from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
