# Understudy

*Working name. Hack the Burgh XIII, Edinburgh, 7 to 8 Nov 2026.*

Understudy watches how people work, shows where a novice loses time against an expert, coaches on the real screen with help that fades as the person improves, and lets an agent take over the repetitive parts, only when the worker opts in. A memory file the worker owns adapts it to them. It is generalised across job roles through role packs.

Targets: **HRT** (predictions and decisions), **G-Research** (make the invisible visible), **Wordsmith** (the most complicated end-to-end browser-use workflow).

> **Status:** planning complete on Sat 7 Nov 2026, about 14:00 GMT. Nothing is built yet. Submission is **Sun 8 Nov 2026, 12:00 GMT**.

## If you are the build laptop, start here

1. Read [CLAUDE.md](CLAUDE.md). It holds the rules. Then read, in order:
   [docs/SPEC_LIST.md](docs/SPEC_LIST.md), [docs/IMPLEMENTATION_SPEC.md](docs/IMPLEMENTATION_SPEC.md), [docs/REFERENCES.md](docs/REFERENCES.md), [docs/UI_DIRECTION.md](docs/UI_DIRECTION.md), [docs/IDEA_BOARD.md](docs/IDEA_BOARD.md).
2. Copy `.env.example` to `.env`. Set `ALONGSIDE_PATH` to the local copy of the owner's Alongside project on this machine, and `OPENAI_API_KEY`. Leave the model IDs for spike S1.
3. Run `scripts/check-env.sh`.
4. Run `scripts/clone-references.sh`. It makes read-only local copies of the reference repos in `references/` (gitignored). Read them to guide the modular design. **Do not run or import anything from them.**
5. Do milestone **M0** in the implementation spec: spikes S1 to S4, the Alongside copy, and mock mode. Record the results in `docs/SPIKES.md`.
6. Continue through M1 to M10. Push to `main` at every checkpoint.

## Things only a human can do

- Grant macOS **Accessibility** and **Screen Recording** to the app and the terminal, and be present for the first real-click spike (S2).
- Put the OpenAI key in `.env`.
- Run the live study with the four teammates, after the analysis plan is committed.
- Rehearse and give the demo, and submit before the deadline.

## What is in this repo

| Path | What |
|---|---|
| `docs/SPEC_LIST.md` | Every requirement with ID, priority, track and acceptance test |
| `docs/IMPLEMENTATION_SPEC.md` | Architecture, contracts, algorithms, milestones, cut lines |
| `docs/IDEA_BOARD.md` | All ideas by status, parked alternatives, decision log |
| `docs/REFERENCES.md` | The ten Devpost projects, their GitHub repos, licences, what to take |
| `docs/UI_DIRECTION.md` | Our own uncluttered, standout interface |
| `docs/DECISIONS.md`, `docs/SPIKES.md` | Running notes from the build |
| `scripts/` | `clone-references.sh`, `check-env.sh` |

## Disclosure

Understudy's coach is built on **Alongside**, the author's own earlier open-source project (https://github.com/suhaanm/deepmind-hackathon, first commit 31 Oct 2026, MIT). All Alongside code is by the author. The README will list exactly which Alongside modules were reused once the build is done. Alongside includes code adapted from third parties, whose notices are kept in `THIRD_PARTY_NOTICES.md`.

## Inspired by

We read these projects to guide the design and re-implemented the ideas in our own code, except where noted in `THIRD_PARTY_NOTICES.md`. Thank you to their authors.

[Okidoki](https://devpost.com/software/okidoki) · [Vision OS](https://devpost.com/software/vision-os-4ckmq3) · [Bandit](https://devpost.com/software/bandit-the-only-band-you-need) · [MOA](https://devpost.com/software/moa) · [Mark8](https://devpost.com/software/mark8-go-to-market-world-model) · [Pupil](https://devpost.com/software/pupil-utzxy2) · [Drigil](https://devpost.com/software/drigil) · [Rouge](https://devpost.com/software/rouge-cm8jig) · [PodsControlMac](https://devpost.com/software/podscontrolmac-control-your-mac-with-airpods) · [Stride](https://devpost.com/software/stride-09alcg)

## Licence

Not chosen yet. Until the owner adds a licence file, all rights are reserved.
