from collections import defaultdict
import json
from flask import Blueprint, current_app, flash, render_template, jsonify, request, url_for, redirect
from flask_login import current_user, login_required
from app.models import Audience, CuratedList
from sqlalchemy import or_
from app import db
from functools import wraps
import time
from copy import deepcopy

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
    interests_string = request.args.get('interests', '') # Retrieve the interests from the URL
    if len(interests_string) > 1:
        interests = [i.strip() for i in interests_string.split(',') if i.strip()]
    else:
        interests = interests_string  # Process the string

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
        # Parse JSON data from the request
        data = request.get_json()
        interests = data.get('interests', [])
        subreddits = data.get('subreddits', [])
        
        print(f"Creating audience with {len(subreddits)} subreddits")
        
        # Validate inputs
        if not interests or not subreddits:
            return jsonify({'error': 'Missing required data'}), 400
        
        # Format and validate subreddit list
        s_list = []
        for s in subreddits:
            if isinstance(s, dict) and 'name' in s:
                subreddit_data = {
                    'name': s['name'],
                    'subscribers': int(s.get('subscribers', 0)),
                    # 'description': s.get('description', '')
                }
                s_list.append(subreddit_data)
        
        # Validate JSON serialization
        try:
            serialized = json.dumps(s_list)
            # Verify deserialization works too
            json.loads(serialized)
        except (TypeError, ValueError) as e:
            print(f"JSON serialization error: {e}")
            return jsonify({'error': 'Invalid data format'}), 400
            
        print(f"Formatted subreddit_list: {len(s_list)}")
        print(f"Sample subreddit data: {s_list[0] if s_list else 'empty'}")
        
        # Create Audience object
        audience = Audience(
            name=f"Audience for {', '.join(interests)}",
            description=f"Curated subreddits for: {', '.join(interests)}",
            category='saved',
            user_id=current_user.id,
            theme=interests[0],
            topic=', '.join(interests[1:]) if len(interests) > 1 else None,
            subscribers=sum(s.get('subscribers', 0) for s in s_list),
            active_users=0,
            subreddit_list=s_list,  # This will be deep copied in the model
            data={
                'interests': interests,
                'total_subreddits': len(s_list)
            }
        )
        
        # Debug prints
        print(f"Pre-commit subreddit_list type: {type(audience.subreddit_list)}")
        print(f"Pre-commit subreddit_list: {audience.subreddit_list}")
        
        try:
            db.session.add(audience)
            db.session.flush()  # Flush to get the ID but don't commit yet
            
            # Verify the data before commit
            if not audience.subreddit_list:
                raise ValueError("Subreddit list is empty before commit")
                
            db.session.commit()
            
            # Fetch and verify the saved audience
            saved_audience = db.session.query(Audience).get(audience.id)
            
            print(f"Post-commit subreddit_list: {saved_audience.subreddit_list}")
            
            if not saved_audience or not saved_audience.subreddit_list:
                raise ValueError("Subreddit list missing after save")
            
            return jsonify({
                'success': True,
                'redirect': '/dashboard',
                'audience_id': saved_audience.id,
                'subreddit_count': len(saved_audience.subreddit_list)
            }), 201
            
        except Exception as db_error:
            db.session.rollback()
            print(f"Database error: {str(db_error)}")
            return jsonify({'error': f'Database error: {str(db_error)}'}), 500
            
    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main.route('/audience/<int:id>')
@login_required
def audience_detail(id):
    try:
        audience = Audience.query.get_or_404(id)
        
        print("\n=== Audience Debug Info ===")
        print(f"Audience ID: {audience.id}")
        print(f"Audience Name: {audience.name}")
        print(f"Subreddit List: {audience.subreddit_list}")
        
        if not audience.subreddit_list:
            print("Warning: No subreddits found in audience")
            return render_template(
                'audience/detail.html',
                audience=audience,
                content={'trending_topics': [], 'theme_analysis': [], 'total_posts': 0}
            )
            
        reddit_service = RedditService()
        content = {
            'trending_topics': [],
            'theme_analysis': [],
            'total_posts': 0,
            'total_subreddits': len(audience.subreddit_list)
        }
        
        # Debug counter for successful analyses
        successful_analyses = 0
        
        # Analyze each subreddit
        for subreddit in audience.subreddit_list:
            try:
                print(f"\nAnalyzing subreddit: {subreddit['name']}")
                analysis = reddit_service.get_subreddit_analysis(subreddit['name'])
                
                if analysis:
                    print(f"Analysis received for {subreddit['name']}")
                    print(f"Trending topics count: {len(analysis.get('trending_topics', []))}")
                    print(f"Themes count: {len(analysis.get('themes', []))}")
                    
                    # Add trending topics with subreddit context
                    for topic in analysis['trending_topics']:
                        topic['subreddit'] = subreddit['name']
                        content['trending_topics'].append(topic)
                        
                    # Add themes with subreddit context
                    for theme in analysis['themes']:
                        theme['subreddit'] = subreddit['name']
                        content['theme_analysis'].append(theme)
                        
                    successful_analyses += 1
                else:
                    print(f"No analysis data received for {subreddit['name']}")
            except Exception as e:
                print(f"Error analyzing subreddit {subreddit['name']}: {e}")
                continue
        
        print(f"\nAnalysis Summary:")
        print(f"Total subreddits processed: {len(audience.subreddit_list)}")
        print(f"Successful analyses: {successful_analyses}")
        print(f"Total trending topics collected: {len(content['trending_topics'])}")
        print(f"Total themes collected: {len(content['theme_analysis'])}")
        
        # Sort and limit trending topics by engagement score
        if content['trending_topics']:
            content['trending_topics'].sort(key=lambda x: x['engagement'], reverse=True)
            content['trending_topics'] = content['trending_topics'][:20]
        
        # Group themes by category
        if content['theme_analysis']:
            from collections import defaultdict
            theme_summary = defaultdict(lambda: {'count': 0, 'subreddits': set()})
            for theme in content['theme_analysis']:
                theme_summary[theme['theme']]['count'] += theme['count']
                theme_summary[theme['theme']]['subreddits'].add(theme['subreddit'])
            
            # Convert theme summary to list and sort
            content['theme_summary'] = [
                {
                    'theme': theme,
                    'count': data['count'],
                    'subreddits': list(data['subreddits'])
                }
                for theme, data in theme_summary.items()
            ]
            content['theme_summary'].sort(key=lambda x: x['count'], reverse=True)
        else:
            content['theme_summary'] = []
        
        print("\nFinal content structure:")
        print(f"Trending topics: {len(content['trending_topics'])}")
        print(f"Theme summary: {len(content.get('theme_summary', []))}")
        
        return render_template(
            'audience/detail.html',
            audience=audience,
            content=content
        )
        
    except Exception as e:
        print(f"Route error: {e}")
        return render_template('error.html'), 500

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