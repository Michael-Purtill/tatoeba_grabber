from dataclasses import dataclass
import httpx
import json

@dataclass
class SentenceSet:
    lang: str
    sentences: [str]

class Scraper:
    access_args = {}
    
    def __init__(self, access_args):
        self.access_args = access_args
    
    def generate_access_obj(self) -> dict:
        ...
    
    def sentence_generator(self):
        ...
        
class Tatoeba(Scraper):
    
    def generate_access_obj(self):
        url = 'https://tatoeba.org/en/api_v0/search?from={lang}&word_count_min={min_words}&page={page}'
        
        return {
            'url': url
        }
    
    def sentence_generator(self):
        access_obj = self.generate_access_obj()
        
        fmtd_obj = access_obj.copy()
        fmtd_obj['url'] = access_obj['url'].format(**self.access_args)
        
        res = json.loads(httpx.get(**fmtd_obj).text)
        
        while res['paging']['Sentences']['page'] < res['paging']['Sentences']['pageCount']:
            ss = SentenceSet(lang='fr', sentences=[r['text'] for r in res['results']])
            self.access_args['page'] += 1
            fmtd_obj = access_obj.copy()
            fmtd_obj['url'] = access_obj['url'].format(**self.access_args)
        
            res = json.loads(httpx.get(**fmtd_obj).text)
            
            yield ss
            
    
            

        
        
        
    