import XCTest
@testable import MeetingOS

final class TaskEditReasonTests: XCTestCase {
    /// The bridge validates against exactly these two strings (`memory.EDIT_REASONS`); a third would be
    /// refused as "Geçersiz düzenleme nedeni" and the user's edit would fail for a field they did not ask for.
    func testTheWireValuesAreTheOnesTheBridgeAccepts() {
        XCTAssertEqual(TaskEditReason.choices.map(\.rawValue), ["inference_error", "changed_later"])
        XCTAssertEqual(TaskEditReason.inferenceError.payload, "inference_error")
        XCTAssertEqual(TaskEditReason.changedLater.payload, "changed_later")
    }

    /// Unknown stays unknown: nothing is sent, so nothing is recorded, so an unexplained edit never becomes a
    /// "the model was wrong" label.
    func testSayingNothingSendsNothing() {
        XCTAssertNil(TaskEditReason.unsaid.payload)
        XCTAssertEqual(TaskEditReason.unsaid.label, "Belirtilmedi")
    }

    /// Two radio buttons and no third one, so the chosen button is also the way back out.
    func testTheChosenButtonClearsItself() {
        XCTAssertEqual(TaskEditReason.unsaid.toggled(.inferenceError), .inferenceError)
        XCTAssertEqual(TaskEditReason.inferenceError.toggled(.changedLater), .changedLater)
        XCTAssertEqual(TaskEditReason.inferenceError.toggled(.inferenceError), .unsaid)
    }

    func testEveryCaseHasATurkishLabel() {
        for reason in TaskEditReason.allCases { XCTAssertFalse(reason.label.isEmpty) }
    }
}
