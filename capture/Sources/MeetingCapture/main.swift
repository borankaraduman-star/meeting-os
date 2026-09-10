import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import Darwin

var journal: FileHandle?
let journalLock = NSLock()
/// When the last chunk was finalized. The restart budget resets only if audio actually flowed again, so a
/// stream that keeps dying without ever producing a chunk still runs out of attempts.
var lastChunkAt = Date.distantPast
func markChunk() { journalLock.lock(); lastChunkAt = Date(); journalLock.unlock() }
func chunkClock() -> Date { journalLock.lock(); let value = lastChunkAt; journalLock.unlock(); return value }

/// Every journal line carries the wall clock it was written on. Chunk `start` values are elapsed audio on the
/// capture host clock: they freeze while the Mac sleeps, and a relaunched helper splices its own timeline onto
/// the last finalized chunk, so the wall seconds those two things cost are recorded nowhere else. With `wall`
/// on the chunk lines the drift is measured rather than guessed, and finalize can put the ⌘M markers — which
/// the app stamps on the wall clock — back where the transcript actually is.
func emit(_ object: [String: Any]) {
    var object = object
    object["wall"] = (Date().timeIntervalSince1970*1000).rounded()/1000
    if let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]), var line = String(data: data, encoding: .utf8) {
        line += "\n"
        let bytes = Data(line.utf8)
        journalLock.lock()
        if let journal = journal { try? journal.write(contentsOf: bytes); try? journal.synchronize() }
        journalLock.unlock()
        try? FileHandle.standardOutput.write(contentsOf: bytes)
    }
}

final class ChunkWriter {
    let directory: URL
    let source: String
    let chunkSeconds: Double
    /// Seconds of recording this process inherited from a helper that died (--start-offset). Sample times stay
    /// this process's own elapsed audio; the offset is added only when a chunk is announced, so the meeting keeps
    /// one continuous timeline and assemble_capture lays the continuation after — never on top of — the old audio.
    let offset: Double
    var file: AVAudioFile?
    var temporary: URL?
    var start = 0.0
    var frames: AVAudioFramePosition = 0
    var rate = 0.0
    var index = 0
    var expectedEnd: Double?
    init(_ directory: URL, _ source: String, _ chunkSeconds: Double, offset: Double = 0) {
        self.directory = directory; self.source = source; self.chunkSeconds = chunkSeconds; self.offset = offset
        index = ChunkWriter.nextIndex(directory, source)
    }
    /// A relaunched helper writes into the folder its predecessor filled. Captured audio is never overwritten, so
    /// numbering starts past every chunk (finished or half-written) already on disk.
    static func nextIndex(_ directory: URL, _ source: String) -> Int {
        guard let names = try? FileManager.default.contentsOfDirectory(atPath: directory.path) else { return 0 }
        var next = 0
        let prefix = source + "-"
        for name in names where name.hasPrefix(prefix) && name.hasSuffix(".wav") {
            let digits = name.dropFirst(prefix.count).prefix(6)
            if digits.count == 6, digits.allSatisfy({ $0.isASCII && $0.isNumber }), let n = Int(digits) { next = max(next, n+1) }
        }
        return next
    }
    func append(_ buffer: AVAudioPCMBuffer, time: Double) throws {
        // Split before discontinuities so consumers can preserve real gaps.
        if let end = expectedEnd, abs(time-end) > 0.1 {
            try finish()
            emit(["event":"gap", "source":source, "start":end+offset, "end":time+offset])
        }
        if let f = file, f.processingFormat != buffer.format { try finish() }
        if file == nil {
            start = max(0, time); frames = 0; rate = buffer.format.sampleRate
            temporary = directory.appendingPathComponent(String(format: "%@-%06d.partial.wav", source, index))
            // 16-bit PCM on disk (AVAudioFile converts from the float processing format): the 12-second
            // chunks are transient and were the largest thing on disk at 48 kHz stereo float32.
            let settings: [String: Any] = [AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: buffer.format.sampleRate, AVNumberOfChannelsKey: buffer.format.channelCount,
                                           AVLinearPCMBitDepthKey: 16, AVLinearPCMIsFloatKey: false, AVLinearPCMIsBigEndianKey: false, AVLinearPCMIsNonInterleaved: false]
            file = try AVAudioFile(forWriting: temporary!, settings: settings, commonFormat: buffer.format.commonFormat, interleaved: buffer.format.isInterleaved)
        }
        try file!.write(from: buffer)
        frames += AVAudioFramePosition(buffer.frameLength)
        expectedEnd = time + Double(buffer.frameLength)/buffer.format.sampleRate
        if Double(frames)/rate >= chunkSeconds { try finish() }
    }
    func finish() throws {
        guard file != nil, let temp = temporary else { return }
        file = nil // Close and finalize WAV before announcing it.
        let final = directory.appendingPathComponent(String(format: "%@-%06d.wav", source, index))
        try FileManager.default.moveItem(at: temp, to: final)
        markChunk()
        emit(["event":"chunk", "source":source, "path":final.path, "start":start+offset,
              "duration":Double(frames)/rate, "sample_rate":rate, "index":index])
        temporary = nil; index += 1
    }
}

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    let queue = DispatchQueue(label: "meeting-os.audio-writer")
    let writers: [SCStreamOutputType: ChunkWriter]
    let origin: Double
    /// Watchdog state: the failure that ends the meeting, a stream-level stop the run loop recovers from
    /// (sleep, display change, ScreenCaptureKit hiccup), and when audio last arrived. The 0.25 s run-loop timer
    /// reads all three, so they sit behind their own lock rather than on the audio writer queue — a `queue.sync`
    /// hop made the watchdog wait twelve times a second behind an AVAudioFile write, a moveItem and an fsync,
    /// and `lastSample` was written from the Task context without the queue at all.
    private let watch = NSLock()
    private var failureValue: Error?
    private var streamErrorValue: Error?
    private var lastSampleValue = Date()
    init(directory: URL, seconds: Double, offset: Double = 0) {
        origin = CMClockGetTime(CMClockGetHostTimeClock()).seconds
        writers = [.audio: ChunkWriter(directory, "system", seconds, offset: offset), .microphone: ChunkWriter(directory, "mic", seconds, offset: offset)]
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        watch.lock(); streamErrorValue = error; watch.unlock()
        emit(["event":"stream_stopped", "message":error.localizedDescription])
    }
    func takeStreamError() -> Error? { watch.lock(); defer { watch.unlock() }; let e = streamErrorValue; streamErrorValue = nil; return e }
    func secondsSinceLastSample() -> Double { watch.lock(); defer { watch.unlock() }; return Date().timeIntervalSince(lastSampleValue) }
    func markSample() { watch.lock(); lastSampleValue = Date(); watch.unlock() }
    func stream(_ stream: SCStream, didOutputSampleBuffer sample: CMSampleBuffer, of type: SCStreamOutputType) {
        guard let writer = writers[type], sample.isValid, CMSampleBufferDataIsReady(sample),
              let description = sample.formatDescription,
              let asbd = CMAudioFormatDescriptionGetStreamBasicDescription(description),
              let format = AVAudioFormat(streamDescription: asbd) else { return }
        let count = CMSampleBufferGetNumSamples(sample)
        guard count > 0, let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(count)) else { return }
        pcm.frameLength = AVAudioFrameCount(count)
        let status = CMSampleBufferCopyPCMDataIntoAudioBufferList(sample, at: 0, frameCount: Int32(count), into: pcm.mutableAudioBufferList)
        guard status == noErr else { emit(["event":"error", "message":"PCM copy failed: \(status)"]); return }
        let time = sample.presentationTimeStamp.seconds - origin
        guard time.isFinite, time > -1 else { emit(["event":"error", "message":"Invalid capture clock"]); return }
        markSample()
        do { try writer.append(pcm, time: time) }
        catch { fail(error); emit(["event":"error", "message":error.localizedDescription]) }
    }
    func finish() throws {
        try queue.sync { for writer in writers.values { try writer.finish() } }
    }
    func getFailure() -> Error? { watch.lock(); defer { watch.unlock() }; return failureValue }
    func fail(_ error:Error) { watch.lock(); failureValue = error; watch.unlock() }
}

func option(_ key: String) -> String? {
    let args = CommandLine.arguments
    guard let i = args.firstIndex(of: key), i+1 < args.count else { return nil }
    return args[i+1]
}

func remainingBytes(_ directory:URL) -> Int64? {
    let values=try? FileManager.default.attributesOfFileSystem(forPath:directory.path)
    return (values?[.systemFreeSize] as? NSNumber)?.int64Value
}
func diskError() -> NSError { NSError(domain:"MeetingCapture",code:6,userInfo:[NSLocalizedDescriptionKey:"Disk doldu. Ses dosyaları korundu; devam etmek için yer açın."]) }
let diskWarnBytes: Int64 = 3_000_000_000   // journal a warning the app can show; recording continues
let diskStopBytes: Int64 = 400_000_000     // floor: stop only when the disk is genuinely about to fill
let diskStartBytes: Int64 = 600_000_000
let assemblySources = 2                    // mic + system: finalize assembles one float32 file per source
let assemblyHeadroomBytes: Int64 = 200_000_000
/// What finalize will need free to assemble this recording: 16 kHz float32 per source for every second
/// recorded so far, plus headroom. A fixed 400 MB stop threshold let a two-hour meeting run the disk down to
/// a point where assembly (≈1.02 GB) could no longer produce the very files the recording exists for.
func assemblyReserveBytes(elapsed: Double, sources: Int = assemblySources) -> Int64 {
    let perSource = max(0, elapsed) * 16000 * 4
    let needed = perSource * Double(sources)
    guard needed.isFinite, needed < 1e15 else { return Int64.max/4 }
    return max(diskStopBytes, Int64(needed) + assemblyHeadroomBytes)
}
func run() async throws {
    if CommandLine.arguments.contains("--help") {
        print("MeetingCapture --output DIR [--seconds 60] [--chunk-seconds 12] [--start-offset 0] [--self-test]")
        return
    }
    let directory = URL(fileURLWithPath: option("--output") ?? "capture", isDirectory: true).standardizedFileURL
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    signal(SIGPIPE, SIG_IGN)
    // Seconds already recorded into this folder by a helper that died. The supervisor hands it back so one
    // meeting keeps one timeline across relaunches; without it an existing folder still means "already used".
    let startOffset = max(0, Double(option("--start-offset") ?? "0") ?? 0)
    guard startOffset.isFinite, startOffset < 86400 else {
        throw NSError(domain:"MeetingCapture", code:8, userInfo:[NSLocalizedDescriptionKey:"start-offset must be 0...86400"])
    }
    // The flag itself says "the supervisor is handing this folder back", not its value: a helper that died
    // before its first chunk hands back 0.000 seconds, and that relaunch must be allowed like any other.
    let continuation = CommandLine.arguments.contains("--start-offset")
    let journalURL = directory.appendingPathComponent("capture-native.jsonl")
    let inherited = FileManager.default.fileExists(atPath: journalURL.path)
    guard !inherited || continuation else {
        throw NSError(domain:"MeetingCapture", code:5, userInfo:[NSLocalizedDescriptionKey:"Choose a new recording folder"])
    }
    if !inherited { FileManager.default.createFile(atPath: journalURL.path, contents: nil, attributes: [.posixPermissions:0o600]) }
    journal = try FileHandle(forWritingTo: journalURL)
    if inherited { try journal?.seekToEnd() }   // append: the predecessor's history is part of this recording
    let chunk = Double(option("--chunk-seconds") ?? "12") ?? 12
    guard chunk >= 1 && chunk <= 60 else { throw NSError(domain:"MeetingCapture", code:1, userInfo:[NSLocalizedDescriptionKey:"chunk-seconds must be 1...60"]) }
    if CommandLine.arguments.contains("--self-test") {
        let format = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)!
        let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16000)!
        pcm.frameLength = 16000
        for n in 0..<16000 { pcm.floatChannelData![0][n] = Float(sin(Double(n)*0.1)*0.1) }
        for source in ["mic", "system"] {
            let writer = ChunkWriter(directory, source, 1, offset: startOffset)   // same timeline rules the real path uses
            try writer.append(pcm, time: source == "mic" ? 0.25 : 0.5)
            try writer.finish()
        }
        return
    }
    // A continuation inherits its predecessor's seconds, and those have to be assembled too.
    if let available=remainingBytes(directory), available < max(diskStartBytes, assemblyReserveBytes(elapsed: startOffset)) { throw diskError() }
    guard await AVCaptureDevice.requestAccess(for: .audio) else {
        throw NSError(domain:"MeetingCapture", code:2, userInfo:[NSLocalizedDescriptionKey:"Microphone access denied. Enable MeetingCapture in System Settings > Privacy & Security > Microphone."])
    }
    let content: SCShareableContent
    do { content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true) }
    catch { throw NSError(domain:"MeetingCapture", code:4, userInfo:[NSLocalizedDescriptionKey:"System audio capture unavailable. Check System Settings > Privacy & Security > Screen & System Audio Recording. Original error: \(error.localizedDescription)"]) }
    guard let display = content.displays.first else { throw NSError(domain:"MeetingCapture", code:3, userInfo:[NSLocalizedDescriptionKey:"No display available"] ) }
    let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
    let config = SCStreamConfiguration()
    config.capturesAudio = true; config.captureMicrophone = true
    config.excludesCurrentProcessAudio = true
    config.sampleRate = 48000; config.channelCount = 2
    config.width = 2; config.height = 2
    config.minimumFrameInterval = CMTime(value:1, timescale:1)
    config.showsCursor = false
    let capture = Capture(directory: directory, seconds: chunk, offset: startOffset)
    func makeStream() throws -> SCStream {
        let stream = SCStream(filter: filter, configuration: config, delegate: capture)
        try stream.addStreamOutput(capture, type: .audio, sampleHandlerQueue: capture.queue)
        try stream.addStreamOutput(capture, type: .microphone, sampleHandlerQueue: capture.queue)
        return stream
    }
    var stream = try makeStream()
    try await stream.startCapture()
    capture.markSample()
    let recordingStarted = Date()
    emit(["event":"started", "directory":directory.path, "clock":"hostTime", "sources":["mic", "system"], "start_offset":startOffset])
    let restartGate = DispatchQueue(label:"meeting-os.restart")
    var restarting = false
    var restarts = 0
    var lastRestartAt = Date.distantPast
    let restartBudget = 3
    let restartBackoff = [2.0, 5.0, 10.0]      // a display or audio device that just went away needs time to come back
    let healthySeconds = 600.0                 // chunks landing for this long means the stream really recovered
    /// Rebuild the stream after a stop error, a 20 s silence from ScreenCaptureKit, or a wake (sleep/wake, display
    /// changes). Three tries in a row, then give up — but a meeting runs for hours, so ten minutes of healthy
    /// chunks earns a fresh budget instead of ending the recording at the third hiccup of the afternoon.
    func restartStream(reason: String) {
        // The old `guard` returned from the closure, not the function, so overlapping restarts were possible.
        let proceed: Bool = restartGate.sync { if restarting { return false }; restarting = true; return true }
        guard proceed else { return }
        Task {
            defer { restartGate.sync { restarting = false } }
            if restarts >= restartBudget, chunkClock() > lastRestartAt, Date().timeIntervalSince(lastRestartAt) >= healthySeconds {
                emit(["event":"restart_budget_reset", "after_attempts":restarts]); restarts = 0
            }
            if restarts >= restartBudget { capture.fail(NSError(domain:"MeetingCapture", code:7, userInfo:[NSLocalizedDescriptionKey:"Ses akışı üç kez yeniden kurulamadı: \(reason)"])); return }
            restarts += 1; lastRestartAt = Date()
            emit(["event":"restarting", "attempt":restarts, "reason":reason])
            try? await stream.stopCapture()
            try? await Task.sleep(nanoseconds: UInt64(restartBackoff[min(restarts, restartBackoff.count)-1] * 1_000_000_000))
            do {
                let fresh = try makeStream(); try await fresh.startCapture(); stream = fresh; capture.markSample()
                emit(["event":"restarted", "attempt":restarts])
            } catch {
                emit(["event":"stream_stopped", "message":"yeniden kurulamadı: \(error.localizedDescription)"])
            }
        }
    }
    signal(SIGINT, SIG_IGN); signal(SIGTERM, SIG_IGN)
    let duration = Double(option("--seconds") ?? "86400") ?? 86400
    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        let gate = DispatchQueue(label:"meeting-os.stop")
        var stopped = false
        let sigint = DispatchSource.makeSignalSource(signal: SIGINT, queue:gate)
        let sigterm = DispatchSource.makeSignalSource(signal: SIGTERM, queue:gate)
        let timer = DispatchSource.makeTimerSource(queue:gate)
        let stop = {
            if !stopped { stopped = true; sigint.cancel(); sigterm.cancel(); timer.cancel(); continuation.resume() }
        }
        sigint.setEventHandler(handler:stop); sigterm.setEventHandler(handler:stop)
        let deadline = Date().addingTimeInterval(max(1,duration))
        timer.schedule(deadline:.now()+0.25, repeating:0.25)
        var diskCheck=Date.distantPast
        var warnedDisk=false
        var lastWall=Date()
        var lastHost=CMClockGetTime(CMClockGetHostTimeClock()).seconds
        var wakeGap=0.0
        timer.setEventHandler {
            // Sleep/wake: the wall clock moved on while the audio host clock (and this 0.25 s timer) did not.
            // Chunk starts stay on the recording's own elapsed-audio timeline, so the lost wall seconds show up
            // nowhere else — the journal records them here so finalize and the report can account for them.
            let wall=Date(); let host=CMClockGetTime(CMClockGetHostTimeClock()).seconds
            let jump=wall.timeIntervalSince(lastWall)-(host-lastHost)
            lastWall=wall; lastHost=host
            if jump > 2*chunk {
                wakeGap += jump
                emit(["event":"wake", "gap":(jump*10).rounded()/10, "total_gap":(wakeGap*10).rounded()/10])
                restartStream(reason:"uykudan uyanıldı")   // the stream is dead after sleep even when it never reported a stop
            }
            if Date().timeIntervalSince(diskCheck)>5 {
                diskCheck=Date()
                // Recomputed every check: the longer the meeting runs, the more room its assembly needs.
                let stopAt = assemblyReserveBytes(elapsed: startOffset + Date().timeIntervalSince(recordingStarted))
                let warnAt = max(diskWarnBytes, stopAt * 3)   // assemblyReserveBytes is capped well below Int64.max/3
                if let available=remainingBytes(directory) {
                    if available < stopAt { capture.fail(diskError()) }
                    else if available < warnAt && !warnedDisk { warnedDisk=true; emit(["event":"low_disk", "free_bytes":available]) }
                    else if available >= warnAt { warnedDisk=false }
                }
            }
            if let err = capture.takeStreamError() { restartStream(reason: err.localizedDescription) }
            else if !restarting && capture.secondsSinceLastSample() > 20 { restartStream(reason: "20 sn ses gelmedi") }
            if Date() >= deadline || capture.getFailure() != nil { stop() }
        }
        sigint.resume(); sigterm.resume(); timer.resume()
    }
    try? await stream.stopCapture()   // a stream that already died throws here; the chunk in progress must still be flushed
    try capture.finish()
    if let error = capture.getFailure() { throw error }
    emit(["event":"stopped"])
}

Task {
    do { try await run(); exit(0) }
    catch { emit(["event":"error", "message":error.localizedDescription]); exit(1) }
}
dispatchMain()
