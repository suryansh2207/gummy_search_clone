import numpy as np
from transformers import pipeline, AutoTokenizer, AutoModel
from sklearn.cluster import KMeans
from gensim import corpora, models
import spacy
import torch
from collections import defaultdict
from datetime import datetime, timedelta
import torch.nn.functional as F
from textstat import textstat
from sklearn.feature_extraction.text import TfidfVectorizer
from langdetect import detect
import re

class ContentAnalyzer:
    def __init__(self):
        # Load models
        self.nlp = spacy.load('en_core_web_sm')
        self.tokenizer = AutoTokenizer.from_pretrained('bert-base-uncased')
        self.model = AutoModel.from_pretrained('bert-base-uncased')
        self.sentiment_analyzer = pipeline('sentiment-analysis')
        self.zero_shot = pipeline('zero-shot-classification')
        self.tfidf = TfidfVectorizer(max_features=1000)
        
        # Theme categories
        self.themes = [
            'Technology', 'Gaming', 'Sports', 'Business', 
            'Entertainment', 'Science', 'Education', 'Politics'
        ]

        self.theme_patterns = {
            'Questions': r'\?|how|what|why|when|where|who',
            'Discussion': r'discuss|opinion|thoughts|think|debate',
            'News': r'update|announcement|release|launch|breaking',
            'Guide': r'guide|tutorial|help|tips|howto',
            'Review': r'review|rating|experience|recommend',
            'Showcase': r'project|created|built|made|completed',
            'Problem': r'issue|bug|error|problem|help',
            'Meta': r'subreddit|rules|meta|mod|announcement'
        }

    def analyze_content(self, posts):
        if not posts:
            return self._empty_response()

        # Process posts
        processed_posts = self._preprocess_posts(posts)
        
        # Generate embeddings
        embeddings = self._get_embeddings(processed_posts)
        
        return {
            'trending_topics': self._extract_topics(processed_posts),
            'themes': self._classify_themes(processed_posts, embeddings),
            'clusters': self._cluster_content(embeddings, processed_posts),
            'sentiment': self._analyze_sentiment(processed_posts),
            'readability': self._analyze_readability(processed_posts),
            'engagement_patterns': self._analyze_engagement(processed_posts),
            'trends': self._analyze_trends(processed_posts),
            'keywords': self._extract_keywords(processed_posts),
            'quality_metrics': self._analyze_quality(processed_posts),
            'language_stats': self._analyze_language(processed_posts)
        }

    def _preprocess_posts(self, posts):
        processed = []
        for post in posts:
            text = f"{post.title} {getattr(post, 'selftext', '')}"
            doc = self.nlp(text)
            
            # Extract meaningful tokens
            tokens = [token.text.lower() for token in doc 
                     if not token.is_stop and token.is_alpha]
            
            processed.append({
                'text': text,
                'tokens': tokens,
                'title': post.title,
                'url': f"https://reddit.com{post.permalink}",
                'engagement': post.score + len(post.comments.list()),
                'created': datetime.fromtimestamp(post.created_utc)
            })
        return processed

    def _get_embeddings(self, processed_posts):
        embeddings = []
        for post in processed_posts:
            # Get BERT embeddings
            inputs = self.tokenizer(post['text'], 
                                 return_tensors='pt', 
                                 truncation=True, 
                                 max_length=512)
            with torch.no_grad():
                outputs = self.model(**inputs)
            # Use CLS token embedding
            embeddings.append(outputs.last_hidden_state[0][0].numpy())
        return np.array(embeddings)

    def _extract_topics(self, processed_posts):
        # Prepare corpus
        texts = [post['tokens'] for post in processed_posts]
        dictionary = corpora.Dictionary(texts)
        corpus = [dictionary.doc2bow(text) for text in texts]
        
        # Train LDA model
        lda_model = models.LdaModel(corpus,
                                  num_topics=10,
                                  id2word=dictionary,
                                  passes=15)
        
        # Extract topics
        topics = []
        for idx, topic in lda_model.print_topics():
            words = [(word, float(score)) for word, score in 
                    [item.split('*') for item in topic.split(' + ')]]
            topics.append({
                'id': idx,
                'keywords': words[:5],
                'posts': len([1 for doc_topics in lda_model[corpus]
                            if idx == max(doc_topics, key=lambda x: x[1])[0]])
            })
        
        return topics

    def _classify_themes(self, processed_posts, embeddings):
        theme_data = defaultdict(lambda: {
            'posts': 0,
            'total_engagement': 0,
            'recent_posts': [],
            'summary': ''
        })
        
        for post in processed_posts:
            # Check each theme pattern
            for theme, pattern in self.theme_patterns.items():
                if re.search(pattern, post['text'], re.IGNORECASE):
                    theme_data[theme]['posts'] += 1
                    theme_data[theme]['total_engagement'] += post['engagement']
                    theme_data[theme]['recent_posts'].append(post['text'])

        # Create summaries for each theme
        for theme in theme_data:
            posts_text = ' '.join(theme_data[theme]['recent_posts'][-10:])  # Last 10 posts
            theme_data[theme]['summary'] = self._summarize_text(posts_text)

        # Convert to list format
        themes = []
        for theme, data in theme_data.items():
            if data['posts'] > 0:  # Only include themes with posts
                themes.append({
                    'theme': theme,
                    'posts': data['posts'],
                    'engagement': data['total_engagement'],
                    'summary': data['summary']
                })
        
        return sorted(themes, key=lambda x: x['engagement'], reverse=True)

    def _summarize_text(self, text):
        # Simple extractive summarization
        sentences = text.split('.')[:3]  # Take first 3 sentences
        summary = '. '.join(s.strip() for s in sentences if s.strip())
        return summary if summary else "No summary available"

    def _cluster_content(self, embeddings, processed_posts):
        # K-means clustering
        n_clusters = min(8, len(processed_posts))
        kmeans = KMeans(n_clusters=n_clusters)
        clusters = kmeans.fit_predict(embeddings)
        
        # Organize posts by cluster
        cluster_data = defaultdict(list)
        for post, cluster_id in zip(processed_posts, clusters):
            cluster_data[int(cluster_id)].append({
                'title': post['title'],
                'url': post['url'],
                'engagement': post['engagement']
            })
        
        return [{
            'cluster_id': cluster_id,
            'size': len(posts),
            'top_posts': sorted(posts, 
                              key=lambda x: x['engagement'], 
                              reverse=True)[:3]
        } for cluster_id, posts in cluster_data.items()]

    def _analyze_sentiment(self, processed_posts):
        sentiments = []
        for post in processed_posts:
            result = self.sentiment_analyzer(post['text'][:512])[0]
            sentiments.append({
                'title': post['title'],
                'label': result['label'],
                'score': result['score'],
                'engagement': post['engagement']
            })
        
        return {
            'overall': self._aggregate_sentiment(sentiments),
            'examples': sorted(sentiments, 
                             key=lambda x: x['engagement'], 
                             reverse=True)[:5]
        }

    def _aggregate_sentiment(self, sentiments):
        total_pos = sum(1 for s in sentiments if s['label'] == 'POSITIVE')
        return {
            'positive_ratio': total_pos / len(sentiments),
            'average_score': np.mean([s['score'] for s in sentiments])
        }

    def _analyze_readability(self, posts):
        scores = []
        for post in posts:
            scores.append({
                'title': post['title'],
                'flesch_score': textstat.flesch_reading_ease(post['text']),
                'grade_level': textstat.text_standard(post['text'])
            })
        return scores

    def _analyze_engagement(self, posts):
        time_periods = {
            'morning': 0,
            'afternoon': 0,
            'evening': 0,
            'night': 0
        }
        for post in posts:
            hour = post['created'].hour
            if 6 <= hour < 12: time_periods['morning'] += post['engagement']
            elif 12 <= hour < 17: time_periods['afternoon'] += post['engagement']
            elif 17 <= hour < 22: time_periods['evening'] += post['engagement']
            else: time_periods['night'] += post['engagement']
        return time_periods

    def _analyze_trends(self, posts):
        weekly_data = defaultdict(lambda: {'posts': 0, 'engagement': 0})
        for post in posts:
            week = post['created'].isocalendar()[1]
            weekly_data[week]['posts'] += 1
            weekly_data[week]['engagement'] += post['engagement']
        return dict(weekly_data)

    def _extract_keywords(self, posts):
        texts = [post['text'] for post in posts]
        tfidf_matrix = self.tfidf.fit_transform(texts)
        feature_names = self.tfidf.get_feature_names_out()
        
        keywords = []
        for idx, text in enumerate(texts):
            scores = dict(zip(feature_names, tfidf_matrix[idx].toarray()[0]))
            keywords.append({
                'title': posts[idx]['title'],
                'top_keywords': sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
            })
        return keywords

    def _analyze_quality(self, posts):
        metrics = []
        for post in posts:
            metrics.append({
                'title': post['title'],
                'length': len(post['text']),
                'avg_word_length': np.mean([len(word) for word in post['tokens']]),
                'unique_words': len(set(post['tokens'])),
                'engagement_ratio': post['engagement'] / len(post['text']) if len(post['text']) > 0 else 0
            })
        return metrics

    def _analyze_language(self, posts):
        languages = defaultdict(int)
        for post in posts:
            try:
                lang = detect(post['text'])
                languages[lang] += 1
            except:
                languages['unknown'] += 1
        return dict(languages)

    def _empty_response(self):
        return {
            'trending_topics': [],
            'themes': [],
            'clusters': [],
            'sentiment': {'overall': {}, 'examples': []},
            'readability': [],
            'engagement_patterns': {},
            'trends': {},
            'keywords': [],
            'quality_metrics': [],
            'language_stats': {}
        }