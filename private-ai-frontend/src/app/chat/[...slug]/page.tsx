"use client";

import { useParams, useRouter } from 'next/navigation';
import React, { useEffect, useRef, useState, ChangeEvent } from 'react';
import ReactMarkdown from "react-markdown";

type Message = {
  type: "chat" | "system";
  username: string;
  message: string;
  ts: number; // Unix timestamp in seconds
};

export default function ChatRoomPage() {
  const params = useParams();
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [currentMessage, setCurrentMessage] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [username, setUsername] = useState("");
  // State for RAG controls
  const [limit, setLimit] = useState(5);
  const [scoreThreshold, setScoreThreshold] = useState(0.3);

  const websocket = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const projectId = Array.isArray(params.slug) ? params.slug[0] : "demo";
  const roomId = Array.isArray(params.slug) ? params.slug[1] : "general";

  // Scroll to the bottom of the messages list
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages]);

  useEffect(() => {
    // Check for auth token and username
    const token = localStorage.getItem("access_token");
    const user = localStorage.getItem("chat_username");

    if (!token || !user) {
      // If no token/user, redirect to login page
      router.push("/login");
      return;
    }
    setUsername(user);

    const wsHostname = window.location.hostname;
    const wsUrl = `ws://${wsHostname}:8081/ws/${projectId}/${roomId}/${user}?token=${token}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log("WebSocket connected");
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const messageData = JSON.parse(event.data);
        setMessages((prevMessages) => [...prevMessages, messageData]);
      } catch (error) {
        console.error("Failed to parse message data:", error);
      }
    };

    ws.onclose = () => {
      console.log("WebSocket disconnected");
      setIsConnected(false);
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    websocket.current = ws;

    // Cleanup on component unmount
    return () => {
      ws.close();
    };
  }, [projectId, roomId, router]);

  const sendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      currentMessage.trim() &&
      websocket.current?.readyState === WebSocket.OPEN
    ) {
      const payload = { message: currentMessage, rag_controls: { limit, score_threshold: scoreThreshold } };
      websocket.current.send(JSON.stringify(payload));
      setCurrentMessage("");
    }
  };

  return (
    <div className="flex flex-col h-screen max-w-4xl mx-auto p-4">
      <div className="border-b pb-2 mb-4">
        <h1 className="text-2xl font-bold">
          Chat Room: {projectId} / {roomId}
        </h1>
        <p className="text-sm text-gray-500">
          Your username: {username} | Status:{" "}
          <span className={isConnected ? "text-green-500" : "text-red-500"}>
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </p>
      </div>

      <div className="flex-1 overflow-y-auto mb-4 p-4 bg-gray-50 rounded-lg">
        {messages.map((msg, index) => (
          <div
            key={index}
            className={`flex mb-3 ${
              msg.username === username ? "justify-end" : "justify-start"
            }`}
          >
            {msg.type === "system" ? (
              <p className="w-full text-center text-xs text-gray-500 italic">
                {msg.username} {msg.message}
              </p>
            ) : (
              <div
                className={`max-w-lg lg:max-w-xl px-4 py-2 rounded-lg ${
                  msg.username === username
                    ? "bg-blue-500 text-white"
                    : "bg-gray-200 text-gray-800"
                }`}
              >
                <div className="flex justify-between items-center mb-1">
                  <p className="text-xs font-bold">
                    {msg.username}
                  </p>
                  <p className="text-xs opacity-70">
                    {new Date(msg.ts * 1000).toLocaleString('th-TH', {
                      day: '2-digit',
                      month: '2-digit',
                      year: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
                <div className="prose prose-sm max-w-none text-inherit">
                  <ReactMarkdown>{msg.message}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* RAG Controls Section */}
      <div className="p-4 border-t bg-gray-100 dark:bg-gray-800 dark:border-gray-700">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <label
              htmlFor="limit"
              className="block font-medium text-gray-700 dark:text-gray-300"
            >
              Limit: {limit}
            </label>
            <input
              type="range"
              id="limit"
              name="limit"
              min="1"
              max="20"
              value={limit}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setLimit(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
            />
          </div>
          <div>
            <label htmlFor="score" className="block font-medium text-gray-700 dark:text-gray-300">
              Score: {scoreThreshold.toFixed(2)}
            </label>
            <input
              type="range" id="score" name="score" min="0" max="1" step="0.05" value={scoreThreshold}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setScoreThreshold(Number(e.target.value))}
              className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700"
            />
          </div>
        </div>
      </div>

      <form onSubmit={sendMessage} className="flex items-center gap-3">
        <input
          type="text"
          value={currentMessage}
          onChange={(e) => setCurrentMessage(e.target.value)}
          className="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Type your message..."
          disabled={!isConnected}
        />
        <button
          type="submit"
          className="px-6 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:bg-gray-400"
          disabled={!isConnected}
        >
          Send
        </button>
      </form>
    </div>
  );
}
