# YOLO+LLM Automation MVP

A secure automation engine that combines signed execution plans with Chrome extension automation. The system uses cryptographic signatures to ensure all automation scripts are authorized and tamper-proof.

## Architecture Overview

This is a **secure automation engine** with the following key components:

- **Backend**: Node.js Express server with Ed25519 signing capabilities
- **Chrome Extension**: MV3 extension with service worker architecture
- **Security**: Cryptographic signatures, device binding, domain whitelisting
- **Automation**: Supports xiaohongshu.com, indeed.com, and other whitelisted domains

## Quick Start

### 1. Backend Setup
```bash
cd backend
npm install
npm run gen:seed           # Copy output to .env ED25519_SEED_B64
cp .env.example .env       # Configure environment variables
npm run user:add admin 123456 acct_admin
npm run dev
```

### 2. Extension Setup
1. Get the backend public key (temporarily log it in `src/lib/keys.js`)
2. Put the base64 public key in `extension/keys.json`
3. Add `extension/vendor/nacl-fast-es.js` (ESM version of tweetnacl)
4. Load unpacked extension in Chrome from `extension/` directory

### 3. Test
1. Open xiaohongshu IM or Indeed job pages
2. Click extension icon → Login with `admin / 123456`
3. Click "Run Plan" → Check service worker console for results

## Project Structure

```
/
├─ README.md
├─ .gitignore
├─ /backend                 # Node/Express backend
│  ├─ package.json
│  ├─ .env.example
│  ├─ src/                  # Main backend code
│  ├─ data/                 # User data and EQP plans
│  └─ tools/                # Utility scripts
│
├─ /extension               # Chrome MV3 extension
│  ├─ manifest.json
│  ├─ keys.json             # Public key configuration
│  ├─ vendor/               # Local dependencies
│  ├─ sw/                   # Service worker modules
│  ├─ cs/                   # Content scripts
│  └─ ui/                   # Extension popup interface
│
└─ /schema                  # JSON schemas (optional)
```

## Security Features

- **Ed25519/P-256 ECDSA**: Cryptographic signing of all automation plans
- **Device Binding**: Authorization tied to unique device IDs
- **Domain Whitelist**: Extension only operates on approved domains
- **Short-term Auth**: 24-hour JWT tokens with revocation capability
- **Brute Force Protection**: Progressive lockout after failed login attempts

## Development Commands

### Backend
- `npm run dev` - Development server with auto-reload
- `npm start` - Production server
- `npm run gen:seed` - Generate Ed25519 seed
- `npm run user:add <username> <password> [account_id]` - Add user

### Extension
- Load unpacked extension from `extension/` directory in Chrome
- Test with `node backend/tools/test_extension.js` (if implemented)