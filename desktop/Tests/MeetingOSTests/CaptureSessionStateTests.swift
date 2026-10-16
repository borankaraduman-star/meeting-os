import XCTest
@testable import MeetingOS

/// Synthetic event sequences only: no PCM, no helper, no real recording folder. Each payload is what the bridge
/// would report for that moment of a recording.
final class CaptureSessionStateTests: XCTestCase {
    let dir = "/tmp/meetingos-test/recordings/A"
    let t0 = Date(timeIntervalSince1970: 1_000_000)

    private func launched(_ dir: String? = nil) -> CaptureSessionState {
        var s = CaptureSessionState(); s.startRequested(directory: dir ?? self.dir); XCTAssertTrue(s.processLaunched()); return s
    }
    private func payload(_ state: String, session: String = "s-1", mic: Any? = nil, system: Any? = nil, extra: [String: Any] = [:]) -> [String: Any] {
        var p: [String: Any] = ["schema": 2, "state": "capturing", "session": session, "session_state": state, "seconds": 0]
        var channels: [String: Any] = [:]
        if let mic { channels["mic"] = mic }; if let system { channels["system"] = system }
        if !channels.isEmpty { p["channels"] = channels }
        return p.merging(extra) { _, new in new }
    }

    func testStartedWithoutPCMWaitsForStreamAndClaimsNoAudio() {
        var s = launched()
        XCTAssertTrue(s.apply(payload("awaiting_stream", mic: "awaiting_first_buffer", system: "awaiting_first_buffer"), directory: dir, now: t0))
        XCTAssertEqual(s.phase, .awaitingStream)
        XCTAssertFalse(s.isReceiving)
        XCTAssertEqual(s.channelStatus("mic").label, "İlk ses bekleniyor")
        XCTAssertEqual(s.channelStatus("system").label, "İlk ses bekleniyor")
        XCTAssertNil(s.warning(now: t0.addingTimeInterval(4.9)))
        XCTAssertEqual(s.warning(now: t0.addingTimeInterval(5)), "Ses gelmiyor · akış kuruldu ama hiçbir kaynaktan ses alınmadı")
        let line = s.activityLine(payload("awaiting_stream", mic: "awaiting_first_buffer", system: "awaiting_first_buffer"), now: t0)!
        XCTAssertTrue(line.hasPrefix("Ses akışı bekleniyor\nMikrofon: İlk ses bekleniyor\nSistem: İlk ses bekleniyor"))
        XCTAssertFalse(line.contains("Kayıt:"))
        XCTAssertNotEqual(s.overallDot(now: t0), "ok")
        XCTAssertFalse(s.countsElapsed, "a stream without a buffer is not recording time")
    }

    func testPermissionWaitsTwentySecondsWithoutTimeoutThenDenialFails() {
        var s = launched()
        XCTAssertEqual(s.phase, .awaitingPermission)
        s.apply(payload("awaiting_permission", extra: ["permission": ["microphone": "requested"]]), directory: dir, now: t0)
        let later = t0.addingTimeInterval(20)
        XCTAssertEqual(s.phase, .awaitingPermission)
        XCTAssertNil(s.warning(now: later), "a permission prompt has no deadline")
        XCTAssertFalse(s.isReceiving)
        XCTAssertFalse(s.countsElapsed)
        XCTAssertEqual(s.overallDot(now: later), "waiting")
        XCTAssertFalse(s.activityLine(payload("awaiting_permission"), now: later)!.contains("Kayıt:"))
        s.apply(payload("failed", extra: ["permission": ["microphone": "denied"]]), directory: dir, now: later)
        XCTAssertEqual(s.phase, .failed)
        XCTAssertEqual(s.overallDot(now: later), "failed")
        XCTAssertTrue(s.headline.contains("Mikrofon"))
        XCTAssertTrue(s.headline.contains("Sistem Ayarları"))
        XCTAssertFalse(s.headline.contains("denied"))
        s.processExited(succeeded: false)
        XCTAssertEqual(s.phase, .failed)
        XCTAssertTrue(s.headline.contains("izni verilmedi"), "the explained failure keeps its message after the exit")
    }

    func testZeroMicBuffersAreSilentDataNotADeadChannel() {
        var s = launched()
        s.apply(payload("receiving", mic: ["state": "silent", "age_seconds": 0.5], system: ["state": "signal", "age_seconds": 0.2], extra: ["seconds": 65]), directory: dir, now: t0)
        XCTAssertEqual(s.channelStatus("mic"), .silent)
        XCTAssertEqual(s.channelStatus("mic").label, "Ses geliyor · sessiz")
        XCTAssertEqual(s.channelStatus("system").label, "Sinyal var")
        XCTAssertTrue(s.isReceiving)
        XCTAssertNil(s.warning(now: t0.addingTimeInterval(60)))
        XCTAssertEqual(s.overallDot(now: t0), "ok")
        XCTAssertEqual(s.headline, "Kayıt: 01:05")
        XCTAssertTrue(s.countsElapsed)
        XCTAssertEqual(s.channelStatus("mic").dot, "silent")
    }

    func testSilentBufferAloneIsGreen() {
        var s = launched()
        s.apply(payload("receiving", mic: "silent", system: "silent"), directory: dir, now: t0)
        XCTAssertTrue(s.isReceiving)
    }

    func testLateEventFromEarlierSessionOrFolderIsIgnored() {
        var old = launched("/tmp/meetingos-test/recordings/OLD")
        old.apply(payload("receiving", session: "old", mic: "signal", system: "signal"), directory: "/tmp/meetingos-test/recordings/OLD", now: t0)
        var s = old
        s.startRequested(directory: dir); s.processLaunched()
        XCTAssertNil(s.session, "nothing of the previous session carries over")
        XCTAssertTrue(s.channels.isEmpty)
        XCTAssertFalse(s.apply(payload("receiving", session: "old", mic: "signal", system: "signal"), directory: "/tmp/meetingos-test/recordings/OLD", now: t0))
        XCTAssertTrue(s.apply(payload("awaiting_stream", session: "new", mic: "awaiting_first_buffer", system: "awaiting_first_buffer"), directory: dir, now: t0))
        XCTAssertEqual(s.session, "new")
        // After a sleep the old session's delayed buffer line lands in this folder's poll: still not ours.
        XCTAssertFalse(s.apply(payload("receiving", session: "old", mic: "signal", system: "signal"), directory: dir, now: t0.addingTimeInterval(2)))
        XCTAssertFalse(s.apply(payload("receiving", session: "new", mic: "signal", extra: ["directory": "/tmp/meetingos-test/recordings/OLD"]), directory: dir, now: t0))
        XCTAssertEqual(s.phase, .awaitingStream)
        XCTAssertFalse(s.isReceiving)
    }

    func testInterruptionThenRestartIsVisibleAndRecovers() {
        var s = launched()
        s.apply(payload("receiving", mic: "signal", system: "signal"), directory: dir, now: t0)
        s.apply(payload("receiving", mic: "signal", system: "stalled", extra: ["restarts": 1]), directory: dir, now: t0.addingTimeInterval(30))
        XCTAssertEqual(s.channelStatus("system").label, "Akış kesildi")
        XCTAssertEqual(s.channelStatus("system").dot, "stale")
        XCTAssertTrue(s.isReceiving, "the mic still delivers")
        // The helper rebuilt the stream: no new session, the same folder, buffers again.
        s.apply(payload("receiving", mic: "signal", system: "signal", extra: ["restarts": 1]), directory: dir, now: t0.addingTimeInterval(40))
        XCTAssertEqual(s.channelStatus("system"), .signal)
        // A reading that stopped refreshing is a stalled stream, whatever its last word was.
        s.apply(payload("receiving", mic: ["state": "signal", "age_seconds": 45], system: "signal"), directory: dir, now: t0.addingTimeInterval(90))
        XCTAssertEqual(s.channelStatus("mic"), .stalled)
    }

    func testStopWhilePreparingLeavesNoGhostAndNothingPending() {
        var s = CaptureSessionState(); s.startRequested(directory: dir)
        XCTAssertEqual(s.phase, .preparing)
        XCTAssertEqual(s.stopRequested(), .discard)
        XCTAssertEqual(s.phase, .stopped)
        XCTAssertNil(s.directory)
        XCTAssertFalse(s.countsElapsed)
        XCTAssertFalse(s.processLaunched(), "a launch after the stop is not a recording")
        XCTAssertFalse(s.apply(payload("receiving", mic: "signal"), directory: dir, now: t0), "a pending event does not revive it")
        XCTAssertNil(s.activityLine(payload("receiving", mic: "signal"), now: t0))
        s.startRequested(directory: "/tmp/meetingos-test/recordings/B")
        XCTAssertEqual(s.phase, .preparing)
        XCTAssertTrue(s.channels.isEmpty)
        XCTAssertFalse(s.apply(payload("receiving", mic: "signal"), directory: dir, now: t0), "the next session never takes the old folder's events")
    }

    func testStopAfterLaunchFinishesAndPayloadCannotReopen() {
        var s = launched()
        s.apply(payload("receiving", mic: "signal", system: "signal"), directory: dir, now: t0)
        XCTAssertEqual(s.stopRequested(), .signal)
        XCTAssertEqual(s.phase, .finishing)
        XCTAssertEqual(s.stopRequested(), .signal, "a second press still escalates")
        s.apply(payload("receiving", mic: "signal", system: "signal"), directory: dir, now: t0)
        XCTAssertEqual(s.phase, .finishing)
        XCTAssertNil(s.activityLine(payload("receiving", mic: "signal"), now: t0), "the stop's own wording stays")
        s.processExited(succeeded: true)
        XCTAssertEqual(s.phase, .stopped)
        XCTAssertFalse(s.apply(payload("receiving", mic: "signal"), directory: dir, now: t0))
    }

    func testMicWithoutSystemAndSilentTranscriptionAreThreeSeparateStages() {
        var s = launched()
        s.apply(payload("receiving", mic: "signal", system: "awaiting_first_buffer", extra: ["preview": ["enabled": true, "segments": 0]]), directory: dir, now: t0)
        // Stage 1: the process is up. Stage 2: the mic delivers, the system channel does not. Stage 3: no text yet.
        XCTAssertTrue(s.processRunning)
        XCTAssertEqual(s.channelStatus("mic"), .signal)
        XCTAssertEqual(s.channelStatus("system"), .awaitingFirstBuffer)
        XCTAssertEqual(s.text, .waiting)
        XCTAssertTrue(s.isReceiving, "an unanswered transcription never turns the recording red")
        XCTAssertNil(s.warning(now: t0.addingTimeInterval(4)))
        XCTAssertEqual(s.warning(now: t0.addingTimeInterval(6)), "Sistem kaynağından henüz ses gelmiyor")
        XCTAssertEqual(s.overallDot(now: t0.addingTimeInterval(6)), "warning")
        let line = s.activityLine(payload("receiving", mic: "signal", system: "awaiting_first_buffer"), now: t0.addingTimeInterval(6))!
        XCTAssertEqual(line, "Kayıt: 00:00\nMikrofon: Sinyal var\nSistem: İlk ses bekleniyor\nSistem kaynağından henüz ses gelmiyor")
        s.apply(payload("receiving", mic: "signal", system: "signal", extra: ["preview": ["enabled": true, "segments": 3]]), directory: dir, now: t0.addingTimeInterval(8))
        XCTAssertEqual(s.text, .arriving)
        XCTAssertNil(s.warning(now: t0.addingTimeInterval(8)))
    }

    func testStreamAgeFromPayloadAnchorsTheWarning() {
        var s = launched()
        s.apply(payload("awaiting_stream", mic: "awaiting_first_buffer", system: "awaiting_first_buffer", extra: ["stream_age_seconds": 6]), directory: dir, now: t0)
        XCTAssertNotNil(s.warning(now: t0))
    }

    func testFailedLaunchAndHelperDeathBeforeAudio() {
        var s = CaptureSessionState(); s.startRequested(directory: dir)
        s.processExited(succeeded: false)
        XCTAssertEqual(s.phase, .failed)
        var t = launched()
        t.apply(payload("awaiting_stream"), directory: dir, now: t0)
        t.processExited(succeeded: false)
        XCTAssertEqual(t.phase, .failed)
        XCTAssertFalse(t.headline.contains("Error"))
        var r = launched()
        r.apply(payload("receiving", mic: "signal"), directory: dir, now: t0)
        r.processExited(succeeded: false)
        XCTAssertEqual(r.phase, .stopped, "audio reached disk: a recording, not a failed start")
    }

    func testLegacyPayloadKeepsItsOwnTextAndNeverWarns() {
        var s = launched()
        let legacy: [String: Any] = ["state": "capturing", "seconds": 125, "signals": ["mic": ["state": "signal"], "system": ["state": "digital_silence"]]]
        XCTAssertTrue(s.apply(legacy, directory: dir, now: t0))
        XCTAssertTrue(s.legacy)
        XCTAssertEqual(s.activityLine(legacy, now: t0), "Kayıt: 02:05\nMikrofon: Sinyal var\nSistem: Sessiz")
        XCTAssertEqual(s.phase, .receiving)
        XCTAssertNil(s.warning(now: t0.addingTimeInterval(60)))
        let noSignals: [String: Any] = ["state": "capturing", "seconds": 127]
        XCTAssertTrue(s.apply(noSignals, directory: dir, now: t0))
        XCTAssertNil(s.activityLine(noSignals, now: t0), "a poll without a reading keeps the last line")
        XCTAssertEqual(s.channelStatus("mic"), .signal)
        var u = launched()
        u.apply(["state": "capturing", "signals": ["mic": ["state": "unavailable"], "system": ["state": "unavailable"]]], directory: dir, now: t0)
        XCTAssertEqual(u.channelStatus("mic").label, "Doğrulanamadı")
        XCTAssertFalse(u.isReceiving)
    }
    /// The exact shape meeting_os/desktop.py capture_state answers with (capture_metrics.session_view): a helper start
    /// error carries the bridge's Turkish sentence, a denied permission its `permission` map.
    func testBridgePayloadShapesFromPython() {
        var s = launched()
        let failed: [String: Any] = ["state": "error", "seconds": 0, "sources": [:], "schema": 2, "session": "s-1", "session_state": "failed",
                                     "message": "Kayıt yardımcısı ses akışını başlatamadı; ses kaydı alınamadı.",
                                     "channels": ["mic": ["state": "awaiting_first_buffer", "epoch": 0, "age_seconds": 1.0], "system": ["state": "awaiting_first_buffer", "epoch": 0, "age_seconds": 1.0]]]
        XCTAssertTrue(s.apply(failed, directory: dir, now: t0))
        XCTAssertEqual(s.phase, .failed)
        XCTAssertEqual(s.headline, "Kayıt yardımcısı ses akışını başlatamadı; ses kaydı alınamadı.")
        var d = launched()
        d.apply(["schema": 2, "session": "s-1", "session_state": "failed", "permission": ["microphone": "denied"], "message": "Mikrofon izni verilmedi"], directory: dir, now: t0)
        XCTAssertEqual(d.phase, .failed)
        XCTAssertTrue(d.headline.contains("Mikrofon"))
        var w = launched()
        w.apply(["schema": 2, "session": "s-1", "session_state": "awaiting_stream", "stream_age_seconds": 7.5,
                 "channels": ["mic": ["state": "awaiting_first_buffer"], "system": ["state": "awaiting_first_buffer"]]], directory: dir, now: t0)
        XCTAssertNotNil(w.warning(now: t0), "the stream's own age dates the five-second warning")
    }
}
