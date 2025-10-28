import os
import importlib
import json
import threading
import time
import uuid

# Dynamically import Flask to avoid static "could not be resolved" warnings and provide a clear install error.
try:
    flask = importlib.import_module("flask")
except Exception as e:
    raise ImportError("The 'flask' package is required. Install it with 'pip install flask' and try again. Original error: {}".format(e))
Flask = flask.Flask
jsonify = flask.jsonify
request = flask.request
from flask import stream_with_context, Response

# Require ollama to be installed; fail-fast with clear error if missing.
try:
    ollama = importlib.import_module("ollama")
except Exception:
    ollama = None

from rag_engine import handle_query


app = Flask(__name__)

# track active streaming requests: request_id -> threading.Event
_active_streams = {}


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

    # Try to refine using Ollama (non-stream mode). Non-fatal if not available.
    if ollama is not None:
        try:
            system_msg = "Bạn chỉ được phép trả lời dựa trên phần 'answer' từ tài liệu tham khảo."
            messages = [
                {"role": "system", "content": f"{system_msg}\n\nTài liệu tham khảo:\n{context_text}"},
                {"role": "user", "content": user_message},
            ]
            resp = ollama.chat(model="gemma2:2b", messages=messages)
            assistant_content = ""
            if isinstance(resp, dict):
                assistant_content = resp.get("message", {}).get("content") or resp.get("content") or ""
            if assistant_content:
                answer = assistant_content
        except Exception:
            pass

    print(f"[LLM ANSWER] {answer}")
    return jsonify({
        "answer": answer,
        "rag_match": rag_result.get("match"),
        "rag_score": rag_result.get("score"),
        "candidates": candidates,
    }), 200


def _stream_chunks(text):
    """Yield small chunks (words) from text to simulate token streaming or real incremental output.
    For production you'd hook into your model's real streaming API here.
    """
    # naive split by whitespace while preserving punctuation
    for token in text.split():
        yield token
    # ensure at least one chunk
    if not text:
        yield ""


def _stream_chunks_chars(text):
    if not text:
        yield ""
    for ch in text:
        yield ch


@app.route('/api/llm/stream', methods=['POST'])
def llm_stream():
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400

    user_message = (payload.get('message') or '').strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    request_id = payload.get('request_id') or str(uuid.uuid4())
    cancel_event = threading.Event()
    _active_streams[request_id] = cancel_event

    def generate():
        try:
            # run retrieval first (fast)
            try:
                rag_result = handle_query(user_message, top_k=int(payload.get('top_k', 3)))
            except Exception as e:
                yield f"data: {json.dumps({'request_id': request_id, 'error': 'rag_error', 'detail': str(e)})}\n\n"
                return

            # base answer
            answer = rag_result.get('answer', '') or ''

            # optionally refine with ollama but in streaming we will just stream the final text's tokens
            if ollama is not None:
                try:
                    candidates = rag_result.get('candidates', [])
                    context_text = "\n\n".join(f"Question: {c.get('question','')}\nAnswer: {c.get('answer','')}" for c in candidates)
                    system_msg = "Bạn chỉ được phép trả lời dựa trên phần 'answer' từ tài liệu tham khảo."
                    messages = [
                        {"role": "system", "content": f"{system_msg}\n\nTài liệu tham khảo:\n{context_text}"},
                        {"role": "user", "content": user_message},
                    ]
                    resp = ollama.chat(model="gemma2:2b", messages=messages)
                    if isinstance(resp, dict):
                        assistant_content = resp.get('message', {}).get('content') or resp.get('content') or ''
                    else:
                        assistant_content = ''
                    if assistant_content:
                        answer = assistant_content
                except Exception:
                    pass

            # stream tokens to client as SSE "data: <json>\n\n"
            for ch in _stream_chunks_chars(answer):
                if cancel_event.is_set():
                    yield f"data: {json.dumps({'request_id': request_id, 'cancelled': True})}\n\n"
                    return
                payload_obj = {'request_id': request_id, 'chunk': ch}
                yield f"data: {json.dumps(payload_obj)}\n\n"
                time.sleep(0.02)  # adjust to taste

            # completed
            yield f"data: {json.dumps({'request_id': request_id, 'done': True})}\n\n"
        finally:
            _active_streams.pop(request_id, None)

    headers = {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no'
    }
    return Response(stream_with_context(generate()), headers=headers)


@app.route('/api/llm/cancel', methods=['POST'])
def llm_cancel():
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"error": "Invalid JSON payload"}), 400
    request_id = payload.get('request_id')
    if not request_id:
        return jsonify({"error": "Missing request_id"}), 400

    ev = _active_streams.get(request_id)
    if ev:
        ev.set()
        return jsonify({'request_id': request_id, 'cancelled': True}), 200
    else:
        return jsonify({'error': 'unknown request_id'}), 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "1") == "1")