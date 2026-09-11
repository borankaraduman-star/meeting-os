import XCTest
@testable import MeetingOS

/// 1.2.81 — the user's decision on a summary item, and the answer on a Kontrol item.
///
/// What these guard is the part a person sees: an item is identified by something that survives a
/// re-analysis, a removal is folded away rather than deleted, an edit shows the user's wording while the
/// model's sentence stays reachable, and "Geç" never reads as approval.
final class InsightDecisionTests:XCTestCase {
    func item(_ d:[String:Any])->Insight { Insight(d) }

    // MARK: - Identity

    func testAnItemIsIdentifiedByItsIdNotBySentence() {
        let one=item(["text":"Yeni cümle","model_text":"Eski cümle","item_id":"abc123"])
        let two=item(["text":"Bambaşka bir cümle","item_id":"abc123"])
        XCTAssertEqual(one.id,two.id)
        XCTAssertEqual(one.modelText,"Eski cümle")
    }
    func testAnAnalysisWithoutIdsStillRendersOneRowPerSentence() {
        XCTAssertEqual(item(["text":"Kaynaksız madde"]).id,"Kaynaksız madde")
    }
    func testTheLayerFlagsAreReadFromTheBridge() {
        let edited=item(["text":"Benim cümlem","model_text":"Modelin cümlesi","item_id":"a","user_edited":true,"confirmed":true])
        XCTAssertTrue(edited.userEdited); XCTAssertTrue(edited.confirmed); XCTAssertFalse(edited.removed)
        let gone=item(["text":"Kaldırılan","item_id":"b","removed":true,"remove_reason":"duplicate"])
        XCTAssertTrue(gone.removed); XCTAssertEqual(SummaryUX.reasonLabel(gone.removeReason),"Tekrar")
    }

    // MARK: - Kaldırılan maddeler

    func testRemovedItemsAreFoldedAwayBehindOneLine() {
        let items=[item(["text":"Duran","item_id":"a"]),item(["text":"Kalkan","item_id":"b","removed":true])]
        XCTAssertEqual(SummaryUX.removedCount(items),1)
        XCTAssertEqual(SummaryUX.visible(items,showRemoved:false).map(\.text),["Duran"])
        XCTAssertEqual(SummaryUX.visible(items,showRemoved:true).count,2)   // hidden, never deleted
    }
    func testTheRemovedLineSaysWhichWayPressingItGoes() {
        XCTAssertEqual(SummaryUX.removedLine(2,shown:false),"2 madde kaldırıldı · göster")
        XCTAssertEqual(SummaryUX.removedLine(2,shown:true),"2 madde kaldırıldı · gizle")
        XCTAssertEqual(SummaryUX.removedLine(0,shown:false),"")
    }
    func testEveryRemoveReasonIsOptionalAndNamedInTurkish() {
        XCTAssertEqual(SummaryUX.removeReasons.map(\.code),["wrong","duplicate","too_detailed"])
        XCTAssertEqual(SummaryUX.removeReasons.map(\.label),["Yanlış","Tekrar","Gereksiz ayrıntı"])
        XCTAssertEqual(SummaryUX.reasonLabel("bilinmeyen"),"")   // a reason the app does not know is not invented
    }

    // MARK: - Çipler ve menü

    func testTheUserDecisionIsTheFirstThingTheChipsSay() {
        XCTAssertEqual(SummaryUX.chips(review:false,superseded:false,confirmed:true,edited:false).map(\.text),["doğru"])
        XCTAssertEqual(SummaryUX.chips(review:true,superseded:false,confirmed:false,edited:true).map(\.text),["düzeltildi","kontrol"])
        XCTAssertEqual(SummaryUX.chips(review:true,superseded:true,confirmed:true,edited:false).map(\.text),["doğru","geri alındı"])
    }
    func testAPlainItemStillCarriesNoChip() {
        XCTAssertTrue(SummaryUX.chips(review:false,superseded:false).isEmpty)
    }
    func testConfirmIsASwitchAndSaysSo() {
        XCTAssertEqual(SummaryUX.confirmTitle(false),"Doğru")
        XCTAssertEqual(SummaryUX.confirmTitle(true),"Doğru işaretini kaldır")
    }
    func testAnEmptyOrUnchangedCorrectionSavesNothing() {
        XCTAssertFalse(SummaryUX.editable("   ",original:"Madde"))
        XCTAssertFalse(SummaryUX.editable("Madde",original:"Madde "))
        XCTAssertTrue(SummaryUX.editable("Madde, düzeltilmiş",original:"Madde"))
    }

    // MARK: - Eşleşmeyen değişiklikler

    func testAnOrphanedDecisionIsShownUnderItsOwnSection() {
        let all=[InsightUnmatched(["item_id":"a","section":"summary","action":"remove","reason":"wrong","label":"kaldırma · Yanlış"]),
                 InsightUnmatched(["item_id":"b","section":"decisions","action":"edit","text":"Benim cümlem","label":"düzeltme"])]
        XCTAssertEqual(SummaryUX.unmatched(all,section:"summary").map(\.label),["kaldırma · Yanlış"])
        XCTAssertEqual(SummaryUX.unmatched(all,section:"decisions").first?.text,"Benim cümlem")
        XCTAssertEqual(SummaryUX.unmatchedLine(2),"2 değişikliğiniz bu analizde eşleşmedi")
        XCTAssertEqual(SummaryUX.unmatchedLine(0),"")
    }
}

/// Kontrol: three answers, and only two of them are answers about the content.
final class ReviewResolutionTests:XCTestCase {
    func review(_ d:[String:Any])->ReviewItem { ReviewItem(d) }

    func testTheQueueKeyAndSourceVersionComeFromTheBridge() {
        let item=review(["kind":"unnamed_speaker","segment_id":4,"key":"unnamed_speaker:Konuşmacı 2","source_version":"t:abc123"])
        XCTAssertEqual(item.key,"unnamed_speaker:Konuşmacı 2")
        XCTAssertEqual(item.sourceVersion,"t:abc123")
        XCTAssertTrue(ReviewUX.resolvable(item))
    }
    func testAnOlderBridgeWithoutAKeyStillResolves() {
        let item=review(["kind":"asr","segment_id":7])
        XCTAssertEqual(item.key,"asr:7")   // derived locally rather than leaving the buttons dead
        XCTAssertTrue(ReviewUX.resolvable(item))
    }
    func testTheThreeAnswersAreOfferedInOrder() {
        XCTAssertEqual(ReviewUX.results.map(\.code),["correct","corrected","skipped"])
        XCTAssertEqual(ReviewUX.results.map(\.label),["Doğru","Düzelt…","Geç"])
    }
    func testSkipNeverReadsAsApproval() {
        XCTAssertTrue(ReviewUX.help("skipped").contains("onay değildir"))
        XCTAssertTrue(ReviewUX.help("correct").contains("bir daha sorulmaz"))
        XCTAssertTrue(ReviewUX.help("corrected").contains("kaynak değişirse"))
    }
    func testAFlaggedTaskReadsAsItsOwnKindOfQuestion() {
        XCTAssertEqual(review(["kind":"task_review","task":"t1"]).title,"Görev kontrol bekliyor")
        XCTAssertEqual(review(["kind":"task_owner","task":"t1"]).title,"Görev sahibi belirsiz")
        XCTAssertEqual(review(["kind":"task_review","task":"t1"]).key,"task_review:t1")
    }
}
