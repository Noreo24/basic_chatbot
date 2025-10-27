import os
import importlib

# Dynamically import Flask to avoid static "could not be resolved" warnings and provide a clear install error.
try:
    flask = importlib.import_module("flask")
except Exception as e:
    raise ImportError("The 'flask' package is required. Install it with 'pip install flask' and try again. Original error: {}".format(e))
Flask = flask.Flask
jsonify = flask.jsonify
request = flask.request

# Require ollama to be installed; fail-fast with clear error if missing.
try:
    ollama = importlib.import_module("ollama")
except Exception as e:
    raise ImportError("The 'ollama' client is required. Install it and try again. Original error: {}".format(e))

from rag_engine import handle_query


app = Flask(__name__)


@app.route("/api/llm/", methods=["GET", "POST"])
def llm_api():
    if request.method == "GET":
        return jsonify({"status": "ok", "service": "llm-rag"})

    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    user_message = (payload.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    top_k = int(payload.get("top_k", 3))

    try:
        rag_result = handle_query(user_message, top_k=top_k)
    except Exception as e:
        return jsonify({"error": "RAG error", "detail": str(e)}), 500

    candidates = rag_result.get("candidates", [])
    context_text = "\n\n".join(f"Question: {c.get('question','')}\nAnswer: {c.get('answer','')}" for c in candidates)
    answer = rag_result.get("answer", "") or ""

    # Refine with Ollama using a strict system instruction and the gemma2:2b model.
    try:
        system_msg = "Bạn chỉ được phép trả lời dựa trên phần 'answer' từ tài liệu tham khảo."
        messages = [
            {"role": "system", "content": f"{system_msg}\n\nTài liệu tham khảo:\n{context_text}"},
            {"role": "user", "content": user_message},
        ]
        # Use fixed model as requested
        resp = ollama.chat(model="gemma2:2b", messages=messages)
        assistant_content = ""
        if isinstance(resp, dict):
            assistant_content = resp.get("message", {}).get("content") or resp.get("content") or ""
        if assistant_content:
            answer = assistant_content
    except Exception:
        # Don't crash the service if Ollama refine fails; return base RAG answer
        pass

    print(f"[LLM ANSWER] {answer}")
    return jsonify({
        "answer": answer,
        "rag_match": rag_result.get("match"),
        "rag_score": rag_result.get("score"),
        "candidates": candidates,
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "1") == "1")