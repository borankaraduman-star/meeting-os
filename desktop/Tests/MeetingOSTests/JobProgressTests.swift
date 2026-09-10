import XCTest
@testable import MeetingOS

/// The estimate is the only number people leave the Mac on the strength of, so every rule that keeps it
/// honest — the warm-up piece, the cap, the unit it prefers — is pinned here.
final class JobProgressTests: XCTestCase {

    private func progress(_ json: String) throws -> JobProgress {
        try JSONDecoder().decode(JobProgress.self, from: Data(json.utf8))
    }

    /// A payload without the new keys decodes and behaves exactly as it did before they existed.
    func testPieceCountEstimateUnchanged() throws {
        let p = try progress(#"{"stage":"transcribing","current":2,"total":4,"source":"","updated_at":0}"#)
        XCTAssertNil(p.uploaded_seconds)
        XCTAssertNil(p.total_seconds)
        XCTAssertEqual(p.remaining(elapsed: 120), "≈2 dk kaldı")
        XCTAssertEqual(p.line(elapsed: 120), "Konuşma yazıya çevriliyor · 2/4 bölüm · ≈2 dk kaldı")
    }

    /// Pieces are not the same length; seconds are. When both are reported the seconds win.
    func testSecondsPreferredOverPieces() throws {
        let p = try progress(#"{"stage":"transcribing","current":2,"total":8,"source":"","updated_at":0,"uploaded_seconds":600,"total_seconds":3600}"#)
        // 300 s of wall clock bought 600 s of audio; 3000 s of audio are left → 1500 s → 25 dk.
        // The piece counter would have claimed 15 dk from the same payload.
        XCTAssertEqual(p.remaining(elapsed: 300), "≈25 dk kaldı")
    }

    /// The first piece carries model loading and the upload warm-up, so it is not a rate — with either unit.
    func testFirstPieceIsNotARate() throws {
        let p = try progress(#"{"stage":"transcribing","current":1,"total":8,"source":"","updated_at":0,"uploaded_seconds":300,"total_seconds":3600}"#)
        XCTAssertNil(p.remaining(elapsed: 120))
    }

    /// Seconds alone are enough: a stage that reports no pieces still gets an estimate.
    func testSecondsWithoutPieceCounts() throws {
        let p = try progress(#"{"stage":"transcribing","current":0,"total":0,"source":"","updated_at":0,"uploaded_seconds":120,"total_seconds":600}"#)
        XCTAssertEqual(p.remaining(elapsed: 60), "≈4 dk kaldı")
    }

    /// An hour is the cap for a job the user is waiting on; a deliberately throttled one is allowed two.
    func testCapIsOneHourNormallyAndTwoWhenThrottled() throws {
        let p = try progress(#"{"stage":"transcribing","current":2,"total":30,"source":"","updated_at":0,"uploaded_seconds":100,"total_seconds":3600}"#)
        XCTAssertNil(p.remaining(elapsed: 200))
        XCTAssertEqual(p.remaining(elapsed: 200, lowPriority: true), "≈117 dk kaldı")
    }

    /// Past two hours even a throttled job says nothing: a wrong number is worse than no number.
    func testBeyondTwoHoursSaysNothing() throws {
        let p = try progress(#"{"stage":"transcribing","current":2,"total":30,"source":"","updated_at":0,"uploaded_seconds":100,"total_seconds":3600}"#)
        XCTAssertNil(p.remaining(elapsed: 300, lowPriority: true))
    }

    /// A finished upload (or a malformed one) must not divide by zero or claim a negative remainder.
    func testDegenerateSecondsFallBackToPieces() throws {
        let done = try progress(#"{"stage":"transcribing","current":2,"total":4,"source":"","updated_at":0,"uploaded_seconds":3600,"total_seconds":3600}"#)
        XCTAssertEqual(done.remaining(elapsed: 120), "≈2 dk kaldı")
        let zero = try progress(#"{"stage":"transcribing","current":2,"total":4,"source":"","updated_at":0,"uploaded_seconds":0,"total_seconds":3600}"#)
        XCTAssertEqual(zero.remaining(elapsed: 120), "≈2 dk kaldı")
    }
}
