from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import Audience
from app.services.reddit_service import RedditService
from app.extensions import db
from sqlalchemy import or_
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime

audience = Blueprint('audience', __name__, url_prefix='/api/audiences')

@audience.route('/', methods=['GET'])
def list_audiences():
    search_query = request.args.get('search', '')
    theme = request.args.get('theme', '')
    topic = request.args.get('topic', '')
    category = request.args.get('category', 'saved')
    
    query = Audience.query.filter_by(category=category)
    
    if search_query:
        query = query.filter(or_(
            Audience.name.ilike(f'%{search_query}%'),
            Audience.description.ilike(f'%{search_query}%')
        ))
    if theme:
        query = query.filter_by(theme=theme)
    if topic:
        query = query.filter_by(topic=topic)
        
    audiences = query.all()
    return jsonify([a.to_dict() for a in audiences])

@audience.route('/<int:id>', methods=['GET'])
@login_required
def get_audience(id):
    try:
        audience_obj = Audience.query.get_or_404(id)
        reddit_service = RedditService()
        
        # Get real-time data
        audience_data = reddit_service.get_subreddit_data(audience_obj.subreddit)
        
        if audience_data:
            # Update stats
            audience_obj.subscribers = audience_data['stats']['subscribers']
            audience_obj.active_users = audience_data['stats']['active_users']
            audience_obj.last_updated = datetime.utcnow()
            db.session.commit()
        
        return render_template('audience/detail.html',
                             audience=audience_obj,
                             audience_data=audience_data or {})
    except Exception as e:
        print(f"Error in get_audience: {e}")
        return render_template('audience/detail.html',
                             audience=audience_obj,
                             audience_data={})

@audience.route('/', methods=['POST'])
@jwt_required()
def create_audience():
    data = request.get_json()
    user_id = get_jwt_identity()
    
    audience = Audience(
        name=data['name'],
        subreddit=data['subreddit'],
        category=data.get('category', 'saved'),
        theme=data.get('theme'),
        topic=data.get('topic'),
        description=data.get('description'),
        user_id=user_id
    )
    
    db.session.add(audience)
    db.session.commit()
    return jsonify(audience.to_dict()), 201

@audience.route('/<int:id>', methods=['PUT'])
@jwt_required()
def update_audience(id):
    audience = Audience.query.get_or_404(id)
    data = request.get_json()
    
    for key, value in data.items():
        if hasattr(audience, key):
            setattr(audience, key, value)
    
    db.session.commit()
    return jsonify(audience.to_dict())

@audience.route('/<int:id>', methods=['DELETE'])
@jwt_required()
def delete_audience(id):
    audience = Audience.query.get_or_404(id)
    db.session.delete(audience)
    db.session.commit()
    return jsonify({'message': 'Audience deleted successfully'})

@audience.route('/search', methods=['GET'])
@login_required
def search_subreddit():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    reddit_service = RedditService()
    results = reddit_service.search_subreddits(query)
    return jsonify(results)

@audience.route('/fetch-subreddit', methods=['GET'])
@login_required
def fetch_subreddit():
    subreddit_name = request.args.get('name')
    if not subreddit_name:
        return jsonify({'error': 'Subreddit name required'}), 400
    
    reddit_service = RedditService()
    subreddit_data = reddit_service.get_subreddit_info(subreddit_name)
    
    if not subreddit_data:
        return jsonify({'error': 'Subreddit not found'}), 404
        
    return jsonify(subreddit_data)

@audience.route('/save', methods=['POST'])
@login_required
def save_subreddit():
    data = request.get_json()
    
    existing = Audience.query.filter_by(
        subreddit=data['name'],
        user_id=current_user.id
    ).first()
    
    if existing:
        return jsonify({'error': 'Already saved'}), 400
        
    audience = Audience(
        name=data['title'],
        subreddit=data['name'],
        description=data.get('description', ''),
        subscribers=data.get('subscribers', 0),
        category='saved',
        user_id=current_user.id
    )
    
    db.session.add(audience)
    db.session.commit()
    
    return jsonify(audience.to_dict()), 201

@audience.route('/curated')
@login_required
def curated_audiences():
    reddit_service = RedditService()
    audiences = reddit_service.get_curated_audiences()
    
    # Group by category
    categories = {}
    for audience in audiences:
        category = audience.get('category', 'Other')
        if category not in categories:
            categories[category] = []
        categories[category].append(audience)
    
    return render_template('audiences/curated.html', 
                         categories=categories)

@audience.route('/trending')
@login_required
def trending_audiences():
    reddit_service = RedditService()
    trending_data = reddit_service.get_trending_audiences()
    
    # Convert audience data to serializable format
    audiences = [{
        'name': a['name'],
        'subreddit': a['subreddit'],
        'description': a['description'],
        'subscribers': a['subscribers'],
        'active_users': a['active_users'],
        'growth_rate': a['growth_rate'],
        'theme': a['theme'],
        'topic': a['topic']
    } for a in trending_data]
    
    return render_template('audiences/trending.html', audiences=audiences)

@audience.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Audience not found'}), 404

@audience.errorhandler(401)
def unauthorized_error(error):
    return jsonify({'error': 'Unauthorized'}), 401