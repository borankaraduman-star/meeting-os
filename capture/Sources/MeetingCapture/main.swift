import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import Darwin

var journal: FileHandle?
let journalLock = NSLock()

func emit(_ object: [String: Any]) {
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
    var file: AVAudioFile?
    var temporary: URL?
    var start = 0.0
    var frames: AVAudioFramePosition = 0
    var rate = 0.0
    var index = 0
    var expectedEnd: Double?
    init(_ directory: URL, _ source: String, _ chunkSeconds: Double) {
        self.directory = directory; self.source = source; self.chunkSeconds = chunkSeconds
    }
    func append(_ buffer: AVAudioPCMBuffer, time: Double) throws {
        // Split before discontinuities so consumers can preserve real gaps.
        if let end = expectedEnd, abs(time-end) > 0.1 {
            try finish()
            emit(["event":"gap", "source":source, "start":end, "end":time])
        }
        if let f = file, f.processingFormat != buffer.format { try finish() }
        if file == nil {
            start = max(0, time); frames = 0; rate = buffer.format.sampleRate
            temporary = directory.appendingPathComponent(String(format: "%@-%06d.partial.wav", source, index))
            var settings = buffer.format.settings
            settings[AVLinearPCMIsNonInterleaved] = false
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
        emit(["event":"chunk", "source":source, "path":final.path, "start":start,
              "duration":Double(frames)/rate, "sample_rate":rate, "index":index])
        temporary = nil; index += 1
    }
}

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    let queue = DispatchQueue(label: "meeting-os.audio-writer")
    let writers: [SCStreamOutputType: ChunkWriter]
    let origin: Double
    var failure: Error?
    init(directory: URL, seconds: Double) {
        origin = CMClockGetTime(CMClockGetHostTimeClock()).seconds
        writers = [.audio: ChunkWriter(directory, "system", seconds), .microphone: ChunkWriter(directory, "mic", seconds)]
    }
    func stream(_ stream: SCStream, didStopWithError error: Error) {
        queue.async { self.failure = error; emit(["event":"error", "message":error.localizedDescription]) }
    }
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
        do { try writer.append(pcm, time: time) }
        catch { failure = error; emit(["event":"error", "message":error.localizedDescription]) }
    }
    func finish() throws {
        try queue.sync { for writer in writers.values { try writer.finish() } }
    }
    func getFailure() -> Error? { queue.sync { failure } }
    func fail(_ error:Error) { queue.sync { failure=error } }
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
func diskError() -> NSError { NSError(domain:"MeetingCapture",code:6,userInfo:[NSLocalizedDescriptionKey:"Disk alanı azaldı. Ses dosyaları korundu; devam etmek için yer açın."]) }
func run() async throws {
    if CommandLine.arguments.contains("--help") {
        print("MeetingCapture --output DIR [--seconds 60] [--chunk-seconds 12] [--self-test]")
        return
    }
    let directory = URL(fileURLWithPath: option("--output") ?? "capture", isDirectory: true).standardizedFileURL
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    signal(SIGPIPE, SIG_IGN)
    let journalURL = directory.appendingPathComponent("capture-native.jsonl")
    guard !FileManager.default.fileExists(atPath: journalURL.path) else {
        throw NSError(domain:"MeetingCapture", code:5, userInfo:[NSLocalizedDescriptionKey:"Choose a new recording folder"])
    }
    FileManager.default.createFile(atPath: journalURL.path, contents: nil, attributes: [.posixPermissions:0o600])
    journal = try FileHandle(forWritingTo: journalURL)
    let chunk = Double(option("--chunk-seconds") ?? "12") ?? 12
    guard chunk >= 1 && chunk <= 60 else { throw NSError(domain:"MeetingCapture", code:1, userInfo:[NSLocalizedDescriptionKey:"chunk-seconds must be 1...60"]) }
    if CommandLine.arguments.contains("--self-test") {
        let format = AVAudioFormat(standardFormatWithSampleRate: 16000, channels: 1)!
        let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 16000)!
        pcm.frameLength = 16000
        for n in 0..<16000 { pcm.floatChannelData![0][n] = Float(sin(Double(n)*0.1)*0.1) }
        for source in ["mic", "system"] {
            let writer = ChunkWriter(directory, source, 1)
            try writer.append(pcm, time: source == "mic" ? 0.25 : 0.5)
            try writer.finish()
        }
        return
    }
    if let available=remainingBytes(directory), available < 1_200_000_000 { throw diskError() }
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
    let capture = Capture(directory: directory, seconds: chunk)
    let stream = SCStream(filter: filter, configuration: config, delegate: capture)
    try stream.addStreamOutput(capture, type: .audio, sampleHandlerQueue: capture.queue)
    try stream.addStreamOutput(capture, type: .microphone, sampleHandlerQueue: capture.queue)
    try await stream.startCapture()
    emit(["event":"started", "directory":directory.path, "clock":"hostTime", "sources":["mic", "system"]])
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
        timer.setEventHandler {
            if Date().timeIntervalSince(diskCheck)>5 {
                diskCheck=Date()
                if let available=remainingBytes(directory), available < 1_000_000_000 { capture.fail(diskError()) }
            }
            if Date() >= deadline || capture.getFailure() != nil { stop() }
        }
        sigint.resume(); sigterm.resume(); timer.resume()
    }
    try await stream.stopCapture()
    try capture.finish()
    if let error = capture.getFailure() { throw error }
    emit(["event":"stopped"])
}

Task {
    do { try await run(); exit(0) }
    catch { emit(["event":"error", "message":error.localizedDescription]); exit(1) }
}
dispatchMain()
