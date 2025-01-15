from flask import Blueprint, render_template, jsonify, request, url_for
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
    # Get user's audiences with proper ordering
    user_audiences = Audience.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Audience.created_at.desc()
    ).all()
    
    return render_template('dashboard.html', 
                         audiences=user_audiences)

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
    try:
        data = request.get_json()
        interests = [i.strip() for i in data.get('interests', '').split(',') if i.strip()]
        subreddits = data.get('subreddits', [])
        
        if not interests or not subreddits:
            return jsonify({'error': 'Missing required data'}), 400
            
        audience = Audience(
            name=f"Audience for {', '.join(interests)}",
            description=f"Curated subreddits for: {', '.join(interests)}",
            category='saved',
            user_id=current_user.id,
            theme=interests[0],
            topic=', '.join(interests[1:]) if len(interests) > 1 else None,
            subscribers=sum(s.get('subscribers', 0) for s in subreddits),
            active_users=0,
            subreddit_list=[{
                'name': s['name'],
                'subscribers': s['subscribers'],
                'description': s['description']
            } for s in subreddits],
            data={
                'interests': interests,
                'total_subreddits': len(subreddits)
            }
        )
        
        db.session.add(audience)
        db.session.commit()
        
        return jsonify({'success': True, 'redirect': '/dashboard'}), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"Error saving audience: {e}")
        return jsonify({'error': str(e)}), 500

@main.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@main.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500