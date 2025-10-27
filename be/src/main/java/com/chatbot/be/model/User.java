package com.chatbot.be.model;

import java.util.List;

import lombok.Data;

@Data
public class User {
    private long id;
    private String fullName;
    private String phone;
    private String password;
    private List<Conversation> conversations;
}
