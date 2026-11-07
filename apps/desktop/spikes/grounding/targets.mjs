// Benchmark definition. `gid` = data-ground-id (synthetic/STAGE) or key into `selectors` (real sites).
// negative:true => the element is NOT on screen, the correct answer is found:false.

export const SYNTH_SCREENS = {
  'video-call': [
    { gid: 'start-call', desc: 'the green Start call button' },
    { gid: 'leave-call', desc: 'the red Leave button' },
    { gid: 'mute-mic', desc: 'the round microphone icon button for muting yourself' },
    { gid: 'share-screen', desc: 'the round share screen icon button' },
    { gid: 'schedule-call', desc: 'the Schedule a call button' },
    { negative: true, desc: 'the Send message button' },
    { negative: true, desc: 'the Join with meeting code box' },
  ],
  messages: [
    { gid: 'send-button', desc: 'the blue Send button' },
    { gid: 'message-box', desc: 'the box where you type a message' },
    { gid: 'scam-link', desc: 'the web link inside the parcel message' },
    { gid: 'scam-bubble', desc: 'the yellow message bubble about a held parcel' },
    { gid: 'search-field', desc: 'the Search box at the top of the conversation list' },
    { negative: true, desc: 'the Delete conversation button' },
  ],
  settings: [
    { gid: 'text-size-slider', desc: 'the Text size slider' },
    { gid: 'dark-mode-toggle', desc: 'the Dark mode switch' },
    { gid: 'nav-accessibility', desc: 'the Accessibility item in the left-hand list' },
    { gid: 'apply-button', desc: 'the blue Apply button' },
    { gid: 'brightness-slider', desc: 'the Brightness slider' },
    { negative: true, desc: 'the Night Shift schedule dropdown' },
  ],
  webmail: [
    { gid: 'compose-button', desc: 'the blue Compose button' },
    { gid: 'row1-subject', desc: 'the subject of the HMRC Refunds email' },
    { gid: 'mail-search', desc: 'the Search mail box' },
    { gid: 'folder-spam', desc: 'the Spam folder in the left-hand list' },
    { gid: 'profile-avatar', desc: 'the round profile picture with the letter S' },
    { negative: true, desc: 'the Unsubscribe link' },
  ],
  login: [
    { gid: 'password-field', desc: 'the Password box' },
    { gid: 'signin-button', desc: 'the blue Sign in button' },
    { gid: 'forgot-link', desc: 'the Forgotten your password link' },
    { gid: 'remember-me', desc: 'the Remember me checkbox' },
    { negative: true, desc: 'the Create an account button' },
  ],
  files: [
    { gid: 'folder-taxes', desc: 'the yellow Taxes 2025 folder' },
    { gid: 'file-letter', desc: 'the letter-to-council document' },
    { gid: 'desktop-bin', desc: 'the Recycle Bin on the desktop' },
    { gid: 'nav-photos', desc: 'Photos in the left-hand sidebar' },
    { negative: true, desc: 'the Print button in the toolbar' },
  ],
};


export const HARD_SCREENS = {
  editor: [
    { gid: 'paperclip-btn', desc: 'the paperclip icon in the toolbar' },
    { gid: 'bold-btn', desc: 'the Bold (B) button' },
    { gid: 'underline-btn', desc: 'the Underline (U) button' },
    { gid: 'undo-btn', desc: 'the Undo arrow button' },
    { gid: 'print-btn', desc: 'the printer icon' },
    { gid: 'save-button', desc: 'the Save button at the top right' },
    { negative: true, desc: 'the Spell check button' },
    { negative: true, desc: 'the Download as PDF button' },
  ],
  popup: [
    { gid: 'popup-close', desc: 'the small round close (X) button on the newsletter pop-up' },
    { gid: 'cookie-accept', desc: 'the orange Accept all button' },
    { gid: 'cookie-manage', desc: 'the Manage choices button' },
    { gid: 'delivery-link', desc: 'the Delivery information link' },
    { gid: 'add-wishlist', desc: 'the Add to wishlist button' },
    { negative: true, desc: 'the Reject all cookies button' },
    { negative: true, desc: 'the Checkout button' },
  ],
};

// Real public web UIs. Ground truth comes from DOM selectors, so it is exact for the viewport captured.
export const REAL_SITES = [
  {
    id: 'real-govuk',
    url: 'https://www.gov.uk/',
    targets: [
      { selector: 'input[type=search], #q, input[name=keywords]', desc: 'the search box at the top of the page' },
      { selector: 'a[href="/browse/benefits"]', desc: 'the Benefits link' },
      { negative: true, desc: 'the Log in to your account button' },
    ],
  },
  {
    id: 'real-wikipedia',
    url: 'https://en.wikipedia.org/wiki/Main_Page',
    targets: [
      { selector: '#searchInput', desc: 'the Search Wikipedia box' },
      { selector: '#n-randompage a, a[title="Load a random page"]', desc: 'the Random article link in the left-hand menu' },
      { negative: true, desc: 'the Buy now button' },
    ],
  },
  {
    id: 'real-hn',
    url: 'https://news.ycombinator.com/',
    targets: [
      { selector: 'a[href="newest"]', desc: 'the "new" link in the orange top bar' },
      { selector: 'a.morelink', desc: 'the More link at the bottom of the list' },
      { negative: true, desc: 'the Subscribe button' },
    ],
  },
  {
    id: 'real-bbc',
    url: 'https://www.bbc.co.uk/news',
    targets: [
      { selector: 'a[href="/news/uk"], a[href*="/news/uk"]', desc: 'the UK link in the news navigation bar' },
      { negative: true, desc: 'the Download the app button' },
    ],
  },
];
