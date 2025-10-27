package com.chatbot.be.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.chatbot.be.model.Message;
import com.chatbot.be.service.ChatbotService;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/v1")
public class ChatbotController {
    private final ChatbotService chatbotService;

    public ChatbotController(ChatbotService chatbotService) {
        this.chatbotService = chatbotService;
    }

    @PostMapping("/chat")
    public Mono<ResponseEntity<Message>> chat(@RequestBody String message) {
        return chatbotService.processChatRequest(message).map(response -> ResponseEntity.ok(response))
                .defaultIfEmpty(ResponseEntity.badRequest().build());
    }
}