from flask import Flask, jsonify, request 
import json 
from threading import Lock 
import os 
# optional ollama client 
try: 
    import ollama 
except Exception: 
    ollama = None 

# safe import rag wrapper 
try:
    from rag_engine import handle_query 
except Exception: 
    def handle_query(message, top_k=None): 
        return {"answer": "", "match": None, "score": 0.0, "candidates": []} 
    
app = Flask(__name__) 
lock = Lock() 

def _parse_json_bytes(raw): 
    for enc in ("utf-8", "utf-16", "latin-1"): 
        try: 
            return json.loads(raw.decode(enc)) 
        except (UnicodeDecodeError, ValueError): 
            continue 
        return None 

@app.route("/api/llm/", methods=["POST", "GET"]) 
def llm_api(): 
    if request.method == "GET": 
        return jsonify({"status": "ok", "service": "llm-rag"}) 
    raw = request.get_data() 
    payload = _parse_json_bytes(raw) 
    if not payload or not isinstance(payload, dict): 
        return jsonify({"error": "Invalid JSON payload"}), 400 
    user_message = (payload.get("message") or "").strip() 
    if not user_message: 
        return jsonify({"error": "Empty message"}), 400 
    top_k = payload.get("top_k", 3) 
    try: 
        rag_result = handle_query(user_message, top_k=top_k) 
    except Exception as e: 
        return jsonify({"error": "RAG error", "detail": str(e)}), 500 
    
    candidates = rag_result.get("candidates", []) 
    context_text = "\n\n".join(f"Question: {c.get('question','')}\nAnswer: {c.get('answer','')}" for c in candidates) 
    answer = rag_result.get("answer", "") or "" 
    
    # Optional refine with Ollama (only if available) 
    if ollama is not None: 
        try: 
            system_msg = "Bạn chỉ được phép trả lời dựa trên phần 'answer' từ tài liệu tham khảo." 
            messages = [ {"role": "system", "content": f"{system_msg}\n\nTài liệu tham khảo:\n{context_text}"}, {"role": "user", "content": user_message}, ] 
            resp = ollama.chat(model=os.environ.get("OLLAMA_MODEL", "gemma2:2b"), messages=messages) 
            assistant_content = "" 
            if isinstance(resp, dict): 
                assistant_content = resp.get("message", {}).get("content") or resp.get("content") or "" 
            if assistant_content: 
                answer = assistant_content 
        except Exception: 
            pass 
    print(f"[LLM ANSWER] {answer}") 
    return jsonify({ "answer": answer, "rag_match": rag_result.get("match"), "rag_score": rag_result.get("score"), "candidates": candidates }), 200 

if __name__ == "__main__": 
    port = int(os.environ.get("PORT", 8000)) 
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG","1") == "1")