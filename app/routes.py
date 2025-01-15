# app/routes.py
from flask import Blueprint, render_template, jsonify, request, current_app
from app.models import Audience, AudienceList
from app.utils.reddit_api import RedditAPI
from datetime import datetime, timedelta
from sqlalchemy import or_
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from .models import User, Audience, CuratedList, Website
from .services.scraper import ScraperService
from app import db
from app.services.reddit_service import RedditService

main = Blueprint('main', __name__)

def get_reddit_api():
    return RedditService()

@main.route('/')
def index():
    # Get statistics
    stats = {
        'saved_count': Audience.query.filter_by(category='saved').count(),
        'curated_count': Audience.query.filter_by(category='curated').count(),
        'trending_count': Audience.query.filter_by(category='trending').count()
    }
    
    # Get recent trending audiences
    trending = Audience.query.filter_by(category='trending')\
        .order_by(Audience.weekly_posts.desc())\
        .limit(5).all()
    
    return render_template('index.html', stats=stats, trending=trending)

@main.route('/audiences/saved')
def saved_audiences():
    search_query = request.args.get('search', '')
    theme = request.args.get('theme', '')
    topic = request.args.get('topic', '')
    
    query = Audience.query.filter_by(category='saved')
    
    if search_query:
        query = query.filter(or_(
            Audience.name.ilike(f'%{search_query}%'),
            Audience.description.ilike(f'%{search_query}%')
        ))
    if theme:
        query = query.filter_by(theme=theme)
    if topic:
        query = query.filter_by(topic=topic)
    
    audiences = query.order_by(Audience.subscribers.desc()).all()
    
    themes = db.session.query(Audience.theme)\
        .filter(Audience.theme.isnot(None))\
        .distinct().all()
    topics = db.session.query(Audience.topic)\
        .filter(Audience.topic.isnot(None))\
        .distinct().all()
    
    return render_template('audiences/saved.html', 
                         audiences=audiences,
                         themes=themes,
                         topics=topics)

@main.route('/audiences/curated')
def curated_audiences():
    curated_lists = AudienceList.query.filter_by(category='curated').all()
    return render_template('audiences/curated.html', curated_lists=curated_lists)

@main.route('/audiences/trending')
def trending_audiences():
    last_update = Audience.query.filter_by(category='trending')\
        .order_by(Audience.last_updated.desc())\
        .first()
    
    if not last_update or \
       datetime.utcnow() - last_update.last_updated > timedelta(hours=24):
        update_trending_audiences()
    
    audiences = Audience.query.filter_by(category='trending')\
        .order_by(Audience.weekly_posts.desc())\
        .all()
    
    return render_template('audiences/trending.html', audiences=audiences)

@main.route('/api/search-subreddits')
def api_search_subreddits():
    query = request.args.get('q', '')
    reddit_api = get_reddit_api()
    results = reddit_api.search_subreddits(query)
    return jsonify(results)

@main.route('/api/save-audience', methods=['POST'])
def api_save_audience():
    data = request.json
    
    existing = Audience.query.filter_by(subreddit=data['subreddit']).first()
    if existing:
        return jsonify({'error': 'Audience already exists'}), 400
    
    reddit_api = get_reddit_api()
    reddit_data = reddit_api.get_subreddit_info(data['subreddit'])
    
    if not reddit_data:
        return jsonify({'error': 'Failed to fetch subreddit data'}), 400
    
    audience = Audience(
        name=reddit_data['name'],
        subreddit=data['subreddit'],
        category='saved',
        theme=data.get('theme'),
        topic=data.get('topic'),
        description=reddit_data['description'],
        subscribers=reddit_data['subscribers'],
        weekly_posts=reddit_data['weekly_posts'],
        active_users=reddit_data['active_users'],
        metadata={
            'icon_img': reddit_data['icon_img'],
            'over18': reddit_data['over18'],
            'url': reddit_data['url'],
            'title': reddit_data['title']
        }
    )
    
    db.session.add(audience)
    db.session.commit()
    
    return jsonify(audience.to_dict())

@main.route('/api/delete-audience', methods=['POST'])
def api_delete_audience():
    data = request.json
    audience = Audience.query.filter_by(id=data['id']).first()
    
    if not audience:
        return jsonify({'error': 'Audience not found'}), 404
        
    db.session.delete(audience)
    db.session.commit()
    
    return jsonify({'success': True})

@main.route('/api/create-list', methods=['POST'])
def api_create_list():
    data = request.json
    
    audience_list = AudienceList(
        name=data['name'],
        description=data['description'],
        category='curated'
    )
    
    db.session.add(audience_list)
    db.session.commit()
    
    return jsonify(audience_list.to_dict())

def update_trending_audiences():
    reddit_api = get_reddit_api()
    trending_data = reddit_api.get_trending_subreddits()
    
    for data in trending_data:
        audience = Audience.query.filter_by(subreddit=data['name']).first()
        if not audience:
            audience = Audience(
                subreddit=data['name'],
                category='trending'
            )
            db.session.add(audience)
        
        audience.update_from_reddit_data(data)
    
    db.session.commit()

@main.route('/api/init-curated', methods=['POST'])
def init_curated():
    if AudienceList.query.filter_by(category='curated').first():
        return jsonify({'message': 'Curated lists already initialized'})
    
    curated_lists = [
        {
            'name': 'Technology Communities',
            'description': 'Popular technology-focused subreddits',
            'subreddits': ['programming', 'technology', 'webdev', 'Python', 'javascript']
        },
        {
            'name': 'Digital Marketing',
            'description': 'Communities for marketing professionals',
            'subreddits': ['marketing', 'SEO', 'socialmedia', 'PPC', 'contentmarketing']
        }
    ]
    
    reddit_api = get_reddit_api()
    
    for list_data in curated_lists:
        audience_list = AudienceList(
            name=list_data['name'],
            description=list_data['description'],
            category='curated'
        )
        db.session.add(audience_list)
        
        for subreddit_name in list_data['subreddits']:
            reddit_data = reddit_api.get_subreddit_info(subreddit_name)
            if reddit_data:
                audience = Audience.query.filter_by(subreddit=subreddit_name).first()
                if not audience:
                    audience = Audience(
                        subreddit=subreddit_name,
                        category='curated'
                    )
                    audience.update_from_reddit_data(reddit_data)
                    db.session.add(audience)
                audience_list.audiences.append(audience)
    
    db.session.commit()
    return jsonify({'message': 'Curated lists initialized successfully'})

@main.route('/save_audience', methods=['POST'])
def save_audience():
    data = request.get_json()
    audience = Audience.from_dict(data)
    audience.save()
    return jsonify(audience.to_dict()), 201

@main.route('/get_audience/<int:id>', methods=['GET'])
def get_audience(id):
    audience = Audience.query.get(id)
    if audience is None:
        return jsonify({'error': 'Audience not found'}), 404
    return jsonify(audience.to_dict())

@main.route('/update_audience/<int:id>', methods=['PUT'])
def update_audience(id):
    data = request.get_json()
    audience = Audience.query.get(id)
    if audience is None:
        return jsonify({'error': 'Audience not found'}), 404
    audience.update_from_dict(data)
    audience.save()
    return jsonify(audience.to_dict())

@main.route('/delete_audience/<int:id>', methods=['DELETE'])
def delete_audience(id):
    audience = Audience.query.get(id)
    if audience is None:
        return jsonify({'error': 'Audience not found'}), 404
    audience.delete()
    return jsonify({'message': 'Audience deleted successfully'})

# Auth Routes
@main.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'error': 'Email already registered'}), 409
    
    user = User(
        email=data['email'],
        password=generate_password_hash(data['password']),
        name=data.get('name', '')
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'User registered successfully'}), 201

@main.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(email=data['email']).first()
    if not user or not check_password_hash(user.password, data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    access_token = create_access_token(identity=user.id)
    return jsonify({'token': access_token}), 200

# Audience Routes
@main.route('/audience', methods=['POST'])
@jwt_required()
def create_audience():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    # Create new audience
    audience = Audience(
        name=data['name'],
        description=data.get('description', ''),
        user_id=user_id,
        criteria=data.get('criteria', {}),
        tags=data.get('tags', [])
    )
    
    # Process website URLs if provided
    if 'websites' in data:
        scraper = ScraperService()
        for url in data['websites']:
            website_data = scraper.scrape(url)
            website = Website(
                url=url,
                title=website_data.get('title'),
                description=website_data.get('description'),
                meta_data=website_data.get('meta_data')
            )
            audience.websites.append(website)
    
    db.session.add(audience)
    db.session.commit()
    return jsonify(audience.to_dict()), 201

@main.route('/audience/<int:id>', methods=['GET'])
@jwt_required()
def get_audience(id):
    user_id = get_jwt_identity()
    audience = Audience.query.filter_by(id=id, user_id=user_id).first()
    if not audience:
        return jsonify({'error': 'Audience not found'}), 404
    return jsonify(audience.to_dict())

@main.route('/audiences', methods=['GET'])
@jwt_required()
def list_audiences():
    user_id = get_jwt_identity()
    query = Audience.query.filter_by(user_id=user_id)
    
    # Filter by tags
    tags = request.args.getlist('tags')
    if tags:
        query = query.filter(Audience.tags.contains(tags))
    
    # Search by name
    search = request.args.get('search')
    if search:
        query = query.filter(Audience.name.ilike(f'%{search}%'))
    
    audiences = query.all()
    return jsonify([a.to_dict() for a in audiences])

# Curated List Routes
@main.route('/lists', methods=['POST'])
@jwt_required()
def create_list():
    user_id = get_jwt_identity()
    data = request.get_json()
    
    curated_list = CuratedList(
        name=data['name'],
        description=data.get('description', ''),
        user_id=user_id,
        is_public=data.get('is_public', False)
    )
    
    if 'audience_ids' in data:
        audiences = Audience.query.filter(
            Audience.id.in_(data['audience_ids']),
            Audience.user_id == user_id
        ).all()
        curated_list.audiences.extend(audiences)
    
    db.session.add(curated_list)
    db.session.commit()
    return jsonify(curated_list.to_dict()), 201

@main.route('/lists/<int:id>', methods=['GET'])
def get_list(id):
    curated_list = CuratedList.query.get_or_404(id)
    if not curated_list.is_public:
        # Check if user is authorized
        jwt_required()(lambda: None)()
        user_id = get_jwt_identity()
        if curated_list.user_id != user_id:
            return jsonify({'error': 'Unauthorized'}), 403
    return jsonify(curated_list.to_dict())

# Error handlers
@main.errorhandler(Exception)
def handle_error(error):
    return jsonify({'error': str(error)}), 500

@main.route('/api/audiences', methods=['GET'])
def get_audiences():
    category = request.args.get('category', 'all')
    if category != 'all':
        audiences = Audience.query.filter_by(category=category).all()
    else:
        audiences = Audience.query.all()
    return jsonify([audience.to_dict() for audience in audiences])

@main.route('/api/lists', methods=['GET'])
def get_lists():
    category = request.args.get('category', 'all')
    if category != 'all':
        lists = AudienceList.query.filter_by(category=category).all()
    else:
        lists = AudienceList.query.all()
    return jsonify([lst.to_dict() for lst in lists])