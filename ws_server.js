// server.js
const WebSocket = require('ws');
const fs = require('fs');
const path = require('path');

// ===== CONFIG =====
const PORT = 9000; // Matches WS_SERVER in bot.js
const SAVE_AUDIO = true; // Save incoming audio chunks for debugging
const AUDIO_DIR = path.join(__dirname, 'audio_chunks');

// Create directory for chunks if needed
if (SAVE_AUDIO && !fs.existsSync(AUDIO_DIR)) {
    fs.mkdirSync(AUDIO_DIR);
}

// ===== START WS SERVER =====
const wss = new WebSocket.Server({ port: PORT }, () => {
    console.log(`✅ WebSocket server running on ws://localhost:${PORT}`);
});

wss.on('connection', (ws) => {
    console.log('🤖 Bot connected');

    ws.on('message', async (message) => {
        try {
            const msg = JSON.parse(message);
            handleMessage(msg, ws);
        } catch (err) {
            console.error('❌ Invalid message from client:', message);
        }
    });

    ws.on('close', () => {
        console.log('❌ Bot disconnected');
    });
});

// ===== MESSAGE HANDLER =====
function handleMessage(msg, ws) {
    switch (msg.type) {
        case 'participantsInfo':
            console.log('👥 Participants:', msg.data);
            break;

        case 'participantJoined':
            console.log(`➕ ${msg.data.displayName || 'Unknown'} joined`);
            break;

        case 'participantLeft':
            console.log(`➖ ${msg.data.id} left`);
            break;

        case 'displayNameChange':
            console.log(`✏️ Name change:`, msg.data);
            break;

        case 'dominantSpeakerChanged':
            console.log(`🎤 Dominant speaker changed: ${msg.speakerId || msg.data.id}`);
            break;

        case 'audioChunk':
            console.log(`🎧 Audio chunk from ${msg.speakerName || 'Unknown'} (${msg.payload.length} bytes)`);
            
            if (SAVE_AUDIO) {
                saveAudioChunk(msg);
            }

            // TODO: send to transcription function
            // transcribeAudio(msg.payload).then(text => console.log('📝 Transcript:', text));
            break;

        case 'joined':
            console.log('✅ Bot joined the meeting');
            break;

        default:
            console.log('📦 Unknown message type:', msg.type);
    }
}

// ===== SAVE AUDIO CHUNKS =====
function saveAudioChunk(msg) {
    const filename = `${Date.now()}_${msg.speakerName || 'unknown'}.webm`;
    const filepath = path.join(AUDIO_DIR, filename);
    const buffer = Buffer.from(msg.payload);
    fs.writeFileSync(filepath, buffer);
    console.log(`💾 Saved audio: ${filepath}`);
}

// ===== (Placeholder) TRANSCRIPTION =====
// async function transcribeAudio(payloadArray) {
//     const buffer = Buffer.from(payloadArray);
//     // Call Whisper API or local model here
//     return "Transcribed text...";
// }
