from flask import Blueprint, jsonify, request
from app.services.reddit_service import RedditService

api = Blueprint('api', __name__, url_prefix='/api')

@api.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
        
    reddit = RedditService()
    results = reddit.search_subreddits(query)
    return jsonify(results)