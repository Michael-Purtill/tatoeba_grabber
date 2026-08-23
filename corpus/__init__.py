from spacy.language import Language
import spacy

class Corpus:
    link: str
    language: str
    nlp: Language
    spacy_model: str
    
    def __init__(self):
        self.nlp = spacy.load(self.spacy_model)
    
    def page_iterator(self):
        ...
    
    def sentence_generator(self, page):
        ...
