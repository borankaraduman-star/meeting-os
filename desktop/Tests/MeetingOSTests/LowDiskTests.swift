import XCTest
@testable import MeetingOS

/// "The disk is filling up" is unusable during a meeting; "the recording stops in 69 minutes" is a decision.
final class LowDiskTests: XCTestCase {

    /// A gigabyte is one hour of chunks, but not one hour of recording: the assembly the meeting still owes
    /// itself grows by 128 000 B/s, and the last 200 MB are headroom, not minutes.
    func testMinutesLeftCountsTheGrowingStopThreshold() {
        XCTAssertEqual(DiskSpace.minutesLeft(freeBytes: 1_040_000_000), 33)
        XCTAssertEqual(DiskSpace.minutesLeft(freeBytes: 3_000_000_000), 111)
        XCTAssertEqual(DiskSpace.minutesLeft(freeBytes: 200_000_000), 0)
        XCTAssertEqual(DiskSpace.minutesLeft(freeBytes: 0), 0)
        XCTAssertEqual(DiskSpace.minutesLeft(freeBytes: -5), 0)
    }

    func testLowDiskLine() {
        XCTAssertEqual(CaptureSignalPresentation.lowDisk(["low_disk_bytes": 1_200_000_000]),
                       "Disk azalıyor · 1,2 GB boş · kayıt 39 dk sonra durabilir")
    }

    /// No warning from the helper means nothing is said; a reading that cannot be parsed invents nothing either.
    func testNoLowDiskWarningSaysNothing() {
        XCTAssertNil(CaptureSignalPresentation.lowDisk(["state": "capturing"]))
        XCTAssertNil(CaptureSignalPresentation.lowDisk(["low_disk_bytes": "çok"]))
        XCTAssertNil(CaptureSignalPresentation.lowDisk(["low_disk_bytes": true]))
    }

    /// The status line gains the disk line only when there is one; an ordinary meeting reads as before.
    func testStatusLineCarriesTheDiskLine() {
        let capture: [String: Any] = [
            "state": "capturing",
            "seconds": 125,
            "low_disk_bytes": 1_200_000_000,
            "signals": [
                "mic": ["state": "signal"] as [String: Any],
                "system": ["state": "digital_silence"] as [String: Any]
            ]
        ]
        XCTAssertEqual(CaptureSignalPresentation.label(capture),
                       "Kayıt: 02:05\nMikrofon: Sinyal var\nSistem: Sessiz\nDisk azalıyor · 1,2 GB boş · kayıt 39 dk sonra durabilir")
    }

    /// Before ⌃⌥R: warn under 1,5 GB, refuse only under the helper's own floor, and never refuse over a
    /// volume that could not be read at all.
    func testStartNoticeAndRefusal() {
        XCTAssertNil(DiskSpace.startNotice(freeBytes: 2_000_000_000))
        XCTAssertNil(DiskSpace.startNotice(freeBytes: nil))
        let notice = DiskSpace.startNotice(freeBytes: 900_000_000)
        XCTAssertNotNil(notice)
        XCTAssertTrue(notice?.hasPrefix("Disk dolu: en az 1,5 GB boş alan gerekir (kayıt ≈1 GB/saat)") == true)
        XCTAssertTrue(notice?.contains("900 MB boş") == true)
        XCTAssertFalse(DiskSpace.refuses(freeBytes: 900_000_000))
        XCTAssertTrue(DiskSpace.refuses(freeBytes: 500_000_000))
        XCTAssertFalse(DiskSpace.refuses(freeBytes: nil))
    }
}
