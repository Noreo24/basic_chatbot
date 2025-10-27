package com.chatbot.be.model;

import java.time.LocalDateTime;

import lombok.Data;

@Data
public class Message {
    private long id;
    private String question;
    private String answer;
    private LocalDateTime timestamp;
    private long conversationId;
}
