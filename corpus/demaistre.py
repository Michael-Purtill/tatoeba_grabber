from corpus import Corpus
import httpx
from bs4 import BeautifulSoup
import time
import spacy
import pandas as pd

class DeMaistre(Corpus):
    link = 'https://fr.wikisource.org/wiki/Consid%C3%A9rations_sur_la_France'
    language = 'french'
    spacy_model = 'fr_core_news_md'
    headers = {'user-agent': 'BookScraper/1.0 (https://github.com/Michael-Purtill/tatoeba_grabber)'}
    
    def page_processor(self, page):
        soup = BeautifulSoup(page, 'html.parser')
        # The schema.org/Chapter div is only the header template (author/title
        # nav box); the body text lives in ProofreadPage's output div.
        raw_content = soup.find(class_='prp-pages-output')
        ps = raw_content.find_all('p')
        
        text = [p.get_text().strip() for p in ps]

        return ' '.join(text)

    def page_iterator(self):
        with httpx.Client(headers=self.headers) as client:
            raw = client.get(self.link)
            raw.raise_for_status()

            soup = BeautifulSoup(raw.text, 'html.parser')

            content = soup.find(class_='ws-summary')

            page_links = [f"https://fr.wikisource.org{a.get('href')}" for a in content.find_all('a')][1:]

            raw_pages = []
            
            for pl in page_links[0:1]:
                raw_pages.append(client.get(pl).text)

            i = 0
            while i < len(raw_pages):
                rp = raw_pages[i]
                i += 1
                yield self.page_processor(rp)
    
    def sentence_generator(self, page):
        doc = self.nlp(page)
        sent_dfs = []
        
        # sentences = [sent.text.strip() for sent in doc.sents]\
        for sent in doc.sents:
            raw_sent_dicts = []
            
            for token in sent:
                sd = {
                    'i': token.i,                    # position — you need this to sort groups
                    'token': token.text,
                    'lemma': token.lemma_,
                    'pos': token.pos_,
                    'tag': token.tag_,
                    'dep': token.dep_,               # the link type
                    'head_i': token.head.i,          # the anchor
                    'morph': str(token.morph),       # see note below
                }
                raw_sent_dicts.append(sd)
            
            sent_df = pd.DataFrame.from_dict(raw_sent_dicts)
            print(sent_df)
            print()
            sent_dfs.append(sent_df)
        
        
    
        
        