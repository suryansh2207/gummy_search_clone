import praw
import re
from flask import current_app
from collections import Counter
from datetime import datetime
from textblob import TextBlob
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import time
import logging
from prawcore.exceptions import RequestException, ResponseException
import urllib3
from prawcore import NotFound

# Configure logging
logging.basicConfig(level=logging.DEBUG)
praw_logger = logging.getLogger('prawcore')
praw_logger.setLevel(logging.DEBUG)
urllib3_logger = logging.getLogger('urllib3')
urllib3_logger.setLevel(logging.DEBUG)

from app.models import Audience
from .reddit_analyzer import RedditAnalyzer

# Download necessary NLTK data
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
nltk.download('averaged_perceptron_tagger')


class RedditService:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=current_app.config['REDDIT_CLIENT_ID'],
            client_secret=current_app.config['REDDIT_CLIENT_SECRET'],
            user_agent=current_app.config['REDDIT_USER_AGENT']
        )
        self.analyzer = RedditAnalyzer()
        self.min_request_delay = 2  # Minimum delay between requests in seconds
        
        # Theme indicators dictionary
        self.theme_indicators = {
            'Question/Help': ['help', 'question', 'how', 'what', 'why', 'where', 'who', 'when', '?'],
            'Discussion': ['discuss', 'opinion', 'think', 'thoughts', 'perspective', 'view'],
            'Guide/Tutorial': ['guide', 'tutorial', 'how to', 'tips', 'advice', 'steps', 'learn'],
            'News/Update': ['news', 'update', 'announcement', 'release', 'launched'],
            'Showcase': ['showcase', 'created', 'made', 'built', 'finished', 'completed'],
            'Resource': ['resource', 'tool', 'library', 'framework', 'package', 'download'],
            'Meta': ['meta', 'subreddit', 'rules', 'moderator', 'community'],
        }

    
    def get_subreddit_analysis(self, subreddit_name):
        try:
            print(f"\nStarting analysis for r/{subreddit_name}")
            subreddit = self.reddit.subreddit(subreddit_name)
            
            print("Fetching posts...")
            posts = list(subreddit.hot(limit=50))  # Get top 50 posts
            print(f"Fetched {len(posts)} posts")
            
            # Run analysis
            print("Analyzing trending topics...")
            trending_topics = self.analyzer.get_trending_topics(posts)
            print(f"Found {len(trending_topics)} trending topics")
            
            print("Analyzing themes...")
            themes = self.analyzer.analyze_themes(posts)
            print(f"Found {len(themes)} themes")
            
            analysis_result = {
                'metadata': {
                    'name': subreddit.display_name,
                    'subscribers': subreddit.subscribers,
                    'description': subreddit.description,
                    'active_users': subreddit.active_user_count
                },
                'trending_topics': trending_topics,
                'themes': themes,
            }
            
            print(f"Analysis complete for r/{subreddit_name}")
            return analysis_result
            
        except Exception as e:
            print(f"Error analyzing subreddit r/{subreddit_name}: {e}")
            return None
        
    def search_subreddit(reddit, subreddit_name, keywords, sort='new', limit=25):
        try:
            subreddit = reddit.subreddit(subreddit_name)
            search_query = ' OR '.join(keywords)
            
            # Get posts based on sorting option
            if sort == 'new':
                posts = subreddit.new(limit=limit)
            elif sort == 'hot':
                posts = subreddit.hot(limit=limit)
            elif sort == 'top':
                posts = subreddit.top(limit=limit)
            else:
                posts = subreddit.new(limit=limit)
                
            results = []
            for post in posts:
                # Check if post contains any of the keywords
                if any(keyword.lower() in post.title.lower() or 
                    (post.selftext and keyword.lower() in post.selftext.lower()) 
                    for keyword in keywords):
                    results.append({
                        'title': post.title,
                        'url': f"https://reddit.com{post.permalink}",
                        'score': post.score,
                        'num_comments': post.num_comments,
                        'created_utc': post.created_utc,
                        'author': str(post.author),
                        'is_self': post.is_self,
                        'thumbnail': post.thumbnail if hasattr(post, 'thumbnail') else None
                    })

            return results
        except NotFound:
            return []
        except Exception as e:
            print(f"Error searching subreddit: {str(e)}")
            return []

    def get_subreddit_info(self, name):
        if not name or not isinstance(name, str):
            current_app.logger.error("Invalid subreddit name.")
            return None

        try:
            subreddit = self.reddit.subreddit(name.strip())
            return {
                'name': subreddit.display_name,
                'title': getattr(subreddit, 'title', ''),
                'description': getattr(subreddit, 'description', ''),
                'subscribers': getattr(subreddit, 'subscribers', 0)
            }
        except Exception as e:
            current_app.logger.error(f"Error fetching subreddit info: {str(e)}")
            return None

    def get_trending_subreddits(self):
        try:
            trending = self.reddit.trending_subreddits()
            return [self.get_subreddit_info(sr) for sr in trending]
        except Exception as e:
            current_app.logger.error(f"Error fetching trending subreddits: {str(e)}")
            return []

    def search_by_interest(self, interest):
        if not interest or not isinstance(interest, str):
            current_app.logger.error("Invalid interest provided.")
            return []

        try:
            results = []
            for subreddit in self.reddit.subreddits.search(interest, limit=15):
                try:
                    if subreddit and subreddit.subscribers > 10000:
                        results.append({
                            'name': subreddit.display_name,
                            'title': subreddit.title,
                            'description': getattr(subreddit, 'description', ''),
                            'subscribers': subreddit.subscribers,
                            'category': interest
                        })
                except Exception as e:
                    current_app.logger.error(f"Error processing subreddit: {str(e)}")
                    continue

            return sorted(results, key=lambda x: x['subscribers'], reverse=True)
        except Exception as e:
            current_app.logger.error(f"Error searching by interest: {str(e)}")
            return []

    def get_subreddit_data(self, subreddit_name):
        if not subreddit_name or not isinstance(subreddit_name, str):
            current_app.logger.error("Invalid subreddit name provided.")
            return None

        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = list(subreddit.hot(limit=100))
            current_app.logger.debug(f"Fetched {len(posts)} posts from subreddit '{subreddit_name}'.")

            analysis = self.analyzer.analyze_content(posts)
            current_app.logger.debug(f"Analysis result: {analysis}")

            return {
                'stats': {
                    'subscribers': getattr(subreddit, 'subscribers', 0),
                    'active_users': getattr(subreddit, 'active_user_count', 0)
                },
                'trending_topics': analysis.get('trending_topics', 'No trending topics available'),
                'themes': analysis.get('themes', 'No hot discussions available'),
                'sentiment': analysis.get('sentiment', {})
            }
        except Exception as e:
            current_app.logger.error(f"Error fetching subreddit data: {str(e)}")
            return None


    def _categorize_posts(self, posts):
        categories = {category: [] for category in self.category_patterns.keys()}
        categories['top_content'] = []

        for post in posts:
            if post.score > 100 or len(list(post.comments)) > 50:
                categories['top_content'].append({
                    'title': post.title,
                    'score': post.score,
                    'comments': len(list(post.comments)),
                    'url': f"https://reddit.com{post.permalink}"
                })

            text = f"{post.title} {post.selftext}".lower()
            for category, pattern in self.category_patterns.items():
                if re.search(pattern, text):
                    categories[category].append({
                        'title': post.title,
                        'score': post.score,
                        'comments': len(list(post.comments)),
                        'sentiment': TextBlob(text).sentiment.polarity
                    })

        return categories

    def get_trending_topics(self, interest):
        try:
            if not interest:
                return None
                
            subreddits = list(self.reddit.subreddits.search(interest, limit=5))
            trending_data = []
            
            for subreddit in subreddits:
                posts = self.get_subreddit_posts(subreddit.display_name)
                if posts and posts.get('data'):
                    trending_data.extend(posts['data']['trending_topics'])
            
            return sorted(trending_data, key=lambda x: x['engagement'], reverse=True)[:20]
            
        except Exception as e:
            print(f"Error getting trending topics: {e}")  # Debug
            return None

    def get_curated_audiences(self):
        categories = {
            'Technology': ['programming', 'webdev', 'techstartups', 'tech', 'technology'],
            'Business': ['entrepreneur', 'startups', 'marketing', 'business', 'smallbusiness'],
            'Gaming': ['gaming', 'gamedev', 'pcgaming', 'indiegaming'],
            'Science': ['science', 'datascience', 'physics', 'biology'],
            'Creative': ['design', 'art', 'writing', 'photography']
        }
        
        try:
            curated = []
            for category, subreddits in categories.items():
                category_data = []
                for subreddit_name in subreddits:
                    try:
                        subreddit = self.reddit.subreddit(subreddit_name)
                        category_data.append({
                            'name': subreddit.display_name,
                            'subreddit': subreddit.display_name.lower(),
                            'description': subreddit.description,
                            'subscribers': subreddit.subscribers,
                            'active_users': subreddit.active_user_count,
                            'category': category,
                            'theme': category.lower(),
                            'topic': subreddit_name
                        })
                    except Exception as e:
                        print(f"Error fetching subreddit {subreddit_name}: {e}")
                        continue
                
                if category_data:
                    curated.extend(category_data)
            
            return sorted(curated, key=lambda x: x.get('subscribers', 0), reverse=True)
        except Exception as e:
            print(f"Error getting curated audiences: {e}")
            return []

    def get_trending_audiences(self):
        try:
            trending = []
            subreddits = self.reddit.subreddits.popular(limit=20)
            
            for subreddit in subreddits:
                # Calculate growth rate safely
                growth_rate = 0
                if subreddit.subscribers and subreddit.subscribers > 0:
                    active_ratio = (subreddit.active_user_count or 0) / subreddit.subscribers
                    growth_rate = round(active_ratio * 100, 1)
                
                trending.append({
                    'name': subreddit.display_name,
                    'subreddit': subreddit.display_name,
                    'description': subreddit.description,
                    'subscribers': subreddit.subscribers or 0,
                    'active_users': subreddit.active_user_count or 0,
                    'growth_rate': growth_rate,
                    'theme': None,
                    'topic': None
                })
            
            return sorted(trending, key=lambda x: x['growth_rate'], reverse=True)
        except Exception as e:
            print(f"Error getting trending audiences: {e}")
            return []

    def get_trending_content(self, subreddit_name, limit=25):
        print(f"Fetching trending content for: {subreddit_name}")  # Debug
        
        try:
            if not subreddit_name:
                return None
                
            subreddit = self.reddit.subreddit(str(subreddit_name).strip())
            print(f"Got subreddit: {subreddit.display_name}")  # Debug
            
            posts = []
            for post in subreddit.hot(limit=limit):
                try:
                    if not hasattr(post, 'title') or not post.title:
                        continue
                        
                    posts.append({
                        'topic': str(post.title),
                        'score': int(getattr(post, 'score', 0)),
                        'comments': int(getattr(post, 'num_comments', 0)),
                        'url': str(getattr(post, 'url', '')),
                        'created_utc': int(getattr(post, 'created_utc', 0))
                    })
                    print(f"Added post: {post.title[:50]}...")  # Debug
                    
                except Exception as e:
                    print(f"Error processing post: {e}")  # Debug
                    continue
                    
            if not posts:
                print("No posts found")  # Debug
                return {
                    'trending_topics': [],
                    'theme_analysis': [],
                    'total_posts': 0
                }
            
            # Sort by score
            posts.sort(key=lambda x: x['score'], reverse=True)
            
            return {
                'trending_topics': posts[:10],  # Top 10 posts
                'theme_analysis': self.analyzer.analyze_themes(posts) if posts else [],
                'total_posts': len(posts)
            }
            
        except Exception as e:
            print(f"Error in get_trending_content: {e}")  # Debug
            return None

    def _process_posts(self, posts):
        if not posts:
            return {
                'trending_topics': [],
                'theme_analysis': [],
                'total_posts': 0
            }

        trending_topics = [{
            'topic': str(post.title)[:100],
            'score': getattr(post, 'score', 0),
            'comments': getattr(post, 'num_comments', 0),
            'url': getattr(post, 'url', ''),
            'created_utc': getattr(post, 'created_utc', 0)
        } for post in posts if hasattr(post, 'title') and post.title]

        return {
            'trending_topics': trending_topics,
            'theme_analysis': self.analyzer.analyze_themes(posts) if posts else [],
            'total_posts': len(posts)
        }

    def get_subreddit_posts(self, subreddit_name):
        try:
            print(f"Fetching posts for r/{subreddit_name}")  # Debug
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get both hot and top posts
            hot_posts = list(subreddit.hot(limit=25))
            top_posts = list(subreddit.top('week', limit=25))
            all_posts = list(set(hot_posts + top_posts))
            
            if not all_posts:
                return None

            # Use analyzer for trending topics and themes
            trending_topics = self.analyzer.get_trending_topics(all_posts)
            theme_analysis = self.analyzer.analyze_themes(all_posts)
            
            return {
                'data': {
                    'trending_topics': trending_topics,
                    'theme_analysis': theme_analysis,
                    'total_posts': len(all_posts)
                }
            }
            
        except Exception as e:
            print(f"Error fetching subreddit posts: {e}")  # Debug
            return None