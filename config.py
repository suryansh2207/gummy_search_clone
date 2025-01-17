# app/config.py
import os
from dotenv import load_dotenv
from configparser import ConfigParser

load_dotenv()

class Config:
    # Flask configuration
    SECRET_KEY = 'dev'
    
    # Reddit API credentials
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'Gummyclone/1.0')
    REDDIT_REDIRECT_URI = os.getenv('REDDIT_REDIRECT_URI', 'http://127.0.0.1:5000/callback')
    
    # Session configuration
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    PERMANENT_SESSION_LIFETIME = 3600  # Session lifetime in seconds (1 hour)

    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = 'sqlite:///app.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False