// knack-wake: the "Hey Knack" listener. A small command-line program that Knack's Electron main process starts as a child, so the macOS
// Microphone and Speech Recognition prompts belong to Knack. It listens to the default microphone and recognises speech ON THIS MAC ONLY.
//
// What it prints, and nothing else, one JSON object per line on stdout (closed fields):
//   {"event":"ready"}                       recognition is armed
//   {"event":"heard"}                       the wake phrase matched (Matcher.swift)
//   {"event":"error","code":"<code>"}       a closed reason code (see WakeError); then the program exits
// It NEVER prints, stores or logs what it heard, and never writes a file. The words of an utterance live in one variable in memory, are matched,
// and are dropped at the end of the utterance. Audio is held only as a short in-memory pre-roll (about half a second) and in the recogniser's own
// buffer; nothing is sent to any server: `requiresOnDeviceRecognition` is true, and if on-device recognition is not available for the locale this
// program exits with `on_device_unavailable` and never falls back to the network.
//
// Exit status: 0 stopped on request (SIGTERM, SIGINT, or the parent closed our stdin); 3 a final condition Knack must show to the worker (a
// permission refused, no on-device recogniser); 4 a transient failure (Knack may start us again after a pause).
//
// Written for Knack. Not run by the build agent: it needs the Microphone and Speech Recognition permissions only the owner can grant.
import AVFoundation
import Foundation
import Speech

setvbuf(stdout, nil, _IOLBF, 0)

enum WakeError: String {
    case micDenied = "mic_denied"
    case micRestricted = "mic_restricted"
    case speechDenied = "speech_denied"
    case speechRestricted = "speech_restricted"
    case onDeviceUnavailable = "on_device_unavailable"
    case localeUnsupported = "locale_unsupported"
    case recognizerUnavailable = "recognizer_unavailable"
    case audioEngineFailed = "audio_engine_failed"
    case noInputDevice = "no_input_device"
    case internalError = "internal"
}

func emit(_ event: String, code: String? = nil) {
    var s = "{\"event\":\"\(event)\""
    if let c = code { s += ",\"code\":\"\(c)\"" }
    s += "}\n"
    FileHandle.standardOutput.write(Data(s.utf8))
}

func fail(_ code: WakeError, exitCode: Int32) -> Never {
    emit("error", code: code.rawValue)
    exit(exitCode)
}

// ------------------------------------------------------------------------------------------------ arguments
// --locale <id> (default: the order below). The identifier is checked before it is used.
func argumentLocale() -> String? {
    let args = CommandLine.arguments
    guard let i = args.firstIndex(of: "--locale"), i + 1 < args.count else { return nil }
    let v = args[i + 1]
    let ok = v.range(of: "^[A-Za-z]{2,3}([-_][A-Za-z0-9]{2,8}){0,2}$", options: .regularExpression) != nil
    return ok ? v : nil
}

// ------------------------------------------------------------------------------------------------ permissions (asked here, at first use)
final class Box<T>: @unchecked Sendable {
    var value: T
    init(_ v: T) { value = v }
}

func ensureMicrophone() {
    switch AVCaptureDevice.authorizationStatus(for: .audio) {
    case .authorized:
        return
    case .notDetermined:
        let sem = DispatchSemaphore(value: 0)
        let granted = Box(false)
        AVCaptureDevice.requestAccess(for: .audio) { ok in
            granted.value = ok
            sem.signal()
        }
        sem.wait()
        if !granted.value { fail(.micDenied, exitCode: 3) }
    case .restricted:
        fail(.micRestricted, exitCode: 3)
    default:
        fail(.micDenied, exitCode: 3)
    }
}

func ensureSpeech() {
    switch SFSpeechRecognizer.authorizationStatus() {
    case .authorized:
        return
    case .notDetermined:
        let sem = DispatchSemaphore(value: 0)
        let status = Box(SFSpeechRecognizerAuthorizationStatus.notDetermined)
        SFSpeechRecognizer.requestAuthorization { s in
            status.value = s
            sem.signal()
        }
        sem.wait()
        switch status.value {
        case .authorized: return
        case .restricted: fail(.speechRestricted, exitCode: 3)
        default: fail(.speechDenied, exitCode: 3)
        }
    case .restricted:
        fail(.speechRestricted, exitCode: 3)
    default:
        fail(.speechDenied, exitCode: 3)
    }
}

/// The first locale with an on-device recogniser. FAIL CLOSED: a recogniser that exists but cannot run on this Mac is never used.
func pickRecognizer() -> SFSpeechRecognizer {
    var candidates: [String] = []
    if let l = argumentLocale() { candidates.append(l) }
    if let env = ProcessInfo.processInfo.environment["KNACK_WAKE_LOCALE"], !env.isEmpty { candidates.append(env) }
    candidates.append(contentsOf: ["en-GB", "en-US"])
    var existed = false
    for id in candidates {
        guard let r = SFSpeechRecognizer(locale: Locale(identifier: id)) else { continue }
        existed = true
        if r.isAvailable && r.supportsOnDeviceRecognition { return r }
    }
    fail(existed ? .onDeviceUnavailable : .localeUnsupported, exitCode: 3)
}

// ------------------------------------------------------------------------------------------------ the listener
func rms(_ b: AVAudioPCMBuffer) -> Float {
    guard let ch = b.floatChannelData?[0], b.frameLength > 0 else { return 0 }
    var sum: Float = 0
    let n = Int(b.frameLength)
    for i in 0..<n { sum += ch[i] * ch[i] }
    return (sum / Float(n)).squareRoot()
}

func copy(_ b: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
    guard let c = AVAudioPCMBuffer(pcmFormat: b.format, frameCapacity: b.frameLength), let src = b.floatChannelData, let dst = c.floatChannelData else { return nil }
    c.frameLength = b.frameLength
    for ch in 0..<Int(b.format.channelCount) { memcpy(dst[ch], src[ch], Int(b.frameLength) * MemoryLayout<Float>.size) }
    return c
}

final class Listener: @unchecked Sendable {
    // All state below is touched only on `queue`.
    private let queue = DispatchQueue(label: "app.knack.wake.audio")
    private let engine = AVAudioEngine()
    private let recognizer: SFSpeechRecognizer
    private let gate = WakeGate()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var generation = 0
    private var taskStartedAt = Date.distantPast
    private var lastVoiceAt = Date.distantPast
    private var endedAt: Date?
    private var preroll: [AVAudioPCMBuffer] = []
    private var latest = "" // the current utterance's words: memory only, never printed, dropped at every reset
    private var settleItem: DispatchWorkItem?
    private var noiseFloor: Float = 0.002
    private var errorRun = 0
    private var errorRunStart = Date.distantPast

    // Tuning: all in seconds or RMS units, none of them reachable from outside.
    private let hangover: TimeInterval = 1.0 // quiet this long ends an utterance
    private let maxTaskAge: TimeInterval = 45 // restart well before any system limit on one recognition task
    private let settleWait: TimeInterval = 0.45 // a close or weak spelling at the end waits this long for more words
    private let finalWait: TimeInterval = 2.0 // after endAudio, how long to wait for the final result before cancelling
    private let prerollMax = 6

    init(recognizer: SFSpeechRecognizer) {
        self.recognizer = recognizer
    }

    func start() {
        queue.async { self.startEngine(first: true) }
    }

    func stop() {
        queue.sync {
            self.settleItem?.cancel()
            self.task?.cancel()
            self.request?.endAudio()
            self.engine.inputNode.removeTap(onBus: 0)
            self.engine.stop()
        }
    }

    // ---- audio engine
    private func startEngine(first: Bool) {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { fail(.noInputDevice, exitCode: 4) }
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, _ in
            guard let self, let c = copy(buffer) else { return }
            self.queue.async { self.onAudio(c) }
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            fail(.audioEngineFailed, exitCode: 4)
        }
        if first {
            NotificationCenter.default.addObserver(forName: .AVAudioEngineConfigurationChange, object: engine, queue: nil) { [weak self] _ in
                self?.queue.async { self?.startEngine(first: false) }
            }
            emit("ready")
        }
    }

    // ---- one buffer of audio
    private func onAudio(_ buf: AVAudioPCMBuffer) {
        let now = Date()
        let level = rms(buf)
        let threshold = max(0.012, noiseFloor * 3)
        let voice = level > threshold
        if !voice { noiseFloor = min(0.02, max(0.0005, noiseFloor * 0.99 + level * 0.01)) }
        if voice { lastVoiceAt = now }
        if let ended = endedAt {
            // The utterance is over; waiting for the recogniser's final result.
            if now.timeIntervalSince(ended) > finalWait { resetTask() }
            return
        }
        guard let req = request else {
            if voice {
                beginUtterance(now: now)
                for p in preroll { request?.append(p) }
                preroll.removeAll()
                request?.append(buf)
            } else {
                preroll.append(buf)
                if preroll.count > prerollMax { preroll.removeFirst() }
            }
            return
        }
        req.append(buf)
        if now.timeIntervalSince(lastVoiceAt) > hangover || now.timeIntervalSince(taskStartedAt) > maxTaskAge { endUtterance(now: now) }
    }

    // ---- an utterance: one recognition request and task
    private func beginUtterance(now: Date) {
        generation += 1
        let gen = generation
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.requiresOnDeviceRecognition = true // FAIL CLOSED: never the server
        req.taskHint = .search
        req.contextualStrings = ["Hey Knack", "Knack"]
        if #available(macOS 13.0, *) { req.addsPunctuation = true }
        request = req
        endedAt = nil
        latest = ""
        taskStartedAt = now
        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            // Copy only what is needed out of the callback: the words and the final flag.
            let text = result?.bestTranscription.formattedString
            let isFinal = result?.isFinal ?? false
            let failed = error != nil
            self.queue.async { self.onResult(gen: gen, text: text, isFinal: isFinal, failed: failed) }
        }
    }

    private func endUtterance(now: Date) {
        request?.endAudio()
        endedAt = now
        // The text so far is evaluated as settled: the speaker stopped.
        evaluate(settled: true)
    }

    private func resetTask() {
        settleItem?.cancel()
        settleItem = nil
        generation += 1 // late callbacks of the old task are ignored
        task?.cancel()
        task = nil
        request = nil
        endedAt = nil
        latest = ""
        preroll.removeAll()
    }

    private func onResult(gen: Int, text: String?, isFinal: Bool, failed: Bool) {
        guard gen == generation else { return }
        if let t = text {
            errorRun = 0
            latest = t
            if !evaluate(settled: isFinal) && isFinal { resetTask() }
        }
        if failed && text == nil {
            let now = Date()
            if now.timeIntervalSince(errorRunStart) > 20 { errorRun = 0; errorRunStart = now }
            errorRun += 1
            resetTask()
            // A task that fails over and over is a recogniser that cannot run: stop and say so (Knack decides when to try again).
            if errorRun >= 4 { fail(.recognizerUnavailable, exitCode: 4) }
        } else if isFinal {
            resetTask()
        }
    }

    /// Feeds the current words to the matcher. Returns true when it accepted (and reset everything).
    @discardableResult
    private func evaluate(settled: Bool) -> Bool {
        settleItem?.cancel()
        settleItem = nil
        guard !latest.isEmpty else { return false }
        let r = gate.feed(latest, settled: settled, now: ProcessInfo.processInfo.systemUptime)
        if r.accepted {
            emit("heard")
            resetTask()
            return true
        }
        if r.waiting && !settled {
            let item = DispatchWorkItem { [weak self] in self?.evaluate(settled: true) }
            settleItem = item
            queue.asyncAfter(deadline: .now() + settleWait, execute: item)
        }
        return false
    }
}

// ------------------------------------------------------------------------------------------------ main
ensureMicrophone()
ensureSpeech()
let listener = Listener(recognizer: pickRecognizer())
listener.start()

// Stop on request: the microphone is released when this process ends.
let stopSignals = [SIGTERM, SIGINT].map { sig -> DispatchSourceSignal in
    signal(sig, SIG_IGN)
    let s = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    s.setEventHandler {
        listener.stop()
        exit(0)
    }
    s.resume()
    return s
}
_ = stopSignals

// The parent going away closes our stdin: leave at once rather than listen to a room nobody is managing.
DispatchQueue.global().async {
    while FileHandle.standardInput.availableData.count > 0 {}
    listener.stop()
    exit(0)
}

dispatchMain()
