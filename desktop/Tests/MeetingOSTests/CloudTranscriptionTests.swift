import XCTest
@testable import MeetingOS
final class CloudTranscriptionTests:XCTestCase {
    func testOpenRouterModeRecordsWithoutLivePreview() {
        XCTAssertFalse(CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r").contains("--live"))
        XCTAssertTrue(CloudTranscription.recordArguments(mode:"local",directory:"/d",title:"T",receipt:"/r").contains("--live"))
    }
    func testFinalizeAndImportNeverCarryKeysAndResumeKeepsStoredModel() {
        let f=CloudTranscription.finalizeArguments(meeting:"m1",model:"deepgram/nova-3",output:"/o")
        XCTAssertEqual(f,["openrouter-finalize","m1","--allow-upload","--output","/o","--model","deepgram/nova-3"])
        XCTAssertTrue(CloudTranscription.importArguments(path:"/a.m4a",title:"T",model:"deepgram/nova-3",output:"/o").contains("--no-local"))
        let cloud=Meeting(["id":"m2","status":"incomplete","recovery_state":"interrupted","metadata":["cloud_mode":"capture","model":"deepgram/nova-3"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").prefix(2),["openrouter-finalize","m2"])
        XCTAssertFalse(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").contains("--model"))
        let legacy=Meeting(["id":"m3","status":"incomplete","recovery_state":"interrupted","metadata":["engine":"openrouter","model":"openai/gpt-transcribe"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:legacy,model:"openai/gpt-transcribe",output:"/o").first,"openrouter-import")
    }
    func testFinalizeOnlyForStoppedRecordingsWithAudio() {
        let rec=Meeting(["id":"r","status":"incomplete","recovery_state":"interrupted","metadata":["capture_dir":"/c"]])
        XCTAssertTrue(CloudTranscription.canFinalize(meeting:rec,busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:rec,busy:true))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"r","status":"processing","recovery_state":"active","metadata":["capture_dir":"/c"]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"r","status":"complete","metadata":["capture_dir":"/c"]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:Meeting(["id":"t","status":"incomplete","metadata":["text_only":true]]),busy:false))
        XCTAssertFalse(CloudTranscription.canFinalize(meeting:nil,busy:false))
    }
}
