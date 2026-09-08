import XCTest
@testable import MeetingOS

final class CaptureSignalPresentationTests: XCTestCase {

    func testCapturingWithSignalAndDigitalSilence() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 125,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "digital_silence"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 02:05\nMikrofon: Sinyal var\nSistem: Sessiz")
    }

    func testZeroSecondsFormatsAsZero() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 0,
            "signals": [
                "mic": ["state": "digital_silence"] as [String: Any],
                "system": ["state": "digital_silence"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:00\nMikrofon: Sessiz\nSistem: Sessiz")
    }

    func testMissingSignalsDictionaryReportsUnverified() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 10
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:10\nMikrofon: Doğrulanamadı\nSistem: Doğrulanamadı")
    }

    func testMissingIndividualSignalKeyReportsUnverified() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 10,
            "signals": [
                "mic": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:10\nMikrofon: Sinyal var\nSistem: Doğrulanamadı")
    }

    func testUnavailableSignalStateReportsUnverified() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 10,
            "signals": [
                "mic": ["state": "unavailable"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:10\nMikrofon: Doğrulanamadı\nSistem: Sinyal var")
    }

    func testStaleSignalOlderThan30SecondsIsMarkedNotCurrent() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 60,
            "signals": [
                "mic": ["state": "signal", "age_seconds": 45] as [String: Any],
                "system": ["state": "digital_silence", "age_seconds": 31] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 01:00\nMikrofon: Güncel değil\nSistem: Güncel değil")
    }

    func testSignalAgeAtThirtySecondBoundaryIsStillFresh() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 30,
            "signals": [
                "mic": ["state": "signal", "age_seconds": 30] as [String: Any],
                "system": ["state": "digital_silence", "age_seconds": 0] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:30\nMikrofon: Sinyal var\nSistem: Sessiz")
    }

    func testInvalidAgeSecondsIsTreatedAsNotCurrent() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 5,
            "signals": [
                "mic": ["state": "signal", "age_seconds": Double.nan] as [String: Any],
                "system": ["state": "signal", "age_seconds": -5] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:05\nMikrofon: Güncel değil\nSistem: Güncel değil")
    }

    func testSecondsNaNIsClampedToZero() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": Double.nan,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:00\nMikrofon: Sinyal var\nSistem: Sinyal var")
    }

    func testSecondsInfinityIsRejected() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": Double.infinity,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:00\nMikrofon: Sinyal var\nSistem: Sinyal var")
    }

    func testNegativeSecondsIsClampedToZero() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": -100,
            "signals": [
                "mic": ["state": "digital_silence"] as [String: Any],
                "system": ["state": "digital_silence"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:00\nMikrofon: Sessiz\nSistem: Sessiz")
    }

    func testExtremelyLargeSecondsValueIsCappedAtOneDay() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": Double.greatestFiniteMagnitude,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 24:00:00\nMikrofon: Sinyal var\nSistem: Sinyal var")
    }

    func testWrongTypeSecondsIsClampedToZero() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": "not-a-number",
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt: 00:00\nMikrofon: Sinyal var\nSistem: Sinyal var")
    }

    func testWaitingStateShowsWaitingMessageWithoutPermissionMention() {
        let capture: [String: Any] = [
            "state": "waiting",
            "seconds": 0,
            "signals": [
                "mic": ["state": "unavailable"] as [String: Any],
                "system": ["state": "unavailable"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Ses akışı bekleniyor\nMikrofon: Doğrulanamadı\nSistem: Doğrulanamadı")
        XCTAssertFalse(result.lowercased().contains("izin"))
        XCTAssertFalse(result.lowercased().contains("permission"))
    }

    func testStoppedStateShowsStoppedMessage() {
        let capture: [String: Any] = [
            "state": "stopped",
            "seconds": 200,
            "signals": [
                "mic": ["state": "digital_silence"] as [String: Any],
                "system": ["state": "digital_silence"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt durduruldu\nMikrofon: Sessiz\nSistem: Sessiz")
    }

    func testErrorStateShowsErrorMessageWithoutPermissionAdvice() {
        let capture: [String: Any] = [
            "state": "error",
            "seconds": 10,
            "signals": [
                "mic": ["state": "unavailable"] as [String: Any],
                "system": ["state": "unavailable"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Kayıt hatası\nMikrofon: Doğrulanamadı\nSistem: Doğrulanamadı")
        XCTAssertFalse(result.lowercased().contains("izin"))
        XCTAssertFalse(result.lowercased().contains("sıfırla"))
    }

    func testUnknownOrMissingStateReportsUnknown() {
        let capture: [String: Any] = [
            "seconds": 10,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "signal"] as [String: Any]
            ]
        ]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Durum bilinmiyor\nMikrofon: Sinyal var\nSistem: Sinyal var")
    }

    func testEmptyCaptureProducesUnknownStateAndUnverifiedSignals() {
        let capture: [String: Any] = [:]
        let result = CaptureSignalPresentation.label(capture)
        XCTAssertEqual(result, "Durum bilinmiyor\nMikrofon: Doğrulanamadı\nSistem: Doğrulanamadı")
    }
}

final class CaptureSignalJSONTests: XCTestCase {
    func testJSONNumericZeroAndOneAreNotBooleans() throws {
        let data = Data(#"{"state":"capturing","seconds":1,"signals":{"mic":{"state":"signal","age_seconds":0}}}"#.utf8)
        let capture = try XCTUnwrap(JSONSerialization.jsonObject(with:data) as? [String:Any])
        let result=CaptureSignalPresentation.label(capture)
        XCTAssertTrue(result.contains("00:01"))
        XCTAssertTrue(result.contains("Mikrofon: Sinyal var"))
    }
}

final class CapturePreviewWarningTests: XCTestCase {
    func testKnownMissingPreviewIsExplicit() {
        let value=CaptureSignalPresentation.label(["state":"capturing","seconds":30,"preview":["has_known_failures":true]])
        XCTAssertTrue(value.contains("Canlı metin eksik"))
    }
    func testNoKnownFailureDoesNotClaimFullTranscript() {
        let value=CaptureSignalPresentation.label(["state":"capturing","preview":["has_known_failures":false]])
        XCTAssertFalse(value.contains("Canlı metin eksik"))
        XCTAssertFalse(value.contains("tamamlandı"))
    }
}
