from dataclasses import dataclass
import httpx
import json

# @dataclass
# class SentenceSet:
#     lang: str
#     sentences: [str]

class Scraper:
    access_args = {}
    
    def __init__(self, access_args):
        self.access_args = access_args
    
    def generate_access_obj() -> dict:
        ...
    
    def sentence_generator():
        ...
        
class Tatoeba(Scraper):
    
    def generate_access_obj():
        url = 'https://tatoeba.org/en/api_v0/search\?from={lang}&word_count_min={min_words}&page={page}'
        
        return {
            'url': url
        }
    
    def sentence_generator():
        access_obj = self.generate_access_obj()
        
        fmtd_obj = access_obj.copy()
        fmtd_obj['url'] = url.format(**self.access_args)
        
        res = json(httpx.get(**fmtd_obj).text)
        
        while res['paging']['Sentences']['page'] < res['paging']['Sentences']['pageCount']:
            yield from res['results']['text']
            
            fmtd_obj = access_obj.copy()
            fmtd_obj['url'] = url.format(**self.access_args)
            fmtd_obj['page'] += 1
        
            res = json(httpx.get(**fmtd_obj).text)
        
        
        
    