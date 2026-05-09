from classes import Tatoeba, NLP

def main():
    t = Tatoeba({'page': 1, 'lang': 'fra', 'min_words': 7})
    
    x = next(t.sentence_generator())
    
    nlp = NLP(x)
    
    print(nlp.token_sets[0][0].morph)
if __name__ == '__main__':
    main()