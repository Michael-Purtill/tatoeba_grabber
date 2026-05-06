from classes import Tatoeba

def main():
    t = Tatoeba({'page': 1, 'lang': 'fra', 'min_words': 7})
    
    x = next(t.sentence_generator())
    y = next(t.sentence_generator())
    print(x)
    print()
    print(y)
if __name__ == '__main__':
    main()