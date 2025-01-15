import praw
import re
from flask import current_app
from collections import Counter
from datetime import datetime, timedelta
from textblob import TextBlob
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

from app.models import Audience
from .reddit_analyzer import RedditAnalyzer
nltk.download('punkt')
nltk.download('stopwords')

class RedditService:
    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=current_app.config['REDDIT_CLIENT_ID'],
            client_secret=current_app.config['REDDIT_CLIENT_SECRET'],
            user_agent=current_app.config['REDDIT_USER_AGENT']
        )
        self.analyzer = RedditAnalyzer()
        
        self.category_patterns = {
            'news': r'news|update|announced|release',
            'solution_requests': r'looking for|need|anyone know|recommend|suggestion',
            'pain_points': r'problem|issue|frustrated|annoying|hate',
            'advice_requests': r'how to|help|advice|guide|tips',
            'ideas': r'idea|thought|concept|suggestion',
            'money_talk': r'price|cost|worth|expensive|cheap|money|paid',
            'opportunities': r'hiring|job|opportunity|looking to hire',
            'self_promotion': r'i made|check out|launching|my project|i created'
        }
    
    def search_subreddits(self, query):
        results = []
        for subreddit in self.reddit.subreddits.search(query, limit=10):
            results.append({
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.description,
                'subscribers': subreddit.subscribers
            })
        return results
    
    def get_subreddit_info(self, name):
        try:
            subreddit = self.reddit.subreddit(name)
            return {
                'name': subreddit.display_name,
                'title': subreddit.title,
                'description': subreddit.description,
                'subscribers': subreddit.subscribers
            }
        except:
            return None
    
    def get_trending_subreddits(self):
        trending = self.reddit.trending_subreddits()
        return [self.get_subreddit_info(sr) for sr in trending]
    
    def search_by_interest(self, interest):
        try:
            results = []
            for subreddit in self.reddit.subreddits.search(interest, limit=15):
                try:
                    if subreddit and subreddit.subscribers and subreddit.subscribers > 10000:
                        results.append({
                            'name': subreddit.display_name,
                            'title': subreddit.title,
                            'description': getattr(subreddit, 'description', ''),
                            'subscribers': subreddit.subscribers,
                            'category': interest
                        })
                except Exception as e:
                    print(f"Error processing subreddit: {e}")
                    continue
            return sorted(results, key=lambda x: x['subscribers'], reverse=True)
        except Exception as e:
            print(f"Error searching Reddit: {e}")
            return []

    def get_subreddit_data(self, subreddit_name):
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = list(subreddit.hot(limit=100))
            
            analysis = self.analyzer.analyze_content(posts)
            
            return {
                'stats': {
                    'subscribers': subreddit.subscribers,
                    'active_users': subreddit.active_user_count
                },
                'trending_topics': analysis['trending_topics'],
                'themes': analysis['themes'],
                'sentiment': analysis['sentiment']
            }
        except Exception as e:
            print(f"Error fetching subreddit data: {e}")
            return None

    def _categorize_posts(self, posts):
        categories = {category: [] for category in self.category_patterns.keys()}
        categories['top_content'] = []  # For highly engaged posts
        
        for post in posts:
            # Add to top content if highly engaged
            if post.score > 100 or len(list(post.comments)) > 50:
                categories['top_content'].append({
                    'title': post.title,
                    'score': post.score,
                    'comments': len(list(post.comments)),
                    'url': f"https://reddit.com{post.permalink}"
                })
            
            # Categorize based on patterns
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

    def _analyze_themes(self, categorized_posts):
        themes = {}
        
        # Process each category
        for category, posts in categorized_posts.items():
            themes[category] = {
                'posts': sorted(posts, key=lambda x: x.get('score', 0), reverse=True)[:5],
                'count': len(posts),
                'total_engagement': sum(p.get('score', 0) for p in posts)
            }
        
        return themes

    def _extract_topics(self, posts):
        topics = Counter()
        for post in posts:
            text = f"{post.title} {post.selftext if hasattr(post, 'selftext') else ''}"
            words = word_tokenize(text.lower())
            topics.update(words)
        return [topic for topic, _ in topics.most_common(5)]

    def _extract_market_data(self, posts):
        products = Counter()
        services = Counter()
        
        for post in posts:
            text = f"{post.title} {post.selftext}"
            # Add product/service detection logic here
            
        return {
            'products': [{'name': p, 'mentions': c} for p, c in products.most_common(5)],
            'services': [{'name': s, 'mentions': c} for s, c in services.most_common(5)]
        }

    def _calculate_engagement(self, topic, posts):
        engagement = 0
        for post in posts:
            if topic in post.title.lower():
                engagement += post.score + len(post.comments)
        return engagement

    def get_trending_topics(self, interest):
        try:
            # Search subreddits for this interest
            subreddits = list(self.reddit.subreddits.search(interest, limit=5))
            trending_data = []
            
            for subreddit in subreddits:
                try:
                    hot_posts = list(subreddit.hot(limit=10))
                    trending_data.append({
                        'subreddit': subreddit.display_name,
                        'subscribers': subreddit.subscribers,
                        'active_users': subreddit.active_user_count,
                        'hot_posts': [{
                            'title': post.title,
                            'score': post.score,
                            'comments': len(list(post.comments)),
                            'url': f"https://reddit.com{post.permalink}"
                        } for post in hot_posts]
                    })
                except Exception as e:
                    print(f"Error processing subreddit {subreddit.display_name}: {e}")
                    continue
                    
            return trending_data
        except Exception as e:
            print(f"Error fetching trending topics: {e}")
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