import XCTest
@testable import MeetingOS

/// Week-two audit: the karne and the cross-meeting lists used to answer "we did not look" with a row of zeros,
/// and used to hide a reversed decision instead of showing it reversed. These cover the parsing and the pure
/// sentences behind that separation — no view is built, so they stay fast.
final class AuditTextTests:XCTestCase {
    func testNeverAnalysedMeetingSaysSoInsteadOfCountingZeros() {
        XCTAssertEqual(AuditText.counts(analyzed:false,decisions:0,actions:0,questions:0),"analiz yok")
        XCTAssertEqual(AuditText.counts(analyzed:true,decisions:0,actions:0,questions:0),"0 karar · 0 görev · 0 soru")
        XCTAssertEqual(AuditText.counts(analyzed:true,decisions:3,actions:2,questions:1),"3 karar · 2 görev · 1 soru")
    }
    func testCostSaysWhenItIsAGuessAndWhenItIsUnknown() {
        XCTAssertEqual(AuditText.meetingCost(0.0042,known:true,estimated:false),"$0.004")
        XCTAssertEqual(AuditText.meetingCost(0.0042,known:true,estimated:true),"$0.004 (tahmini)")
        XCTAssertEqual(AuditText.meetingCost(0.0042,known:false,estimated:true),"—")   // unknown beats estimated
        XCTAssertEqual(AuditText.meetingCost(nil,known:true,estimated:false),"—")
        XCTAssertEqual(AuditText.periodCost(1.234,known:true),"$1.23")
        XCTAssertEqual(AuditText.periodCost(nil,known:false),"—")
    }
    func testTheGapIsOnlyNamedWhenThereIsOne() {
        XCTAssertNil(AuditText.unanalyzed(0))
        XCTAssertEqual(AuditText.unanalyzed(2),"2 toplantı analiz edilmedi")
    }
    func testSourceLineOnlyGrowsWhenSomethingWentStale() {
        XCTAssertEqual(AuditText.sourceLine(staleMeetings:0),"Her toplantının en güncel analizinden alınmıştır")
        XCTAssertEqual(AuditText.sourceLine(staleMeetings:3),"Her toplantının en güncel analizinden alınmıştır · 3 toplantının analizi bayat")
    }
}

final class ScoreMeetingParseTests:XCTestCase {
    func testNewAuditKeysAreRead() {
        let s=ScoreMeeting(["meeting":"m1","title":"Sprint","created":"2026-09-08T10:00:00","minutes":42.0,
                            "counts":["decisions":0,"actions":0,"questions":0],"cost":0.012,
                            "analyzed":false,"stale":true,"analysis_cost":0.0042,"analysis_calls":3,
                            "analysis_estimated":true,"analysis_cost_known":true])
        XCTAssertFalse(s.analyzed); XCTAssertTrue(s.stale); XCTAssertEqual(s.analysisCalls,3)
        XCTAssertEqual(s.countsLine,"analiz yok")
        XCTAssertEqual(s.analysisCostLine,"Analiz $0.004 (tahmini)")
    }
    func testUnpricedAnalysisShowsADashRatherThanZero() {
        let s=ScoreMeeting(["meeting":"m2","analyzed":true,"analysis_cost_known":false,
                            "counts":["decisions":2,"actions":1,"questions":0]])
        XCTAssertEqual(s.countsLine,"2 karar · 1 görev · 0 soru")
        XCTAssertEqual(s.analysisCostLine,"Analiz —")
        XCTAssertFalse(s.stale)
    }
    func testAnOlderBridgeWithoutTheKeysStillReadsAsBefore() {
        let s=ScoreMeeting(["meeting":"m3","counts":["decisions":1,"actions":0,"questions":0],"cost":0.5])
        XCTAssertTrue(s.analyzed)          // the old contract promised these rows were analysed
        XCTAssertFalse(s.analysisCostKnown)
        XCTAssertEqual(s.countsLine,"1 karar · 0 görev · 0 soru")
        XCTAssertEqual(s.analysisCostLine,"Analiz —")
    }
}

final class CrossMeetingStaleParseTests:XCTestCase {
    func testWaitingItemCarriesStale() {
        let hot=WaitingItem(["task":"t1","title":"PRD","meeting":"m1","meeting_title":"Sprint","age_days":9,"stale":true])
        XCTAssertTrue(hot.stale); XCTAssertEqual(hot.age,9)
        XCTAssertFalse(WaitingItem(["task":"t2","title":"PRD"]).stale)
    }
    func testDecisionCarriesReversalNoteAndStale() {
        let d=DecisionEntry(["meeting":"m1","title":"Sprint","created":"2026-09-08T10:00:00","text":"Postgres",
                             "superseded":true,"note":"9 Eyl’de geri alındı","stale":true],index:0)
        XCTAssertTrue(d.superseded); XCTAssertTrue(d.stale); XCTAssertEqual(d.note,"9 Eyl’de geri alındı")
        let plain=DecisionEntry(["meeting":"m2","text":"Redis","note":"   "],index:1)
        XCTAssertFalse(plain.superseded); XCTAssertFalse(plain.stale)
        XCTAssertNil(plain.note)           // a blank note is no note, not an empty line under the decision
    }
    func testQuestionGroupCarriesStale() {
        XCTAssertTrue(QuestionGroup(["text":"Bütçe?","count":2,"stale":true],index:0).stale)
        XCTAssertFalse(QuestionGroup(["text":"Bütçe?"],index:0).stale)
    }
}

final class MeetingLabelTests:XCTestCase {
    func testDeletedMeetingKeepsItsOwnWordsAndBlankNeverReachesTheRow() {
        XCTAssertEqual(MeetingLabel.title("toplantı silindi"),"toplantı silindi")
        XCTAssertEqual(MeetingLabel.title(nil),MeetingLabel.unknown)
        XCTAssertEqual(MeetingLabel.title(""),MeetingLabel.unknown)
        XCTAssertEqual(MeetingLabel.title("   "),MeetingLabel.unknown)
        XCTAssertEqual(VoiceSample(["id":1,"seconds":12.0,"kind":"otomatik","meeting_title":"toplantı silindi"]).meetingTitle,"toplantı silindi")
        XCTAssertEqual(VoiceSample(["id":2,"seconds":12.0,"kind":"elle","meeting_title":""]).meetingTitle,MeetingLabel.unknown)
        XCTAssertEqual(CleanCandidate(["id":3,"meeting_title":"toplantı silindi"]).meetingTitle,"toplantı silindi")
    }
}
