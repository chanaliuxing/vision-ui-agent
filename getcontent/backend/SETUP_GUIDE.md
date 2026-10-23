# Manual Testing & Configuration Guide

## 1. Backend Setup

### Install Dependencies
```bash
cd backend
npm install
```

### Environment Configuration
Copy and configure environment:
```bash
cp .env.example .env
```

Edit `.env` file:
```env
# Database
DATABASE=postgresql://username:password@localhost:5432/yolo_automation

# API Keys (set your own keys in .env)
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here

# Ed25519 Keys (auto-generated)
ED25519_PRIVATE_KEY_B64=<will be generated>
ED25519_PUBLIC_KEY_B64=<will be generated>
```

### Database Setup
```bash
# Generate Ed25519 keys first
npm run gen:seed

# Run migrations (creates tables)
# Note: Migrations run automatically on server start
```

### Start Backend Server
```bash
npm run dev
```

Server should show:
```
🚀 Backend server running on http://localhost:8787
📊 Health check: http://localhost:8787/health
🔒 Database: PostgreSQL configured
```

## 2. Extension Setup

### Load Extension in Chrome
1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right toggle)
3. Click "Load unpacked"
4. Select the `/extension` folder
5. Extension should appear with name "YOLO+LLM Automation"

### Verify Extension Installation
- Extension icon should appear in Chrome toolbar
- Click the icon to open popup
- Should show "Not authenticated" status initially

## 3. Manual Testing Steps

### Test 1: Backend Health Check
```bash
curl http://localhost:8787/health
```
Expected response:
```json
{"status":"healthy","database":"connected"}
```

### Test 2: Create Test User
```bash
cd backend
node tools/add-user.js testuser testpass
```
Expected output:
```
✅ User created/updated in PostgreSQL:
   Account ID: acct_testuser
   Username: testuser
```

### Test 3: Extension Login
1. Click extension icon in Chrome
2. Click "Login" button (dev mode bypasses auth)
3. Status should change to "Hello testuser" in green

### Test 4: Test Auto-Runner Controls
1. In popup, you should see "Auto-Runner Daemon" section
2. Status should show "Auto-runner: Stopped" in orange
3. "Start Auto-Runner" button should be enabled
4. "Stop Auto-Runner" button should be disabled

### Test 5: Start Auto-Runner
1. Click "Start Auto-Runner" button
2. Status should change to "Auto-runner: ACTIVE" in green
3. Start button becomes disabled, Stop button becomes enabled
4. Check browser console - should see daemon started logs

### Test 6: Command Queue System
```bash
# Enqueue a test command
node backend/tools/test_daemon_flow.js
```

Expected output shows complete flow:
```
🚀 Testing Daemon Automation Flow

1. Testing backend health...
✅ Backend health: { status: 'healthy', database: 'connected' }

2. Logging in with test user...
✅ Logged in: testuser

3. Creating test device...
✅ Device heartbeat: { ok: true, at: 1234567890 }

4. Enqueuing test command...
✅ Command enqueued: { ok: true, id: '1' }

5. Polling for next command...
✅ Command claimed: { id: '1', type: 'xhs_reply', ... }

6. Testing command resolver...
✅ Command resolved: TQP generated

7. Acknowledging command completion...
✅ Command acknowledged: { ok: true }
```

### Test 7: Page Information Collection
Navigate to xiaohongshu.com and run:
```bash
# Test page collection command
curl -X POST http://localhost:8787/commands/enqueue \
  -H "Content-Type: application/json" \
  -H "Cookie: sid=<your_session_cookie>" \
  -d '{
    "device_id": "test_browser_001",
    "type": "page_collect",
    "url": "https://xiaohongshu.com",
    "vars": {
      "action": "collect_page_info",
      "include_analysis": true
    }
  }'
```

## 4. Configuration Options

### Backend Configuration (`.env`)
```env
# Server Settings
PORT=8787
NODE_ENV=development

# Database
DATABASE=postgresql://user:pass@localhost:5432/db_name

# LLM Configuration
LLM_PROVIDER=gemini                    # gemini, openai, deepseek
LLM_MODEL=gemini-1.5-flash            # model name
LLM_FALLBACKS=openai:gpt-4o-mini      # fallback providers

# Security
ED25519_PRIVATE_KEY_B64=<generated>    # Signing key
ED25519_PUBLIC_KEY_B64=<generated>     # Verification key

# Features
CORS_ORIGINS=chrome-extension://*      # Allow extension
```

### Extension Configuration (`keys.json`)
```json
{
  "publicKey_b64": "<matches backend public key>",
  "version": "1.0.0"
}
```

### Daemon Polling Configuration
In `extension/sw/daemon.js`:
```javascript
let POLL_MS = 5000;  // Poll every 5 seconds
```

## 5. Troubleshooting

### Extension Not Loading
- Check `chrome://extensions/` for errors
- Verify manifest.json permissions
- Check service worker console for errors

### Backend Connection Issues
- Verify server is running on port 8787
- Check CORS settings for extension origin
- Ensure PostgreSQL database is accessible

### Authentication Problems
- Verify test user exists in database
- Check session cookies in browser
- Confirm Ed25519 keys match between backend/extension

### Daemon Not Working
- Check auto-runner status in popup
- Verify service worker is running
- Look for polling errors in console
- Confirm command queue has pending commands

## 6. Advanced Testing

### Load Testing
```bash
# Create multiple commands
for i in {1..10}; do
  curl -X POST http://localhost:8787/commands/enqueue \
    -H "Content-Type: application/json" \
    -d "{\"device_id\":\"test_$i\",\"type\":\"xhs_reply\",\"url\":\"https://xiaohongshu.com\"}"
done
```

### Monitor Command Status
```bash
# Check database directly
psql $DATABASE_URL -c "SELECT id, type, status, created_at FROM commands ORDER BY created_at DESC LIMIT 10;"
```

### Extension Console Debugging
1. Go to `chrome://extensions/`
2. Click "service worker" link under your extension
3. Monitor logs for daemon activity:
```
[DAEMON] poll loop starting
[DAEMON] claimed command: {id: 1, type: 'page_collect'}
[DAEMON] command completed successfully
```