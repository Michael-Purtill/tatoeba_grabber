import argparse

from corpus.demaistre import DeMaistre


def main():
    parser = argparse.ArgumentParser(description='Build an Anki deck from a corpus.')
    parser.add_argument('-o', '--output', default='demaistre.apkg',
                        help='path to write the .apkg to (default: %(default)s)')
    parser.add_argument('-n', '--limit', type=int, default=None,
                        help='only the N easiest sentences (default: the whole corpus)')
    parser.add_argument('--name', default=None,
                        help='deck name as it appears in Anki')
    parser.add_argument('--no-audio', dest='audio', action='store_false',
                        help='skip text-to-speech (much faster while iterating)')
    args = parser.parse_args()

    corpus = DeMaistre()
    print(f'Scraping and parsing {corpus.link} ...')

    count = corpus.generate_deck(args.output, name=args.name,
                                 limit=args.limit, audio=args.audio)
    print(f'Wrote {count} cards to {args.output}')


if __name__ == '__main__':
    main()
