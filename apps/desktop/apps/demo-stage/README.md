# Practice Desktop (`apps/demo-stage`)

A brand-neutral fake "desktop in a web page" with three small apps. It is (1) the deterministic stage for the live demo, (2) the **grounding benchmark** (exact ground-truth boxes for every target), (3) the safe fallback if the real-screen run misbehaves, and (4) the seed convention for the later Practice Sandbox.

Static HTML/CSS/vanilla JS. No build step, no npm dependencies, no network requests, works from `file://` too. All names ("VideoChat", "Messages", "Aldermoor Bank", "Riverside Surgery", ...) are invented; no real logos or branding.

Apps: **VideoChat** (contacts, Start call, Join, mute/camera/Leave, fake call timer, settings gear), **Messages** (4 genuine texts + staged scam texts), **Settings** (Display -> text size, decoy Advanced).

## Run

```bash
python3 -m http.server 5180 --bind 127.0.0.1 --directory apps/demo-stage   # or `npm run stage` once ARCH wires it
open "http://127.0.0.1:5180/index.html?still=1#desktop"
```

Press **F** for browser fullscreen (then the page fills the display exactly, so `rects()` equals display-normalised coordinates). Works at 1440x900, 1920x1080 and browser zoom 100-150% (tested down to 960x600 CSS px).

## Fixtures: jump straight to a known screen

Use the URL hash (`#video/call-screen`) or `?fixture=video/call-screen`, or call `__stage.go('video/call-screen')`. Every fixture starts from a clean state. Add `?still=1` for reproducible screenshots.

| fixture | what you see |
|---|---|
| `desktop` | desktop icons, widgets, nothing open |
| `desktop/scam` | desktop; scam text just arrived (notification banner + red 1 badge on Messages). `desktop/scam/parcel`, `desktop/scam/family` pick a variant; `desktop/genuine/N` the same for a genuine text |
| `desktop/menu` | desktop with the top-left Menu open |
| `video` / `video/contacts` | VideoChat, nothing selected |
| `video/lily` | Lily selected, green **Start call** visible |
| `video/precall` | "Ready to join?" screen with blue **Join** (`video/precall/camera-off` starts with the camera off) |
| `video/calling` | call screen, "Calling Lily..." (frozen) |
| `video/call-screen` | connected call, timer `00:12` in still mode (`/muted`, `/camera-off` variants) |
| `video/ended` | "Call ended - 00:42" |
| `video/settings` | VideoChat settings (gear) |
| `video/contact/<id>` | contact selected: `dave lily priya surgery rosa tom` |
| `messages` / `messages/inbox` | Messages, 4 genuine conversations, none open |
| `messages/scam-list` | scam delivered and unread at the top, none open |
| `messages/scam` | scam open (bank "account locked" text with lookalike link). `messages/scam-parcel`, `messages/scam-family` for the other variants |
| `messages/scam/menu` | scam open, three-dots menu open (Report junk / Block / Delete) |
| `messages/scam/reported` | after Report junk (amber banner). Also `/blocked` |
| `messages/scam/link` | after tapping the link (practice pop-up, `linkClicked=true`) |
| `messages/genuine/0..3` | genuine text delivered and open: 0 surgery reminder, 1 Lily, 2 family chat, 3 pharmacy |
| `settings` / `settings/general` | Settings on General |
| `settings/display` | Display panel with the Text size card |
| `settings/display/size/0..4` | text size 100/125/150/175/200% (`settings/display/bigger` = size 1) |
| `settings/sound`, `/notifications`, `/privacy`, `/advanced` | other panels (Advanced is the decoy) |
| `settings/advanced/reset-confirm` | "Reset all settings?" confirmation pop-up |

## URL parameters

| param | effect |
|---|---|
| `?still=1` | freeze time and motion: no animations/transitions, clock fixed at `10:42`, call timer fixed at `00:12`, notifications do not auto-dismiss, ringing lasts 0.9 s. (`prefers-reduced-motion` is honoured too.) |
| `?debug=1` | draw every ground box with its id on the page (also hotkey **D**). Boxes come from the `__stage.rects()` output, so they validate the API |
| `?fixture=<route>` | same as the hash |
| `?scale=0..4` | initial text size step |
| `?theme=dark`, `?contrast=high` | initial theme / high-contrast (also toggles in Settings -> Display) |

Hotkeys (ignored while typing in a text box): **S** deliver the scam text, **G** deliver the next genuine text, **Shift+R** reset, **D** debug boxes, **F** fullscreen, **Esc** close pop-up.

## `window.__stage` API

```ts
rects(opts?): Record<string,{xmin,ymin,xmax,ymax}>   // visible ground ids -> NORMALISED 0-1000 of the viewport, top-left origin, y down (TEAM_BRIEF §4)
rectOf(id, opts?): {xmin,ymin,xmax,ymax} | null
catalog(opts?): {id, app, kind, label, desc, visible, box}[]   // kind: button|link|input|switch|slider|handle|select|menuitem|text|block|media|container
state(): {...}        // route, app, textStep/textScalePct, video{view,selected,callState,seconds,mic,camera}, messages{selected,unread,delivered,linkClicked,reported,blocked,...}, settings{section}, toast, modal, ...
go(route) / reset() / setStep(flowId, n)
deliverScam(variant?: 'bank'|'parcel'|'family'|0|1|2)   // default 'bank' -> conversation id `scam`
deliverGenuine(i: 0..3)                                  // re-delivers genuine text i as a fresh unread notification
events() / lastEvent(type?) / clearEvents() / onEvent(fn) // action log; also window event 'stage:event'
setTextStep(n), connectCall(), debug(on), ids(), duplicateIds(), flows (= window.STAGE_FLOWS), ready, hotkeys
```

`opts`: `{space:'screen'}` returns boxes normalised to the whole display (uses `window.screenX/Y` and the browser chrome offset: approximate unless the page is fullscreen or at 100% zoom); `{includeOccluded:true}` also returns elements hidden behind a pop-up/window.

Ground-truth rules: only elements that are rendered, not clipped by a scroll container and not covered by another element (majority of 7 sample points) are returned. Boxes of `text` ids hug the text; `button/link/input/...` boxes are the element; `block` (bubbles, cards, toast, modal), `media` (video tiles) and `container` ids use the element box. Range sliders also get `<id>.thumb` (the draggable handle). Nothing is persisted (no storage), so every reload starts clean.

Events (`type`): `click {id, act, x, y}` (x,y normalised), `open_app`, `close_app`, `select_contact`, `precall`, `call_started`, `call_connected`, `call_ended {seconds}`, `mic`, `camera`, `deliver {kind, conv}`, `open_conversation`, `report_junk`, `block`, `link_clicked`, `message_sent`, `text_size {step, percent, via}`, `settings_section`, `switch`, `settings_reset`, `modal`, `toast_dismissed`.

## ID convention

`data-ground-id="<app>.<area>.<name>"`, lower-case, dots for scope, underscores inside a name: `video.start_call`, `video.precall.join`, `video.call.hangup`, `messages.conv.scam`, `messages.msg.scam.0` (bubble n of a conversation), `messages.link.scam`, `settings.nav.display`, `settings.text_larger`, `desk.icon.video`. Apps: `desk` (shell), `video`, `messages`, `settings`, `modal`. IDs are unique per screen (`duplicateIds()` returns `[]`). Optional `data-desc` on key elements holds a visual description (`catalog()[i].desc`). Messages conversation ids: `scam` (bank), `scam_parcel`, `scam_family`, `surgery`, `lily`, `family`, `pharmacy`.

### Deliberate decoys (so "find the right button" is not trivial)

Two **Join** buttons (toolbar `video.toolbar.join` is a decoy; the real one is `video.precall.join`), gear icons in both VideoChat and the desktop, icon-only rail buttons, `Share/Chat/People/More` in the call bar, six decoy desktop apps (Web, Files, Photos, Notes, Calendar, Bin) that only open a "not part of the practice desktop" pop-up, Settings -> Advanced (scary switches, `Reset all settings...` with confirmation), and the same word "Settings" in two places.

### Staged texts (for scam-vs-genuine tests)

| conv id | sender | text | red flags |
|---|---|---|---|
| `scam` | Aldermoor Bank, +44 7700 900482 | "URGENT: Aldermoor Bank. Your account has been LOCKED after suspicious activity. Verify your identity within 2 hours or your money will be frozen. Verify now: https://aldermoor-bank.secure-verify.co/login" | urgency, threat, lookalike domain (`secure-verify.co`), click-to-verify |
| `scam_parcel` | Parcel Courier | "We tried to deliver your parcel today ... Pay a GBP 1.45 re-delivery fee within 24 hours ...: https://parcel-redelivery-uk.top/pay" | small fee, deadline, odd `.top` domain |
| `scam_family` | Unknown number | "Hi Mum, I dropped my phone in water. This is my new number ... Can you send GBP 480 to this account right now? It is urgent ..." | new number, money request, urgency, no link |
| `surgery` (genuine 0) | Riverside Surgery | appointment reminder: Dr Okafor, Tue 4 Nov 10:20, call the number on your appointment card | none (no link, no money) |
| `lily` (genuine 1) | Lily | "Hi Gran! Are you free for a video call on Sunday at 4? ..." | none |
| `family` (genuine 2) | Family Chat | "Dave: Lunch at ours on Saturday, 1pm. Who is bringing the trifle?" | none |
| `pharmacy` (genuine 3) | Greenfield Pharmacy | "Your prescription is ready to collect ... bring your name and date of birth" | none |

Tapping a link never navigates: it opens a practice pop-up and sets `state().messages.linkClicked = true` (use this to verify the learner did NOT tap it).

## The three lesson flows (ground truth for TEACH / SERVICES)

`targetDescription` is written visually for the grounder; `expectedOutcome` describes the screen after the step. Same data lives in `flows.js` as `window.STAGE_FLOWS` (and `__stage.flows`). Each transition is verified by an automated click-through at 960x600, 1280x720, 1440x900 and 1920x1080: click the centre of `rectOf(targetId)`, then compare the visible id set with the "fixture after" screen.

#### `video_call` - "Start a video call with Lily"

Start state: `#desktop`. Jump to the state after step *n* with `__stage.setStep('video_call', n)` (0 = start).

| # | step id | instruction (learner) | target id | targetDescription (for the grounder) | expectedOutcome (for the verifier) | safety-critical | fixture after |
|---|---|---|---|---|---|---|---|
| 1 | `video_call.open_app` | Open the VideoChat app on your desktop. | `desk.icon.video` | Teal rounded-square icon with a white video-camera symbol and the label VideoChat, first icon in the left-hand column of the desktop | The VideoChat window is open: a contacts list on the left (Dave Morgan, Lily, Priya Shah, Riverside Surgery, Rosa Bell, Tom) and "Select a contact" text on the right. | no | `#video/contacts` |
| 2 | `video_call.pick_lily` | Click Lily in your contacts list. | `video.contact.lily` | Row labelled Lily with the subtitle Granddaughter and a green dot, second row in the contacts list on the left of the VideoChat window | Lily's row is highlighted and the right-hand pane shows a large avatar, the name Lily, "Granddaughter", and a large green Start call button. | no | `#video/lily` |
| 3 | `video_call.start_call` | Press the green Start call button. | `video.start_call` | Large green button reading Start call with a camera icon, in the right-hand pane below Lily's name | A screen titled "Ready to join?" appears with a camera preview, Camera and Microphone switches, a large blue Join button and a Cancel button. | no | `#video/precall` |
| 4 | `video_call.join` | Press the blue Join button to begin the call. | `video.precall.join` | Large blue button reading Join, below the camera preview and the switches on the Ready to join screen (not the small Join button in the contacts toolbar) | The call screen fills the window: Lily's picture, her name top-left, "Connected" under it, a timer top-right counting up, and a bottom row of controls ending with a red Leave button. (It says "Calling..." for about two seconds first.) | no | `#video/call-screen` |
| 5 | `video_call.leave` | When you have finished talking, press the red Leave button. | `video.call.hangup` | Red button with a white phone-handset icon and the word Leave, right-most button in the bottom control bar of the call screen | A "Call ended" screen says how long the call lasted and offers Call Lily again and Back to contacts. | no | `#video/ended` |

#### `spot_scam` - "Check whether a text message is a scam"

Start state: `#desktop/scam`. Jump to the state after step *n* with `__stage.setStep('spot_scam', n)` (0 = start).

| # | step id | instruction (learner) | target id | targetDescription (for the grounder) | expectedOutcome (for the verifier) | safety-critical | fixture after |
|---|---|---|---|---|---|---|---|
| 1 | `spot_scam.open_messages` | Open the Messages app on your desktop. | `desk.icon.messages` | Blue rounded-square icon with a white speech bubble and a small red 1 badge, label Messages, second icon in the left-hand column of the desktop | The Messages window is open; the conversation list shows Aldermoor Bank at the top in bold with a blue dot; the right pane says "Select a conversation to read it." | no | `#messages/scam-list` |
| 2 | `spot_scam.open_text` | Click the Aldermoor Bank message to read it. | `messages.conv.scam` | Top row of the conversation list, name Aldermoor Bank in bold with a blue unread dot and a preview starting URGENT | The message opens on the right: sender Aldermoor Bank, number +44 7700 900482, and a grey bubble saying the account is LOCKED with a blue underlined web address. | no | `#messages/scam` |
| 3 | `spot_scam.inspect` | Read it carefully, but do not tap the blue link. | `messages.msg.scam.0` | The grey message bubble from Aldermoor Bank (the blue underlined web address inside it is messages.link.scam: point at it, never click it) | Nothing changes on screen and no pop-up appears (the link was not clicked). The learner can name warning signs: urgency, threat of frozen money, odd web address. | yes | `#messages/scam` |
| 4 | `spot_scam.open_menu` | Open the three-dots menu at the top right of the message. | `messages.thread.menu` | Small round button with three dots in the top-right corner of the open conversation, next to the sender name | A small menu drops down with Report junk, Block this number and Delete conversation. | no | `#messages/scam/menu` |
| 5 | `spot_scam.report` | Choose Report junk. | `messages.thread.report` | First item, Report junk with a warning-triangle icon, in the dropdown under the three-dots button | The menu closes and an amber banner reads "Reported as junk. This number is now blocked." | no | `#messages/scam/reported` |

#### `bigger_text` - "Make the text on the screen bigger"

Start state: `#desktop`. Jump to the state after step *n* with `__stage.setStep('bigger_text', n)` (0 = start).

| # | step id | instruction (learner) | target id | targetDescription (for the grounder) | expectedOutcome (for the verifier) | safety-critical | fixture after |
|---|---|---|---|---|---|---|---|
| 1 | `bigger_text.open_settings` | Open the Settings app on your desktop. | `desk.icon.settings` | Grey rounded-square icon with a white gear symbol and the label Settings, third icon in the left-hand column of the desktop | The Settings window is open on General: a list on the left (General, Display, Sound, Notifications, Privacy, Advanced) and language/time rows on the right. | no | `#settings` |
| 2 | `bigger_text.open_display` | Click Display in the list on the left. | `settings.nav.display` | Second item, Display with a monitor icon, in the vertical list on the left of the Settings window | The Display panel shows a Text size card with a Smaller button, a slider, a Larger button and the readout "100% · Default". | no | `#settings/display` |
| 3 | `bigger_text.make_bigger` | Press the Larger button once to make the text bigger. | `settings.text_larger` | Button with a big letter A and the word Larger, to the right of the slider inside the Text size card | Every piece of text on screen, including the top bar and the window, is visibly bigger (125%). The readout says "125% · Large". | no | `#settings/display/size/1` |

Notes: `video_call` step 4 shows "Calling..." for ~2 s (0.9 s with `?still=1`) before the timer starts. After the call, `video.ended.*` is shown; `desk.callpill` appears in the top bar if the VideoChat window is minimised during a call.

## All ground ids (generated from the visible catalog of every fixture)

#### Desktop shell (`desk.*`)

| id | kind | label / text | first visible in |
|---|---|---|---|
| `desk.clock` | text | 10:42 | `desktop` |
| `desk.icon.bin` | button | Bin | `desktop` |
| `desk.icon.calendar` | button | Calendar | `desktop` |
| `desk.icon.files` | button | Files | `desktop` |
| `desk.icon.messages` | button | Messages | `desktop` |
| `desk.icon.notes` | button | Notes | `desktop` |
| `desk.icon.photos` | button | Photos | `desktop` |
| `desk.icon.settings` | button | Settings | `desktop` |
| `desk.icon.video` | button | VideoChat | `desktop` |
| `desk.icon.web` | button | Web | `desktop` |
| `desk.menu` | button | Menu | `desktop` |
| `desk.menu.messages` | menuitem | Messages | `desktop/menu` |
| `desk.menu.power` | menuitem | Power options… | `desktop/menu` |
| `desk.menu.settings` | menuitem | Settings | `desktop/menu` |
| `desk.menu.video` | menuitem | VideoChat | `desktop/menu` |
| `desk.task.messages` | button | Messages | `messages/scam/reported` |
| `desk.task.settings` | button | Settings | `settings/general` |
| `desk.task.video` | button | VideoChat | `video/contacts` |
| `desk.title` | text | Desktop | `desktop` |
| `desk.toast` | block | Messages · nowAldermoor BankURGENT: Aldermoor Bank. Your acc | `desktop/scam` |
| `desk.toast.dismiss` | button | Dismiss | `desktop/scam` |
| `desk.toast.open` | button | Open | `desktop/scam` |
| `desk.toast.text` | text | URGENT: Aldermoor Bank. Your account has been LOCKED after s | `desktop/scam` |
| `desk.toast.title` | text | Aldermoor Bank | `desktop/scam` |
| `desk.topbar` | container | Menu Desktop In call 00:00 - return to VideoChat 86% 10:42 | `desktop` |
| `desk.widget.note` | block | Sticky note Lily's birthday on Sunday. Ring Dave about Satur | `desktop` |
| `desk.widget.weather` | block | Today 12°C Cloudy, light wind | `desktop` |

#### VideoChat (`video.*`)

| id | kind | label / text | first visible in |
|---|---|---|---|
| `video.call` | container | Call screen | `video/calling` |
| `video.call.camera` | button | Stop video | `video/calling` |
| `video.call.chat` | button | Chat | `video/calling` |
| `video.call.hangup` | button | Leave | `video/calling` |
| `video.call.main_video` | media | Calling Lily… Lily | `video/calling` |
| `video.call.mic` | button | Mute | `video/calling` |
| `video.call.more` | button | More | `video/calling` |
| `video.call.name` | text | Lily | `video/calling` |
| `video.call.people` | button | People | `video/calling` |
| `video.call.self_video` | media | Camera off You | `video/calling` |
| `video.call.share` | button | Share | `video/calling` |
| `video.call.status` | text | Calling… | `video/calling` |
| `video.call.timer` | text | 00:00 | `video/calling` |
| `video.contact.dave` | button | DMDave MorganNeighbour | `video/contacts` |
| `video.contact.lily` | button | LLilyGranddaughter · Online | `video/contacts` |
| `video.contact.priya` | button | PSPriya ShahFriend · Online | `video/contacts` |
| `video.contact.rosa` | button | RBRosa BellBook club | `video/contacts` |
| `video.contact.surgery` | button | RSRiverside SurgeryReception | `video/contacts` |
| `video.contact.tom` | button | TPTom (plumber)Work | `video/contacts` |
| `video.contacts` | container | Contacts | `video/contacts` |
| `video.detail` | container | Select a contact to see more. | `video/contacts` |
| `video.detail.avatar` | media | L | `video/lily` |
| `video.detail.empty` | text | Select a contact to see more. | `video/contacts` |
| `video.detail.message` | button | Message | `video/lily` |
| `video.detail.name` | text | Lily | `video/lily` |
| `video.detail.relation` | text | Granddaughter · Online now | `video/lily` |
| `video.detail.voice_only` | button | Voice call only | `video/lily` |
| `video.ended.again` | button | Call Lily again | `video/ended` |
| `video.ended.back` | button | Back to contacts | `video/ended` |
| `video.ended.heading` | text | Call ended | `video/ended` |
| `video.ended.summary` | text | You were on a call with Lily for 00:42. | `video/ended` |
| `video.precall.camera` | switch | Camera | `video/precall` |
| `video.precall.cancel` | button | Cancel | `video/precall` |
| `video.precall.heading` | text | Ready to join? | `video/precall` |
| `video.precall.join` | button | Join | `video/precall` |
| `video.precall.mic` | switch | Microphone | `video/precall` |
| `video.precall.preview` | media | Camera is on | `video/precall` |
| `video.precall.speaker` | select | Speaker | `video/precall` |
| `video.precall.subtitle` | text | Call with Lily | `video/precall` |
| `video.rail.calls` | button | Calls | `video/contacts` |
| `video.rail.chats` | button | Chats | `video/contacts` |
| `video.rail.contacts` | button | Contacts | `video/contacts` |
| `video.search` | input | Search contacts | `video/contacts` |
| `video.settings` | button | VideoChat settings | `video/contacts` |
| `video.settings.autostart` | switch | Start VideoChat when I sign in | `video/settings` |
| `video.settings.back` | button | Back | `video/settings` |
| `video.settings.blur` | switch | Blur my background | `video/settings` |
| `video.settings.camera` | select | Camera | `video/settings` |
| `video.settings.heading` | text | VideoChat settings | `video/settings` |
| `video.settings.hw_accel` | switch | Hardware acceleration | `video/settings` |
| `video.settings.microphone` | select | Microphone | `video/settings` |
| `video.settings.ring` | switch | Ring for incoming calls | `video/settings` |
| `video.settings.sign_out` | button | Sign out | `video/settings` |
| `video.start_call` | button | Start call | `video/lily` |
| `video.toolbar.join` | button | Join | `video/contacts` |
| `video.toolbar.new_meeting` | button | New meeting | `video/contacts` |
| `video.toolbar.schedule` | button | Schedule | `video/contacts` |
| `video.win.close` | button | Close window | `video/contacts` |
| `video.win.maximise` | button | Maximise window | `video/contacts` |
| `video.win.minimise` | button | Minimise window | `video/contacts` |
| `video.win.title` | text | VideoChat | `video/contacts` |
| `video.window` | container | VideoChat window | `video/contacts` |

#### Messages (`messages.*`)

| id | kind | label / text | first visible in |
|---|---|---|---|
| `messages.banner` | block | Reported as junk. This number is now blocked. | `messages/scam/reported` |
| `messages.compose.input` | input | Type a message | `messages/scam/reported` |
| `messages.compose.send` | button | Send | `messages/scam/reported` |
| `messages.conv.family` | button | FCFamily ChatWedDave: Lunch at ours on Saturday, 1pm. Who is | `messages/scam/reported` |
| `messages.conv.lily` | button | LLilyThuHi Gran! Are you free for a video call on Sunday at  | `messages/scam/reported` |
| `messages.conv.pharmacy` | button | GPGreenfield PharmacyMonYour prescription is ready to collec | `messages/scam/reported` |
| `messages.conv.scam` | button | ABAldermoor BankNowURGENT: Aldermoor Bank. Your account has  | `messages/scam/reported` |
| `messages.conv.scam_family` | button | UNUnknown numberNowHi Mum, I dropped my phone in water. This | `messages/scam-family` |
| `messages.conv.scam_parcel` | button | PCParcel CourierNowWe tried to deliver your parcel today but | `messages/scam-parcel` |
| `messages.conv.surgery` | button | RSRiverside SurgeryYesterdayReminder: you have an appointmen | `messages/scam/reported` |
| `messages.link.scam` | link | https://aldermoor-bank.secure-verify.co/login | `messages/scam/reported` |
| `messages.list` | container | ABAldermoor BankNowURGENT: Aldermoor Bank. Your account has  | `messages/scam/reported` |
| `messages.msg.family.0` | block | Jo: Photos from the garden party are up!Tue 20:15 | `messages/genuine/2` |
| `messages.msg.family.1` | block | Dave: Lunch at ours on Saturday, 1pm. Who is bringing the tr | `messages/genuine/2` |
| `messages.msg.lily.0` | block | Hello love, how was your week?Thu 18:02 | `messages/genuine/1` |
| `messages.msg.lily.1` | block | Hi Gran! Are you free for a video call on Sunday at 4? I wan | `messages/genuine/1` |
| `messages.msg.pharmacy.0` | block | Your prescription is ready to collect from Greenfield Pharma | `messages/genuine/3` |
| `messages.msg.scam_family.0` | block | Hi Mum, I dropped my phone in water. This is my new number,  | `messages/scam-family` |
| `messages.msg.scam_parcel.0` | block | We tried to deliver your parcel today but nobody was home. P | `messages/scam-parcel` |
| `messages.msg.scam.0` | block | URGENT: Aldermoor Bank. Your account has been LOCKED after s | `messages/scam/reported` |
| `messages.msg.surgery.0` | block | Reminder: you have an appointment with Dr Okafor on Tuesday  | `messages/genuine/0` |
| `messages.new` | button | New message | `messages/scam/reported` |
| `messages.search` | input | Search messages | `messages/scam/reported` |
| `messages.thread` | container | AB Aldermoor Bank +44 7700 900482 Report junk Block this num | `messages/scam/reported` |
| `messages.thread.block` | menuitem | Block this number | `messages/scam/menu` |
| `messages.thread.delete` | menuitem | Delete conversation | `messages/scam/menu` |
| `messages.thread.empty` | container | Select a conversation to read it. | `messages/inbox` |
| `messages.thread.menu` | button | More options | `messages/scam/reported` |
| `messages.thread.number` | text | +44 7700 900482 | `messages/scam/reported` |
| `messages.thread.report` | menuitem | Report junk | `messages/scam/menu` |
| `messages.thread.sender` | text | Aldermoor Bank | `messages/scam/reported` |
| `messages.title` | text | Conversations | `messages/scam/reported` |
| `messages.win.close` | button | Close window | `messages/scam/reported` |
| `messages.win.maximise` | button | Maximise window | `messages/scam/reported` |
| `messages.win.minimise` | button | Minimise window | `messages/scam/reported` |
| `messages.win.title` | text | Messages | `messages/scam/reported` |
| `messages.window` | container | Messages window | `messages/scam/reported` |

#### Settings (`settings.*`)

| id | kind | label / text | first visible in |
|---|---|---|---|
| `settings.advanced.clear_cache` | button | Clear cache | `settings/advanced` |
| `settings.advanced.developer_mode` | switch | Developer mode | `settings/advanced` |
| `settings.advanced.disable_security` | switch | Turn off security checks | `settings/advanced` |
| `settings.advanced.dns` | input | DNS server | `settings/advanced` |
| `settings.advanced.heading` | text | Advanced | `settings/advanced` |
| `settings.advanced.proxy` | input | Network proxy | `settings/advanced` |
| `settings.advanced.remote_access` | switch | Allow remote access | `settings/advanced` |
| `settings.advanced.reset_all` | button | Reset all settings… | `settings/advanced` |
| `settings.advanced.warning` | block | Careful: these settings are for experts. Changing them can s | `settings/advanced` |
| `settings.display.brightness` | slider | Brightness | `settings/display` |
| `settings.display.brightness.thumb` | handle | Brightness handle | `settings/display` |
| `settings.display.dark_theme` | switch | Dark theme | `settings/display` |
| `settings.display.heading` | text | Display | `settings/display` |
| `settings.display.high_contrast` | switch | High contrast | `settings/display` |
| `settings.display.night_light` | switch | Night light | `settings/display` |
| `settings.general.about` | text | Practice Desktop 1.0 - for learning only | `settings/general` |
| `settings.general.device_name` | input | Device name | `settings/general` |
| `settings.general.heading` | text | General | `settings/general` |
| `settings.general.language` | select | Language | `settings/general` |
| `settings.general.time_format` | select | Time format | `settings/general` |
| `settings.nav.advanced` | button | Advanced | `settings/general` |
| `settings.nav.display` | button | Display | `settings/general` |
| `settings.nav.general` | button | General | `settings/general` |
| `settings.nav.notifications` | button | Notifications | `settings/general` |
| `settings.nav.privacy` | button | Privacy | `settings/general` |
| `settings.nav.sound` | button | Sound | `settings/general` |
| `settings.notifications.heading` | text | Notifications | `settings/notifications` |
| `settings.notifications.messages` | switch | Messages | `settings/notifications` |
| `settings.notifications.reminders` | switch | Reminders | `settings/notifications` |
| `settings.notifications.videochat` | switch | VideoChat | `settings/notifications` |
| `settings.privacy.camera_access` | switch | Camera access | `settings/privacy` |
| `settings.privacy.heading` | text | Privacy | `settings/privacy` |
| `settings.privacy.location` | switch | Location | `settings/privacy` |
| `settings.privacy.microphone_access` | switch | Microphone access | `settings/privacy` |
| `settings.privacy.share_usage` | switch | Share usage data | `settings/privacy` |
| `settings.search` | input | Search settings | `settings/general` |
| `settings.sound.heading` | text | Sound | `settings/sound` |
| `settings.sound.mute` | switch | Mute all sounds | `settings/sound` |
| `settings.sound.output` | select | Play sound through | `settings/sound` |
| `settings.sound.volume` | slider | Volume | `settings/sound` |
| `settings.sound.volume.thumb` | handle | Volume handle | `settings/sound` |
| `settings.text_larger` | button | Make text bigger | `settings/display` |
| `settings.text_size_slider` | slider | Text size | `settings/display` |
| `settings.text_size_slider.thumb` | handle | Text size handle | `settings/display` |
| `settings.text_size.heading` | text | Text size | `settings/display` |
| `settings.text_size.preview` | block | PreviewYour appointment is on Tuesday at 10:20. Please arriv | `settings/display` |
| `settings.text_size.value` | block | 100% · Default | `settings/display` |
| `settings.text_smaller` | button | Make text smaller | `settings/display` |
| `settings.win.close` | button | Close window | `settings/general` |
| `settings.win.maximise` | button | Maximise window | `settings/general` |
| `settings.win.minimise` | button | Minimise window | `settings/general` |
| `settings.win.title` | text | Settings | `settings/general` |
| `settings.window` | container | Settings window | `settings/general` |

#### Pop-up dialog (`modal.*`)

| id | kind | label / text | first visible in |
|---|---|---|---|
| `modal` | block | Practice linkIn real life this would open a web page. Nothin | `messages/scam/link` |
| `modal.body` | text | In real life this would open a web page. Nothing was opened, | `messages/scam/link` |
| `modal.cancel` | button | Cancel | `settings/advanced/reset-confirm` |
| `modal.confirm` | button | Reset everything | `settings/advanced/reset-confirm` |
| `modal.ok` | button | OK | `messages/scam/link` |
| `modal.title` | text | Practice link | `messages/scam/link` |

## Accessibility and known gaps

- Every control is a native button/input/select with a visible 3 px focus ring, `aria-label`s on icon-only buttons, a focus-trapped pop-up (Esc closes), `role="status"` notifications, `prefers-reduced-motion` and `?still=1` support, text sized in `rem` (the Text size setting scales the whole UI 100-200%), dark theme and high-contrast mode.
- Known gaps: no sound; the clock and call timer are real-time unless `?still=1`; at the 200% text size on viewports narrower than ~1280 px the second column of desktop icons sits behind an open window; `rects({space:'screen'})` is approximate unless fullscreen (press F) at 100% zoom; Settings search only filters the section list; New meeting / Schedule / Share / Chat / People / More only open a "for show" pop-up; the debug overlay (`?debug=1`) must be off for clean benchmark screenshots.
