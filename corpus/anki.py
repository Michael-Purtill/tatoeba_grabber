"""Rendering of parsed sentences into Anki notes.

The back of a card shows the sentence again, with every token clickable. Because
a verbal complex is frequently non-contiguous ("ne ... ai ... vu"), its members
cannot be wrapped in a single element; instead each member carries the same
`data-group`, and clicking any one of them highlights the whole group.
"""

from html import escape

import genanki

# Stable ids: regenerating the deck must update the existing model and deck
# rather than create duplicates on import.
MODEL_ID = 1607392319
DECK_ID = 2059400110

POS_LABELS = {
    'ADJ': 'adjective', 'ADP': 'preposition', 'ADV': 'adverb', 'AUX': 'auxiliary',
    'CCONJ': 'coordinating conjunction', 'DET': 'determiner', 'INTJ': 'interjection',
    'NOUN': 'noun', 'NUM': 'numeral', 'PART': 'particle', 'PRON': 'pronoun',
    'PROPN': 'proper noun', 'SCONJ': 'subordinating conjunction', 'VERB': 'verb',
}

FEATURE_LABELS = {
    ('Gender', 'Masc'): 'masculine', ('Gender', 'Fem'): 'feminine',
    ('Number', 'Sing'): 'singular', ('Number', 'Plur'): 'plural',
    ('Person', '1'): '1st person', ('Person', '2'): '2nd person',
    ('Person', '3'): '3rd person',
    ('Tense', 'Pres'): 'present', ('Tense', 'Imp'): 'imperfect',
    ('Tense', 'Past'): 'past', ('Tense', 'Fut'): 'future',
    ('Mood', 'Ind'): 'indicative', ('Mood', 'Sub'): 'subjunctive',
    ('Mood', 'Cnd'): 'conditional', ('Mood', 'Imp'): 'imperative',
    ('VerbForm', 'Inf'): 'infinitive', ('VerbForm', 'Part'): 'participle',
    ('VerbForm', 'Fin'): 'finite',
    ('Polarity', 'Neg'): 'negative', ('Reflex', 'Yes'): 'reflexive',
    ('PronType', 'Dem'): 'demonstrative', ('PronType', 'Rel'): 'relative',
    ('PronType', 'Int'): 'interrogative', ('PronType', 'Prs'): 'personal',
    ('Definite', 'Def'): 'definite', ('Definite', 'Ind'): 'indefinite',
    ('Poss', 'Yes'): 'possessive',
}

# Compound tenses, keyed on (auxiliary mood, auxiliary tense). The participle
# supplies the lexical verb; the auxiliary carries the tense of the whole.
COMPOUND_TENSES = {
    ('Ind', 'Pres'): 'passé composé',
    ('Ind', 'Imp'): 'plus-que-parfait',
    ('Ind', 'Fut'): 'futur antérieur',
    ('Ind', 'Past'): 'passé antérieur',
    ('Cnd', 'Pres'): 'conditionnel passé',
    ('Sub', 'Pres'): 'subjonctif passé',
    ('Sub', 'Imp'): 'subjonctif plus-que-parfait',
}

SIMPLE_TENSES = {
    ('Ind', 'Pres'): 'présent',
    ('Ind', 'Imp'): 'imparfait',
    ('Ind', 'Fut'): 'futur simple',
    ('Ind', 'Past'): 'passé simple',
    ('Cnd', 'Pres'): 'conditionnel présent',
    ('Sub', 'Pres'): 'subjonctif présent',
    ('Sub', 'Imp'): 'subjonctif imparfait',
}


# spaCy lemmatises these to the pre-vocalic masculine ("un bel arbre"), but the
# dictionary headword is the plain masculine singular.
LEMMA_OVERRIDES = {'bel': 'beau', 'nouvel': 'nouveau', 'vieil': 'vieux',
                   'fol': 'fou', 'mol': 'mou'}

# Features already implied by a named tense; repeating them beside "passé
# composé" contradicts it, since they describe the auxiliary rather than the whole.
TENSE_IMPLIED = {'Mood', 'Tense', 'VerbForm', 'Voice'}


def readable_morph(token, skip=()) -> str:
    """Morphological features as an English phrase."""
    parts = [
        FEATURE_LABELS[(key, value)]
        for key, values in token.morph.to_dict().items()
        for value in [values]
        if key not in skip and (key, value) in FEATURE_LABELS
    ]
    return ', '.join(parts)


def tense_name(head, auxiliaries) -> str | None:
    """Name the tense of a verbal complex, or of a lone verb."""
    if auxiliaries:
        aux = auxiliaries[0]
        mood = (aux.morph.get('Mood') or [''])[0]
        tense = (aux.morph.get('Tense') or [''])[0]
        return COMPOUND_TENSES.get((mood, tense))
    mood = (head.morph.get('Mood') or [''])[0]
    tense = (head.morph.get('Tense') or [''])[0]
    if not mood and head.morph.get('VerbForm') == ['Inf']:
        return 'infinitif'
    return SIMPLE_TENSES.get((mood, tense))


class NoteBuilder:
    """Turns spaCy sentences into the fields of an Anki note."""

    # en.wiktionary carries French entries with English definitions; the #French
    # fragment jumps past the other languages sharing the same spelling.
    WIKTIONARY = 'https://en.wiktionary.org/wiki/{word}#French'

    # Everything except punctuation and symbols gets an entry; Wiktionary has
    # French articles for function words too ("ne", "le", "de").
    UNLINKABLE_POS = {'PUNCT', 'SPACE', 'SYM', 'X'}

    # spaCy tag -> the partOfSpeech heading Wiktionary uses, so the fetched
    # definitions can lead with the section that matches the parse.
    WIKTIONARY_POS = {
        'NOUN': 'Noun', 'PROPN': 'Proper noun', 'VERB': 'Verb', 'AUX': 'Verb',
        'ADJ': 'Adjective', 'ADV': 'Adverb', 'ADP': 'Preposition',
        'PRON': 'Pronoun', 'DET': 'Article', 'NUM': 'Numeral',
        'CCONJ': 'Conjunction', 'SCONJ': 'Conjunction', 'PART': 'Particle',
        'INTJ': 'Interjection',
    }

    def __init__(self, corpus):
        self.corpus = corpus

    def wiktionary_url(self, lemma: str) -> str:
        return self.WIKTIONARY.format(word=lemma.replace(' ', '_'))

    def token_payload(self, token, head, auxiliaries):
        """Label, lemma and link for one token (or for the group it heads)."""
        if head is not None:
            # Group: name the whole complex, and carry agreement from the
            # auxiliary (person/number) without repeating its own tense.
            tense = tense_name(head, auxiliaries)
            label = f'verb — {tense}' if tense else 'verb'
            agreement = readable_morph(auxiliaries[0] if auxiliaries else head,
                                       skip=TENSE_IMPLIED)
            if agreement:
                label = f'{label} ({agreement})'
            lemma = LEMMA_OVERRIDES.get(head.lemma_, head.lemma_)
            return label, lemma, head.pos_

        return self.own_label(token) + (token.pos_,)

    def own_label(self, token):
        """How a single token describes itself, ignoring any group it is in."""
        label = POS_LABELS.get(token.pos_, token.pos_.lower())
        tense = tense_name(token, []) if token.pos_ in ('VERB', 'AUX') else None
        if tense:
            label = f'{label} — {tense}'
        # A named tense already states mood and form; listing them again is noise.
        features = readable_morph(token, skip=TENSE_IMPLIED if tense else ())
        if features:
            label = f'{label} ({features})'
        lemma = LEMMA_OVERRIDES.get(token.lemma_, token.lemma_)
        return label, lemma

    def sentence_html(self, sent) -> str:
        """The sentence with every meaningful token wrapped in a clickable span."""
        groups = self.corpus.group_ids(sent)
        # Auxiliaries belong to their head's entry, not to one of their own.
        auxiliaries: dict[int, list] = {}
        for token in sent:
            if token.dep_ in self.corpus.AUX_DEPS:
                auxiliaries.setdefault(token.head.i, []).append(token)

        pieces = []
        for token in sent:
            # Show the period spelling; the grammar comes from the modernised
            # form the tagger actually saw.
            text = escape(token._.original or token.text)
            space = escape(token.whitespace_)

            group_id = groups.get(token.i)
            head = sent.doc[group_id] if group_id is not None else None
            is_grouped = head is not None and len(
                [i for i, g in groups.items() if g == group_id]) > 1

            if token.is_punct or token.is_space:
                pieces.append(text + space)
                continue

            label, lemma, pos = self.token_payload(
                token, head if is_grouped else None,
                auxiliaries.get(group_id, []) if is_grouped else [])

            attrs = ['class="tok"', f'data-label="{escape(label)}"']
            if is_grouped:
                attrs.append(f'data-group="{group_id}"')
                # The clicked token's own role, so that "ne" reads as a negation
                # particle rather than inheriting "verb" from its group.
                own, _ = self.own_label(token)
                attrs.append(f'data-own="{escape(own)}"')
            if pos not in self.UNLINKABLE_POS and lemma:
                attrs.append(f'data-lemma="{escape(lemma)}"')
                attrs.append(f'data-url="{escape(self.wiktionary_url(lemma))}"')
                wpos = self.WIKTIONARY_POS.get(pos)
                if wpos:
                    attrs.append(f'data-pos="{escape(wpos)}"')

            pieces.append(f'<span {" ".join(attrs)}>{text}</span>{space}')

        return ''.join(pieces)


FRONT_TEMPLATE = """
<div class="sentence front">{{Sentence}}</div>
"""

BACK_TEMPLATE = """
<div class="audio">{{Audio}}</div>
<div class="sentence" id="sentence">{{Annotated}}</div>
<div class="translation">{{Translation}}</div>
<div id="panel" class="panel empty">Tap any word for its grammar.</div>
<div class="source">{{Source}}</div>
<script>
(function () {
  var sentence = document.getElementById('sentence');
  var panel = document.getElementById('panel');
  if (!sentence || !panel) return;

  function clear() {
    var active = sentence.querySelectorAll('.tok.active');
    for (var i = 0; i < active.length; i++) active[i].classList.remove('active');
  }

  function show(token) {
    clear();
    var group = token.getAttribute('data-group');
    // Highlight every member of the group, which may be non-contiguous.
    var members = group
      ? sentence.querySelectorAll('[data-group="' + group + '"]')
      : [token];
    var words = [];
    for (var i = 0; i < members.length; i++) {
      members[i].classList.add('active');
      words.push(members[i].textContent);
    }

    var label = token.getAttribute('data-label') || '';
    var lemma = token.getAttribute('data-lemma');
    var url = token.getAttribute('data-url');

    var html = '<div class="headword">' + words.join(' ') + '</div>';
    html += '<div class="grammar">' + label + '</div>';
    // In a group, also say what the clicked token itself is doing.
    var own = token.getAttribute('data-own');
    if (own) {
      html += '<div class="own">' + token.textContent + ' &middot; ' + own + '</div>';
    }
    if (lemma && url) {
      html += '<div class="lemma">dictionary form: <a href="' + url +
              '" target="_blank" rel="noopener">' + lemma + '</a></div>';
      html += '<div class="definition" id="definition">Looking up ' + lemma + '…</div>';
    }
    panel.innerHTML = html;
    panel.classList.remove('empty');
    if (lemma) define(lemma, token.getAttribute('data-pos'), ++request);
  }

  // ---- Wiktionary definitions -------------------------------------------
  // The REST API sends Access-Control-Allow-Origin: *, so the card's webview
  // may call it directly. Every render is tagged with a request number: a slow
  // response for a word the reader has already clicked past is discarded.
  var API = 'https://en.wiktionary.org/api/rest_v1/page/definition/';
  var request = 0;
  var memory = {};

  function cached(key) {
    if (memory[key] !== undefined) return memory[key];
    try {
      var stored = localStorage.getItem('wikt:' + key);
      return stored ? JSON.parse(stored) : undefined;
    } catch (e) { return undefined; }
  }

  function remember(key, value) {
    memory[key] = value;
    try { localStorage.setItem('wikt:' + key, JSON.stringify(value)); } catch (e) {}
  }

  // Wiktionary definitions arrive as HTML: strip anything active, and turn the
  // relative /wiki/ links into ones that resolve outside the card.
  function sanitize(markup) {
    var host = document.createElement('div');
    host.innerHTML = markup;
    var unwanted = host.querySelectorAll('script, style');
    for (var i = 0; i < unwanted.length; i++) unwanted[i].remove();
    var all = host.querySelectorAll('*');
    for (var j = 0; j < all.length; j++) {
      var el = all[j];
      var names = [];
      for (var k = 0; k < el.attributes.length; k++) names.push(el.attributes[k].name);
      for (var n = 0; n < names.length; n++) {
        var name = names[n];
        if (name === 'href' && el.tagName === 'A') {
          var href = el.getAttribute('href') || '';
          if (href.indexOf('/wiki/') === 0) {
            el.setAttribute('href', 'https://en.wiktionary.org' + href);
            el.setAttribute('target', '_blank');
            el.setAttribute('rel', 'noopener');
          } else if (href.indexOf('http') !== 0) {
            el.removeAttribute('href');
          }
        } else if (name !== 'class') {
          el.removeAttribute(name);
        }
      }
    }
    return host.innerHTML;
  }

  function render(entries, preferredPos) {
    // Lead with the section matching the parse, so a word that is both noun
    // and verb opens on the reading this sentence actually uses.
    var ordered = entries.slice().sort(function (a, b) {
      var am = a.partOfSpeech === preferredPos ? 0 : 1;
      var bm = b.partOfSpeech === preferredPos ? 0 : 1;
      return am - bm;
    });
    var html = '';
    for (var i = 0; i < Math.min(ordered.length, 3); i++) {
      var entry = ordered[i];
      html += '<div class="sense"><span class="pos">' + entry.partOfSpeech + '</span><ol>';
      var defs = entry.definitions || [];
      for (var j = 0; j < Math.min(defs.length, 3); j++) {
        var text = sanitize(defs[j].definition || '');
        if (text.replace(/<[^>]*>/g, '').trim()) html += '<li>' + text + '</li>';
      }
      html += '</ol></div>';
    }
    return html || '<span class="muted">No French entry found.</span>';
  }

  function paint(lemma, entries, preferredPos, ticket) {
    if (ticket !== request) return;            // reader moved on
    var target = document.getElementById('definition');
    if (!target) return;
    target.innerHTML = entries ? render(entries, preferredPos)
                               : '<span class="muted">Definition unavailable offline.</span>';
  }

  function define(lemma, preferredPos, ticket) {
    var hit = cached(lemma);
    if (hit !== undefined) { paint(lemma, hit, preferredPos, ticket); return; }
    if (!window.fetch) { paint(lemma, null, preferredPos, ticket); return; }

    fetch(API + encodeURIComponent(lemma))
      .then(function (response) {
        if (!response.ok) throw new Error(response.status);
        return response.json();
      })
      .then(function (data) {
        var entries = data && data.fr ? data.fr : null;
        remember(lemma, entries);
        paint(lemma, entries, preferredPos, ticket);
      })
      .catch(function () { paint(lemma, null, preferredPos, ticket); });
  }

  sentence.addEventListener('click', function (event) {
    var token = event.target.closest ? event.target.closest('.tok') : null;
    if (token) { event.preventDefault(); show(token); }
  });
})();
</script>
"""

CSS = """
.card {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 20px;
  text-align: left;
  color: #1a1a1a;
  background: #fdfdfb;
  padding: 16px;
}
.sentence { line-height: 1.9; margin-bottom: 18px; }
.sentence.front { text-align: center; font-size: 22px; }
.tok {
  cursor: pointer;
  border-bottom: 1px dotted #b3b3b3;
  padding: 1px 0;
}
.tok:hover { background: #f0ece2; }
.tok.active { background: #ffe9a8; border-bottom-color: #d9a441; }
.translation {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 16px;
  color: #555;
  margin: -6px 0 16px 0;
  padding-left: 12px;
  border-left: 3px solid #e0d9c4;
}
.panel {
  border-top: 1px solid #ddd;
  padding-top: 12px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px;
  min-height: 60px;
}
.panel.empty { color: #999; font-style: italic; }
.headword { font-weight: 600; font-size: 17px; margin-bottom: 2px; }
.grammar { color: #444; }
.own { margin-top: 4px; color: #777; font-size: 14px; }
.lemma { margin-top: 6px; }
.lemma a { color: #1c6ea4; }
.definition { margin-top: 10px; font-size: 14px; line-height: 1.5; }
.definition .sense { margin-bottom: 8px; }
.definition .pos {
  display: inline-block; font-size: 11px; letter-spacing: .06em;
  text-transform: uppercase; color: #8a7a52; background: #f4efe0;
  padding: 1px 6px; border-radius: 3px;
}
.definition ol { margin: 4px 0 0 0; padding-left: 22px; }
.definition li { margin-bottom: 3px; }
.definition a { color: #1c6ea4; text-decoration: none; }
.definition .muted { color: #999; font-style: italic; }
.audio { margin-bottom: 10px; }
.source { margin-top: 14px; font-size: 12px; color: #aaa; }

.nightMode .card, .night_mode .card { color: #e8e6e3; background: #2c2c2e; }
.nightMode .tok:hover, .night_mode .tok:hover { background: #3a3a3c; }
.nightMode .tok.active, .night_mode .tok.active { background: #5c4a1f; }
.nightMode .translation, .night_mode .translation {
  color: #b8b5b0; border-left-color: #4a442f;
}
.nightMode .grammar, .night_mode .grammar { color: #bbb; }
.nightMode .own, .night_mode .own { color: #999; }
.nightMode .lemma a, .night_mode .lemma a { color: #6bb3e0; }
.nightMode .definition a, .night_mode .definition a { color: #6bb3e0; }
.nightMode .definition .pos, .night_mode .definition .pos {
  color: #d8c48a; background: #3d3721;
}
"""


def build_model() -> genanki.Model:
    return genanki.Model(
        MODEL_ID,
        'Parsed sentence',
        fields=[{'name': 'Sentence'}, {'name': 'Annotated'},
                {'name': 'Source'}, {'name': 'Audio'},
                {'name': 'Translation'}],
        templates=[{
            'name': 'Reading',
            'qfmt': FRONT_TEMPLATE,
            'afmt': BACK_TEMPLATE,
        }],
        css=CSS,
    )
