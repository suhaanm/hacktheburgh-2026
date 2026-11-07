# PodsControlMac (no licence: ideas only) - notes for background yield (HND-5) and the human/agent trace split (CAP-6)

**What it does well.** The automation (head-driven scrolling) tags the synthetic events it posts so that its own global listen-only event monitors can ignore them. Separate monitors watch real pointer movement, real typing and real manual scrolling; any of them registers "human is here" and the automation backs off for a cool-off period. Typing activity is just a timestamp compared against a threshold. It also smooths a signal with fast attack and slow release.

**What informs us.** HND-5 (background runs yield within 1 second when human input is signalled), CAP-6 (agent actions never enter the human trace), and a model for how help fades (fast to react, slow to relax).

**What we do differently.**
- Our background routines run in a *separate Playwright context*, so they never move the human's pointer. The yield signal is an abstract `HumanInputSignal` (a thread-safe event + timestamp) that the desktop app or engine can set; real OS-level monitors are the desktop track's job.
- Yield is a first-class path in the supervisor: signalled input cancels the current generation, the run records a checkpoint and a `yielded` audit line, and the routine is resumable. A hold-off period must elapse of no input before a resume is allowed.
- All agent step events carry `actor: "agent"`; the agent service never writes `actor: "human"` events (tested).
