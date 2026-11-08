# Knack

*Built at Hack the Burgh XIII, Edinburgh, 7 to 8 November 2026. Formerly called Understudy. Tracks: Metaview, HRT, G-Research, Wordsmith, JetBrains.*

**Every team has one person who just knows.** Their skill lives in their head, so it never spreads, and when they leave it leaves with them. **Knack is AI enablement that learns from your best people and puts their instincts on everyone else's screen:** it shows where a worker loses time against an expert, coaches on the real screen with help that fades as they improve, and lets an agent take repetitive work only when the worker says yes.

Say "Hey Knack" in any app. Knack sees your screen (only after you say yes), rings the thing to click next, talks you through it, and, when you ask it to do the click, does it behind one card that only your real mouse click can answer. Managers get a firm view of where time is lost, in aggregate, never anyone's screen.

Knack is built to close the gap between good and best.

## What it does

- **Voice and on-screen guidance in every app.** Hey Knack (or Option-Space) opens a live conversation with Gemini Live. Knack looks at your screen, draws a ring on what matters and speaks back. It works over any app on your Mac, your browser included.
- **A coach whose help fades.** Help levels L1 to L4 are decided by plain code, not by a model, so a chatty model cannot talk the product out of fading. Skipped steps are priced in seconds and in wrong answers, because in seconds skipping looks free.
- **The work genome.** A worker's steps are aligned with the nearest expert's, so the gap shows up step by step, with an interval on every number and two controls (expert against expert, shuffled labels).
- **Routines, one opt-in at a time.** Knack finds repeated work, proposes an automation, watches first, runs it, and parks the one irreversible step until you click.
- **Do it for me, in any app.** A task about your screen proposes a card naming the window; then every step goes through the safety pipeline (pinned window, trusted target read, structural gates, denylist, kill key). Sending, buying, deleting and submitting stay gated.
- **A browser agent that stops for you.** It browses and reads on its own, clears cookie banners, and waits for your click at anything it cannot judge.
- **Background agents.** A job that needs code or data work starts your own Claude command as a monitored background agent, after one consent card.
- **A firm view.** Admins see a firm in aggregate: roles, people, automation, risk and forecasts, as bands and counts, never a worker's screen.
- **Role packs.** UK benefits processor, data analyst and programmer. A memory file the worker owns adapts Knack to them.

## Try it

macOS, Python 3.12 or newer, `uv`, Node.

```bash
make setup          # Python and Node dependencies
make demo           # offline demo on generated data, mock models, nothing leaves the laptop
```

For live models and voice, copy `.env.example` to `.env`, set `GEMINI_API_KEY` and the model names, then `make live`. Knack.app is built with `cd apps/desktop && npm run package` (unsigned, sealed with a stable identity so macOS keeps its permissions across builds). First launch walks you through Microphone, Speech Recognition, Screen Recording and Accessibility; the two consent cards answer only to a real click.

