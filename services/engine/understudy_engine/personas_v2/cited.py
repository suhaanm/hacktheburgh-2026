"""Published regularities the realistic generators are calibrated to, with how well each was verified.

Rules for this file (they are the honesty rules of the REALISM track):

* Nothing here is a claim that the generated data matches real users. A generator is "within published ranges" when
  its marginals fall inside the ranges below; that is a plausibility check, not validation.
* Every entry says how it was checked. ``status`` is one of
    ``secondary``   the number was read from a search-result summary or a secondary page that quotes the primary paper;
                    the primary paper was NOT opened in this session;
    ``assumption``  no verified number was found: the range is ours and deliberately wide;
    ``qualitative`` only the direction of the effect is cited.
* No number was invented to look like a citation. Where a constant could not be verified the range says so.
* The search results were produced by a search engine's own summaries; they can be wrong. Treat ``secondary`` as
  "worth checking against the primary before quoting", which is what the report says too.

``CITED[key]["range"]`` is the interval the generator's effective value must fall inside for the marginal check.
"""
from __future__ import annotations

CITED: dict[str, dict] = {
    "klm_keystroke_s": {
        "what": "KLM keystroke operator K, seconds per keystroke",
        "range": (0.12, 1.2),
        "typical": {"expert_90wpm": 0.12, "average_skilled_55wpm": 0.20, "average_nonsecretarial_40wpm": 0.28},
        "source": "Card, Moran & Newell (1980) CACM 23(7) and the 1983 book; tiers and the 0.12 to 1.2 s range as given in Kieras's KLM tutorial",
        "status": "secondary",
        "note": "Values read from search summaries of the tutorial; the original papers were not opened. The 1983 book's K is 0.20 s.",
    },
    "klm_pointing_s": {
        "what": "KLM pointing operator P (mouse to a target), seconds",
        "range": (0.4, 1.8), "typical": 1.1,
        "source": "Card, Moran & Newell (1980/1983); 1.1 s is the standard value",
        "status": "secondary",
        "note": "The range is ours around the standard 1.1 s: P depends on distance and target size (Fitts).",
    },
    "klm_homing_s": {
        "what": "KLM homing operator H (hand between keyboard and mouse), seconds",
        "range": (0.3, 0.6), "typical": 0.4,
        "source": "Card, Moran & Newell (1980/1983); 0.4 s is the standard value",
        "status": "secondary", "note": "Range is ours around the standard value.",
    },
    "klm_mental_s": {
        "what": "KLM mental preparation operator M, seconds",
        "range": (0.9, 2.0), "typical": 1.35,
        "source": "Card, Moran & Newell (1980/1983); 1.35 s is the standard value",
        "status": "secondary", "note": "Range is ours around the standard value.",
    },
    "fitts_mouse_slope_s_per_bit": {
        "what": "Fitts' law slope b for a mouse, seconds per bit of index of difficulty",
        "range": (0.08, 0.20), "typical": 0.096,
        "source": "Card, English & Burr (1978) mouse fit MT = 1.03 + 0.096 ID, as discussed in MacKenzie's pages (yorku.ca/mack/ijhcs2004.html)",
        "status": "secondary",
        "note": "ISO 9241-9 throughput for mice is reported at about 4 to 5 bits/s (rarely above 5); the intercept in the old fit includes a homing time, so a smaller intercept is used here (0.1 to 0.8 s).",
    },
    "fitts_mouse_throughput_bps": {
        "what": "ISO 9241-9 mouse throughput, bits per second",
        "range": (2.5, 6.0), "typical": (4.0, 5.0),
        "source": "MacKenzie and colleagues (summarised on yorku.ca/mack); ISO throughput cluster at 4 to 5 bits/s",
        "status": "secondary", "note": "The effective throughput of the generated pointing times is checked against this range.",
    },
    "hick_hyman_slope_s_per_bit": {
        "what": "Hick-Hyman law slope b, seconds per bit of choice information",
        "range": (0.05, 0.30),
        "source": "Hick (1952); Hyman (1953); HCI review Seow (2005) Human-Computer Interaction 20(3)",
        "status": "assumption",
        "note": "UNVERIFIED: none of the pages opened gave a ms-per-bit slope. The range is a wide assumption, not a citation.",
    },
    "power_law_exponent": {
        "what": "exponent of the power law of practice (time falls as n to the minus alpha)",
        "range": (0.1, 1.0), "typical": "less than 1",
        "source": "Newell & Rosenbloom (1981) in Anderson (ed.) Cognitive Skills and Their Acquisition; Heathcote, Brown & Mewhort (2000) Psychonomic Bulletin & Review 7(2), who argue individual curves are exponential and the power law is an averaging artefact; R. B. Anderson (2001) simulation of the artefact",
        "status": "secondary",
        "note": "A source says the exponent in real data is typically below 1.0; no tighter verified range was found, so 0.1 to 1.0 is used. Half the simulated people learn exponentially, so the average looks like a power law.",
    },
    "pause_lognormal_mixture": {
        "what": "pauses in keystroke logs are leptokurtic, well described by a mixture of lognormals",
        "range": (5.0, 400.0), "unit": "p99 over median of pause durations",
        "source": "Almond, Deane, Quinlan, Wagner & Sydorenko (2012) ETS RR-12-23 'A preliminary analysis of keystroke log data from a timed writing task'; Guo et al. (2018) J. Educational Measurement",
        "status": "secondary",
        "note": "The p99-over-median range is ours (wide): the sources say leptokurtic and mixture of lognormals, not a ratio.",
    },
    "dwell_weibull_negative_aging": {
        "what": "page dwell times are Weibull with shape below 1 (the hazard of leaving falls with time on page)",
        "range": (0.3, 1.0), "unit": "Weibull shape",
        "source": "Liu, White & Dumais (2010) SIGIR, 'Understanding web browsing behaviors through Weibull analysis of dwell time'",
        "status": "secondary", "note": "A commentary says 99 percent of pages show negative aging; that figure was not checked against the paper.",
    },
    "burstiness_cv": {
        "what": "inter-event times of human activity are bursty (coefficient of variation above 1, not Poisson)",
        "range": (1.1, 20.0), "unit": "CV of event inter-arrival times",
        "source": "Barabasi (2005) Nature 435:207 (heavy tails); Stouffer, Malmgren & Amaral (2005) arXiv physics/0510216, who argue a lognormal fits better than a power law",
        "status": "secondary",
        "note": "The family of the heavy tail is disputed, which is why the generators randomise between lognormal and Lomax tails. The CV range is ours.",
    },
    "interruptions_per_hour": {
        "what": "interruptions or task switches per hour of knowledge work",
        "range": (0.5, 6.0),
        "source": "Gonzalez & Mark (2004) CHI 'Constant, constant, multi-tasking craziness' (about 11 minutes per working sphere, via a magazine summary); Mark, Gonzalez & Harris (2005) CHI",
        "status": "secondary",
        "note": "Quoted second hand (magazine summary of the studies). A 3-minute figure that some write-ups quote could not be found and is not used.",
    },
    "interruption_recovery_min": {
        "what": "time to get back to the original task after an interruption, minutes (heavy tail)",
        "range": (0.25, 30.0),
        "source": "Mark, Gonzalez & Harris (2005); Altmann & Trafton (2002) Cognitive Science 26(1) for resumption lag growing with interruption length and demand; Mark, Gudith & Klocke (2008) CHI: people work faster after interruptions at a cost in stress",
        "status": "secondary",
        "note": "A figure of about 25 minutes to return to the original task is quoted in a magazine summary; the range is wide on purpose.",
    },
    "fatigue_slowdown_per_hour": {
        "what": "slowdown per hour of continuous work (time-on-task decrement)",
        "range": (0.0, 0.15),
        "source": "Mackworth (1948) vigilance decrement (qualitative: detection falls over the first 30 minutes then more slowly)",
        "status": "qualitative",
        "note": "The effect is cited for detection accuracy, not speed. The range for a speed multiplier is our assumption.",
    },
    "circadian_amplitude": {
        "what": "time-of-day amplitude of the speed multiplier",
        "range": (0.0, 0.10),
        "source": "none verified in this session (circadian and post-lunch dip literature was not found)",
        "status": "assumption", "note": "UNVERIFIED: wide assumption.",
    },
    "slip_rate_per_step": {
        "what": "probability of an uncorrected-or-corrected slip per productive step",
        "range": (0.005, 0.07),
        "source": "a systematic review of clinical data entry reports single-entry error rates of 0.04 to 6.5 percent depending on field complexity (seen as a snippet only); vendor blogs quote 1 to 4 percent of fields and are not relied on",
        "status": "secondary", "note": "Low confidence: unit (field versus keystroke) differs across sources.",
    },
    "typing_population": {
        "what": "typists form several distinct groups; faster typists make fewer errors",
        "range": None,
        "source": "Dhakal, Feit, Kristensson & Oulasvirta (2018) CHI, 168,000 volunteers, 136 million keystrokes: eight typist clusters; faster typists make fewer errors",
        "status": "qualitative",
        "note": "Used for the sign of the speed-error correlation across people (negative). No numbers verified: the mean inter-key interval and error rates could not be read from the pages opened.",
    },
    "practice_forgetting": {
        "what": "between-session forgetting and warm-up decrement",
        "range": (0.0, 0.30), "unit": "relative slowdown of the first minutes of a session",
        "source": "none verified", "status": "assumption", "note": "UNVERIFIED: wide assumption.",
    },
}


def status_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for v in CITED.values():
        out[v["status"]] = out.get(v["status"], 0) + 1
    return out
