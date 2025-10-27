import pandas as pd 
import numpy as np 
import os 

# TF 
from sklearn.feature_extraction.text import TfidfVectorizer 
from sklearn.metrics.pairwise import cosine_similarity 

try: 
    import importlib.util, importlib 
    if importlib.util.find_spec("sentence_transformers") is not None: 
        SentenceTransformer = importlib.import_module("sentence_transformers").SentenceTransformer 
    else: 
        raise ImportError("sentence_transformers not found") 
    import faiss 
    _HAVE_EMB = True 
except Exception: 
    _HAVE_EMB = False 
    
class RAGEngine: 
    def __init__(self, path, use_tfidf=False, model_path=None, top_k=3): 
        ''' 
        path: path to data.csv or data.xlsx(expects columns 'question' and 'answer') 
        use_tfidf: if True use TF-IDF retriever(no model download) 
        model_path: local path to sentence-transformers model (if embeddings used) 
        top_k: default top-k results 
        ''' 
        # ensure basic attributes are set before any branching 
        self.top_k = top_k 
        self.use_tfidf = use_tfidf 
        
        # Load csv or excel 
        if str(path).lower().endswith('.csv'): 
            self.df = pd.read_csv(path) 
        else: 
            self.df = pd.read_excel(path, engine='openpyxl') 
        # Build concatenated texts from question+answer columns (fallback to empty strings) 
        self.texts = (self.df.get('question', '').fillna('') + ' ' + self.df.get('answer', '').fillna('')).tolist() 
        # Choose retriever 
        if self.use_tfidf: 
            self._build_tfidf() 
        else: 
            if not _HAVE_EMB: 
                raise RuntimeError("sentence-transformers/faiss not available. Install or set use_tfidf=True") 
            self._build_embedding_index(model_path) 
        print(f"[RAGEngine] Đã nạp {len(self.texts)} dòng từ file: {path}") 
    def _build_tfidf(self): 
        self.vectorizer = TfidfVectorizer(max_features=10000, ngram_range=(1,2)) 
        self.X = self.vectorizer.fit_transform(self.texts) 
        print("[RAGEngine] TF-IDF retriever đã sẵn sàng") 

    def _build_embedding_index(self, model_path): 
        if model_path: 
            self.model = SentenceTransformer(model_path) 
        else: 
            self.model = SentenceTransformer('all-MiniLM-L6-v2') 
        embeddings = self.model.encode(self.texts, convert_to_numpy=True, show_progress_bar=True) 
        faiss.normalize_L2(embeddings)
        dim = embeddings.shape[1] 
        self.index = faiss.IndexFlatIP(dim) 
        self.index.add(embeddings) 
        self._embeddings_matrix = embeddings 
    
    def retrieve(self, query, top_k=None): 
        k = top_k or self.top_k
        if self.use_tfidf: 
            q_vec = self.vectorizer.transform([query]) 
            sims = cosine_similarity(q_vec, self.X).flatten() 
            top_indices = np.argsort(-sims)[:k] 
            return [(int(i), self.texts[i], float(sims[i])) for i in top_indices] 
        else: 
            q_emb = self.model.encode([query], convert_to_numpy=True) 
            faiss.normalize_L2(q_emb) 
            D, I = self.index.search(q_emb, k) 
            return [(int(I[0][i]), self.texts[I[0][i]], float(D[0][i])) for i in range(len(I[0]))]
    
# lazy singleton engine 
_engine = None
def _get_engine():
    global _engine 
    if _engine is None: 
        data_path = os.environ.get("RAG_DATA_PATH", os.path.join(os.path.dirname(__file__), "data.csv")) 
        use_tfidf = os.environ.get("RAG_USE_TFIDF", "1") == "1" 
        model_path = os.environ.get("RAG_MODEL_PATH", None) 
        _engine = RAGEngine(data_path, use_tfidf=use_tfidf, model_path=model_path) 
    return _engine 

def handle_query(message, top_k=None): 
    '''
    Simple wrapper expected by service.py. 
    Returns dict: { answer, match, score, candidates } 
    candidates: list of { index, question, answer, text, score } 
    '''
    eng = _get_engine() 
    results = eng.retrieve(message, top_k=top_k) 
    candidates = [] 
    for idx, text, score in results: 
        # try to get original question/answer from dataframe if available 
        try: 
            row = eng.df.iloc[int(idx)] 
            q = row.get("question", "") if "question" in row else "" 
            a = row.get("answer", "") if "answer" in row else "" 
        except Exception: 
            q, a = "", "" 
        candidates.append({"index": int(idx), "question": q, "answer": a, "text": text, "score": float(score)}) 
    if candidates: 
        best = candidates[0] 
        answer = best.get("answer") or best.get("text") or "" 
        match = best.get("text") 
        score = best.get("score", 0.0) 
    else: 
        answer = "" 
        match = None 
        score = 0.0 
        
    return {"answer": answer, "match": match, "score": score, "candidates": candidates}