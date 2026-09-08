import XCTest
@testable import MeetingOS
final class RecordingNavigationTests:XCTestCase {
    func testPollingDoesNotStealSelectionAfterFirstLiveMeeting() {
        var navigation=RecordingNavigation();navigation.begin()
        XCTAssertEqual(navigation.resolve(active:"live"),"live")
        XCTAssertNil(navigation.resolve(active:"live"))
    }
    func testUserNavigationWhileWaitingCancelsAutomaticJump() {
        var navigation=RecordingNavigation();navigation.begin()
        navigation.selectionChanged()
        XCTAssertNil(navigation.resolve(active:"live"))
    }
    func testStoppedRecordingCannotNavigateOnLateSnapshot() {
        var navigation=RecordingNavigation();navigation.begin();navigation.cancel()
        XCTAssertNil(navigation.resolve(active:"old-live"))
    }
    func testNextRecordingCanSelectItsOwnMeetingOnce() {
        var navigation=RecordingNavigation();navigation.begin()
        _=navigation.resolve(active:"first");navigation.begin()
        XCTAssertEqual(navigation.resolve(active:"second"),"second")
        XCTAssertNil(navigation.resolve(active:"second"))
    }
}
