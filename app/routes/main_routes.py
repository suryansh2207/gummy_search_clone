import json
from flask import Blueprint, current_app, flash, render_template, jsonify, request, url_for, redirect
from flask_login import current_user, login_required
from app.models import Audience, CuratedList
from sqlalchemy import or_
from app import db
from functools import wraps
import time

from app.services.content_analyzer import ContentAnalyzer
from app.services.reddit_service import RedditService
main = Blueprint('main', __name__)

def rate_limit(limit=1, per=1):
    def decorator(f):
        last_reset = {}
        counts = {}
        
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                # Use IP or user_id as key
                key = str(current_user.id) if current_user.is_authenticated else request.remote_addr
                now = time.time()
                
                # Reset counter if time window expired
                if key not in last_reset or now - last_reset[key] >= per:
                    last_reset[key] = now
                    counts[key] = 0
                
                # Check limit
                if counts.get(key, 0) >= limit:
                    return jsonify({
                        'error': 'Rate limit exceeded',
                        'retry_after': int(per - (now - last_reset[key]))
                    }), 429
                
                counts[key] = counts.get(key, 0) + 1
                return f(*args, **kwargs)
                
            except Exception as e:
                current_app.logger.error(f"Rate limit error: {e}")
                return f(*args, **kwargs)
                
        return wrapper
    return decorator

@main.route('/')
def index():
    if current_user.is_authenticated:
        try:
            user_audiences = Audience.query.filter_by(user_id=current_user.id).all()
            stats = {
                'saved_audiences': len(user_audiences),
                'total_subscribers': sum(a.subscribers or 0 for a in user_audiences),
                'recent_audiences': [a.to_dict() for a in 
                    Audience.query.filter_by(user_id=current_user.id)
                    .order_by(Audience.created_at.desc())
                    .limit(3)]
            }
            return render_template('dashboard/home.html', stats=stats)
            
        except Exception as e:
            current_app.logger.error(f"Error in index route: {e}")
            return render_template('error.html'), 500
            
    return render_template('landing.html')

@main.route('/search')
@rate_limit(limit=10, per=60)  # 10 requests per minute
def search():
    return render_template('search.html')

@main.route('/trending')  # Cache for 10 minutes
@rate_limit(limit=5, per=60)  # 5 requests per minute
def trending():
    try:
        page = int(request.args.get('page', 1))
        timeframe = request.args.get('timeframe', 'weekly')
        limit = int(request.args.get('limit', 10))
        
        query = Audience.query.filter_by(category='trending')
        
        if timeframe == 'weekly':
            query = query.order_by(Audience.weekly_posts.desc())
        else:
            query = query.order_by(Audience.active_users.desc())
            
        audiences = query.paginate(page, limit, False).items
        return jsonify([a.to_dict() for a in audiences])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

@main.route('/audience/<int:id>')
@login_required
def audience_detail(id):
    try:
        audience = Audience.query.get_or_404(id)
        reddit_service = RedditService()
        
        trending_data = {
            'trending_topics': [],
            'theme_analysis': [],
            'total_posts': 0,
            'errors': []
        }
        
        valid_subreddits = [s for s in audience.subreddit_list if s.get('name')]
        
        if not valid_subreddits:
            trending_data['errors'].append('No valid subreddits found')
            return render_template(
                'audience/detail.html',
                audience=audience,
                trending_data=trending_data
            )
        
        for subreddit in valid_subreddits:
            try:
                if not subreddit['name']:
                    continue
                    
                content = reddit_service.get_trending_content(
                    subreddit_name=str(subreddit['name']).strip(),
                    limit=25
                )
                
                if content and content.get('trending_topics'):
                    trending_data['trending_topics'].extend(content['trending_topics'])
                if content and content.get('theme_analysis'):
                    trending_data['theme_analysis'].extend(content['theme_analysis'])
                if content and content.get('total_posts'):
                    trending_data['total_posts'] += content['total_posts']
                    
            except Exception as e:
                error_msg = f"Error analyzing r/{subreddit['name']}: {str(e)}"
                trending_data['errors'].append(error_msg)
                current_app.logger.error(error_msg)
                continue
        
        if trending_data['trending_topics']:
            trending_data['trending_topics'].sort(key=lambda x: x.get('engagement', 0), reverse=True)
            trending_data['trending_topics'] = trending_data['trending_topics'][:20]
        
        if trending_data['theme_analysis']:
            theme_counts = {}
            for theme in trending_data['theme_analysis']:
                if not theme or not theme.get('theme'):
                    continue
                theme_key = str(theme['theme'])
                if theme_key in theme_counts:
                    theme_counts[theme_key]['count'] += theme.get('count', 0)
                    if theme.get('examples'):
                        theme_counts[theme_key]['examples'].extend(theme['examples'])
                else:
                    theme_counts[theme_key] = theme.copy()
            
            trending_data['theme_analysis'] = sorted(
                theme_counts.values(), 
                key=lambda x: x.get('count', 0),
                reverse=True
            )
        
        return render_template(
            'audience/detail.html',
            audience=audience,
            trending_data=trending_data
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in audience detail: {e}")
        return render_template('error.html'), 500

@main.route('/api/posts/<subreddit>')
@login_required
def get_subreddit_posts(subreddit):
    reddit_service = RedditService()
    posts = reddit_service.get_subreddit_posts(subreddit)
    return jsonify({'posts': posts})

@main.route('/api/posts/search')
@login_required
def search_posts():
    subreddit = request.args.get('subreddit')
    query = request.args.get('query')
    
    if not subreddit or not query:
        return jsonify({'error': 'Missing parameters'}), 400
        
    reddit_service = RedditService()
    posts = reddit_service.search_posts(subreddit, query)
    
    return jsonify({
        'posts': posts,
        'total': len(posts)
    })


@main.route('/api/subreddit/<subreddit>/analysis')
@login_required
@rate_limit(limit=5, per=60)
def get_subreddit_analysis(subreddit):
    try:
        reddit_service = RedditService()
        analysis = reddit_service.get_subreddit_analysis(subreddit)
        
        if analysis is None:
            return jsonify({'error': 'Unable to analyze subreddit'}), 404
            
        return jsonify(analysis)
    except Exception as e:
        current_app.logger.error(f"Error in subreddit analysis: {e}")
        return jsonify({'error': str(e)}), 500

@main.route('/api/subreddit/<subreddit>/search')
@login_required
@rate_limit(limit=10, per=60)
def search_subreddit(subreddit):
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'Query parameter required'}), 400
        
    try:
        reddit_service = RedditService()
        results = reddit_service.search_posts(subreddit, query)
        return jsonify({'results': results})
    except Exception as e:
        current_app.logger.error(f"Error in subreddit search: {e}")
        return jsonify({'error': str(e)}), 500

@main.route('/api/subreddit/<subreddit>/save', methods=['POST'])
@login_required
def save_subreddit_analysis(subreddit):
    try:
        reddit_service = RedditService()
        analysis = reddit_service.get_subreddit_analysis(subreddit)
        
        if analysis is None:
            return jsonify({'error': 'Unable to analyze subreddit'}), 404
            
        # Create new audience from analysis
        audience = Audience(
            name=f"r/{subreddit} Analysis",
            description=analysis['metadata']['description'],
            category='saved',
            user_id=current_user.id,
            theme=next(iter(analysis['themes'])) if analysis['themes'] else None,
            topic=', '.join([topic['topic'] for topic in analysis['trending_topics'][:3]]),
            subscribers=analysis['metadata']['subscribers'],
            active_users=analysis['metadata']['active_users'],
            data={
                'analysis_date': time.time(),
                'trending_topics': analysis['trending_topics'],
                'themes': analysis['themes'],
                'sentiment': analysis['sentiment']
            }
        )
        
        db.session.add(audience)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'audience_id': audience.id
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving analysis: {e}")
        return jsonify({'error': str(e)}), 500

@main.route('/dashboard/analysis')
@login_required
def analysis_dashboard():
    # Get user's saved analyses
    saved_analyses = Audience.query.filter_by(
        user_id=current_user.id,
        category='saved'
    ).order_by(
        Audience.created_at.desc()
    ).all()
    
    return render_template(
        'dashboard/analysis.html',
        saved_analyses=saved_analyses
    )

@main.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@main.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500