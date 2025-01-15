from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user, login_required
from app.models import Audience, CuratedList
from sqlalchemy import or_
from app import db

from app.services.reddit_service import RedditService

main = Blueprint('main', __name__)

@main.route('/')
def index():
    if current_user.is_authenticated:
        # Get user's stats
        user_audiences = Audience.query.filter_by(user_id=current_user.id).all()
        stats = {
            'saved_audiences': len(user_audiences),
            'total_subscribers': sum(a.subscribers or 0 for a in user_audiences),
            'recent_audiences': Audience.query.filter_by(user_id=current_user.id)
                              .order_by(Audience.created_at.desc()).limit(3).all()
        }
        return render_template('dashboard/home.html', stats=stats)
    return render_template('landing.html')

@main.route('/search')
def search():
    return render_template('search.html')

@main.route('/trending')
def trending():
    timeframe = request.args.get('timeframe', 'weekly')
    limit = int(request.args.get('limit', 10))
    
    query = Audience.query.filter_by(category='trending')
    
    if timeframe == 'weekly':
        query = query.order_by(Audience.weekly_posts.desc())
    else:
        query = query.order_by(Audience.active_users.desc())
        
    audiences = query.limit(limit).all()
    return jsonify([a.to_dict() for a in audiences])

@main.route('/stats')
def get_stats():
    return jsonify({
        'total_audiences': Audience.query.count(),
        'total_lists': CuratedList.query.count(),
        'categories': {
            'saved': Audience.query.filter_by(category='saved').count(),
            'curated': Audience.query.filter_by(category='curated').count(),
            'trending': Audience.query.filter_by(category='trending').count()
        }
    })

@main.route('/dashboard')
@login_required
def dashboard():
    user_audiences = Audience.query.filter_by(user_id=current_user.id).all()
    user_lists = CuratedList.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', 
                         audiences=user_audiences,
                         lists=user_lists)

@main.route('/discover')
@login_required
def discover():
    interests_string = request.args.get('interests', '')
    interests = [i.strip() for i in interests_string.split(',') if i.strip()]
    
    # Get related audiences based on interests
    related_audiences = []
    if interests:
        for interest in interests:
            audiences = Audience.query.filter(
                or_(
                    Audience.theme.ilike(f'%{interest}%'),
                    Audience.topic.ilike(f'%{interest}%')
                )
            ).limit(5).all()
            related_audiences.extend(audiences)
    
    # Get curated lists matching interests
    curated_lists = []
    if interests:
        for interest in interests:
            lists = CuratedList.query.filter(
                or_(
                    CuratedList.theme.ilike(f'%{interest}%'),
                    CuratedList.topic.ilike(f'%{interest}%')
                )
            ).limit(3).all()
            curated_lists.extend(lists)
    
    # Get popular subreddits for interests
    reddit_service = RedditService()
    popular_subreddits = []
    if interests:
        for interest in interests:
            subreddits = reddit_service.search_by_interest(interest)
            popular_subreddits.extend(subreddits)
    
    return render_template('discover.html',
                         interests=interests_string,
                         related_audiences=related_audiences,
                         curated_lists=curated_lists,
                         popular_subreddits=popular_subreddits)

@main.route('/api/audiences/bulk', methods=['POST'])
@login_required
def save_bulk_audience():
    data = request.get_json()
    interests = [i.strip() for i in data.get('interests', '').split(',') if i.strip()]
    subreddits = data.get('subreddits', [])
    
    # Store all subreddits
    subreddit_names = [s.get('name') for s in subreddits if s.get('name')]
    
    audience = Audience(
        name=f"Audience for {', '.join(interests)}",
        subreddit=subreddit_names[0] if subreddit_names else None,  # Primary subreddit
        description=f"Curated subreddits for: {', '.join(interests)}",
        category='saved',
        user_id=current_user.id,
        subreddit_list=subreddit_names,  # Store all subreddits
        theme=interests[0] if interests else None,
        topic=', '.join(interests),
        data={}  # Will be populated with aggregated data
    )
    
    # Get initial data from all subreddits
    reddit_service = RedditService()
    combined_data = reddit_service.analyze_multiple_subreddits(subreddit_names)
    audience.data = combined_data
    
    db.session.add(audience)
    db.session.commit()
    
    return jsonify(audience.to_dict()), 201

@main.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@main.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500