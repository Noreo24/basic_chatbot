package com.chatbot.be.websocket;

import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.Disposable;

/**
 * Servlet-based WebSocket handler (TextWebSocketHandler) that proxies chat
 * requests to the Python
 * LLM service (SSE) and streams tokens back to the client. Supports
 * cancellation by requestId.
 */
@Component
public class ChatWebSocketHandler extends TextWebSocketHandler {

    private final WebClient webClient;
    private final ObjectMapper mapper = new ObjectMapper();

    // track active streaming subscriptions by requestId so they can be cancelled
    private final Map<String, Disposable> activeStreams = new ConcurrentHashMap<>();

    public ChatWebSocketHandler(WebClient.Builder builder) {
        this.webClient = builder.baseUrl("http://localhost:8000").build();
    }

    @Override
    public void handleTextMessage(WebSocketSession session, TextMessage message) throws IOException {
        String payload = message.getPayload();
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> map = mapper.readValue(payload, Map.class);
            String requestId = (String) map.get("requestId");
            Boolean cancel = (Boolean) map.getOrDefault("cancel", false);

            if (cancel != null && cancel && requestId != null) {
                // notify python to cancel
                webClient.post().uri(uriBuilder -> uriBuilder.path("/api/llm/cancel").build())
                        .contentType(MediaType.APPLICATION_JSON).bodyValue(Map.of("request_id", requestId))
                        .retrieve().bodyToMono(Void.class).subscribe();

                Disposable d = activeStreams.remove(requestId);
                if (d != null && !d.isDisposed()) {
                    d.dispose();
                }

                session.sendMessage(
                        new TextMessage("{\"requestId\": \"" + requestId + "\", \"status\": \"cancelled\"}"));
                return;
            }

            String userMessage = (String) map.get("message");
            final String finalRequestId = (requestId == null || requestId.isEmpty())
                    ? java.util.UUID.randomUUID().toString()
                    : requestId;

            // subscribe to Python SSE stream and forward each chunk to websocket session
            Disposable disp = webClient.post()
                    .uri("/api/llm/stream")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of("message", userMessage, "request_id", finalRequestId))
                    .retrieve()
                    .bodyToFlux(String.class)
                    .subscribe(chunk -> {
                        try {
                            session.sendMessage(new TextMessage(chunk));
                        } catch (IOException e) {
                            /* ignore */ }
                    }, err -> {
                        try {
                            session.sendMessage(new TextMessage("{\"error\": \"" + err.getMessage() + "\"}"));
                        } catch (IOException ex) {
                        }
                    }, () -> {
                        try {
                            session.sendMessage(new TextMessage(
                                    "{\"requestId\": \"" + finalRequestId + "\", \"status\": \"done\"}"));
                        } catch (IOException e) {
                        }
                    });

            activeStreams.put(finalRequestId, disp);

        } catch (Exception e) {
            session.sendMessage(new TextMessage("{\"error\": \"invalid-payload\"}"));
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, org.springframework.web.socket.CloseStatus status)
            throws Exception {
        // Optional: clean up any subscriptions associated with this session if you
        // track them per-session
        super.afterConnectionClosed(session, status);
    }
}

// curl -N -H "Content-Type: application/json" -d "{\"message\":\"Ai là Tuan?\",\"request_id\":\"t1\"}" http://localhost:8000/api/llm/stream