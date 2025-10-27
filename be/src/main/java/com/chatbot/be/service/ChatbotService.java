package com.chatbot.be.service;

import java.time.LocalDateTime;
import java.util.Collections;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import com.chatbot.be.mapper.MessageMapper;
import com.chatbot.be.model.Message;

import org.springframework.core.ParameterizedTypeReference;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ChatbotService {
    private final WebClient webClient;
    private final MessageMapper messageMapper;

    public ChatbotService(WebClient.Builder webClientBuilder, MessageMapper messageMapper) {
        // baseUrl có thể lấy từ application.properties;
        // tạm đặt localhost:8000
        this.webClient = webClientBuilder.baseUrl("http://localhost:8000").build();
        this.messageMapper = messageMapper;
    }

    public Mono<Message> processChatRequest(String message) {
        return webClient.post().uri("/api/llm/").contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Collections.singletonMap("message", message)).retrieve()
                .bodyToMono(new ParameterizedTypeReference<Map<String, Object>>() {
                }).map((Map<String, Object> resp) -> {
                    String answer = String.valueOf(resp.getOrDefault("answer", ""));
                    Message m = new Message();
                    m.setQuestion(message);
                    m.setAnswer(answer);
                    m.setTimestamp(LocalDateTime.now());
                    m.setConversationId(1);
                    return m;
                }) // persist bằng MyBatis (blocking) trên boundedElastic scheduler
                .flatMap(m -> Mono.fromCallable(() -> {
                    messageMapper.insertMessage(m);
                    return m;
                }).subscribeOn(Schedulers.boundedElastic()));
    }
}