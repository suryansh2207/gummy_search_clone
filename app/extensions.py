from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_wtf import CSRFProtect
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
csrf = CSRFProtect()
