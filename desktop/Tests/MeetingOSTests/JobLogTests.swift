import XCTest
@testable import MeetingOS

/// Finding #11. A recording and a finalize were allowed to run together and shared one truncated `last-job.log`,
/// so `ErrorPresentation.logSummary` could report the recorder's last line as the failed job's error. One log
/// per job, and a cap so the folder does not grow forever.
final class JobLogTests:XCTestCase {
    func testEachJobGetsItsOwnPath() {
        let dir=URL(fileURLWithPath:"/tmp/meetingos-test")
        let a=JobLog.url(dataDir:dir,jobId:"11111111-2222-3333-4444-555555555555")
        let b=JobLog.url(dataDir:dir,jobId:"99999999-8888-7777-6666-555555555555")
        XCTAssertNotEqual(a,b)
        XCTAssertEqual(a.lastPathComponent,"last-job-11111111-2222-3333-4444-555555555555.log")
        XCTAssertEqual(a.deletingLastPathComponent().path,dir.path)
    }
    /// The id reaches this from a UUID today, but a "/" in it would write outside the data folder.
    func testAJobIdCanNeverEscapeTheDataFolder() {
        let url=JobLog.url(dataDir:URL(fileURLWithPath:"/tmp/meetingos-test"),jobId:"../../etc/passwd")
        XCTAssertEqual(url.deletingLastPathComponent().path,"/tmp/meetingos-test")
        XCTAssertFalse(url.lastPathComponent.contains("/"))
        XCTAssertTrue(JobLog.isJobLog(url.lastPathComponent))
    }
    func testOnlyJobLogsAreRecognized() {
        XCTAssertTrue(JobLog.isJobLog("last-job-abc.log"))
        XCTAssertFalse(JobLog.isJobLog("last-job.log"))     // the compatibility symlink is not one of ours to delete
        XCTAssertFalse(JobLog.isJobLog("update.log"))
        XCTAssertFalse(JobLog.isJobLog("errors.jsonl"))
    }
    func testTheNewestFiveSurviveAndTheRestAreDeleted() {
        let now=Date()
        let files=(0..<8).map { (name:"last-job-\($0).log",modified:now.addingTimeInterval(Double(-$0)*60)) }
        let stale=JobLog.stale(files)
        XCTAssertEqual(Set(stale),["last-job-5.log","last-job-6.log","last-job-7.log"])   // 0…4 are the newest five
    }
    func testNothingIsDeletedBelowTheCap() {
        let now=Date()
        XCTAssertTrue(JobLog.stale([(name:"last-job-a.log",modified:now),(name:"last-job-b.log",modified:now)]).isEmpty)
    }
    /// Never the updater's log, never the error journal, never the symlink Python still opens.
    func testForeignFilesAreLeftAlone() {
        let old=Date().addingTimeInterval(-9999)
        let files=[(name:"update.log",modified:old),(name:"last-job.log",modified:old),(name:"errors.jsonl",modified:old)]
            + (0..<6).map { (name:"last-job-\($0).log",modified:Date().addingTimeInterval(Double(-$0))) }
        let stale=JobLog.stale(files)
        XCTAssertEqual(stale,["last-job-5.log"])
    }
    /// The point of the split: a failed job's summary comes from the file that job wrote, not from whatever
    /// the recorder appended last.
    func testASummaryComesFromTheJobsOwnLog() throws {
        let dir=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:dir) }
        let recorder=JobLog.url(dataDir:dir,jobId:"recorder"), finalize=JobLog.url(dataDir:dir,jobId:"finalize")
        try "kayıt sürüyor · parça 12\n".write(to:recorder,atomically:true,encoding:.utf8)
        try "OpenRouter 402: kredi bitti\n".write(to:finalize,atomically:true,encoding:.utf8)
        XCTAssertEqual(ErrorPresentation.logSummary(finalize),"OpenRouter 402: kredi bitti")
        XCTAssertEqual(ErrorPresentation.logSummary(recorder),"kayıt sürüyor · parça 12")
    }
    func testPruneKeepsTheCapOnDisk() throws {
        let dir=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:dir) }
        for i in 0..<9 {
            let url=JobLog.url(dataDir:dir,jobId:"job\(i)")
            try "satır\n".write(to:url,atomically:true,encoding:.utf8)
            try FileManager.default.setAttributes([.modificationDate:Date().addingTimeInterval(Double(i))],ofItemAtPath:url.path)
        }
        JobLog.prune(dataDir:dir)
        let left=try FileManager.default.contentsOfDirectory(atPath:dir.path).filter(JobLog.isJobLog).sorted()
        XCTAssertEqual(left,["last-job-job4.log","last-job-job5.log","last-job-job6.log","last-job-job7.log","last-job-job8.log"])
    }
}
