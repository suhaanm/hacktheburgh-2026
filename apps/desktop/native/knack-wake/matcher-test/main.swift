// A test harness for Matcher.swift and NOTHING ELSE: it imports no audio or speech framework and opens no device. It reads lines from stdin, each
// "S<TAB>text" (settled) or "P<TAB>text" (a partial result), and prints "accept:exact", "wait:close", "reject" and so on, one per line.
// Used by scripts/wake-parity.sh to check the Swift matcher against the TypeScript one over the corpus (offline strings).
import Foundation

while let line = readLine(strippingNewline: true) {
    guard let tab = line.firstIndex(of: "\t") else {
        print("error")
        continue
    }
    let mode = line[line.startIndex..<tab]
    let text = String(line[line.index(after: tab)...])
    let m = wakeMatch(text, settled: mode == "S")
    print(m.variant.map { "\(m.verdict.rawValue):\($0.rawValue)" } ?? m.verdict.rawValue)
}
