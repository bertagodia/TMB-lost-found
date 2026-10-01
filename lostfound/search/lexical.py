"""Tokenización y referencia BM25."""
from collections import Counter
import math
import re
import unicodedata

STOPWORDS = set('de del el la los las un una unos unas con en y que mi me se es a por para'.split())


def tokens(text):
    plain = ''.join(c for c in unicodedata.normalize('NFKD', text.lower())
                    if not unicodedata.combining(c))
    return [t for t in re.findall(r'\w+', plain) if t not in STOPWORDS]


class LexicalRetriever:
    def __init__(self, objects):
        self.objects = objects
        self.documents = [Counter(tokens(o['description'])) for o in objects]
        self.df = Counter(t for doc in self.documents for t in doc)
        self.avg_length = sum(map(lambda d: sum(d.values()), self.documents)) / max(1, len(objects))

    def scores(self, text):
        """BM25, followed by bounded scaling for a small metadata bonus."""
        result = {}
        for obj, doc in zip(self.objects, self.documents):
            score = 0.0
            for term in set(tokens(text)):
                count = doc[term]
                if not count:
                    continue
                idf = math.log(1 + (len(self.objects) - self.df[term] + 0.5) / (self.df[term] + 0.5))
                denominator = count + 1.5 * (0.25 + 0.75 * sum(doc.values()) / max(1, self.avg_length))
                score += idf * count * 2.5 / denominator
            result[obj['id']] = score / (1 + score)
        return result
