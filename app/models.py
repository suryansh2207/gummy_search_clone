from datetime import datetime
import logging
from sqlalchemy import TypeDecorator
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from sqlalchemy.dialects.postgresql import JSON
from flask_login import UserMixin
from copy import deepcopy
from sqlalchemy.types import TypeDecorator, JSON as SQLAlchemyJSON

# Configure logging
logging.basicConfig(
    filename='sqlalchemy.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

# Optional: Adjust SQLAlchemy logger verbosity
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

class JSONWithDefaultList(TypeDecorator):
    impl = SQLAlchemyJSON
    
    def process_bind_param(self, value, dialect):
        if value is None:
            return []
        return value

class Audience(db.Model):
    __tablename__ = 'audiences'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    subreddit = db.Column(db.String(100))
    category = db.Column(db.String(50), nullable=False)
    theme = db.Column(db.String(100))
    topic = db.Column(db.String(100))
    description = db.Column(db.Text)
    subscribers = db.Column(db.Integer)
    weekly_posts = db.Column(db.Integer)
    active_users = db.Column(db.Integer)
    data = db.Column(JSON)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    list_id = db.Column(db.Integer, db.ForeignKey('curated_list.id'))
    websites = db.relationship('Website', backref='audience', lazy=True)
    subreddit_list = db.Column(JSON, nullable=False, default=lambda: [])
    lists = db.relationship('AudienceListItem', back_populates='audience')

    def __init__(self, **kwargs):
        # Create a deep copy of the subreddit list if provided
        subreddit_list = kwargs.get('subreddit_list')
        if subreddit_list is not None:
            kwargs['subreddit_list'] = deepcopy(subreddit_list)
        else:
            kwargs['subreddit_list'] = []
            
        super(Audience, self).__init__(**kwargs)
        
        # Ensure data is initialized
        if self.data is None:
            self.data = {}

    def update_from_reddit_data(self, reddit_data):
        self.name = reddit_data['name']
        self.description = reddit_data['description']
        self.subscribers = reddit_data['subscribers']
        self.weekly_posts = reddit_data['weekly_posts']
        self.active_users = reddit_data['active_users']
        self.data = {
            'icon_img': reddit_data['icon_img'],
            'over18': reddit_data['over18'],
            'url': reddit_data['url'],
            'title': reddit_data['title']
        }
        self.last_updated = datetime.utcnow()

    def to_dict(self):
        base_dict = {
            'id': self.id,
            'name': self.name,
            'subreddit': self.subreddit,
            'category': self.category,
            'theme': self.theme,
            'topic': self.topic,
            'description': self.description,
            'subscribers': self.subscribers,
            'weekly_posts': self.weekly_posts,
            'active_users': self.active_users,
            'data': self.data,
            'last_updated': self.last_updated.isoformat(),
            'created_at': self.created_at.isoformat(),
            'websites': [w.to_dict() for w in self.websites],
            'subreddit_list': self.subreddit_list
        }
        return base_dict

class AudienceList(db.Model):
    __tablename__ = 'audience_list'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50), nullable=False)
    audiences = db.relationship('AudienceListItem', back_populates='audience_list')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AudienceListItem(db.Model):
    __tablename__ = 'audience_list_items'
    list_id = db.Column(db.Integer, db.ForeignKey('audience_list.id'), primary_key=True)
    audience_id = db.Column(db.Integer, db.ForeignKey('audiences.id'), primary_key=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    audience = db.relationship(Audience, back_populates='lists')
    audience_list = db.relationship(AudienceList, back_populates='audiences')

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    audiences = db.relationship('Audience', backref='user', lazy=True)
    lists = db.relationship('CuratedList', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }

class CuratedList(db.Model):
    __tablename__ = 'curated_list'  # Make sure this is the correct table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    theme = db.Column(db.String(50))  # Add theme field
    topic = db.Column(db.String(50))  # Add topic field
    is_public = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Change the backref name to avoid conflict
    audiences = db.relationship('Audience', secondary='list_audiences',
                                 backref=db.backref('curated_lists', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'theme': self.theme,
            'topic': self.topic,
            'is_public': self.is_public,
            'created_at': self.created_at.isoformat(),
            'user_id': self.user_id,
            'audiences': [a.to_dict() for a in self.audiences]
        }


class Website(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    meta_data = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    audience_id = db.Column(db.Integer, db.ForeignKey('audiences.id'), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'title': self.title,
            'description': self.description,
            'meta_data': self.meta_data,
            'created_at': self.created_at.isoformat()
        }

# Association table for CuratedList and Audience many-to-many relationship
list_audiences = db.Table(
    'list_audiences',
    db.Column('list_id', db.Integer, db.ForeignKey('curated_list.id'), primary_key=True),
    db.Column('audience_id', db.Integer, db.ForeignKey('audiences.id'), primary_key=True)
)
