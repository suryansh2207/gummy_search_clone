from app.extensions import db
from datetime import datetime

class Audience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    subreddit = db.Column(db.String(100))
    description = db.Column(db.Text)
    subscribers = db.Column(db.Integer, default=0)
    category = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    list_id = db.Column(db.Integer, db.ForeignKey('audience_list.id'))
    
    def update_from_reddit_data(self, data):
        self.name = data.get('display_name', self.name)
        self.description = data.get('description', self.description)
        self.subscribers = data.get('subscribers', self.subscribers)
        self.updated_at = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'criteria': self.criteria,
            'tags': self.tags,
            'websites': [w.to_dict() for w in self.websites],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }