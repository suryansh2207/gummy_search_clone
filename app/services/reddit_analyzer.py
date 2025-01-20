# app/reddit_analyzer.py
from collections import Counter, defaultdict
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize
from textblob import TextBlob
import nltk
import re

class RedditAnalyzer:
    def __init__(self):
        nltk.download('punkt')
        nltk.download('stopwords')
        nltk.download('wordnet')
        nltk.download('averaged_perceptron_tagger')
        
        # Custom stop words that preserve important terms
        custom_stops = set(['http', 'https', 'www', 'com', 'reddit'])
        self.stop_words = set(stopwords.words('english')) | custom_stops
        
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
    
    def clean_text(self, text):
        """Basic text cleaning"""
        if not text:
            return ""
        # Remove URLs
        text = re.sub(r'http\S+|www\S+|https\S+', '', text, flags=re.MULTILINE)
        # Remove special characters but keep question marks
        text = re.sub(r'[^\w\s\?]', ' ', text)
        # Remove extra whitespace
        text = ' '.join(text.split())
        return text.lower()

    def get_trending_topics(self, posts, min_count=2):
        """Extract trending topics from posts with improved processing"""
        word_data = defaultdict(lambda: {'count': 0, 'score': 0, 'comments': 0})
        
        for post in posts:
            # Get post title and clean it
            title = post.title.lower()
            
            # Get post text if available
            body = post.selftext.lower() if hasattr(post, 'selftext') else ''
            
            # Combine title and first 500 characters of body
            combined_text = f"{title} {body[:500]}"
            
            # Clean text
            cleaned_text = re.sub(r'http\S+|www\S+|https\S+', '', combined_text)
            cleaned_text = re.sub(r'[^\w\s]', ' ', cleaned_text)
            
            # Extract meaningful phrases (2-3 words)
            words = cleaned_text.split()
            phrases = []
            
            # Single words
            phrases.extend([w for w in words if len(w) > 2 
                          and not w.isnumeric() 
                          and w not in self.stop_words])
            
            # Two-word phrases
            for i in range(len(words)-1):
                phrase = f"{words[i]} {words[i+1]}"
                if all(len(w) > 2 and not w.isnumeric() and w not in self.stop_words 
                       for w in phrase.split()):
                    phrases.append(phrase)
            
            # Update word data with engagement metrics
            for phrase in set(phrases):  # Use set to avoid counting duplicates
                word_data[phrase]['count'] += 1
                word_data[phrase]['score'] += post.score
                word_data[phrase]['comments'] += post.num_comments
        
        # Convert to list of trending topics
        trending = []
        for phrase, data in word_data.items():
            if data['count'] >= min_count:
                engagement_score = (data['score'] * 0.7) + (data['comments'] * 0.3)  # Weight score higher
                trending.append({
                    'topic': phrase,
                    'count': data['count'],
                    'score': data['score'],
                    'comments': data['comments'],
                    'engagement': engagement_score,
                })
        
        # Sort by engagement score
        trending.sort(key=lambda x: x['engagement'], reverse=True)
        
        # Return top 20 trending topics
        return trending[:20]

    def analyze_themes(self, posts):
        """Analyze common themes in posts"""
        theme_counts = defaultdict(int)
        theme_posts = defaultdict(list)
        
        for post in posts:
            title = self.clean_text(post.title)
            text = self.clean_text(post.selftext if hasattr(post, 'selftext') else '')
            combined_text = f"{title} {text}"
            
            # Check for themes
            matched_themes = set()
            for theme, indicators in self.theme_indicators.items():
                if any(indicator in combined_text for indicator in indicators):
                    matched_themes.add(theme)
                    
            # If no theme matched, categorize as "Other"
            if not matched_themes:
                theme_counts['Other'] += 1
                theme_posts['Other'].append({
                    'title': post.title,
                    'url': f"https://reddit.com{post.permalink}",
                    'score': post.score
                })
            else:
                for theme in matched_themes:
                    theme_counts[theme] += 1
                    theme_posts[theme].append({
                        'title': post.title,
                        'url': f"https://reddit.com{post.permalink}",
                        'score': post.score
                    })
        
        # Calculate percentages and prepare results
        total_posts = len(posts)
        themes_analysis = []
        
        for theme in theme_counts.keys():
            count = theme_counts[theme]
            theme_data = {
                'theme': theme,
                'count': count,
                'percentage': round((count / total_posts) * 100, 1),
                'examples': sorted(theme_posts[theme], 
                                 key=lambda x: x['score'], 
                                 reverse=True)[:3]  # Top 3 posts per theme
            }
            themes_analysis.append(theme_data)
        
        # Sort by count
        themes_analysis.sort(key=lambda x: x['count'], reverse=True)
        return themes_analysis