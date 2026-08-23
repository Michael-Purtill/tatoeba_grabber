from corpus.demaistre import DeMaistre
def main():
    corpus = DeMaistre()
    pages = corpus.page_iterator()
    
    for p in pages:
        (corpus.sentence_generator(p))
    
    
if __name__ == '__main__':
    main()