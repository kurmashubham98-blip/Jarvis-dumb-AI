/**
 * Jarvis v2.0 — HUD JavaScript Logic
 * Communicates with the Python backend via pywebview API.
 */

// Format time as HH:MM:SS
function getTimeString() {
    const now = new Date();
    return now.toTimeString().split(' ')[0];
}

// Add a message to the dialogue box
function addMessage(text, role) {
    const box = document.getElementById('dialogue-box');
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    
    // Prefix for Jarvis/User
    let prefix = "";
    if (role === 'jarvis') prefix = "J.A.R.V.I.S: ";
    if (role === 'user') prefix = "SIR: ";
    
    // Timestamp
    const timeSpan = document.createElement('span');
    timeSpan.className = 'timestamp';
    timeSpan.innerText = `[${getTimeString()}]`;
    
    // Content (We use simple text to avoid XSS from raw LLM output, though we are local)
    const contentSpan = document.createElement('span');
    contentSpan.className = 'content';
    
    // If it's a Jarvis message, type it out character by character for effect
    if (role === 'jarvis') {
        msgDiv.appendChild(timeSpan);
        msgDiv.appendChild(contentSpan);
        box.appendChild(msgDiv);
        
        let i = 0;
        // Strip markdown bolding for UI presentation (simple replace)
        const displayTxt = text.replace(/\*\*/g, '');
        
        function typeWriter() {
            if (i < displayTxt.length) {
                contentSpan.textContent += displayTxt.charAt(i);
                i++;
                // Auto scroll
                box.scrollTop = box.scrollHeight;
                setTimeout(typeWriter, 15); // typing speed
            }
        }
        typeWriter();
    } else {
        // User text appears instantly
        contentSpan.innerText = text;
        msgDiv.appendChild(timeSpan);
        msgDiv.appendChild(contentSpan);
        box.appendChild(msgDiv);
        box.scrollTop = box.scrollHeight;
    }
}

// Update the glowing status bar
function updateStatus(text) {
    const el = document.getElementById('system-status');
    el.innerText = text;
    
    // Pulse animation
    el.style.textShadow = '0 0 15px #00d4ff';
    setTimeout(() => {
        el.style.textShadow = '0 0 5px #00ff88';
    }, 500);
}

// Handle text input submission
document.getElementById('user-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        const text = this.value.trim();
        if (text) {
            // Instantly show user message locally
            addMessage(text, 'user');
            
            // Send to python backend if pywebview is ready
            if (window.pywebview && window.pywebview.api) {
                window.pywebview.api.js_submit_input(text);
                updateStatus("PROCESSING...");
            } else {
                addMessage("Warning: Backend API not connected. Running in demo mode.", 'system');
            }
            
            this.value = '';
        }
    }
});

// Focus input on any key press
document.addEventListener('keydown', (e) => {
    // If we're not dragging the window and not already focused
    if(document.activeElement !== document.getElementById('user-input')) {
        document.getElementById('user-input').focus();
    }
});

// Init sequence
window.addEventListener('pywebviewready', function() {
    updateStatus("API LINK ESTABLISHED");
    document.getElementById('user-input').focus();
});
