import os
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class RAGEngine:
    """Simple TF-IDF based retriever.

    Expects a CSV/Excel at `path` with optional columns 'question' and 'answer'.
    This implementation always uses TF-IDF (no embeddings/faiss).
    """

    def __init__(self, path, top_k=3):
        self.top_k = int(top_k)

        if str(path).lower().endswith('.csv'):
            self.df = pd.read_csv(path)
        else:
            # fallback to excel (openpyxl required if used)
            self.df = pd.read_excel(path, engine='openpyxl')

        # safe concat of question+answer into searchable texts
        qcol = self.df.get('question', pd.Series([''] * len(self.df))).fillna('')
        acol = self.df.get('answer', pd.Series([''] * len(self.df))).fillna('')
        self.texts = (qcol.astype(str) + ' ' + acol.astype(str)).tolist()

        self._build_tfidf()

    def _build_tfidf(self):
        self.vectorizer = TfidfVectorizer(max_features=10000, ngram_range=(1, 2))
        # shape: (n_documents, n_features)
        self.X = self.vectorizer.fit_transform(self.texts)

    def retrieve(self, query, top_k=None):
        k = int(top_k or self.top_k)
        q_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self.X).flatten()
        top_indices = np.argsort(-sims)[:k]
        return [(int(i), self.texts[i], float(sims[i])) for i in top_indices]


# lazy singleton engine
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        data_path = os.environ.get("RAG_DATA_PATH", os.path.join(os.path.dirname(__file__), "data.csv"))
        top_k = int(os.environ.get("RAG_TOP_K", 3))
        _engine = RAGEngine(data_path, top_k=top_k)
    return _engine


def handle_query(message, top_k=None):
    """Wrapper used by the service.

    Returns a dict: { answer, match, score, candidates }
    candidates: list of { index, question, answer, text, score }
    """
    eng = _get_engine()
    results = eng.retrieve(message, top_k=top_k)
    candidates = []
    for idx, text, score in results:
        try:
            row = eng.rows[int(idx)]
            q = row.get('question', '') if 'question' in row else ''
            a = row.get('answer', '') if 'answer' in row else ''
        except Exception:
            q, a = '', ''
        candidates.append({
            'index': int(idx),
            'question': str(q),
            'answer': str(a),
            'text': text,
            'score': float(score),
        })

    if candidates:
        best = candidates[0]
        answer = best.get('answer') or best.get('text') or ''
        match = best.get('text')
        score = best.get('score', 0.0)
    else:
        answer = ''
        match = None
        score = 0.0

    return {'answer': answer, 'match': match, 'score': score, 'candidates': candidates}