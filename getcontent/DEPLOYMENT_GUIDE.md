# 🚀 DOM→Vision Fallback System - Deployment & Testing Guide

## 📋 Quick Start Checklist

### 1. 🗃️ Database Setup
```bash
# Navigate to backend directory
cd getcontent/backend

# Run database migration (requires PostgreSQL running)
node migrate.js
```

**Expected Output:**
```
✅ Database connection successful
📄 Loaded migration: 001_workflow_tables.sql
🚀 Executing migration...
✅ Migration completed successfully!

📋 Created tables:
  ✓ workflow_runs
  ✓ run_steps  
  ✓ artifacts
```

### 2. 🔧 Start Required Services

**Terminal 1 - Vision API:**
```bash
cd .
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 - Orchestrator:**
```bash
cd getcontent/backend
node orchestrator.js
```

**Terminal 3 - Main Backend (optional for full system):**
```bash
cd getcontent/backend  
npm run dev
```

### 3. 🌐 Chrome Extension Setup
1. Open Chrome → `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select `./getcontent/extension/` folder
5. Verify extension loads without errors in console

### 4. 🧪 Run End-to-End Test
```bash
cd getcontent
node test_e2e.js
```

---

## 🎯 Expected Test Flow

### Pre-Test Verification
✅ **Orchestrator Health**: `http://127.0.0.1:8788/health`  
✅ **Vision API Health**: `http://127.0.0.1:8000/health`  
✅ **Chrome Extension**: Visible in extension bar, no console errors

### Workflow Execution Steps
1. **Navigate to XHS**: Opens `https://xiaohongshu.com/explore` 
2. **Wait for Search**: Finds search input (DOM or Vision fallback)
3. **Type Search Term**: Enters "海边穿搭" and submits
4. **Wait for Results**: Ensures ≥8 search results loaded
5. **Open 3rd Post**: Clicks the 3rd search result (DOM or Vision)
6. **Wait for Comments**: Finds comment section
7. **Scrape Comments**: Scrolls and extracts comment text (up to 30 scrolls)
8. **Save Artifact**: Saves to `xhs/海边穿搭_第3帖_评论.txt`

### Success Indicators
- ✅ **Workflow Status**: `completed` 
- ✅ **All Steps**: `success` status
- ✅ **Artifact Created**: Text file with substantial content (>50 chars)
- ✅ **Vision Fallback**: Used when DOM selectors fail

---

## 🔧 Troubleshooting

### Database Issues
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL if needed  
brew services start postgresql

# Verify connection
psql $DATABASE_URL -c "SELECT version();"
```

### Service Health Checks
```bash
# Test Orchestrator
curl http://127.0.0.1:8788/health

# Test Vision API  
curl http://127.0.0.1:8000/health

# Test with image
curl -F "image=@sample.png" "http://127.0.0.1:8000/detect?labels=button,textbox"
```

### Extension Debug
1. Open extension popup → Check for authentication
2. Chrome DevTools → Extension service worker console
3. Look for `[TQP]`, `[VISION]`, `[CS]` log messages

### Common Failures

**❌ "No active tab"**
- Solution: Ensure Chrome tab is active with target site loaded

**❌ "Element not found"**  
- Check: DOM selectors may have changed on target site
- Expected: Vision fallback should trigger automatically

**❌ "Vision API failed"**
- Check: YOLO model loaded (`uvicorn` logs should show model loading)
- Check: Screenshot capture permissions in Chrome

**❌ "SAVE_TEXT failed"**
- Check: Orchestrator running on port 8788
- Check: run_id properly passed through workflow

---

## 📊 Performance Metrics

### Expected Timing
- **Workflow Start**: ~1s
- **Navigation**: ~3-5s  
- **Search + Results**: ~5-10s
- **Comment Scraping**: ~30-60s (depends on scroll count)
- **Total Duration**: ~60-120s

### Vision Fallback Scenarios
- **Search Box**: When XHS changes input selectors
- **Search Results**: When card selectors differ
- **Post Navigation**: When URL patterns change

### Artifact Quality
- **Minimum Comments**: >5 for pass
- **Typical Comments**: 20-50 comments
- **File Size**: 2KB-20KB typical range

---

## 🎛️ Configuration Tuning

### Workflow Timeouts
```json
// In xhs_search_comments.json
"verify": {
  "timeout_ms": 8000,  // Increase for slower connections
  "rules": ["dom_count>=8"]  // Adjust minimum result count
}
```

### Comment Scraping
```json
"args": {
  "max_scrolls": 30,        // Increase for more comments
  "scroll_pause_ms": 800,   // Increase for slower loading
  "comment_selectors": [...]  // Add more selector patterns
}
```

### Vision API Labels
```javascript
// In vision.js - inferLabelsFromStep()
const labels = ['search_box', 'textbox', 'input'];  // Customize for site
```

---

## 🚀 Next Steps - Phase 2

After successful Phase 1 testing:

### WebSocket Integration
- Replace `/commands` polling with real-time WebSocket
- Reduce latency and database load

### Selector Self-Healing
- LLM-powered selector regeneration when DOM fails
- Context-aware CSS selector suggestions

### Site Adaptation Library  
- Indeed job application automation
- LinkedIn profile scraping
- Modular site-specific adapters

### Performance Optimization
- Page signature caching for selector reuse
- Smart retry strategies with exponential backoff
- Bulk artifact storage for large datasets

---

## 📝 Test Results Format

```
🧪 Running test: xhs_search_comments
📝 XHS search and comment scraping with DOM→Vision fallback
============================================================
🚀 Starting workflow: xhs_search_and_comments
✅ Workflow started: abc-123-def (8 steps)
⏱️  Polling workflow status (timeout: 180s)...
📊 Status: running | Steps: 3✅ 0❌ 5⏳ | Artifacts: 0
📊 Status: running | Steps: 6✅ 0❌ 2⏳ | Artifacts: 0  
📊 Status: completed | Steps: 8✅ 0❌ 0⏳ | Artifacts: 1
🎉 Workflow completed successfully!
📋 Validating artifacts...
📄 xhs/海边穿搭_第3帖_评论.txt: 15420 characters
✅ xhs/海边穿搭_第3帖_评论.txt contains substantial content
   Preview: "这套搭配真的很好看！海边风格很适合夏天..."
🎉 Test xhs_search_comments PASSED

============================================================
📊 TEST SUMMARY  
============================================================
Total tests: 1
✅ Passed: 1
❌ Failed: 0
💥 Errors: 0
  ✅ xhs_search_comments (1 artifacts)

🏁 Tests completed!
🎉 All tests passed! The DOM→Vision fallback system is working correctly.
```

---

**🎯 Goal**: Complete DOM→Vision integration with artifacts proving XHS comment extraction works end-to-end.