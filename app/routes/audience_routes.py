from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from app.models import Audience,db
from app.services.reddit_service import RedditService
from app.extensions import db
from sqlalchemy import or_
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy.exc import SQLAlchemyError

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

@audience.route('/del/<int:id>', methods=['DELETE'])
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

@audience.route('/curated/save', methods=['POST'])
@login_required
def save_curated_audience():
    try:
        data = request.json
        category = data.get('category')
        subreddits = data.get('subreddits', [])

        if not category or not subreddits:
            return jsonify({'error': 'Invalid input'}), 400

        # Save subreddits to the database as part of the category
        for subreddit in subreddits:
            new_audience = Audience(
                name=subreddit.get('name'),
                description=subreddit.get('description'),
                subscribers=subreddit.get('subscribers'),
                category=category,
                user_id=current_user.id  # Associate with the logged-in user
            )
            db.session.add(new_audience)

        db.session.commit()
        return jsonify({'message': f'Audience saved for category: {category}'}), 200

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({'error': 'Database error occurred', 'details': str(e)}), 500
    except Exception as e:
        return jsonify({'error': 'An error occurred', 'details': str(e)}), 500

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