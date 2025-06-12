import React, { useState, useEffect, useRef } from "react";
import { auth } from "../firebase";
import {
  Box, Paper, TextField, Button, Typography, Stack,
  IconButton, LinearProgress, Alert
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import LogoutIcon from "@mui/icons-material/Logout";
import { signOut } from "firebase/auth";
import { v4 as uuidv4 } from "uuid";
import './ChatInterface.css';
import { getAuth } from "firebase/auth";

function SignOutButton() {
  return (
    <IconButton
      onClick={() => signOut(auth)}
      sx={{ position: 'absolute', right: 16, top: 16 }}
      aria-label="Sign out"
    >
      <LogoutIcon />
    </IconButton>
  );
}

export default function ChatInterface() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setSessionId(uuidv4());
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 🔍 Log Firebase ID token to console for debugging
  useEffect(() => {
    auth.onAuthStateChanged((user) => {
      if (user) {
        user.getIdToken().then(token => {
          console.log("✅ Firebase Auth token:", token);
        });
      } else {
        console.warn("⚠️ No user is signed in");
      }
    });
  }, []);

  const delay = (ms) => new Promise((res) => setTimeout(res, ms));

const simulateTyping = async (text) => {
  for (let i = 0; i < text.length; i++) {
    const currentText = text.slice(0, i + 1);
    await delay(10);

    setMessages((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = {
        ...updated[updated.length - 1],
        text: currentText,
      };
      return updated;
    });
  }
};


  const handleSend = async (e) => {
  e.preventDefault();
  if (!message.trim() || isLoading) return;

  const userMessage = message;
  setMessages(prev => [...prev, { text: userMessage, isUser: true, timestamp: new Date() }]);
  setMessage("");
  setError("");
  setIsLoading(true);

  try {
    const auth = getAuth(); // <-- safer: reinitialize just in case
    const currentUser = auth.currentUser;

    if (!currentUser) {
      throw new Error("User is not logged in.");
    }

    const idToken = await currentUser.getIdToken();

    const response = await fetch("http://localhost:8000/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${idToken}`
      },
      body: JSON.stringify({
        message: userMessage,
        session_id: sessionId
      })
    });

    const data = await response.json();

    if (response.ok) {
      setMessages(prev => [
        ...prev,
        { text: "", isUser: false, timestamp: new Date() }
      ]);
      await simulateTyping(data.response);
    } else {
      throw new Error(data.detail || "Something went wrong.");
    }

  } catch (err) {
    setMessages(prev => [
      ...prev,
      { text: "⚠️ Your bot failed to respond. Try again.", isUser: false, timestamp: new Date() }
    ]);
    setError(err.message);
  }

  setIsLoading(false);
};


  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      handleSend(e);
    }
  };

  return (
    <Box className="chat-container">
      <Paper className="chat-paper" elevation={3}>
        <Box sx={{
          position: 'relative',
          p: 2,
          borderBottom: '1px solid rgba(0, 0, 0, 0.12)'
        }}>
          <Typography variant="h5" component="div">
            AI Booking Assistant
            {isLoading && (
              <LinearProgress
                sx={{
                  width: 100,
                  height: 4,
                  borderRadius: 5,
                  ml: 2,
                  display: 'inline-block'
                }}
              />
            )}
          </Typography>
          <SignOutButton />
        </Box>

        <Stack className="messages-container" sx={{ p: 2 }}>
          {messages.map((msg, idx) => (
            <Box
              key={idx}
              className={`message-box ${msg.isUser ? 'message-user' : 'message-bot'}`}
              sx={{
                alignSelf: msg.isUser ? 'flex-end' : 'flex-start',
                maxWidth: '80%',
                mb: 2
              }}
            >
              <Paper
                elevation={1}
                className={`message-bubble ${msg.isUser ? 'user-bubble' : 'bot-bubble'}`}
                sx={{
                  p: 2,
                  bgcolor: msg.isUser ? '#e3f2fd' : '#f5f5f5',
                  borderRadius: msg.isUser ?
                    '18px 18px 4px 18px' :
                    '18px 18px 18px 4px'
                }}
              >
                <Typography variant="body1">{msg.text}</Typography>
                <Typography
                  variant="caption"
                  display="block"
                  sx={{
                    mt: 0.5,
                    color: 'text.secondary',
                    textAlign: 'right'
                  }}
                >
                  {msg.timestamp?.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit'
                  })}
                </Typography>
              </Paper>
            </Box>
          ))}
          <div ref={messagesEndRef} />
        </Stack>

        <Box
          component="form"
          onSubmit={handleSend}
          sx={{
            p: 2,
            borderTop: '1px solid rgba(0, 0, 0, 0.12)',
            display: 'flex',
            gap: 1,
            alignItems: 'center'
          }}
        >
          <TextField
            fullWidth
            variant="outlined"
            placeholder="Type your message..."
            value={message}
            onChange={e => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            multiline
            maxRows={4}
            sx={{
              '& .MuiOutlinedInput-root': {
                borderRadius: 4,
              }
            }}
          />
          <Button
            type="submit"
            variant="contained"
            color="primary"
            disabled={!message.trim() || isLoading}
            sx={{
              minWidth: 56,
              height: 56,
              borderRadius: '50%',
              padding: 0
            }}
          >
            <SendIcon />
          </Button>
        </Box>

        {error && (
          <Alert
            severity="error"
            sx={{
              borderRadius: 0,
              '& .MuiAlert-message': { width: '100%' }
            }}
          >
            {error}
          </Alert>
        )}
      </Paper>
    </Box>
  );
}
