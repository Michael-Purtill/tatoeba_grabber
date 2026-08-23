from spacy.language import Language
import statistics
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
            if cur.head.i == cur.i:      # reached the root
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

    # --- difficulty scoring -------------------------------------------------

    # spaCy returns this rank for out-of-vocabulary tokens; left raw it would
    # dominate any average, so it is clamped to the vocabulary size instead.
    OOV_RANK = 2 ** 64 - 1
    SUBORD_DEPS = {'acl', 'acl:relcl', 'advcl', 'ccomp', 'xcomp', 'csubj'}

    # Component weights for the composite difficulty score.
    DIFFICULTY_WEIGHTS = {
        'length': 0.35,
        'depth': 0.20,
        'subordination': 0.20,
        'rarity': 0.20,
        'rare_mood': 0.05,
    }

    def token_depth(self, token: Token) -> int:
        """Distance from `token` up to its sentence root."""
        depth, cur = 0, token
        while cur.head.i != cur.i and depth < 100:
            cur, depth = cur.head, depth + 1
        return depth

    def difficulty_features(self, sent: Span) -> dict[str, float] | None:
        """Raw, uncalibrated difficulty signals for one sentence."""
        content = [t for t in sent if t.is_alpha]
        if not content:
            return None

        vocab_size = self.nlp.vocab.vectors.shape[0]
        ranks = [vocab_size if t.rank == self.OOV_RANK else t.rank for t in content]

        verbs = [t for t in sent if t.pos_ in self.VERBAL]
        rare_mood = sum(
            1 for t in verbs
            if t.morph.get('Mood') == ['Sub']
            or (t.morph.get('Tense') == ['Past'] and t.morph.get('VerbForm') == ['Fin'])
        )

        return {
            'length': len(content),
            'depth': max((self.token_depth(t) for t in sent), default=0),
            'subordination': sum(1 for t in sent if t.dep_ in self.SUBORD_DEPS),
            'rarity': statistics.median(ranks),
            'rare_mood': rare_mood,
        }

    def rank_by_difficulty(self, sents: list[Span]) -> list[tuple[float, Span, dict]]:
        """Sort sentences easiest-first with a 0..1 composite score.

        Each raw feature is converted to a percentile within this batch before
        weighting, so components on wildly different scales (token counts vs.
        frequency ranks) contribute comparably. Scores are therefore relative
        to the batch, not absolute across corpora.
        """
        scored = [(s, f) for s in sents if (f := self.difficulty_features(s))]
        if not scored:
            return []

        weights = self.DIFFICULTY_WEIGHTS
        percentiles = {}
        for key in weights:
            values = [f[key] for _, f in scored]
            order = sorted(range(len(values)), key=lambda i: values[i])
            col = [0.0] * len(values)
            for position, i in enumerate(order):
                col[i] = position / max(len(values) - 1, 1)
            percentiles[key] = col

        out = [
            (sum(weights[k] * percentiles[k][i] for k in weights), sent, feats)
            for i, (sent, feats) in enumerate(scored)
        ]
        return sorted(out, key=lambda row: row[0])
