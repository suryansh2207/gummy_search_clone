from flask import current_app
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

class ScraperService:
    def scrape(self, url):
        try:
            response = requests.get(url)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            return {
                'title': soup.title.string if soup.title else '',
                'description': self._get_meta_description(soup),
                'meta_data': self._extract_meta_data(soup)
            }
        except Exception as e:
            current_app.logger.error(f"Error scraping {url}: {str(e)}")
            return {}
    
    def _get_meta_description(self, soup):
        meta = soup.find('meta', attrs={'name': 'description'})
        return meta['content'] if meta else ''
    
    def _extract_meta_data(self, soup):
        meta_data = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            if name:
                meta_data[name] = meta.get('content', '')
        return meta_data