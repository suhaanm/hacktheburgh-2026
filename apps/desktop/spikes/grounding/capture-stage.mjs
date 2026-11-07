// Captures STAGE (apps/demo-stage) fixtures with auto ground truth, for the fast-vs-accurate grounder comparison.
// Serve first: python3 -m http.server 5180 --directory apps/demo-stage   then: node capture-stage.mjs
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, 'shots/stage');
fs.mkdirSync(outDir, { recursive: true });
const BASE = process.env.STAGE_URL ?? 'http://127.0.0.1:5180/index.html?still=1';

// { gid, desc } = UI target; { phrase, in: gid, desc? } = verbatim text inside an element; { negative, desc } = not on screen.
const FIXTURES = {
  'video/contacts': [
    { gid: 'video.toolbar.new_meeting', desc: 'the New meeting button at the top of the VideoChat window' },
    { gid: 'video.toolbar.join', desc: 'the Join button next to New meeting' },
    { gid: 'video.search', desc: 'the Search contacts box' },
    { gid: 'video.contact.lily', desc: 'Lily in the contacts list' },
    { gid: 'video.win.close', desc: 'the small Close window button at the top right of the VideoChat window' },
    { gid: 'desk.icon.settings', desc: 'the Settings icon on the left side of the desktop' },
    { negative: true, desc: 'the green Start call button' },
    { negative: true, desc: 'the red Leave button' },
  ],
  'video/lily': [
    { gid: 'video.start_call', desc: 'the Start call button' },
    { gid: 'video.detail.voice_only', desc: 'the Voice call only button' },
    { gid: 'video.detail.message', desc: 'the Message button' },
    { gid: 'video.rail.calls', desc: 'Calls in the narrow left-hand strip' },
    { negative: true, desc: 'the Mute button' },
  ],
  'video/precall': [
    { gid: 'video.precall.join', desc: 'the Join button to enter the call' },
    { gid: 'video.precall.cancel', desc: 'the Cancel button' },
    { gid: 'video.precall.camera', desc: 'the Camera control under the preview' },
    { gid: 'video.precall.mic', desc: 'the Microphone control under the preview' },
    { negative: true, desc: 'the Share screen button' },
  ],
  'video/calling': [
    { gid: 'video.call.mic', desc: 'the Mute microphone button at the bottom of the call' },
    { gid: 'video.call.hangup', desc: 'the red Leave button' },
    { gid: 'video.call.share', desc: 'the Share button' },
    { negative: true, desc: 'the Call Lily again button' },
  ],
  'video/call-screen': [
    { gid: 'video.call.camera', desc: 'the Stop video button' },
    { gid: 'video.call.chat', desc: 'the Chat button in the call controls' },
    { gid: 'video.call.more', desc: 'the More button in the call controls' },
    { gid: 'video.call.self_video', desc: 'the small picture of yourself in the corner' },
    { gid: 'video.call.timer', desc: 'the call timer at the top right' },
    { negative: true, desc: 'the Send button' },
  ],
  'video/ended': [
    { gid: 'video.ended.again', desc: 'the Call Lily again button' },
    { gid: 'video.ended.back', desc: 'the Back to contacts button' },
    { negative: true, desc: 'the Mute button' },
  ],
  'video/settings': [
    { gid: 'video.settings.back', desc: 'the Back button' },
    { gid: 'video.settings.blur', desc: 'the Blur my background switch' },
    { gid: 'video.settings.sign_out', desc: 'the Sign out button' },
  ],
  'messages/scam': [
    { gid: 'messages.link.scam', desc: 'the web link inside the message from Aldermoor Bank' },
    { gid: 'messages.compose.send', desc: 'the Send button' },
    { gid: 'messages.thread.menu', desc: 'the More options button at the top right of the conversation' },
    { gid: 'messages.new', desc: 'the New message button' },
    { phrase: 'URGENT: Aldermoor Bank.', in: 'messages.msg.scam.0' },
    { phrase: 'Your account has been LOCKED', in: 'messages.msg.scam.0' },
    { phrase: 'Verify your identity within 2 hours', in: 'messages.msg.scam.0' },
    { phrase: 'your money will be frozen', in: 'messages.msg.scam.0' },
    { negative: true, desc: 'the Report spam button' },
  ],
  'messages/scam-parcel': [
    { phrase: 'Pay a £1.45 re-delivery fee', in: 'messages.msg.scam_parcel.0' },
    { phrase: 'within 24 hours', in: 'messages.msg.scam_parcel.0' },
    { phrase: 'https://parcel-redelivery-uk.top/pay', in: 'messages.msg.scam_parcel.0' },
    { phrase: 'or it will be returned', in: 'messages.msg.scam_parcel.0' },
  ],
  'messages/scam-family': [
    { phrase: 'Hi Mum', in: 'messages.msg.scam_family.0' },
    { phrase: 'This is my new number', in: 'messages.msg.scam_family.0' },
    { phrase: 'please delete the old one', in: 'messages.msg.scam_family.0' },
    { phrase: 'send £480 to this account right now', in: 'messages.msg.scam_family.0' },
    { phrase: 'It is urgent', in: 'messages.msg.scam_family.0' },
  ],
  'messages/genuine/0': [
    { phrase: 'Dr Okafor', in: 'messages.msg.surgery.0' },
    { phrase: 'call the surgery on the number on your appointment card', in: 'messages.msg.surgery.0' },
    { gid: 'messages.search', desc: 'the Search messages box' },
  ],
  'messages/genuine/3': [
    { phrase: 'Greenfield Pharmacy', in: 'messages.msg.pharmacy.0' },
    { gid: 'messages.conv.lily', desc: 'the conversation with Lily in the list' },
  ],
  'settings/display': [
    { gid: 'settings.text_size_slider', desc: 'the Text size slider' },
    { gid: 'settings.text_larger', desc: 'the A Larger button next to the slider' },
    { gid: 'settings.text_smaller', desc: 'the A Smaller button next to the slider' },
    { gid: 'settings.nav.display', desc: 'Display in the left-hand settings list' },
    { gid: 'settings.nav.advanced', desc: 'Advanced in the left-hand settings list' },
    { gid: 'settings.display.dark_theme', desc: 'the Dark theme switch' },
    { gid: 'settings.display.high_contrast', desc: 'the High contrast switch' },
    { negative: true, desc: 'the Volume slider' },
    { negative: true, desc: 'the Wi-Fi switch' },
  ],
  'settings/display/size/0': [
    { gid: 'settings.text_size_slider', desc: 'the Text size slider' },
    { gid: 'settings.text_larger', desc: 'the A Larger button next to the slider' },
  ],
  'settings/display/size/2': [
    { gid: 'settings.text_size_slider', desc: 'the Text size slider' },
    { gid: 'settings.text_larger', desc: 'the A Larger button next to the slider' },
  ],
  'settings/display/size/4': [
    { gid: 'settings.text_size_slider', desc: 'the Text size slider' },
    { gid: 'settings.nav.privacy', desc: 'Privacy in the left-hand settings list' },
  ],
  'settings/advanced': [
    { gid: 'settings.advanced.clear_cache', desc: 'the Clear cache button' },
    { gid: 'settings.advanced.reset_all', desc: 'the Reset all settings button' },
    { gid: 'settings.advanced.developer_mode', desc: 'the Developer mode switch' },
    { negative: true, desc: 'the Text size slider' },
  ],
};

const SIZES = [{ w: 1440, h: 900 }];
const EXTRA_1920 = new Set(['video/call-screen', 'messages/scam', 'settings/display']);
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const manifest = [];

for (const fx of Object.keys(FIXTURES)) {
  const sizes = EXTRA_1920.has(fx) ? [...SIZES, { w: 1920, h: 1080 }] : SIZES;
  for (const size of sizes) {
    const ctx = await browser.newContext({ viewport: { width: size.w, height: size.h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    await page.goto(`${BASE}#${fx}`);
    await page.reload();
    await page.waitForTimeout(700);
    const shotId = `stage-${fx.replace(/\//g, '_')}@${size.w}x${size.h}`;
    const png = path.join(outDir, shotId + '.png');
    await page.screenshot({ path: png, type: 'png' });
    // JPEG at q80, native width: what Capture's 'ground' shot would look like.
    execFileSync('sips', ['-s', 'format', 'jpeg', '-s', 'formatOptions', '80', png, '--out', path.join(outDir, shotId + '.jpg')], { stdio: 'ignore' });
    const rects = await page.evaluate(() => window.__stage.rects());
    const targets = [];
    for (const t of FIXTURES[fx]) {
      if (t.negative) { targets.push({ desc: t.desc, negative: true, gt: null, kind: 'negative' }); continue; }
      if (t.phrase) {
        const gt = await page.evaluate(({ gid, phrase }) => {
          const el = document.querySelector(`[data-ground-id="${gid}"]`);
          if (!el) return null;
          const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
          const nodes = []; let full = '';
          for (let n = walker.nextNode(); n; n = walker.nextNode()) { nodes.push({ n, start: full.length }); full += n.nodeValue; }
          const i = full.indexOf(phrase);
          if (i < 0) return null;
          const locate = (pos) => { for (let k = nodes.length - 1; k >= 0; k--) if (nodes[k].start <= pos) return { node: nodes[k].n, off: pos - nodes[k].start }; return null; };
          const a = locate(i), b = locate(i + phrase.length - 1);
          const range = document.createRange();
          range.setStart(a.node, a.off); range.setEnd(b.node, b.off + 1);
          const rs = [...range.getClientRects()].filter((r) => r.width > 1 && r.height > 1);
          if (!rs.length) return null;
          const W = innerWidth, H = innerHeight;
          const u = { xmin: Math.min(...rs.map((r) => r.left)), ymin: Math.min(...rs.map((r) => r.top)), xmax: Math.max(...rs.map((r) => r.right)), ymax: Math.max(...rs.map((r) => r.bottom)) };
          return { xmin: u.xmin / W * 1000, ymin: u.ymin / H * 1000, xmax: u.xmax / W * 1000, ymax: u.ymax / H * 1000, lines: rs.length };
        }, { gid: t.in, phrase: t.phrase });
        if (!gt) { console.warn('phrase GT missing', fx, t.phrase); continue; }
        targets.push({ desc: t.phrase, negative: false, gt, kind: 'phrase', phrase: true });
        continue;
      }
      const gt = rects[t.gid];
      if (!gt) { console.warn('gid not on screen', fx, t.gid); continue; }
      targets.push({ desc: t.desc, negative: false, gt, kind: 'ui', gid: t.gid });
    }
    manifest.push({ shotId, jpg: path.join(outDir, shotId + '.jpg'), png, w: size.w, h: size.h, fixture: fx, targets });
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(here, 'shots/manifest-stage.json'), JSON.stringify(manifest, null, 2));
const all = manifest.flatMap((m) => m.targets);
console.log(`shots=${manifest.length} targets=${all.length} ui=${all.filter((t) => t.kind === 'ui').length} phrase=${all.filter((t) => t.kind === 'phrase').length} negative=${all.filter((t) => t.negative).length}`);
