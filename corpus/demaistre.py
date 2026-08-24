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
    # 18th-century spellings. The -oi- forms are the big win: they carry the
    # imperfect and conditional, which the tagger otherwise reads as present.
    ORTHOGRAPHY_RULES = [
        (r'oient$', 'aient', False),   # étoient  -> étaient
        (r'oit$', 'ait', False),       # pourroit -> pourrait
        (r'oît$', 'aît', False),       # connoît  -> connaît
        (r'ois$', 'ais', False),       # françois -> français
        (r'ans$', 'ants', True),       # enfans   -> enfants
        (r'ens$', 'ents', True),       # monumens -> monuments
    ]
    ORTHOGRAPHY_MAP = {
        'tems': 'temps', 'foible': 'faible', 'foibles': 'faibles',
        'roide': 'raide', 'roides': 'raides', 'sçavoir': 'savoir',
        # Below ORTHOGRAPHY_MIN_LENGTH, so the ending rules never see them.
        # The length guard has to stay: at four and five characters it is
        # "lois"/"trois"/"soit"/"doit" that the rules would otherwise eat.
        'avoit': 'avait', 'étoit': 'était',
        'avois': 'avais', 'étois': 'étais',
    }

    # "millions tournois" is the livre tournois, not a verb form.
    ORTHOGRAPHY_KEEP = {'tournois', 'bourgeois', 'courtois', 'gaulois', 'patois'}

    NEG_ADV = {'pas', 'plus', 'jamais', 'guère', 'point', 'nullement'}
    NE_FORMS = {'ne', "n'", 'n\u2019'}
    headers = {'user-agent': 'BookScraper/1.0 (https://github.com/Michael-Purtill/tatoeba_grabber)'}
    
    def page_processor(self, page):
        soup = BeautifulSoup(page, 'html.parser')
        # The schema.org/Chapter div is only the header template (author/title
        # nav box); the body text lives in ProofreadPage's output div.
        raw_content = soup.find(class_='prp-pages-output')

        # Redlinks are pages nobody has transcribed yet; ProofreadPage renders
        # them as their own title ("Page:Considérations sur la France.djvu/188"),
        # which would otherwise land in the corpus as text.
        for redlink in raw_content.select('a.new'):
            redlink.decompose()

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
            
            for pl in page_links:
                raw_pages.append(client.get(pl).text)

            i = 0
            while i < len(raw_pages):
                rp = raw_pages[i]
                i += 1
                yield self.page_processor(rp)
    
    def sentence_frame(self, sent):
        """One row per token of `sent`, with morph features expanded."""
        raw_sent_dicts = []
        groups = self.group_ids(sent)

        for token in sent:
            sd = {
                'i': token.i,                    # position — you need this to sort groups
                'token': token.text,
                'lemma': token.lemma_,
                'pos': token.pos_,
                'tag': token.tag_,
                'dep': token.dep_,               # the link type
                'head_i': token.head.i,          # the anchor
                # index of the verb anchoring this token's verbal complex,
                # or None if the token is not part of one
                'group_id': groups.get(token.i),
                } | token.morph.to_dict()
            raw_sent_dicts.append(sd)

        sent_df = pd.DataFrame.from_dict(raw_sent_dicts)
        # Nullable Int64, not int64: group_id is None for non-verbal tokens,
        # which would otherwise coerce the whole column to float.
        sent_df['group_id'] = sent_df['group_id'].astype('Int64')
        return sent_df

    def sentence_generator(self, page):
        """DataFrames for each clean sentence in `page`, in document order.

        Use `corpus_frames` instead to rank sentences by difficulty; scoring a
        single page calibrates the percentiles on too few sentences.
        """
        doc = self.normalized_doc(page)
        # Some chapters are only partly proofread, so drop OCR noise before it
        # reaches the frames (garbled tokens are all OOV and would otherwise
        # dominate the rarity feature).
        return [self.sentence_frame(s) for s in doc.sents if self.is_clean_sentence(s)]
