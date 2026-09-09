import XCTest
import AppKit
@testable import MeetingOS

/// Q8/Q9/Q5 on the app side: what the person card says, what the identity explanation says once a person's own
/// bar has moved, and the one line that tells the user naming somebody changed the rest of the meeting.
final class ProfileCardTests:XCTestCase {
    func testPersonCardLineNamesEverySourceOfDoubt() {
        let weak=ProfileHealth(["name":"Gözlük","model":"m","samples":4,"auto_samples":3,"seconds":180.0,"rejections":2,
                                "weakest_fit":0.41,"weakest_sample":7,"weak":true,"last_meeting_title":"Pazartesi toplantısı"])
        XCTAssertEqual(weak.line,"4 örnek (3 otomatik, 1 elle) · 3 dk ses · bir örnek diğerlerine benzemiyor · 2 ret · son: Pazartesi toplantısı")
        XCTAssertEqual(weak.weakestSample,7)
        XCTAssertEqual(weak.fitHelp,"En zayıf örnek benzerliği 0,41")   // the number lives in the tooltip, not the line
        let thin=ProfileHealth(["name":"Ali","model":"m","samples":1,"auto_samples":0,"seconds":12.0])
        XCTAssertEqual(thin.line,"1 örnek (0 otomatik, 1 elle) · 12 sn ses · hiç duyulmadı")
        XCTAssertFalse(thin.weak)
    }
    func testExplanationUsesThePersonsOwnBar() {
        let lowered=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":9.0,
            "candidates":[["name":"Ali","score":0.855,"centroid":0.85,"best_sample":0.86,"samples":2,"threshold_used":0.85,
                           "person_note":"2 onaylı öneri → eşik 0,85"]]])
        XCTAssertEqual(lowered.bar(for:lowered.candidates[0]),0.85)
        XCTAssertEqual(lowered.verdict(for:lowered.candidates[0],rank:0),"isim verildi")   // 0.855 clears the personal bar
        XCTAssertEqual(lowered.candidates[0].personNote,"2 onaylı öneri → eşik 0,85")
        let raised=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":9.0,
            "candidates":[["name":"Veli","score":0.88,"centroid":0.88,"best_sample":0.88,"samples":2,"threshold_used":0.89]]])
        XCTAssertEqual(raised.verdict(for:raised.candidates[0],rank:0),"öneri (soru işaretli)")
        let plain=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,
            "candidates":[["name":"Ayşe","score":0.9,"centroid":0.9,"best_sample":0.9,"samples":1]]])
        XCTAssertEqual(plain.bar(for:plain.candidates[0]),0.87)   // no personal bar sent: the global one stands
        XCTAssertEqual(plain.verdict(for:plain.candidates[0],rank:0),"isim verildi")
    }
    @MainActor func testAdaptationNoteOnlySpeaksWhenSomethingChanged() {
        _ = NSApplication.shared
        let model=Model(); model.timer?.invalidate()
        XCTAssertEqual(model.adaptationNote(["renamed":0,"suggested":0]),"")
        XCTAssertEqual(model.adaptationNote([:]),"")
        XCTAssertEqual(model.adaptationNote(["renamed":0,"suggested":2])," · 2 kişi daha önerildi")
        XCTAssertEqual(model.adaptationNote(["renamed":1,"suggested":2])," · 1 kişi daha tanındı, 2 kişi daha önerildi")
    }
    func testWhyThisNameIsOneSentenceAndTheNumbersAreATooltip() {
        let named=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":9.0,
            "candidates":[["name":"Ayşe","score":0.91,"centroid":0.9,"best_sample":0.92,"samples":3]]])
        XCTAssertEqual(named.sentence,"Bu ses “Ayşe” profiline %91 benziyor ve ikinci adaydan açık ara önde — bu yüzden bu isim verildi.")
        let tooClose=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":9.0,
            "candidates":[["name":"Ayşe","score":0.91,"centroid":0.9,"best_sample":0.92,"samples":3],
                          ["name":"Veli","score":0.89,"centroid":0.89,"best_sample":0.89,"samples":2]]])
        XCTAssertEqual(tooClose.sentence,"Bu ses “Ayşe” profiline %91 benziyor, ikinci adaya farkı az — bu yüzden isim verilmedi.")
        let low=IdentityExplanation.parse(["threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":9.0,
            "candidates":[["name":"Ayşe","score":0.60,"centroid":0.6,"best_sample":0.6,"samples":1]]])
        XCTAssertTrue(low.sentence.hasSuffix("yeterince benzemiyor, bu yüzden isim verilmedi."))
        XCTAssertEqual(IdentityExplanation.parse([:]).sentence,"Karşılaştırılacak kayıtlı ses yok, bu yüzden isim verilmedi.")
        XCTAssertTrue(named.detail.contains("0.91"))          // every number the sentence dropped is still in .help
        XCTAssertTrue(named.detail.contains("İsim eşiği 0.87"))
        XCTAssertFalse(named.sentence.contains("0.87"))
    }
    func testCleanCandidateKeepsWhereTheTurnCameFrom() {
        let c=CleanCandidate(["id":42,"meeting":"m1","meeting_title":"Salı","start":61.5,"end":80.0,"seconds":18.5,"source":"system","text":"uzun bir cümle"])
        XCTAssertEqual(c.id,42); XCTAssertEqual(c.meeting,"m1"); XCTAssertEqual(c.start,61.5); XCTAssertEqual(c.seconds,18.5)
        XCTAssertEqual(CleanCandidate([:]).meetingTitle,"bilinmeyen toplantı")
    }
}
