// Capture the rendered DOM of a Cloudflare-protected page using a real,
// headed Chrome profile. Headless is reliably challenged; headed usually is not.
//
// Setup (Playwright is not vendored; Chrome must be installed):
//   npm init -y && PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 npm i playwright
//
// Usage:
//   node capture.js <url> <output.html>
//
// A Chrome window opens for a few seconds. That is deliberate — headless mode
// gets challenged by Cloudflare and returns 403.
const { chromium } = require('playwright');
const fs = require('fs');

const URL = process.argv[2];
const OUT = process.argv[3];

(async () => {
  const ctx = await chromium.launchPersistentContext('/tmp/pwcap/profile', {
    channel: 'chrome',
    headless: false,
    viewport: { width: 1440, height: 900 },
    locale: 'en-US',
    timezoneId: 'America/New_York',
  });

  const page = ctx.pages()[0] || (await ctx.newPage());
  const resp = await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('status:', resp && resp.status());

  // Give Cloudflare's interstitial time to clear, then let the page settle.
  for (let i = 0; i < 20; i++) {
    const t = await page.title();
    if (!/just a moment|attention required|checking/i.test(t)) break;
    await page.waitForTimeout(1000);
  }
  await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});

  const title = await page.title();
  const html = await page.content();
  fs.writeFileSync(OUT, html);
  console.log('title:', title);
  console.log('bytes:', html.length);
  await ctx.close();
})();
