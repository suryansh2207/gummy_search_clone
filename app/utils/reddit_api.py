# app/utils/reddit_api.py
import praw
import time
from datetime import datetime, timedelta
from typing import Dict, List
import json
import os

class RedditAPI:
    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self._cache_file = 'subreddit_cache.json'
        self._cache_duration = timedelta(hours=24)
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self._cache_file):
            with open(self._cache_file, 'r') as f:
                cache_data = json.load(f)
                self._cache = {k: (v, datetime.fromisoformat(t)) 
                             for k, (v, t) in cache_data.items()}
        else:
            self._cache = {}

    def _save_cache(self):
        cache_data = {k: (v, t.isoformat()) 
                     for k, (v, t) in self._cache.items()}
        with open(self._cache_file, 'w') as f:
            json.dump(cache_data, f)

    def get_subreddit_info(self, subreddit_name: str) -> Dict:
        # Check cache first
        if subreddit_name in self._cache:
            data, timestamp = self._cache[subreddit_name]
            if datetime.now() - timestamp < self._cache_duration:
                return data

        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            data = {
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.description,
                'subscribers': subreddit.subscribers,
                'created_utc': subreddit.created_utc,
                'over18': subreddit.over18,
                'url': f"https://reddit.com/r/{subreddit.display_name}",
                'icon_img': subreddit.icon_img if hasattr(subreddit, 'icon_img') else None,
                'active_users': subreddit.active_user_count if hasattr(subreddit, 'active_user_count') else None,
            }
            
            # Add growth metrics
            posts = list(subreddit.new(limit=100))
            week_ago = time.time() - (7 * 24 * 60 * 60)
            recent_posts = sum(1 for post in posts if post.created_utc > week_ago)
            data['weekly_posts'] = recent_posts
            
            # Cache the result
            self._cache[subreddit_name] = (data, datetime.now())
            self._save_cache()
            
            return data
        except Exception as e:
            print(f"Error fetching subreddit {subreddit_name}: {str(e)}")
            return None

    def search_subreddits(self, query: str, limit: int = 10) -> List[Dict]:
        try:
            results = []
            for subreddit in self.reddit.subreddits.search(query, limit=limit):
                data = self.get_subreddit_info(subreddit.display_name)
                if data:
                    results.append(data)
            return results
        except Exception as e:
            print(f"Error searching subreddits: {str(e)}")
            return []

    def get_trending_subreddits(self, limit: int = 20) -> List[Dict]:
        try:
            trending = []
            # Get popular subreddits and analyze their growth
            for subreddit in self.reddit.subreddits.popular(limit=100):
                data = self.get_subreddit_info(subreddit.display_name)
                if data and data['weekly_posts'] > 50:  # Filter active communities
                    trending.append(data)
            
            # Sort by weekly post activity
            trending.sort(key=lambda x: x['weekly_posts'], reverse=True)
            return trending[:limit]
        except Exception as e:
            print(f"Error getting trending subreddits: {str(e)}")
            return []