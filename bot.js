const WebSocket = require('ws');
const puppeteer = require('puppeteer');

const WS_SERVER = 'ws://localhost:9000';  // Your WS server (optional)
const TOKEN_URL = 'http://localhost:5000/get-token?user_name=EngageTrackBot'; // Token endpoint with user_name param
const ROOM = 'EngageTrackRoomDemo123';
const APP_ID = 'vpaas-magic-cookie-b89487ad3af44f5480c976fcf53f7bdc';
const JAAS_DOMAIN = '8x8.vc';

let ws;
let wsReady = false;
let sendQueue = [];

function connectWS() {
  ws = new WebSocket(WS_SERVER);

  ws.on('open', () => {
    console.log('[WS] Connected to', WS_SERVER);
    wsReady = true;
    while (sendQueue.length) {
      ws.send(sendQueue.shift());
    }
  });

  ws.on('message', (msg) => {
    try {
      const obj = JSON.parse(msg.toString());
      console.log('[WS MESSAGE]', obj);
    } catch {
      // Ignore non-JSON messages
    }
  });

  ws.on('close', () => {
    console.warn('[WS] Closed. Reconnecting in 2 seconds...');
    wsReady = false;
    setTimeout(connectWS, 2000);
  });

  ws.on('error', (err) => {
    console.error('[WS] Error:', err.message || err);
    wsReady = false;
  });
}

function sendToServerJSON(obj) {
  const str = JSON.stringify(obj);
  if (wsReady && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(str);
  } else {
    sendQueue.push(str);
  }
}

connectWS();

(async () => {
  const browser = await puppeteer.launch({
    headless: false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--use-fake-ui-for-media-stream',
      '--autoplay-policy=no-user-gesture-required',
      '--ignore-certificate-errors',
      '--allow-insecure-localhost',
      '--enable-experimental-web-platform-features',
      '--enable-webrtc',
      '--use-fake-device-for-media-stream',
    ],
  });

  const page = await browser.newPage();

  page.on('console', msg => {
    console.log('[Page]', msg.text());
  });

  // Expose a simple send function to send data to WS server if needed
  await page.exposeFunction('sendToServer', (data) => {
    data._localTs = Date.now();
    sendToServerJSON(data);
  });

  const html = `
  <!doctype html>
  <html>
  <head>
    <meta charset="utf-8"/>
    <title>Simple Jitsi Bot</title>
    <style>body,html{margin:0;height:100%}#jitsi{width:100%;height:100vh}</style>
    <script src="https://${JAAS_DOMAIN}/external_api.js"></script>
  </head>
  <body>
    <div id="jitsi"></div>
    <script>
      (async () => {
        const APP_ID = "${APP_ID}";
        const ROOM = "${ROOM}";
        const TOKEN_ENDPOINT = "${TOKEN_URL}";
        const DOMAIN = "${JAAS_DOMAIN}";

        function log(msg) {
          console.log(msg);
          if(window.sendToServer) {
            window.sendToServer({ type: 'log', message: msg });
          }
        }

        async function fetchToken() {
          try {
            const res = await fetch(TOKEN_ENDPOINT);
            const json = await res.json();
            return json.token || null;
          } catch(e) {
            log('Failed to fetch JWT token: ' + e);
            return null;
          }
        }

        const token = await fetchToken();
        if (!token) {
          log('No token received, cannot join meeting.');
          return;
        }

        const options = {
          roomName: APP_ID + "/" + ROOM,
          parentNode: document.getElementById('jitsi'),
          jwt: token,
          configOverwrite: {
            startWithAudioMuted: true,
            startWithVideoMuted: true,
          },
          interfaceConfigOverwrite: {
            MOBILE_APP_PROMO: false,
          },
          userInfo: {
            displayName: 'Bot_' + Math.floor(Math.random() * 10000),
          },
        };

        const api = new JitsiMeetExternalAPI(DOMAIN, options);

        api.addEventListener('videoConferenceJoined', () => {
          log('Bot has joined the conference.');
        });

        api.addEventListener('participantJoined', (event) => {
          log('Participant joined: ' + (event.displayName || '(no name)'));
        });

        api.addEventListener('participantLeft', (event) => {
          log('Participant left: ' + (event.displayName || '(no name)'));
        });

        api.addEventListener('error', (e) => {
          log('Jitsi error: ' + JSON.stringify(e));
        });
      })();
    </script>
  </body>
  </html>
  `;

  await page.setContent(html, { waitUntil: 'load' });

  console.log('Puppeteer bot page created and running.');
})();
