// The wake phrase matcher, in Swift: a line-for-line port of apps/desktop/src/main/wake/matching.ts (that file is the specification and carries the
// rule's description). It is PURE: text in, a verdict out, no audio, no files, no printing. It lives in the helper, not in Electron, because the
// words the recogniser heard must never leave the helper: the helper prints `heard` and nothing else.
//
// scripts/wake-parity.sh compiles this file with a tiny stdin harness (no audio code) and checks it agrees with the TypeScript on the whole corpus.
// Change one file and you must change the other; the parity check fails otherwise.
import Foundation

enum WakeVerdict: String { case accept, wait, reject }
enum WakeVariant: String { case exact, close, weak }
struct WakeMatch {
    var verdict: WakeVerdict
    var variant: WakeVariant?
}

struct WakeToken {
    var word: String
    var boundaryBefore: Bool
    var sentenceBefore: Bool
}

enum WakeLists {
    static let greetings: Set<String> = ["hey", "hay", "heya", "heyy"]
    static let leadIns: Set<String> = ["oh", "ok", "okay", "so", "um", "uh", "well", "right", "alright", "and", "but", "now", "hmm", "er", "yeah", "yes", "hi", "hello"]
    static let namesExact: Set<String> = ["knack"]
    static let namesClose: Set<String> = ["nack", "nac", "knak"]
    static let namesWeak: Set<String> = ["knock", "nock"]
    static let fit: Set<String> = [
        "can", "could", "would", "will", "please", "show", "point", "help", "what", "whats", "what's", "where", "wheres", "where's", "how", "hows", "how's",
        "why", "who", "which", "when", "tell", "find", "guide", "walk", "explain", "take", "look", "let's", "lets", "i", "i'm", "im", "i've", "ive", "i'd", "id",
        "my", "me", "do", "does", "did", "is", "are", "you", "ok", "okay", "thanks", "thank", "hello", "hi", "listen", "stop", "wait", "start", "open", "click",
        "go", "give", "need", "want", "so", "um", "uh",
    ]
    static let strictFit: Set<String> = [
        "can", "could", "would", "will", "please", "show", "point", "help", "what", "whats", "what's", "where", "wheres", "where's", "how", "hows", "how's",
        "why", "which", "tell", "find", "guide", "walk", "explain", "i", "i'm", "im", "i've", "ive", "i'd", "id", "let's", "lets", "ok", "okay", "thanks",
    ]
    static let blockNext: Set<String> = [
        "for", "of", "at", "on", "off", "out", "down", "up", "over", "the", "a", "an", "that", "this", "these", "those", "it", "him", "her", "them", "us", "back",
        "around", "before", "after", "twice", "once", "three", "times", "knock", "nack", "knack", "nock",
    ]
    static let sentenceMarks: Set<Unicode.Scalar> = [".", "?", "!", ";"]
    static let boundaryMarks: Set<Unicode.Scalar> = [".", "?", "!", ";", ","]
}

private func isWordScalar(_ c: Unicode.Scalar) -> Bool {
    return (c.value >= 97 && c.value <= 122) || (c.value >= 48 && c.value <= 57) || c == "'"
}

/// Lower case, straight apostrophes, tokens with their boundary flags. Total: any string tokenises.
func wakeTokenize(_ raw: String) -> [WakeToken] {
    var tokens: [WakeToken] = []
    var cur = String.UnicodeScalarView()
    var boundary = true
    var sentence = true
    func flush() {
        var scalars = Array(cur)
        while let f = scalars.first, f == "'" { scalars.removeFirst() }
        while let l = scalars.last, l == "'" { scalars.removeLast() }
        if !scalars.isEmpty {
            var s = String.UnicodeScalarView()
            s.append(contentsOf: scalars)
            tokens.append(WakeToken(word: String(s), boundaryBefore: tokens.isEmpty ? true : boundary, sentenceBefore: tokens.isEmpty ? true : sentence))
            boundary = false
            sentence = false
        }
        cur = String.UnicodeScalarView()
    }
    for var c in raw.lowercased().unicodeScalars {
        if c == "\u{2018}" || c == "\u{2019}" || c == "\u{02bc}" || c == "\u{0060}" { c = "'" }
        if isWordScalar(c) {
            cur.append(c)
        } else {
            flush()
            if WakeLists.boundaryMarks.contains(c) || c == "\n" { boundary = true }
            if WakeLists.sentenceMarks.contains(c) || c == "\n" { sentence = true }
        }
    }
    flush()
    return tokens
}

/// The verdict for one utterance's text. `settled` says no more words are expected.
func wakeMatch(_ text: String, settled: Bool) -> WakeMatch {
    let t = wakeTokenize(text)
    var waiting: WakeMatch?
    var i = 0
    while i + 1 < t.count {
        defer { i += 1 }
        if !WakeLists.greetings.contains(t[i].word) { continue }
        var startsUtterance = t[i].sentenceBefore
        if !startsUtterance {
            startsUtterance = true
            for x in t[0..<i] where !WakeLists.leadIns.contains(x.word) {
                startsUtterance = false
                break
            }
        }
        if !startsUtterance { continue }
        let name = t[i + 1].word
        let variant: WakeVariant?
        if WakeLists.namesExact.contains(name) { variant = .exact } else if WakeLists.namesClose.contains(name) { variant = .close } else if WakeLists.namesWeak.contains(name) { variant = .weak } else { variant = nil }
        guard let v = variant else { continue }
        let next: WakeToken? = i + 2 < t.count ? t[i + 2] : nil
        switch v {
        case .exact:
            if let n = next, !n.boundaryBefore, WakeLists.blockNext.contains(n.word) { continue }
            return WakeMatch(verdict: .accept, variant: v)
        case .close:
            guard let n = next else {
                if settled { return WakeMatch(verdict: .accept, variant: v) }
                if waiting == nil { waiting = WakeMatch(verdict: .wait, variant: v) }
                continue
            }
            if n.boundaryBefore || WakeLists.fit.contains(n.word) { return WakeMatch(verdict: .accept, variant: v) }
            continue
        case .weak:
            guard let n = next else {
                if !settled, waiting == nil { waiting = WakeMatch(verdict: .wait, variant: v) }
                continue
            }
            if WakeLists.strictFit.contains(n.word) { return WakeMatch(verdict: .accept, variant: v) }
            continue
        }
    }
    return waiting ?? WakeMatch(verdict: .reject, variant: nil)
}

/// One accept per cooldown window. `now` is seconds from any monotonic clock.
final class WakeGate {
    private let cooldown: TimeInterval
    private var lastAt: TimeInterval = -.infinity
    init(cooldown: TimeInterval = 8.0) { self.cooldown = max(0, cooldown) }
    func feed(_ text: String, settled: Bool, now: TimeInterval) -> (accepted: Bool, waiting: Bool) {
        let m = wakeMatch(text, settled: settled)
        switch m.verdict {
        case .reject: return (false, false)
        case .wait: return (false, true)
        case .accept:
            if now - lastAt < cooldown { return (false, false) }
            lastAt = now
            return (true, false)
        }
    }
    func reset() { lastAt = -.infinity }
}
