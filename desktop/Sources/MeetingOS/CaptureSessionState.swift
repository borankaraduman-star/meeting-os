import Foundation

/// Where one recording session stands. "The helper started" only means a stream was set up; the recording is
/// receiving only once a real buffer arrived from at least one channel. The phases come from two sides: the app's
/// own events (start asked, process up, stop asked, process gone) and the bridge's capture payload (schema 2:
/// `session`, `session_state`, `channels`). An older helper's payload (schema 1: `state`, `signals`) still maps.
public enum CapturePhase: String, Equatable {
    case idle, preparing
    case awaitingPermission = "awaiting_permission"
    case awaitingStream = "awaiting_stream"
    case receiving, finishing, stopped, failed

    /// The headline of the status line. A permission prompt has no deadline, so its line never sounds like a failure.
    public var headline: String {
        switch self {
        case .idle: return "Hazır"
        case .preparing: return "Kayıt hazırlanıyor"
        case .awaitingPermission: return "İzin bekleniyor · macOS sorarsa ‘İzin Ver’i seçin"
        case .awaitingStream: return "Ses akışı bekleniyor"
        case .receiving: return "Kayıt sürüyor"
        case .finishing: return "Ses parçaları tamamlanıyor…"
        case .stopped: return "Kayıt durduruldu"
        case .failed: return "Kayıt başlatılamadı"
        }
    }
}

/// One channel's own evidence. A silent buffer is data (the mic is muted, the room is quiet); no buffer is not.
public enum CaptureChannelStatus: String, Equatable {
    case awaitingFirstBuffer = "awaiting_first_buffer"
    case silent, signal, stalled, unverified

    public static let staleSeconds: Double = 30

    /// Accepts the schema-2 names, the helper's `channel_flow` words and the schema-1 `signals` words, as a string or
    /// as `{"state":…, "age_seconds":…}`. Anything unrecognised is "could not verify", never a reassuring state.
    public static func parse(_ raw: Any?) -> CaptureChannelStatus {
        let entry = raw as? [String: Any]
        guard let word = (raw as? String) ?? (entry?["state"] as? String) else { return .unverified }
        let status: CaptureChannelStatus
        switch word {
        case "awaiting_first_buffer", "waiting", "awaiting": status = .awaitingFirstBuffer
        case "silent", "digital_silence": status = .silent
        case "signal", "flowing": status = .signal
        case "stalled", "interrupted", "stale": status = .stalled
        default: status = .unverified
        }
        // A reading that stopped refreshing is a stream that stopped, whatever its last word was.
        if status.hasBuffer, let age = entry?["age_seconds"] {
            guard let n = age as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(), n.doubleValue.isFinite, n.doubleValue >= 0 else { return .stalled }
            if n.doubleValue > staleSeconds { return .stalled }
        }
        return status
    }

    public var hasBuffer: Bool { self == .silent || self == .signal }

    public var label: String {
        switch self {
        case .awaitingFirstBuffer: return "İlk ses bekleniyor"
        case .silent: return "Ses geliyor · sessiz"
        case .signal: return "Sinyal var"
        case .stalled: return "Akış kesildi"
        case .unverified: return "Doğrulanamadı"
        }
    }

    /// The floating panel's dot: the existing ok/silent/stale/unknown words plus "waiting" for no first buffer yet.
    public var dot: String {
        switch self {
        case .signal: return "ok"
        case .silent: return "silent"
        case .stalled: return "stale"
        case .awaitingFirstBuffer: return "waiting"
        case .unverified: return "unknown"
        }
    }
}

/// The third stage, kept apart from the first two: text coming back says nothing about audio, and audio arriving
/// says nothing about the transcription service. An unanswered preview must never colour the recording red.
public enum CaptureTextStage: Equatable { case notRequested, waiting, arriving }

public struct CaptureSessionState: Equatable {
    /// A product target, not a measurement: after the stream is set up, five seconds without a single buffer is
    /// worth a line. It is never a timeout — nothing is stopped or restarted because of it.
    public static let firstBufferGrace: TimeInterval = 5
    public static let channelKeys = ["mic", "system"]
    public static let channelNames = ["mic": "Mikrofon", "system": "Sistem"]

    public enum StopAction: Equatable { case none, discard, signal }

    public private(set) var phase: CapturePhase = .idle
    public private(set) var directory: String?
    public private(set) var session: String?
    public private(set) var channels: [String: CaptureChannelStatus] = [:]
    public private(set) var failure: String?
    public private(set) var legacy = false
    public private(set) var streamSince: Date?
    public private(set) var processRunning = false
    public private(set) var text: CaptureTextStage = .notRequested
    public private(set) var seconds = 0

    public init() {}

    // MARK: app events

    /// A fresh session: nothing of the previous one — session id, channels, a pending payload — carries over.
    public mutating func startRequested(directory: String) {
        self = CaptureSessionState()
        phase = .preparing; self.directory = directory
    }

    /// The helper's first step is the permission check, so a launched process waits on that, without a deadline.
    @discardableResult public mutating func processLaunched() -> Bool {
        guard phase == .preparing else { return false }   // stopped while preparing: a late launch is not a recording
        processRunning = true; phase = .awaitingPermission
        return true
    }

    /// `.discard` when there is nothing to stop yet: no process, so no ghost recording and no elapsed time.
    public mutating func stopRequested() -> StopAction {
        switch phase {
        case .preparing:
            self = CaptureSessionState(); phase = .stopped
            return .discard
        case .awaitingPermission, .awaitingStream, .receiving:
            phase = .finishing; return .signal
        case .finishing: return .signal
        case .idle, .stopped, .failed: return .none
        }
    }

    /// A refused launch or an exited helper. A failure the payload already explained keeps its own message.
    public mutating func processExited(succeeded: Bool) {
        processRunning = false
        if phase == .failed { return }
        // Only a helper that died before any audio is a failed start; after a buffer, what reached disk is a recording.
        let neverReceived = !channels.values.contains(where: \.hasBuffer) && phase != .receiving && phase != .finishing
        if phase == .preparing || !succeeded && neverReceived { phase = .failed; failure = failure ?? "Kayıt başlatılamadı · kayıt yardımcısı kapandı" }
        else { phase = .stopped }
    }

    // MARK: bridge payload

    /// Applies one polled capture payload. Returns false — and changes nothing — for a payload that belongs to
    /// another recording folder or another session (a late line from before a sleep, or the previous meeting).
    @discardableResult public mutating func apply(_ capture: [String: Any], directory: String, now: Date = Date()) -> Bool {
        guard processRunning, [.awaitingPermission, .awaitingStream, .receiving, .finishing].contains(phase) else { return false }
        guard directory == self.directory else { return false }
        if let d = capture["directory"] as? String, !d.isEmpty, d != self.directory { return false }
        if let s = capture["session"] as? String, !s.isEmpty {
            if let locked = session, locked != s { return false }
            session = s
        }
        legacy = !CaptureSignalPresentation.isSessionPayload(capture)
        seconds = CaptureSignalPresentation.sanitizedSeconds(capture["seconds"])
        text = Self.textStage(capture["preview"])

        let reported: [String: Any]? = legacy ? capture["signals"] as? [String: Any] : capture["channels"] as? [String: Any]
        if let reported {   // polls without a reading keep the last one
            for key in Self.channelKeys { channels[key] = CaptureChannelStatus.parse(reported[key]) }
        }

        if let denied = Self.deniedPermission(capture) {
            phase = .failed; failure = denied; return true
        }
        let next = legacy ? legacyPhase(capture) : sessionPhase(capture)
        guard let next else { return true }
        // The bridge's own Turkish sentence (capture_metrics.session_view `message`) names the cause when it knows it.
        if next == .failed { phase = .failed; failure = failure ?? (capture["message"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Kayıt başlatılamadı · ses akışı kurulamadı"; return true }
        if phase == .finishing { return true }   // the user asked to stop; the helper's own words cannot reopen it
        phase = next
        if !legacy, streamSince == nil, next == .awaitingStream || next == .receiving {
            let age = (capture["stream_age_seconds"] as? NSNumber).map(\.doubleValue).flatMap { $0.isFinite && $0 >= 0 ? $0 : nil } ?? 0
            streamSince = now.addingTimeInterval(-age)
        }
        return true
    }

    private func sessionPhase(_ capture: [String: Any]) -> CapturePhase? {
        let anyBuffer = channels.values.contains(where: \.hasBuffer)
        switch capture["session_state"] as? String {
        case "awaiting_permission": return .awaitingPermission
        case "awaiting_stream": return anyBuffer ? .receiving : .awaitingStream
        case "receiving": return .receiving
        case "finishing", "stopped": return .finishing   // the process is still alive; only its exit says stopped
        case "failed": return .failed
        default: return anyBuffer ? .receiving : nil
        }
    }

    /// Schema 1 has no permission or first-buffer events: "capturing" with a closed chunk's reading is the only
    /// proof of audio it carries. No five-second warning is derived from it (its chunks close every 12 s).
    private func legacyPhase(_ capture: [String: Any]) -> CapturePhase? {
        switch capture["state"] as? String {
        case "capturing": return channels.values.contains(where: \.hasBuffer) || capture["signals"] == nil ? .receiving : .awaitingStream
        case "error": return .failed
        case "stopped": return .finishing
        default: return nil
        }
    }

    private static func textStage(_ raw: Any?) -> CaptureTextStage {
        guard let preview = raw as? [String: Any], preview["enabled"] as? Bool == true else { return .notRequested }
        if let n = preview["segments"] as? Int, n > 0 { return .arriving }
        return .waiting
    }

    /// A denied permission is the one failure with a step the user can take, so it is named, in Turkish.
    private static func deniedPermission(_ capture: [String: Any]) -> String? {
        guard let permission = capture["permission"] as? [String: Any] else { return nil }
        let names = [("microphone", "Mikrofon"), ("screen_audio", "Ekran ve Sistem Sesi Kaydı")]
            .filter { permission[$0.0] as? String == "denied" }.map(\.1)
        guard !names.isEmpty else { return nil }
        return "Kayıt başlatılamadı · macOS izni verilmedi: Sistem Ayarları › Gizlilik ve Güvenlik’te Meeting OS için \(names.joined(separator: " ve ")) iznini açıp kaydı yeniden başlatın"
    }

    // MARK: presentation

    /// Green only while at least one channel is actually delivering buffers, silent or not.
    public var isReceiving: Bool { phase == .receiving && channels.values.contains(where: \.hasBuffer) }

    public func channelStatus(_ key: String) -> CaptureChannelStatus {
        if let status = channels[key] { return status }
        return !legacy && (phase == .awaitingStream || phase == .receiving) ? .awaitingFirstBuffer : .unverified
    }

    /// One line once the stream has been up five seconds and a channel has still sent nothing. Never while the
    /// permission prompt is open: the user may be reading it.
    public func warning(now: Date = Date()) -> String? {
        guard !legacy, let since = streamSince, phase == .awaitingStream || phase == .receiving,
              now.timeIntervalSince(since) >= Self.firstBufferGrace else { return nil }
        let waiting = Self.channelKeys.filter { channelStatus($0) == .awaitingFirstBuffer }
        if !channels.values.contains(where: \.hasBuffer), !channels.values.contains(.stalled) {
            return "Ses gelmiyor · akış kuruldu ama hiçbir kaynaktan ses alınmadı"
        }
        guard !waiting.isEmpty else { return nil }
        return waiting.map { "\(Self.channelNames[$0] ?? $0) kaynağından henüz ses gelmiyor" }.joined(separator: " · ")
    }

    public var headline: String {
        switch phase {
        case .receiving: return "Kayıt: \(CaptureSignalPresentation.formattedTime(seconds))"
        case .failed: return failure ?? phase.headline
        default: return phase.headline
        }
    }

    /// The panel's leading dot: "ok" (receiving), "warning", "failed", "waiting" or "idle".
    public func overallDot(now: Date = Date()) -> String {
        if phase == .failed { return "failed" }
        if isReceiving { return warning(now: now) == nil ? "ok" : "warning" }
        if warning(now: now) != nil { return "warning" }
        return [.preparing, .awaitingPermission, .awaitingStream, .receiving].contains(phase) ? "waiting" : "idle"
    }

    /// The status line for a polled payload, or nil when there is nothing new to say: a schema-1 poll without a
    /// signal reading keeps the last line (as before), and a stop in progress keeps its own wording.
    public func activityLine(_ capture: [String: Any], now: Date = Date()) -> String? {
        if phase == .finishing || phase == .stopped || phase == .idle { return nil }
        if legacy { return capture["signals"] != nil ? CaptureSignalPresentation.label(capture) : nil }
        return CaptureSignalPresentation.sessionLabel(headline: headline, mic: channelStatus("mic"), system: channelStatus("system"), warning: warning(now: now), capture: capture)
    }

    /// Elapsed time only exists once audio did: preparing or a permission prompt is not recording time.
    public var countsElapsed: Bool { legacy ? phase != .preparing : phase == .receiving || phase == .finishing }
}
