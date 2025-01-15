from flask import Flask
from flask_login import LoginManager
from .extensions import db, migrate, jwt, csrf
from config import Config
import json

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    csrf.init_app(app)

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'

    @login_manager.user_loader
    def load_user(id):
        return User.query.get(int(id))

    # Import models to ensure they're known to Flask-Migrate
    from .models import User, Audience, CuratedList, Website

    # Register blueprints
    from .routes.audience_routes import audience
    app.register_blueprint(audience, url_prefix='/audience')
    from .routes.auth_routes import auth
    from .routes.main_routes import main
    
    app.register_blueprint(auth)
    app.register_blueprint(main)

    # Register custom template filters
    @app.template_filter('tojson')
    def tojson_filter(obj):
        return json.dumps(obj)

    @app.template_filter('number_format')
    def number_format_filter(value):
        try:
            return "{:,}".format(int(value))
        except (ValueError, TypeError):
            return "0"

    return app
