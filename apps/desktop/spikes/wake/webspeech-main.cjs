// Spike A: does webkitSpeechRecognition initialise / return results inside Electron? Hidden window, isolated profile.
// Usage: electron webspeech-main.cjs [wav]   (wav -> fed through Chromium's fake audio capture device)
const { app, BrowserWindow, session } = require('electron');
const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');

const wav = process.argv.slice(2).find((a) => a.endsWith('.wav'));
const useFake = process.env.WAKE_FAKE_MIC !== '0';
app.setPath('userData', fs.mkdtempSync(path.join(os.tmpdir(), 'wake-spike-')));
if (useFake) {
  app.commandLine.appendSwitch('use-fake-device-for-media-stream');
  app.commandLine.appendSwitch('use-fake-ui-for-media-stream');
  if (wav) app.commandLine.appendSwitch('use-file-for-fake-audio-capture', path.resolve(wav));
}
app.dock?.hide();

app.whenReady().then(async () => {
  session.defaultSession.setPermissionRequestHandler((_wc, _perm, cb) => cb(true));
  session.defaultSession.setPermissionCheckHandler(() => true);
  const win = new BrowserWindow({ show: false, width: 400, height: 300, webPreferences: { backgroundThrottling: false } });
  const log = [];
  win.webContents.on('console-message', (_e, _lvl, msg) => {
    log.push(msg);
    console.log('[page]', msg);
  });
  await win.loadFile(path.join(__dirname, 'webspeech.html'));
  setTimeout(() => {
    console.log('SUMMARY', JSON.stringify({ electron: process.versions.electron, chrome: process.versions.chrome, fake: useFake, wav: wav ?? null, events: log.length }));
    app.quit();
  }, Number(process.env.WAKE_SPIKE_MS ?? 15000));
});
