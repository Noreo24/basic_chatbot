package com.chatbot.be.mapper;

import org.apache.ibatis.annotations.Mapper;

import com.chatbot.be.model.Message;

@Mapper
public interface MessageMapper {
    void insertMessage(Message message);
}
