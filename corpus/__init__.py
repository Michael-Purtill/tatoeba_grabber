from spacy.language import Language
import hashlib
import io
import os
import re
import statistics
import tempfile
import wave

import genanki
from spacy.tokens import Doc, Token
from spacy.tokens import Span, Token
import spacy

# Set once at import: spaCy raises if an extension is registered twice.
if not Token.has_extension('original'):
    Token.set_extension('original', default=None)


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

    def sentence_frame(self, sent):
        ...

    def corpus_frames(self):
        """Every clean sentence in the corpus as a DataFrame, easiest first.

        Ranks across all pages at once rather than per page, so scores are
        comparable between chapters and the percentiles rest on the whole
        corpus instead of a few dozen sentences.
        """
        pages = list(self.page_iterator())
        # Keep the Docs alive: the Spans below hold references into them.
        docs = [self.normalized_doc(page) for page in pages]
        page_of_doc = {id(doc): n for n, doc in enumerate(docs)}

        sents = [s for doc in docs for s in doc.sents if self.is_clean_sentence(s)]

        frames = []
        for score, sent, feats in self.rank_by_difficulty(sents):
            frame = self.sentence_frame(sent)
            # `i` and `head_i` are Doc-relative, so they collide across pages;
            # page_id keeps rows attributable once frames are concatenated.
            frame.insert(0, 'page_id', page_of_doc[id(sent.doc)])
            frame.attrs['text'] = self.original_text(sent)
            frame.attrs['difficulty'] = score
            frame.attrs['difficulty_features'] = feats
            frames.append(frame)
        return frames

    # Piper voice used for card audio, and where the image put it.
    TTS_VOICE = 'fr_FR-siwis-medium'
    TTS_VOICE_DIR = os.environ.get('PIPER_VOICE_DIR', '/opt/piper-voices')

    def _load_voice(self):
        from piper import PiperVoice
        if not hasattr(self, '_voice'):
            self._voice = PiperVoice.load(
                os.path.join(self.TTS_VOICE_DIR, f'{self.TTS_VOICE}.onnx'))
        return self._voice

    def synthesize(self, text, path):
        """Write `text` to `path` as MP3.

        Synthesis runs on the modernised spelling: espeak reads the period
        forms literally, turning "étoit" into /etwa/ rather than /etɛ/ and
        "françois" into /fʁɑ̃swa/ rather than /fʁɑ̃sɛ/.
        """
        import soundfile

        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as handle:
            self._load_voice().synthesize_wav(text, handle)
        buffer.seek(0)

        samples, rate = soundfile.read(buffer, dtype='float32')
        soundfile.write(path, samples, rate, format='MP3', bitrate_mode='VARIABLE')

    @staticmethod
    def audio_name(text):
        """Stable filename, so regenerating a deck reuses Anki's media."""
        digest = hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]
        return f'tba-{digest}.mp3'

    def generate_deck(self, path, name=None, limit=None, audio=True):
        """Write an Anki .apkg of the corpus, easiest sentences first.

        Cards are added in difficulty order so that Anki's default new-card
        ordering introduces the simplest sentences first.
        """
        from corpus.anki import DECK_ID, NoteBuilder, build_model

        model = build_model()
        deck = genanki.Deck(DECK_ID, name or f'{type(self).__name__} ({self.language})')
        builder = NoteBuilder(self)

        pages = list(self.page_iterator())
        docs = [self.normalized_doc(p) for p in pages]   # Spans reference these
        sents = [s for doc in docs for s in doc.sents if self.is_clean_sentence(s)]

        ranked = self.rank_by_difficulty(sents)
        if limit is not None:
            ranked = ranked[:limit]

        # Media lives in a scratch directory only until the package is zipped.
        with tempfile.TemporaryDirectory() as media_dir:
            media = []
            for n, (_score, sent, _feats) in enumerate(ranked, start=1):
                text = self.original_text(sent)
                sound = ''
                if audio:
                    spoken = ' '.join(sent.text.split())   # modernised spelling
                    filename = self.audio_name(spoken)
                    destination = os.path.join(media_dir, filename)
                    self.synthesize(spoken, destination)
                    media.append(destination)
                    sound = f'[sound:{filename}]'
                    if n % 100 == 0:
                        print(f'  ...synthesized {n}/{len(ranked)}')

                deck.add_note(genanki.Note(
                    model=model,
                    fields=[text, builder.sentence_html(sent), self.link, sound],
                    # Keyed on the sentence so re-generating updates notes in
                    # place instead of duplicating them on re-import.
                    guid=genanki.guid_for(text),
                ))

            genanki.Package(deck, media_files=media).write_to_file(path)
        return len(deck.notes)

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

    # --- orthography ---------------------------------------------------------

    # (pattern, replacement, guard_plural) applied to lowercased words. A rewrite
    # is kept only when the candidate is a word the model knows, which rejects
    # over-application (croit -> crait, droit -> drait) without an exception list.
    # guard_plural additionally rejects words whose singular is already known:
    # "anciens" is the plural of "ancien", whereas "impatiens" has no singular
    # "impatien" and is therefore the archaic spelling of "impatients".
    ORTHOGRAPHY_RULES: list[tuple[str, str, bool]] = []

    # Irregular forms no ending rule reaches.
    ORTHOGRAPHY_MAP: dict[str, str] = {}

    # Words never rewritten: modern words that a rule would otherwise capture
    # because both spellings happen to exist.
    ORTHOGRAPHY_KEEP: set[str] = set()

    # Below this length, rewrites hit common short words (soit, doit, dans).
    ORTHOGRAPHY_MIN_LENGTH = 6

    def normalize_word(self, word: str) -> str:
        """Modernise one word's spelling, or return it unchanged."""
        lowered = word.lower()
        if lowered in self.ORTHOGRAPHY_MAP:
            return self._match_case(word, self.ORTHOGRAPHY_MAP[lowered])
        if lowered in self.ORTHOGRAPHY_KEEP or len(word) < self.ORTHOGRAPHY_MIN_LENGTH:
            return word

        for pattern, replacement, guard_plural in self.ORTHOGRAPHY_RULES:
            candidate = re.sub(pattern, replacement, lowered)
            if candidate == lowered:
                continue
            if guard_plural and self.nlp.vocab[lowered[:-1]].has_vector:
                continue
            if self.nlp.vocab[candidate].has_vector:
                return self._match_case(word, candidate)
        return word

    @staticmethod
    def _match_case(original: str, replacement: str) -> str:
        if original.isupper():
            return replacement.upper()
        if original[:1].isupper():
            return replacement.capitalize()
        return replacement

    def normalized_doc(self, text: str) -> Doc:
        """Parse `text` with modernised spelling, keeping the original forms.

        The tagger is trained on contemporary French and mis-reads period
        spellings — "pourroit" (conditional) comes back as an indicative
        present. Rewriting happens per token so the two docs stay aligned; each
        token keeps its original surface form on `token._.original`.
        """
        base = self.nlp.make_doc(text)
        words = [self.normalize_word(t.text) for t in base]
        spaces = [bool(t.whitespace_) for t in base]

        doc = Doc(self.nlp.vocab, words=words, spaces=spaces)
        for _name, component in self.nlp.pipeline:
            doc = component(doc)

        for token, source in zip(doc, base):
            token._.original = source.text
        return doc

    @staticmethod
    def original_text(sent) -> str:
        """The sentence as it was written, before normalisation."""
        return ' '.join(
            ''.join((t._.original or t.text) + t.whitespace_ for t in sent).split())

    # --- text quality -------------------------------------------------------

    # Characters that show up in mis-OCR'd runs ("plu^ ïf", "£aûre") but not in
    # clean transcriptions. Deliberately excludes '°', which is the French
    # ordinal marker and appears in legitimate enumerations (1°, 2°, 3°).
    JUNK_CHARS = set('^*¦~|_\\£¤')

    # A sentence is discarded above this share of out-of-vocabulary tokens.
    # Clean chapters peak around 0.20, garbled OCR reaches 0.67.
    MAX_OOV_RATIO = 0.30

    # Fragments shorter than this carry too little signal to score or teach.
    MIN_ALPHA_TOKENS = 3

    def is_clean_sentence(self, sent: Span) -> bool:
        """Whether `sent` looks like transcribed prose rather than OCR noise."""
        alpha = [t for t in sent if t.is_alpha]
        if len(alpha) < self.MIN_ALPHA_TOKENS:
            return False
        if any(ch in self.JUNK_CHARS for ch in sent.text):
            return False

        # Letter-spaced headings survive OCR as separate tokens ("P R Ê FA C E").
        # Tested against single-letter French words, which are lowercase ("il y a").
        spaced_caps = sum(1 for t in alpha if len(t.text) == 1 and t.text.isupper())
        if spaced_caps / len(alpha) > 0.5:
            return False

        oov = sum(1 for t in alpha if t.rank == self.OOV_RANK)
        return oov / len(alpha) <= self.MAX_OOV_RATIO

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
