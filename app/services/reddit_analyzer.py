from collections import Counter, defaultdict
from flask import current_app
from textblob import TextBlob
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords

class RedditAnalyzer:
    def __init__(self):
        nltk.download('punkt')
        nltk.download('stopwords')
        
        self.stop_words = set(stopwords.words('english')) | {'http', 'https', 'www', 'com', 'reddit'}
        
        self.theme_patterns = {
            'News': r'news|update|announced|release|launching',
            'Solution Requests': r'looking for|need|anyone know|recommend|suggestion',
            'Pain Points': r'problem|issue|frustrated|annoying|hate|bug|broken',
            'Advice Requests': r'how to|help|advice|guide|tips|tutorial',
            'Ideas': r'idea|thought|concept|suggestion|proposal',
            'Money Talk': r'price|cost|worth|expensive|cheap|money|paid|pricing',
            'Opportunities': r'hiring|job|opportunity|looking to hire|position',
            'Self Promotion': r'i made|check out|launching|my project|i created|built'
        }

    def analyze_content(self, posts):
        if not posts:
            current_app.logger.error("No posts available for analysis.")
            return {'trending_topics': [], 'themes': [], 'sentiment': {}}

        try:
            trending_topics = []
            themes = []
            sentiments = []

            for post in posts:
                title = getattr(post, 'title', '').lower()
                if not title:
                    continue

                # Analyze content
                trending_topics.append(title)  # Placeholder for your logic
                themes.append({'title': title, 'score': post.score})
                sentiment = TextBlob(title).sentiment.polarity
                sentiments.append(sentiment)

            current_app.logger.debug(f"Trending topics: {trending_topics}")
            current_app.logger.debug(f"Discussion themes: {themes}")
            current_app.logger.debug(f"Sentiments: {sentiments}")

            return {
                'trending_topics': trending_topics[:5],  # Adjust limit as needed
                'themes': themes[:5],  # Adjust limit as needed
                'sentiment': {'average': sum(sentiments) / len(sentiments) if sentiments else 0}
            }
        except Exception as e:
            current_app.logger.error(f"Error analyzing content: {str(e)}")
            return {'trending_topics': [], 'themes': [], 'sentiment': {}}

    def get_trending_topics(self, posts, min_count=2):
        word_data = defaultdict(lambda: {'count': 0, 'score': 0, 'comments': 0, 'examples': []})
        
        for post in posts:
            # Process title and text
            text = f"{post.title} {post.selftext if hasattr(post, 'selftext') else ''}"
            text = self._clean_text(text)
            
            # Get phrases
            phrases = self._extract_phrases(text)
            
            # Update metrics
            for phrase in set(phrases):
                word_data[phrase]['count'] += 1
                word_data[phrase]['score'] += post.score
                word_data[phrase]['comments'] += len(post.comments.list())
                word_data[phrase]['examples'].append({
                    'title': post.title,
                    'url': f"https://reddit.com{post.permalink}",
                    'score': post.score
                })
        
        # Convert to list and sort
        trending = []
        for phrase, data in word_data.items():
            if data['count'] >= min_count:
                engagement = (data['score'] * 0.7) + (data['comments'] * 0.3)
                trending.append({
                    'topic': phrase,
                    'count': data['count'],
                    'score': data['score'],
                    'comments': data['comments'],
                    'engagement': engagement
                })
        
        # Sort by engagement and return top 20
        return sorted(trending, 
                     key=lambda x: x['engagement'], 
                     reverse=True)[:20]

    def analyze_themes(self, posts):
        theme_data = {theme: [] for theme in self.theme_patterns}
        
        for post in posts:
            try:
                # Get post content
                title = post.title
                text = post.selftext if hasattr(post, 'selftext') else ''
                full_text = self._clean_text(f"{title} {text}")

                if not full_text:
                    continue
                
                # Calculate engagement
                comments_count = len(post.comments.list())
                engagement = post.score + (comments_count * 0.3)
                
                # Check each theme
                for theme, pattern in self.theme_patterns.items():
                    if re.search(pattern, full_text, re.IGNORECASE):
                        theme_data[theme].append({
                            'title': title,
                            'url': f"https://reddit.com{post.permalink}",
                            'score': post.score,
                            'comments': comments_count,
                            'engagement': engagement,
                            'sentiment': TextBlob(full_text).sentiment.polarity,
                            'created_utc': post.created_utc
                        })
            except Exception as e:
                print(f"Error processing post {post.id}: {e}")
                continue
        
        # Process theme data
        processed_themes = {}
        for theme, posts in theme_data.items():
            if posts:
                # Sort posts by engagement
                sorted_posts = sorted(posts, key=lambda x: x['engagement'], reverse=True)
                
                processed_themes[theme] = {
                    'posts': sorted_posts[:5],  # Top 5 posts
                    'count': len(posts),
                    'total_engagement': sum(p['engagement'] for p in posts),
                    'avg_sentiment': sum(p['sentiment'] for p in posts) / len(posts),
                    'metrics': {
                        'total_score': sum(p['score'] for p in posts),
                        'total_comments': sum(p['comments'] for p in posts),
                        'avg_engagement': sum(p['engagement'] for p in posts) / len(posts)
                    }
                }
        
        return processed_themes

    def _clean_text(self, text):
        """Clean text safely"""
        try:
            if not text or not isinstance(text, str):
                return ""
            # Remove URLs    
            text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
            # Remove special chars but keep questions
            text = re.sub(r'[^\w\s\?]', ' ', text)
            # Remove extra whitespace
            return ' '.join(text.split()).strip()
        except Exception as e:
            current_app.logger.error(f"Error cleaning text: {e}")
            return ""

    def _extract_phrases(self, text):
        words = text.split()
        phrases = []
        
        # Single words
        phrases.extend([w for w in words if len(w) > 2 and w not in self.stop_words])
        
        # Two-word phrases
        for i in range(len(words)-1):
            phrase = f"{words[i]} {words[i+1]}"
            if all(len(w) > 2 and w not in self.stop_words for w in phrase.split()):
                phrases.append(phrase)
                
        return phrases

    def analyze_sentiment(self, posts):
        sentiments = []
        for post in posts:
            text = f"{post.title} {post.selftext if hasattr(post, 'selftext') else ''}"
            sentiment = TextBlob(text).sentiment
            sentiments.append(sentiment.polarity)
        
        return {
            'average': sum(sentiments) / len(sentiments) if sentiments else 0,
            'positive': len([s for s in sentiments if s > 0]),
            'negative': len([s for s in sentiments if s < 0]),
            'neutral': len([s for s in sentiments if s == 0])
        }