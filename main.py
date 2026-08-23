from corpus.demaistre import DeMaistre


def main():
    corpus = DeMaistre()

    for page in corpus.page_iterator():
        sent_dfs = corpus.sentence_generator(page)

        for sent_df in sent_dfs:
            print(f"[{sent_df.attrs['difficulty']:.2f}] {sent_df.attrs['text']}")


if __name__ == '__main__':
    main()
