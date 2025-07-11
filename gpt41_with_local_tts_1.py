#!/usr/bin/env python3
"""
Web-based long‑context CLI using Assistants v2 Threads with Termux Text-to-Speech
--------------------------------------------------------------------------------

• Stores a single thread ID in gpt41_thread_id.txt so all calls share context on OpenAI's side (no local history upload needed).
• Keeps *your* local history in gpt41_history.json too, just to show what you already said (optional).
• Replace ASSISTANT_ID with your real one.
• Requires OPENAI_API_KEY in ~/.env  (one line: OPENAI_API_KEY=sk-...)
• Now includes a Flask web interface accessible from any browser on the local network.
• Assistant responses are spoken using Termux's ``termux-tts-speak`` command.
"""

import os, json, time
from pathlib import Path
from dotenv import load_dotenv
import openai
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
import subprocess

# ---------- config ----------
load_dotenv()                                    # pulls API key
openai.api_key = os.getenv("OPENAI_API_KEY")

ASSISTANT_ID = "asst_bUIR4a8XnzOVUj5Op7Ox6nWK"        # <‑‑‑‑ put your asst_... id hereASSISTANT_ID = "asst_bUIR4a8XnzOVUj5Op7Ox6nWK"
THREAD_FILE    = Path(__file__).with_name("gpt41_thread_id.txt")
HIST_FILE      = Path(__file__).with_name("gpt41_history.json")

# ---------- Flask setup ----------
app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# ---------- helpers ----------
def get_thread_id()->str:
    """Return existing thread id or make a new one"""
    if THREAD_FILE.exists():
        return THREAD_FILE.read_text().strip()
    tid = openai.beta.threads.create().id
    THREAD_FILE.write_text(tid)
    print("🆕  Made new thread ➜", tid)
    return tid

def load_history():
    if HIST_FILE.exists():
        return json.loads(HIST_FILE.read_text())
    return []

def save_history(msgs):
    HIST_FILE.write_text(json.dumps(msgs, ensure_ascii=False, indent=2))

def speak_termux(text: str) -> None:
    """Speak text using Termux's TTS command if available."""
    if not text.strip():
        return
    try:
        subprocess.run(["termux-tts-speak", text], check=True)
    except FileNotFoundError:
        print("termux-tts-speak not found; skipping speech")
    except Exception as exc:
        print("Termux TTS failed:", exc)

def chat_once_api(tid, msgs, user):
    """Modified chat_once that returns the response instead of printing"""
    try:
        # add user message to thread
        openai.beta.threads.messages.create(thread_id=tid, role="user", content=user)
        # start run
        run = openai.beta.threads.runs.create(thread_id=tid, assistant_id=ASSISTANT_ID)
        print("▶️  Started run:", run.id)

        # wait for completion (poll up to 60 s total)
        for _ in range(60):
            run = openai.beta.threads.runs.retrieve(thread_id=tid, run_id=run.id)
            if run.status == "completed":
                break
            elif run.status in {"failed","cancelled","expired"}:
                return {"error": f"Assistant run failed. Status: {run.status}"}
            time.sleep(1)
        else:
            return {"error": "Assistant took too long to respond."}

        # fetch last assistant message
        messages = openai.beta.threads.messages.list(thread_id=tid, order="desc", limit=1).data
        answer = "[no assistant message]"
        for m in messages:
            if m.role == "assistant":
                answer = m.content[0].text.value
                break
        
        # local history (optional)
        msgs.append({"role":"user","content":user})
        msgs.append({"role":"assistant","content":answer})
        save_history(msgs)
        
        return {"response": answer}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}

# ---------- Flask routes ----------
@app.route('/')
def index():
    """Serve the main chat interface"""
    html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
    <title>GPT-4 Assistant Chat</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            height: 100vh;
            overflow: hidden;
        }
        
        .chat-container {
            display: flex;
            flex-direction: column;
            height: 100vh;
            max-width: 800px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        
        .header {
            background: #4a5568;
            color: white;
            padding: 1rem;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 1.2rem;
            font-weight: 600;
        }
        
        .status {
            font-size: 0.8rem;
            opacity: 0.8;
            margin-top: 0.25rem;
        }
        
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            background: #f7fafc;
        }
        
        .message {
            margin-bottom: 1rem;
            display: flex;
            align-items: flex-start;
        }
        
        .message.user {
            justify-content: flex-end;
        }
        
        .message-content {
            max-width: 80%;
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }
        
        .message.user .message-content {
            align-items: flex-end;
        }
        
        .message-bubble {
            padding: 0.75rem 1rem;
            border-radius: 1rem;
            word-wrap: break-word;
            white-space: pre-wrap;
            margin-bottom: 0.25rem;
        }
        
        .message.user .message-bubble {
            background: #4299e1;
            color: white;
            border-bottom-right-radius: 0.25rem;
        }
        
        .message.assistant .message-bubble {
            background: white;
            color: #2d3748;
            border: 1px solid #e2e8f0;
            border-bottom-left-radius: 0.25rem;
        }
        
        
        .input-area {
            padding: 1rem;
            background: white;
            border-top: 1px solid #e2e8f0;
            display: flex;
            gap: 0.5rem;
        }
        
        .message-input {
            flex: 1;
            padding: 0.75rem;
            border: 1px solid #e2e8f0;
            border-radius: 1.5rem;
            font-size: 1rem;
            outline: none;
            resize: none;
            min-height: 44px;
            max-height: 120px;
        }
        
        .message-input:focus {
            border-color: #4299e1;
            box-shadow: 0 0 0 3px rgba(66, 153, 225, 0.1);
        }
        
        .send-button {
            background: #4299e1;
            color: white;
            border: none;
            border-radius: 50%;
            width: 44px;
            height: 44px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2rem;
            transition: background-color 0.2s;
        }
        
        .send-button:hover:not(:disabled) {
            background: #3182ce;
        }
        
        .send-button:disabled {
            background: #a0aec0;
            cursor: not-allowed;
        }
        
        .loading {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #718096;
            font-style: italic;
        }
        
        .loading-dots {
            display: inline-block;
        }
        
        .loading-dots::after {
            content: '';
            animation: dots 1.5s infinite;
        }
        
        @keyframes dots {
            0%, 20% { content: ''; }
            40% { content: '.'; }
            60% { content: '..'; }
            80%, 100% { content: '...'; }
        }
        
        .error {
            background: #fed7d7;
            color: #c53030;
            padding: 0.75rem;
            border-radius: 0.5rem;
            margin: 0.5rem;
            border: 1px solid #feb2b2;
        }
        
        .tts-notice {
            background: #e6fffa;
            color: #234e52;
            padding: 0.5rem;
            text-align: center;
            font-size: 0.8rem;
            border-bottom: 1px solid #81e6d9;
        }
        
        @media (max-width: 768px) {
            .chat-container {
                height: 100vh;
                border-radius: 0;
            }
            
            .message-content {
                max-width: 90%;
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="header">
            <h1>🤖 GPT-4 Assistant</h1>
            <div class="status" id="status">Ready to chat</div>
        </div>
        
        <div class="tts-notice">
            🔊 Termux TTS enabled - responses will be spoken automatically
        </div>
        
        <div class="messages" id="messages">
            <div class="message assistant">
                <div class="message-content">
                    <div class="message-bubble">
                        Hello! I'm your GPT-4 Assistant. How can I help you today?
                    </div>
                    <!-- Termux TTS handled server side -->
                </div>
            </div>
        </div>
        
        <div class="input-area">
            <textarea 
                class="message-input" 
                id="messageInput" 
                placeholder="Type your message here..."
                rows="1"
            ></textarea>
            <button class="send-button" id="sendButton" onclick="sendMessage()">
                ➤
            </button>
        </div>
    </div>

    <script>
        const messagesContainer = document.getElementById('messages');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const status = document.getElementById('status');
        
        // Auto-resize textarea
        messageInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = Math.min(this.scrollHeight, 120) + 'px';
        });
        
        // Send message on Enter (but allow Shift+Enter for new lines)
        messageInput.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        function addMessage(content, isUser = false) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user' : 'assistant'}`;
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            const bubbleDiv = document.createElement('div');
            bubbleDiv.className = 'message-bubble';
            bubbleDiv.textContent = content;
            
            contentDiv.appendChild(bubbleDiv);
            
            // Termux TTS is handled server side; no per-message button needed
            
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
            
            // Scroll to bottom
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        function addLoadingMessage() {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message assistant';
            messageDiv.id = 'loading-message';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            const bubbleDiv = document.createElement('div');
            bubbleDiv.className = 'message-bubble loading';
            bubbleDiv.innerHTML = 'Assistant is thinking<span class="loading-dots"></span>';
            
            contentDiv.appendChild(bubbleDiv);
            messageDiv.appendChild(contentDiv);
            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        function removeLoadingMessage() {
            const loadingMessage = document.getElementById('loading-message');
            if (loadingMessage) {
                loadingMessage.remove();
            }
        }
        
        function showError(message) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error';
            errorDiv.textContent = `Error: ${message}`;
            messagesContainer.appendChild(errorDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        
        async function sendMessage() {
            const message = messageInput.value.trim();
            if (!message) return;
            
            // Add user message
            addMessage(message, true);
            
            // Clear input
            messageInput.value = '';
            messageInput.style.height = 'auto';
            
            // Disable send button and show loading
            sendButton.disabled = true;
            status.textContent = 'Sending message...';
            addLoadingMessage();
            
            try {
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ message: message })
                });
                
                const data = await response.json();
                removeLoadingMessage();
                
                if (data.error) {
                    showError(data.error);
                } else {
                    addMessage(data.response);
                }
                
            } catch (error) {
                removeLoadingMessage();
                showError('Failed to send message. Please check your connection.');
                console.error('Error:', error);
            } finally {
                sendButton.disabled = false;
                status.textContent = 'Ready to chat';
                messageInput.focus();
            }
        }
        
        // Load chat history on page load
        async function loadHistory() {
            try {
                const response = await fetch('/history');
                const history = await response.json();
                
                // Clear existing messages except welcome message
                const welcomeMessage = messagesContainer.querySelector('.message');
                messagesContainer.innerHTML = '';
                messagesContainer.appendChild(welcomeMessage);
                
                // Add history messages
                history.forEach(msg => {
                    addMessage(msg.content, msg.role === 'user');
                });
                
            } catch (error) {
                console.error('Failed to load history:', error);
            }
        }
    </script>
</body>
</html>
    """
    return render_template_string(html_template)

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({"error": "No message provided"}), 400
    
    user_message = data['message'].strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    
    tid = get_thread_id()
    msgs = load_history()

    result = chat_once_api(tid, msgs, user_message)
    if "response" in result:
        speak_termux(result["response"])
    return jsonify(result)

@app.route('/history')
def history():
    """Get chat history"""
    msgs = load_history()
    return jsonify(msgs)

# ---------- main ----------
def main():
    print("🌐 Starting GPT-4 Assistant Web Interface with Termux TTS...")
    print("📱 Access from your Android browser at: http://[YOUR_IP]:5000")
    print("🏠 Or locally at: http://localhost:5000")
    print("🔊 Termux TTS feature enabled - responses will be spoken automatically")
    print("🛑 Press Ctrl+C to stop the server")
    
    # Get thread ID to initialize
    tid = get_thread_id()
    print(f"📝 Using thread: {tid}")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == "__main__":
    main()

