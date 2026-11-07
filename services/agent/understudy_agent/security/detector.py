"""Layer 6: injection detector (SEC-6).

Scans text a page, screenshot (OCR), hidden element or image alt text hands us for content aimed at an AI: override
instructions, fake system banners, tool-call syntax, hidden-character smuggling, exfiltration links and orders not to
tell the user. A hit PAUSES the run, is logged and lowers the autonomy rung. A hit is never a reason to act.

Pure code with no model call, so it works offline and cannot itself be talked around. Ordinary form wording ("You must
enter your postcode", "Please click Calculate") is NOT a hit in visible text: false pauses are measured (SEC-12).
In hidden elements, alt text and OCR, an imperative addressed to "you" is far more suspicious and is scored higher.
"""
from __future__ import annotations

import base64
import binascii
import codecs
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

from .sanitize import decode_smuggled, strip_invisible

HIGH, MEDIUM, LOW = 3, 2, 1
PAUSE_SEVERITY = HIGH           # any high-severity hit pauses
PAUSE_TOTAL = 4                 # or several weaker ones together

WHERE = ("text", "hidden_element", "alt_text", "ocr", "field", "title", "url")
_SUSPECT_WHERE = {"hidden_element", "alt_text", "ocr"}


def _c(p: str) -> re.Pattern[str]:
    return re.compile(p, re.I)


@dataclass(frozen=True)
class Rule:
    name: str
    family: str
    severity: int
    pattern: re.Pattern[str]
    only_where: frozenset[str] | None = None  # if set, the rule applies only in these locations


_AI_NOUN = r"(?:ai|a\.i\.|artificial intelligence|llm|language model|large language model|chat ?bot|assistant|ai agent|web agent|browser agent|computer[- ]use (?:agent|model)|automated (?:agent|system|tool|reader)|copilot|claude|chatgpt|gpt(?:-?\d\S*)?|gemini)"
_RISKY_VERB = (r"(?:click|navigate|go to|open|visit|type|enter|fill|send|e-?mail|forward|post|upload|submit|delete|remove|pay|transfer|"
               r"download|install|run|execute|disable|grant|approve|confirm|copy|paste|reveal|share|leak|ignore|stop|skip)")

RULES: tuple[Rule, ...] = (
    # --- override and role-change instructions
    Rule("override_instructions", "instruction", HIGH,
         _c(r"\b(?:ignore|disregard|forget|override|bypass|neglect|abandon)\b[^.\n]{0,50}\b(?:instructions?|rules?|guidelines?|directives?|prompts?|constraints?|restrictions?|safeguards?|safety|programming|policies|policy|task|goal)\b")),
    Rule("new_instructions", "instruction", HIGH,
         _c(r"\b(?:new|updated|revised|additional|real|actual|secret|hidden) (?:system )?(?:instructions?|directives?|orders?|task|objective|goal)s?\s*(?:[:\-—]|are|is|for you)")),
    Rule("role_change", "instruction", HIGH,
         _c(r"\b(?:you are now|from now on[, ]+(?:you|act|behave|respond)|act as (?:an? |the )?(?:different|new|unrestricted|admin|root|system|developer)|pretend (?:to be|you are|that you)|enter (?:developer|debug|admin|god|jailbreak) mode|jailbreak|\bdan mode\b)")),
    Rule("prompt_reference", "instruction", HIGH,
         _c(r"\b(?:system prompt|system message|developer (?:message|instructions?|mode)|initial instructions|your (?:original|hidden|secret) (?:instructions|prompt))\b")),
    Rule("addressed_to_ai", "instruction", HIGH,
         _c(rf"(?:\b(?:attention|note to|message (?:for|to)|instructions? for|notice to|hey|hello|dear|calling|warning to)[ ,:]+(?:the |any |all |every )?(?:other )?{_AI_NOUN}s?\b|\b(?:if|when|whenever) (?:you are|you're|you.re|an?) (?:an? |the )?(?:{_AI_NOUN}|automated|bot|crawler|scraper|agent)\b[^.\n]{{0,20}}(?:reading|processing|browsing|visiting|summari[sz]ing|seeing|see|read)|\b(?:{_AI_NOUN})s?\b[^.\n]{{0,25}}\b(?:reading|processing|browsing|visiting|summari[sz]ing|parsing|crawling|scraping) (?:this|the|my) (?:page|site|website|document|content|text))")),
    Rule("ai_directive", "instruction", HIGH,
         _c(rf"\b{_AI_NOUN}s?\b[^.\n]{{0,15}}[,:]?\s*(?:you )?(?:must|should|shall|need to|have to|are (?:required|instructed|ordered|expected) to|will now|now)\s+(?:immediately |first |now |also |always |never )?{_RISKY_VERB}\b")),
    Rule("as_an_ai", "instruction", MEDIUM,
         _c(r"\bas an? (?:ai|llm|language model|assistant|automated agent)\b[^.\n]{0,40}\b(?:you|your)\b")),
    # --- fake system banners and chat-template tokens
    Rule("template_tokens", "fake_system", HIGH,
         _c(r"(?:<\|(?:im_start|im_end|system|assistant|user|endoftext|eot_id|start_header_id)\|>|<<\s*sys\s*>>|\[/?inst\]|<\s*/?\s*(?:system|assistant|developer|instructions?)\s*>|\[\s*(?:system|assistant|developer)\s*\]|\{\{\s*(?:system|assistant)\b)")),
    Rule("system_banner", "fake_system", MEDIUM,
         _c(r"(?:^|\n)\s*[\[\(<*#>\-\s]*(?:system|admin(?:istrator)?|developer|root|operator|openai|anthropic|security)\s+(?:message|notice|alert|override|instruction|prompt|update|directive|command)s?\s*[\]\)>*:\-—]")),
    Rule("system_role_line", "fake_system", HIGH,
         _c(r"(?:^|\n)\s*[\[\(<*#>\-\s]*(?:system|assistant|developer)\s*[:\]\)>]\s*(?:you|ignore|disregard|new|from now|the user|do not|never|always|override)")),
    Rule("markdown_system_header", "fake_system", HIGH,
         _c(r"(?:^|\n)\s*#{1,4}\s*(?:system|instruction|assistant|new instructions?)\b[^\n]{0,30}\n")),
    # --- tool-call mimicry
    Rule("tool_call_syntax", "tool_call", HIGH,
         _c(r"(?:<\s*/?\s*(?:tool_call|tool_use|function_calls?|invoke|antml:\w+|computer_call|action)\b|\"(?:tool_calls?|function_call|computer_call|tool_use)\"\s*:|\"name\"\s*:\s*\"[\w.\-]+\"\s*,\s*\"(?:arguments|parameters|input)\"\s*:|\bto=functions\.\w+|\bfunctions\.\w+\s*\(|\bcall_tool\s*\(|\[\s*tool_call\s*\]|```\s*(?:tool|function|action|json\s*\n\s*\{\s*\"(?:action|tool))|\"type\"\s*:\s*\"(?:click|type|keypress|navigate|goto|computer_call)\"\s*,\s*\"(?:x|text|url|keys)\")")),
    Rule("action_call_text", "tool_call", MEDIUM,
         _c(r"\b(?:click|goto|navigate|type_text|send_email|http_post|open_url|exec|eval)\s*\(\s*[\"'][^\"')]{1,80}[\"']")),
    # --- exfiltration
    Rule("markdown_image_exfil", "exfiltration", HIGH,
         _c(r"!\[[^\]]{0,200}\]\(\s*<?https?://[^)\s>]*\?[^)\s>]+")),
    Rule("html_image_exfil", "exfiltration", HIGH,
         _c(r"<\s*(?:img|iframe|script|link|source)\b[^>]{0,200}(?:src|href)\s*=\s*[\"']?https?://[^\"'>\s]*\?[^\"'>\s]+")),
    Rule("send_data_to", "exfiltration", HIGH,
         _c(r"\b(?:send|e-?mail|forward|post|upload|transmit|submit|exfiltrate|leak|share|copy|paste|type|enter|put)\b[^.\n]{0,70}\b(?:to|at|into|on|via)\b[^.\n]{0,25}(?:https?://|www\.|[\w.+\-]+@[\w\-]+\.[\w.\-]+)")),
    Rule("reveal_secrets", "exfiltration", HIGH,
         _c(r"\b(?:reveal|print|output|repeat|leak|show|tell me|disclose|dump|display|read out)\b[^.\n]{0,30}\b(?:your|the|all) (?:system prompt|instructions|api keys?|secrets?|passwords?|credentials|memory|conversation|context|cookies|tokens?)\b")),
    Rule("command_download", "exfiltration", HIGH,
         _c(r"\b(?:curl|wget|powershell|invoke-webrequest)\b[^\n]{0,80}https?://|\|\s*(?:sh|bash|zsh)\b")),
    # --- concealment and pressure
    Rule("conceal_from_user", "concealment", HIGH,
         _c(r"\b(?:do not|don'?t|never|without)\b[^.\n]{0,25}\b(?:tell|tell(?:ing)?|inform(?:ing)?|alert(?:ing)?|notify(?:ing)?|mention(?:ing)?|reveal(?:ing)?|show(?:ing)?|ask(?:ing)?)\b[^.\n]{0,20}\b(?:the )?(?:user|human|operator|owner|person|worker|supervisor)\b")),
    Rule("secretly", "concealment", HIGH,
         _c(rf"\b(?:silently|secretly|quietly|covertly|stealthily|in the background without)\b[^.\n]{{0,30}}\b{_RISKY_VERB}\b")),
    Rule("urgent_now", "pressure", MEDIUM,
         _c(rf"\b(?:immediately|right now|at once|without delay)\b[^.\n]{{0,45}}\b{_RISKY_VERB}\b")),
    Rule("urgent_before_anything", "pressure", MEDIUM,
         _c(r"\b(?:before (?:doing|you do) anything else|before anything else|your (?:first|new|real) (?:task|job|priority) is)\b")),
    # --- imperatives aimed at 'you' are only suspicious where a person would not normally see them
    Rule("hidden_imperative", "instruction", HIGH,
         _c(rf"\b(?:you (?:must|should|need to|have to|are required to|will)|please|make sure (?:to|you)|be sure to|instead,?|do not|don't|now)\b[^.\n]{{0,60}}\b{_RISKY_VERB}\b"),
         frozenset(_SUSPECT_WHERE)),
    Rule("visible_imperative_risky", "instruction", LOW,
         _c(r"\b(?:you (?:must|should|need to|have to)|please)\b[^.\n]{0,40}\b(?:send|e-?mail|forward|upload|delete|pay|transfer|install|execute|disable|grant)\b")),
)

# ASCII-art / long base64 / reversed / rot13 payloads that decode to something above
_B64 = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")
_STRONG_FAMILIES_FOR_DECODED = {"instruction", "fake_system", "tool_call", "exfiltration", "concealment"}


def normalise_for_scan(text: str) -> tuple[str, int]:
    """NFKC fold, drop invisible characters (counting them), collapse whitespace runs, keep case for readability."""
    text = unicodedata.normalize("NFKC", text)
    text, removed = strip_invisible(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return text, removed


@dataclass(frozen=True)
class Hit:
    rule: str
    family: str
    severity: int
    where: str
    excerpt: str          # short, sanitised, bracket-neutralised: for the human reviewing the pause, never for a prompt
    excerpt_hash: str     # what the audit log keeps


@dataclass(frozen=True)
class DetectionReport:
    hits: tuple[Hit, ...] = ()
    score: int = 0
    paused: bool = False
    families: frozenset[str] = frozenset()

    @property
    def clean(self) -> bool:
        return not self.hits

    @property
    def lower_rung(self) -> bool:
        """A pause lowers the autonomy rung by one (never raises)."""
        return self.paused

    def summary_code(self) -> str:
        """A short code safe for the audit log (rule names and locations only; no page text)."""
        return ",".join(sorted({f"{h.rule}@{h.where}" for h in self.hits}))[:200]


@dataclass
class PageObservation:
    """What the extension / OCR hands us for one page or screen."""
    text: str = ""                                   # visible text
    hidden_texts: list[str] = field(default_factory=list)   # text in display:none, off-screen, tiny or camouflaged elements
    alt_texts: list[str] = field(default_factory=list)      # alt, title, aria-label of images and controls
    ocr_text: str = ""                               # OCR of the screenshot
    title: str = ""
    url: str = ""

    def visible_text(self) -> str:
        """What a person looking at the screen can read: title, page text and OCR of the screenshot."""
        return "\n".join(x for x in [self.title, self.text, self.ocr_text] if x)

    def full_dump(self) -> str:
        """What a naive text dump of the DOM returns: visible text plus hidden elements and alt text."""
        return "\n".join(x for x in [self.title, self.text, *self.hidden_texts, *self.alt_texts, self.ocr_text] if x)


def _excerpt(text: str, m: re.Match[str]) -> str:
    start = max(0, m.start() - 10)
    raw = text[start:m.end() + 20]
    raw = " ".join(raw.split())[:80]
    return raw.translate(str.maketrans({"<": "‹", ">": "›", "[": "⟦", "]": "⟧", "`": "ˋ"}))


def _h(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:12]


class InjectionDetector:
    def __init__(self, *, enabled: bool = True, rules: Iterable[Rule] = RULES) -> None:
        self.enabled = enabled
        self.rules = tuple(rules)

    # ---------------------------------------------------------------- scanning
    def scan(self, text: str, where: str = "text") -> list[Hit]:
        if not self.enabled or not text:
            return []
        smuggled = decode_smuggled(text)
        norm, removed = normalise_for_scan(text)
        hits: list[Hit] = []
        if smuggled:
            hits.append(Hit("unicode_tag_smuggling", "smuggling", HIGH, where, _safe(smuggled), _h(smuggled)))
        if removed >= 5:
            hits.append(Hit("many_invisible_chars", "smuggling", MEDIUM, where, f"{removed} invisible characters", _h(f"inv{removed}")))
        hits.extend(self._apply_rules(norm, where))
        hits.extend(self._decoded_variants(norm, where))
        if smuggled:
            hits.extend(self._apply_rules(smuggled, where, prefix="smuggled:"))
        return _dedupe(hits)

    def _apply_rules(self, text: str, where: str, prefix: str = "") -> list[Hit]:
        out = []
        for r in self.rules:
            if r.only_where is not None and where not in r.only_where:
                continue
            m = r.pattern.search(text)
            if m:
                out.append(Hit(prefix + r.name, r.family, r.severity, where, _excerpt(text, m), _h(m.group(0).lower())))
        return out

    def _decoded_variants(self, text: str, where: str) -> list[Hit]:
        hits: list[Hit] = []
        # base64 blobs that decode to instruction-like text
        for blob in _B64.findall(text)[:5]:
            try:
                dec = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False).decode("utf-8", "ignore")
            except (binascii.Error, ValueError):
                continue
            if len(dec) >= 12 and sum(c.isprintable() for c in dec) / len(dec) > 0.9:
                for h in self._apply_rules(dec, where, prefix="base64:"):
                    if h.family in _STRONG_FAMILIES_FOR_DECODED:
                        hits.append(h)
        # reversed and rot13 text (cheap obfuscations). Only strong families count.
        for label, variant in (("reversed:", text[::-1]), ("rot13:", codecs.decode(text, "rot13"))):
            for h in self._apply_rules(variant, where, prefix=label):
                if h.family in ("instruction", "fake_system", "tool_call") and h.severity >= HIGH and h.rule.split(":", 1)[-1] in _DECODE_RULES:
                    hits.append(h)
        return hits

    def scan_page(self, page: PageObservation) -> DetectionReport:
        """Scan visible text, title, alt text and OCR as such, and hidden elements with their stricter rules."""
        hits: list[Hit] = []
        hits += self.scan(page.title, "title")
        hits += self.scan(page.text, "text")
        for t in page.alt_texts:
            hits += self.scan(t, "alt_text")
        hits += self.scan(page.ocr_text, "ocr")
        for t in page.hidden_texts:
            hits += self.scan(t, "hidden_element")
        if page.url:
            hits += self.scan(page.url.replace("%20", " "), "url")
        return self.report(hits)

    def scan_fields(self, fields: dict[str, object]) -> DetectionReport:
        """Scan reader output: any string field that looks like an instruction is a hit."""
        hits: list[Hit] = []
        for v in _iter_strings(fields):
            hits += self.scan(v, "field")
        return self.report(hits)

    # ---------------------------------------------------------------- scoring
    @staticmethod
    def report(hits: list[Hit]) -> DetectionReport:
        hits = _dedupe(hits)
        score = sum(h.severity for h in hits)
        paused = any(h.severity >= PAUSE_SEVERITY for h in hits) or score >= PAUSE_TOTAL
        return DetectionReport(hits=tuple(hits), score=score, paused=paused, families=frozenset(h.family for h in hits))


_DECODE_RULES = {"override_instructions", "new_instructions", "role_change", "prompt_reference", "template_tokens",
                 "tool_call_syntax", "system_role_line"}


def _safe(s: str) -> str:
    return " ".join(s.split())[:80].translate(str.maketrans({"<": "‹", ">": "›", "[": "⟦", "]": "⟧"}))


def _dedupe(hits: list[Hit]) -> list[Hit]:
    seen, out = set(), []
    for h in hits:
        k = (h.rule, h.where, h.excerpt_hash)
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out


def _iter_strings(obj: object) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v)
