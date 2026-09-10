import XCTest
@testable import MeetingOS
final class TranscriptBlocksTests:XCTestCase {
    func row(_ id:Int,_ s:Double,_ e:Double,_ text:String,_ name:String,src:String="system",flags:[String]=["cloud_transcript","cloud_diarization","confidence_unavailable","speaker_unverified"],suggested:String="")->Row {
        Row(["id":id,"start":s,"end":e,"text":text,"speaker":name,"source":src,"flags":flags,"suggested":suggested])
    }
    func testInterjectionsFoldIntoTheInterruptedParagraph() {
        let rows=[row(1,0,26,"Uzun konuşma.","Gözlük"),row(2,26.4,27.2,"Hı hı.","Sol Üst"),row(3,27.4,29,"devamı.","Gözlük"),row(4,29.4,29.6,"Tabii.","Sol Üst"),row(5,29.9,36,"son kısım.","Gözlük"),row(6,36.8,61,"Ben ama şey demek istiyorum.","Sol Üst"),row(7,61,61.1,"Evet.","Gözlük"),row(8,61.2,68,"devam ediyorum.","Sol Üst")]
        let blocks=TranscriptBlocks.build(rows)
        XCTAssertEqual(blocks.map(\.label),["Gözlük","Sol Üst"])
        XCTAssertEqual(blocks[0].text,"Uzun konuşma. devamı. son kısım.");XCTAssertEqual(blocks[0].asides.map(\.id),[2,4])
        XCTAssertEqual(blocks[1].asides.map(\.id),[7]);XCTAssertEqual(TranscriptBlocks.asideCount(blocks),3)
    }
    func testShortTurnAtSpeakerChangeStaysItsOwnBlock() {
        let rows=[row(1,0,10,"A konuşuyor.","A"),row(2,10,11,"Evet.","B"),row(3,11,20,"B uzun konuşuyor.","B")]
        let blocks=TranscriptBlocks.build(rows)
        XCTAssertEqual(blocks.map(\.label),["A","B"]);XCTAssertEqual(blocks[1].rows.map(\.id),[2,3]);XCTAssertTrue(blocks[1].asides.isEmpty)
    }
    func testCloudNoticesAreSaidOncePerMeeting() {
        let r=row(1,0,5,"x","Gözlük")
        XCTAssertEqual(r.notices,"")
        XCTAssertEqual(TranscriptBlocks.meetingNotice([r]),"Bulut transkript · OpenRouter · güven ölçümü yok · konuşmacı adları doğrulanmadı · konuşmacı ayrımı sağlayıcıdan")
        XCTAssertNil(TranscriptBlocks.meetingNotice([row(2,0,5,"x","S0",flags:[])]))
        XCTAssertTrue(row(3,0,5,"x","Boran",src:"mic",flags:["cloud_transcript","possible_echo"]).notices.contains("yankı"))
    }
    func testSuggestedNameShowsQuestionMarkUntilConfirmed() {
        XCTAssertEqual(row(1,0,5,"x","Konuşmacı 3",suggested:"Sol Üst").label,"Sol Üst?")
        XCTAssertEqual(Row(["id":1,"speaker":"Konuşmacı 3","speaker_name":"Sol Üst","suggested":"Sol Üst","flags":["cloud_transcript"]]).label,"Sol Üst")
    }
}
final class ReviewItemTests:XCTestCase {
    func testItemsParseTitlesAndIds() {
        let a=ReviewItem(["segment_id":7,"start":65.0,"speaker":"Konuşmacı 2","text":"x","kind":"suggested_name","severity":1,"reason":"r","suggested":"Ayşe","speaker_key":"Konuşmacı 2"])
        XCTAssertEqual(a.title,"İsim onayı bekliyor");XCTAssertEqual(a.time,"01:05");XCTAssertEqual(a.id,"suggested_name:7")
        let g=ReviewItem(["segment_id":3,"kind":"glossary","severity":2,"reason":"r","original":"pemede","replacement":"PMD"])
        XCTAssertEqual(g.title,"Sözlük düzeltmesi");XCTAssertEqual(g.id,"glossary:3:pemede");XCTAssertEqual(g.replacement,"PMD")
        let t=ReviewItem(["kind":"task_owner","severity":2,"reason":"r","task":"t9","text":"Rapor"])
        XCTAssertEqual(t.title,"Görev sahibi belirsiz");XCTAssertEqual(t.id,"task_owner:t9");XCTAssertNil(t.segment);XCTAssertEqual(t.time,"")
    }
}
final class FillerTests:XCTestCase {
    func testFillersAndStuttersAreHiddenButWordsSurvive() {
        XCTAssertEqual(Fillers.clean("Şimdi çok şey, eee az önce hoşuma giden de oydu."),"Şimdi çok şey, az önce hoşuma giden de oydu.")
        XCTAssertEqual(Fillers.clean("Bi- mesela ben ve Burak'ta benzer bir motivasyon olabilir."),"Mesela ben ve Burak'ta benzer bir motivasyon olabilir.")
        XCTAssertEqual(Fillers.clean("Eee uğraşmasak bile zaten hani kişi sayısından ııı dolayı."),"Uğraşmasak bile zaten hani kişi sayısından dolayı.")
        XCTAssertEqual(Fillers.clean("Hı hı."),"Hı hı.")             // never blank a segment
        XCTAssertEqual(Fillers.clean("Ee-commerce ve e-posta iyi."),"Ee-commerce ve e-posta iyi.")   // hyphenated words stay
        XCTAssertEqual(Fillers.clean("Evet."),"Evet.")
    }
}
final class MarkerTests:XCTestCase {
    func testMarkersParseMatchBlocksAndSerialize() {
        let ms=Markers.parse(["markers":[["seconds":61.4,"kind":"decision"],["seconds":"x","kind":"task"],["seconds":200.0,"kind":"later"]]])
        XCTAssertEqual(ms.map(\.kind),["decision","later"]);XCTAssertEqual(ms[0].label,"Karar");XCTAssertEqual(ms[0].time,"01:01")
        XCTAssertEqual(Markers.inBlock(ms,start:30,end:60.8).map(\.kind),["decision"])   // one-second grace
        XCTAssertTrue(Markers.inBlock(ms,start:70,end:100).isEmpty)
        let line=Markers.line(seconds:12.345,kind:"task",now:Date(timeIntervalSince1970:0))
        XCTAssertTrue(line.contains("\"kind\":\"task\""));XCTAssertTrue(line.contains("12.3"));XCTAssertTrue(line.contains("1970-01-01"))
    }
}
final class UpdaterTests:XCTestCase {
    func testHeadlinesAndSettingsRoundTrip() {
        let u=UpdateInfo.parse(["available":true,"behind":3,"subjects":["Fix a","Fix b"],"local":"aaa","remote":"bbb"])
        XCTAssertEqual(u.headline,"Yeni sürüm hazır · 3 değişiklik · Fix a")
        XCTAssertEqual(UpdateInfo.parse(["available":false,"local":"aaa"]).headline,"Güncel (aaa)")
        XCTAssertEqual(UpdateInfo.parse(["available":false,"dirty":true]).headline,"Yerel değişiklikler var; otomatik güncelleme kapalı")
        XCTAssertEqual(UpdateInfo.parse(["error":"GitHub’a ulaşılamadı"]).headline,"GitHub’a ulaşılamadı")
        var s=ReportSettings.parse(["share_reports":false,"share_text":true,"auto_update":true,"report_dir":"/x","user_name":"Ayşe"]); s.shareText=false
        XCTAssertEqual(s.changes as NSDictionary,["share_reports":false,"share_text":false,"auto_update":true,"report_dir":"/x","audio_retention_days":30,"auto_retry":true,"user_name":"Ayşe","team_dir":"","share_glossary":true] as NSDictionary)
        XCTAssertEqual(ReportSettings.parse(["audio_retention_days":60]).audioRetentionDays,60)
        XCTAssertTrue(ReportSettings.parse([:]).autoRetry)   // idle retry is on unless the user turns it off
        XCTAssertFalse(ReportSettings.parse(["auto_retry":false]).autoRetry)
        XCTAssertEqual(ReportSettings.parse([:]).userName,"Boran")   // a settings file written before the name existed
        let team=ReportSettings.parse(["team_dir":"/Volumes/Ekip","share_glossary":false])
        XCTAssertEqual(team.teamDir,"/Volumes/Ekip");XCTAssertFalse(team.shareGlossary)
        XCTAssertTrue(ReportSettings.parse([:]).teamDir.isEmpty);XCTAssertTrue(ReportSettings.parse([:]).shareGlossary)
    }
}
final class ZoomWatchTests:XCTestCase {
    func testMeetingWindowDetection() {
        let win:[[String:Any]]=[["kCGWindowOwnerName":"zoom.us","kCGWindowName":"Zoom Meeting","kCGWindowLayer":0],["kCGWindowOwnerName":"Safari","kCGWindowName":"Zoom Meeting tips","kCGWindowLayer":0]]
        XCTAssertTrue(ZoomWatch.meetingOpen(windows:win,runningBundles:["us.zoom.xos"]))
        XCTAssertFalse(ZoomWatch.meetingOpen(windows:win,runningBundles:["com.apple.Safari"]))
        XCTAssertFalse(ZoomWatch.meetingOpen(windows:[["kCGWindowOwnerName":"zoom.us","kCGWindowName":"Zoom Workplace","kCGWindowLayer":25]],runningBundles:["us.zoom.xos"]))
        XCTAssertFalse(ZoomWatch.meetingOpen(windows:[["kCGWindowOwnerName":"zoom.us","kCGWindowName":"Zoom","kCGWindowLayer":0]],runningBundles:["us.zoom.xos"]))
        let home:[[String:Any]]=[["kCGWindowOwnerName":"zoom.us","kCGWindowName":"Zoom Workplace","kCGWindowLayer":0]]
        XCTAssertTrue(ZoomWatch.meetingOpen(windows:home,runningBundles:["us.zoom.xos"]))            // reminder may mention the home window
        XCTAssertFalse(ZoomWatch.meetingOpen(windows:home,runningBundles:["us.zoom.xos"],strict:true))   // hands-free recording must not
        XCTAssertTrue(ZoomWatch.meetingOpen(windows:win,runningBundles:["us.zoom.xos"],strict:true))
        let share:[[String:Any]]=[["kCGWindowOwnerName":"zoom.us","kCGWindowName":"zoom share toolbar window","kCGWindowLayer":25]]
        XCTAssertTrue(ZoomWatch.meetingOpen(windows:share,runningBundles:["us.zoom.xos"],strict:true))   // screen share hides the meeting window
        XCTAssertEqual(GlobalHotkeys.keyName(GlobalHotkeys.record),"⌃⌥R")
    }
}
final class IdentityExplanationTests:XCTestCase {
    func testVerdictsFollowThresholds() {
        let ex=IdentityExplanation.parse(["candidates":[["name":"Ayşe","score":0.90,"centroid":0.9,"best_sample":0.9,"samples":2],["name":"Ali","score":0.80,"centroid":0.8,"best_sample":0.8,"samples":1]],"threshold":0.87,"margin":0.05,"suggest":0.83,"seconds":12.0])
        XCTAssertEqual(ex.verdict(for:ex.candidates[0],rank:0),"isim verildi");XCTAssertEqual(ex.verdict(for:ex.candidates[1],rank:1),"")
        let close=IdentityExplanation.parse(["candidates":[["name":"Ayşe","score":0.90],["name":"Ali","score":0.88]],"threshold":0.87,"margin":0.05,"suggest":0.83])
        XCTAssertEqual(close.verdict(for:close.candidates[0],rank:0),"ikinci adaya çok yakın, isim verilmedi")
        let weak=IdentityExplanation.parse(["candidates":[["name":"Ayşe","score":0.85]],"threshold":0.87,"margin":0.05,"suggest":0.83])
        XCTAssertEqual(weak.verdict(for:weak.candidates[0],rank:0),"öneri (soru işaretli)")
    }
}
final class CloudTranscriptionTests:XCTestCase {
    func testOpenRouterModeRecordsWithoutLivePreview() {
        XCTAssertFalse(CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r").contains("--live"))
        XCTAssertTrue(CloudTranscription.recordArguments(mode:"local",directory:"/d",title:"T",receipt:"/r").contains("--live"))
    }
    /// A cloud-mode recording quit before finalize ever ran must still be findable by the idle queue.
    func testOpenRouterModeMarksTheRecordingsCloudIntent() {
        XCTAssertTrue(CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r").contains("--cloud"))
        XCTAssertFalse(CloudTranscription.recordArguments(mode:"local",directory:"/d",title:"T",receipt:"/r").contains("--cloud"))
        XCTAssertTrue(JobPriority.isRealtime(CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r")))
        XCTAssertFalse(ResourceGuard.stopsOnPressure(jobArguments:CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"T",receipt:"/r")))
    }
    func testFinalizeAndImportNeverCarryKeysAndResumeKeepsStoredModel() {
        let f=CloudTranscription.finalizeArguments(meeting:"m1",model:"deepgram/nova-3",output:"/o")
        XCTAssertEqual(f,["openrouter-finalize","m1","--allow-upload","--output","/o","--model","deepgram/nova-3"])
        XCTAssertEqual(CloudTranscription.importArguments(model:"deepgram/nova-3",output:"/o"),["openrouter-import","--no-local","--allow-upload","--model","deepgram/nova-3","--output","/o"])
        let cloud=Meeting(["id":"m2","status":"incomplete","recovery_state":"interrupted","metadata":["cloud_mode":"capture","model":"deepgram/nova-3"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").prefix(2),["openrouter-finalize","m2"])
        XCTAssertFalse(CloudTranscription.resumeArguments(meeting:cloud,model:"openai/gpt-transcribe",output:"/o").contains("--model"))
        let legacy=Meeting(["id":"m3","status":"incomplete","recovery_state":"interrupted","metadata":["engine":"openrouter","model":"openai/gpt-transcribe"]])
        XCTAssertEqual(CloudTranscription.resumeArguments(meeting:legacy,model:"openai/gpt-transcribe",output:"/o").first,"openrouter-import")
    }
    /// `ps` shows argv to every user on the Mac: the meeting title, the picked file and the typed question
    /// travel in the environment instead. Only ids, model names and paths the app itself made stay on argv.
    func testUserTextNeverReachesArgv() {
        let record=CloudTranscription.recordArguments(mode:"openrouter",directory:"/d",title:"Gizli görüşme",receipt:"/r")
        XCTAssertFalse(record.contains("Gizli görüşme"));XCTAssertFalse(record.contains("--title"))
        let imported=CloudTranscription.importArguments(model:"deepgram/nova-3",output:"/o")
        XCTAssertFalse(imported.contains { $0.hasSuffix(".m4a") });XCTAssertFalse(imported.contains("--title"))
    }
    func testCloudRowsShowClusterLabelsUntilNamed() {
        let cluster=Row(["id":1,"start":0.0,"end":3.0,"text":"x","speaker":"Konuşmacı 2","source":"system","flags":["cloud_transcript","cloud_diarization"]])
        XCTAssertEqual(cluster.label,"Konuşmacı 2")
        let named=Row(["id":2,"start":0.0,"end":3.0,"text":"x","speaker":"Konuşmacı 2","speaker_name":"Ayşe","source":"system","flags":["cloud_transcript"]])
        XCTAssertEqual(named.label,"Ayşe")
        let mic=Row(["id":3,"start":0.0,"end":3.0,"text":"x","speaker":"Boran","source":"mic","flags":["cloud_transcript"]])
        XCTAssertEqual(mic.label,"Boran")
        let echo=Row(["id":5,"start":0.0,"end":3.0,"text":"x","speaker":"Boran","source":"mic","flags":["cloud_transcript","possible_echo"]])
        XCTAssertEqual(echo.label,"Hoparlör yankısı")
        let local=Row(["id":4,"start":0.0,"end":3.0,"text":"x","speaker":"S1","source":"system","flags":[]])
        XCTAssertEqual(local.label,"Konuşmacı 2")
    }
    func testEchoRowsHiddenByDefault() {
        let system=Row(["id":1,"start":0.0,"end":50.0,"text":"a","speaker":"Konuşmacı 1","speaker_name":"Sağ üst","source":"system","flags":["cloud_transcript"]])
        let echo=Row(["id":2,"start":0.0,"end":50.0,"text":"a","speaker":"Boran","source":"mic","flags":["cloud_transcript","possible_echo"]])
        XCTAssertEqual(CloudTranscription.visibleRows([echo,system],showEcho:false).map(\.id),[1])
        XCTAssertEqual(CloudTranscription.visibleRows([echo,system],showEcho:true).map(\.id),[2,1])
        XCTAssertEqual(CloudTranscription.hiddenEchoCount([echo,system]),1)
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
