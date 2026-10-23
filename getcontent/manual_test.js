#!/usr/bin/env node
import { chromium } from 'playwright';
import path from 'path';
import { fileURLToPath } from 'url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const EXTENSION_PATH = path.join(SCRIPT_DIR, 'extension');

console.log('Opening Chrome with extension for manual testing...');
console.log('Extension path:', EXTENSION_PATH);
console.log('1. Open Chrome Developer Tools');
console.log('2. Go to Extensions page (chrome://extensions)');
console.log('3. Click "Service worker" link under the extension');
console.log('4. Check console for any errors');

const browserContext = await chromium.launchPersistentContext('', {
  headless: false,
  devtools: true,
  args: [
    `--disable-extensions-except=${EXTENSION_PATH}`,
    `--load-extension=${EXTENSION_PATH}`,
  ],
});

const page = await browserContext.newPage();
await page.goto('chrome://extensions');

console.log('Chrome opened. Manual testing enabled.');
console.log('Press Ctrl+C to close when done.');

// Keep the browser open
process.on('SIGINT', async () => {
  console.log('\nClosing browser...');
  await browserContext.close();
  process.exit(0);
});