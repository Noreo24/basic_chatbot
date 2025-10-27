package com.chatbot.be.model;

import java.time.LocalDateTime;
import java.util.List;

import lombok.Data;

@Data
public class Conversation {
    private long id;
    private LocalDateTime createdAt;
    private long userId;
    private List<Message> messages;
}
