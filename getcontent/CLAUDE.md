# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Backend Development
- **Start backend server**: `cd backend && npm run dev` (development with auto-reload)
- **Start production**: `cd backend && npm start`
- **Generate Ed25519 seed**: `cd backend && npm run gen:seed`

### Extension Development
- **Load extension in Chrome**: Load unpacked extension from `extension/` directory
- **Test extension with Playwright**: `node backend/tools/test_extension.js`

### Environment Setup
- Copy `.env.example` to `.env` and configure required API keys
- Database: PostgreSQL connection configured in `.env`
- API keys: REPLICATE_OMNIPARSERV2_API_KEY and other LLM provider keys

## Architecture Overview

### Core System Components
This is a **secure automation engine** that combines signed execution plans with browser extension automation. The system uses cryptographic signatures to ensure all automation scripts are authorized and tamper-proof.

**Key Architecture Principles:**
1. **Security-First**: All automation plans (EQP/SkillCard) must be cryptographically signed by backend
2. **Chrome Extension MV3**: Modern extension architecture with service workers
3. **Multi-Target Automation**: Supports xiaohongshu.com, indeed.com, and other whitelisted domains
4. **Signed Authorization**: Short-term JWT tokens with device binding and revocation capability

### Project Structure
```
/backend          - Node.js Express API server with Ed25519 signing
/extension        - Chrome MV3 extension with service worker architecture
  /sw             - Service worker modules (bootstrap, verification, execution)
  /cs             - Content scripts (DOM interaction, actions)
  /ui             - Extension popup interface
/schema           - JSON schemas for data validation
/tools            - Development utilities and test scripts
```

### Backend API (`/backend`)
- **Authentication**: `/auth/login` - User login with device binding
- **Authorization**: `/entitlement/issue` - Short-term JWT with domain whitelist
- **Plans**: `/plans/fetch` - Signed EQP (Execution Query Plan) delivery
- **Events**: `/events/ingest` - Telemetry and error reporting
- **Revocation**: `/revocations` - Real-time license revocation

### Extension Architecture (`/extension`)
- **Service Worker** (`sw/bootstrap.js`): Main orchestrator, handles auth and plan fetching
- **Verification** (`sw/verify.js`): Ed25519/P-256 ECDSA signature verification using WebCrypto
- **EQP Runner** (`sw/eqp_runner.js`): Executes signed automation plans
- **Content Scripts** (`cs/actions.js`): Safe DOM interaction and user actions
- **Database** (`sw/db.js`): IndexedDB wrapper for secure local storage

### Security Model
- **Cryptographic Signing**: All automation plans signed with Ed25519/P-256
- **Device Binding**: Authorization tied to unique device ID
- **Domain Whitelist**: Extension only operates on approved domains
- **Short-term Auth**: 24-hour JWT tokens with offline grace period
- **Revocation System**: Real-time license cancellation capability

### Data Flow
1. **Extension Initialization** → Fetch keys.json → Import public key
2. **User Login** → Backend generates device-bound JWT
3. **Plan Request** → Backend returns signed EQP/SkillCard
4. **Signature Verification** → WebCrypto validates authenticity
5. **Secure Execution** → Only verified plans are executed
6. **Telemetry** → Anonymous usage data sent to backend

### JSON Schema Validation
- `eqp.schema.json` - Execution Query Plan structure
- `observation.schema.json` - DOM observation data format  
- `skillcard.schema.json` - Reusable automation skill cards
- `result.schema.json` - Execution result format

## Important Implementation Notes

### Extension Development
- Extension follows MV3 manifest requirements
- Uses `chrome.debugger` API for advanced DOM access
- Content Security Policy restricts external resources
- All remote configuration must be cryptographically signed

### Workflow Action Compatibility Issues

**CRITICAL: ext.key vs type_text for Enter Key**

Modern frontend frameworks (React/Vue/小红书) often ignore synthetic KeyboardEvents from Chrome extensions:

```javascript
// ❌ UNRELIABLE - Modern React apps ignore synthetic events
{ "do": "ext.key", "key": "Enter" }

// ✅ RELIABLE - Real text input with special characters
{ "do": "type_text", "text": "\n", "mode": "type" }
```

**Root Cause:**
- `ext.key` → Content script KeyboardEvent simulation (ignored by React synthetic events)
- `type_text` → OS-level input or real `el.value` injection + proper event dispatch

**Best Practice for Enter/Submit:**
1. Use `ext.type_text` with special characters: `\n` (Enter), `\t` (Tab), `\b` (Backspace)
2. Avoid `ext.key` for complex frontend frameworks
3. Always test on target websites before deployment

**Why This Works:**
- Text input with `\n` satisfies "value change" + "Enter submit" logic
- Frameworks monitor `input` events, not just `keydown` events
- Real text injection bypasses synthetic event filtering

### Backend Security
- Ed25519 or P-256 ECDSA for signing (generate keys with `npm run gen:seed`)
- JWT tokens include device_id, expiration, and domain scope
- PostgreSQL for production (connection in `.env`)
- CORS enabled for extension origin

### Testing
- Use `node backend/tools/test_extension.js` for automated extension testing
- Playwright-based integration tests with Chrome extension loading
- Service worker console logs captured for debugging

### Environment Variables
- `DATABASE` - PostgreSQL connection string (required)
- `REPLICATE_OMNIPARSERV2_API_KEY` - Vision AI API key
- LLM provider keys for plan generation (Gemini preferred for vision tasks)

## Development Workflow

### Adding New Automation Targets
1. Add domain to `extension/manifest.json` host_permissions
2. Create signed EQP template in backend
3. Test with extension loaded in Chrome dev mode
4. Validate signature verification pipeline

### Backend API Changes  
1. Update route handlers in `/backend/src/routes/`
2. Ensure all responses include cryptographic signature
3. Test with `node backend/tools/test_extension.js`
4. Update JSON schemas if data structures change

### Extension Updates
1. Modify service worker or content script modules
2. Test signature verification with `tools/verify.js`
3. Validate against target websites in dev mode
4. Ensure CSP compliance and MV3 requirements