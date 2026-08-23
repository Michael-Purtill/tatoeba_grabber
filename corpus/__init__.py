from spacy.language import Language
from spacy.tokens import Span, Token
import spacy


class Corpus:
    link: str
    language: str
    nlp: Language
    spacy_model: str

    # Tokens that can anchor a verbal complex, and the dependency labels that
    # mark a token as an auxiliary of its head rather than a verb in its own right.
    VERBAL = {'VERB', 'AUX'}
    AUX_DEPS = {'aux:tense', 'aux:pass', 'aux:caus'}

    # Negation particles the model leaves without a Polarity=Neg feature.
    # Only consulted when the anchor already carries a `ne`, which disambiguates
    # the ones with non-negative senses ("plus grande", "un point").
    NEG_ADV: set[str] = set()
    NE_FORMS: set[str] = set()

    def __init__(self):
        self.nlp = spacy.load(self.spacy_model)

    def page_iterator(self):
        ...

    def sentence_generator(self, page):
        ...

    def verbal_anchor(self, token: Token) -> Token | None:
        """Nearest verbal ancestor: the token this piece belongs to.

        Walks up rather than checking neighbours, because the pieces of a verbal
        complex are frequently non-adjacent ("il n'a jamais plus rien dit").
        """
        cur, seen = token, set()
        while cur.i not in seen:
            seen.add(cur.i)
            if cur.head is cur:          # reached the root
                break
            cur = cur.head
            if cur.pos_ in self.VERBAL and cur.dep_ not in self.AUX_DEPS:
                return cur
        return None

    def group_ids(self, sent: Span) -> dict[int, int]:
        """Map token index -> index of the head anchoring its verbal complex.

        Groups a verb with its auxiliaries, reflexive clitics and negation, so
        that a compound tense reads as one unit. Tokens outside any verbal
        complex are absent from the result.
        """
        # Anchors: verbal tokens that are not themselves auxiliaries.
        groups = {
            t.i: t.i for t in sent
            if t.pos_ in self.VERBAL and t.dep_ not in self.AUX_DEPS
        }
        anchors_with_ne: set[int] = set()

        for t in sent:
            if t.i in groups:
                continue
            if t.dep_ in self.AUX_DEPS and t.head.i in groups:
                groups[t.i] = t.head.i
                continue
            if t.morph.get('Reflex') == ['Yes'] or t.morph.get('Polarity') == ['Neg']:
                anchor = self.verbal_anchor(t)
                if anchor is not None and anchor.i in groups:
                    groups[t.i] = anchor.i
                    if t.lower_ in self.NE_FORMS:
                        anchors_with_ne.add(anchor.i)

        # Second sweep: lexical negation particles, only where a `ne` was found.
        for t in sent:
            if t.i in groups or t.pos_ != 'ADV':
                continue
            if t.lemma_.lower() not in self.NEG_ADV:
                continue
            anchor = self.verbal_anchor(t)
            if anchor is not None and anchor.i in anchors_with_ne:
                groups[t.i] = anchor.i

        return groups
