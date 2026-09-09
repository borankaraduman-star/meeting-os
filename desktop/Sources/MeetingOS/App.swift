import SwiftUI
import UserNotifications
import UniformTypeIdentifiers
import AppKit
import AVFoundation

struct Meeting: Identifiable {
    let id: String; let title: String; let status: String; let displayStatus:String; let recoveryState:String; let created: String; let capture:[String:Any]; let metadata: [String:Any]
    let segments:Int; let seconds:Double; let speakers:Int; let names:[String]
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; status=d["status"] as? String ?? ""; displayStatus=d["display_status"] as? String ?? status; recoveryState=d["recovery_state"] as? String ?? "unknown"; created=d["created"] as? String ?? ""; metadata=d["metadata"] as? [String:Any] ?? [:]; capture=d["capture"] as? [String:Any] ?? [:]
        let st=d["stats"] as? [String:Any] ?? [:]; segments=st["segments"] as? Int ?? 0; seconds=st["seconds"] as? Double ?? 0; speakers=st["speakers"] as? Int ?? 0; names=st["names"] as? [String] ?? [] }
}
extension Meeting {
    var captureSourcesEmpty:Bool { (capture["sources"] as? [String:Any] ?? [:]).isEmpty }
    /// Sidebar line under the title: what the finished recording holds, or a plain "no speech" for an empty one.
    var sidebarDetail:String {
        guard status=="complete" else { return statusLabel(displayStatus) }
        if segments==0 { return "Konuşma bulunmadı" }
        let length=seconds>=60 ? "\(Int(seconds/60)) dk" : "\(Int(seconds)) sn"
        return speakers>0 ? "\(length) · \(speakers) kişi" : length
    }
}
struct Row: Identifiable, Equatable {
    let id:Int; let start:Double; let end:Double; let text:String; let speaker:String; let name:String; let source:String; let flags:[String]; let suggested:String
    init(_ d:[String:Any]) { id=d["id"] as? Int ?? 0; start=d["start"] as? Double ?? 0; end=d["end"] as? Double ?? 0; text=d["text"] as? String ?? ""; speaker=d["speaker"] as? String ?? ""; name=d["speaker_name"] as? String ?? ""; source=d["source"] as? String ?? ""; flags=d["flags"] as? [String] ?? []; suggested=d["suggested"] as? String ?? "" }
    var label:String {
        if !name.isEmpty { return name }
        if flags.contains("provisional") { return "Geçici konuşmacı" }
        if !suggested.isEmpty { return suggested+"?" }  // borderline voice match awaiting one-click confirmation
        if flags.contains("possible_echo") { return "Hoparlör yankısı" }  // microphone picked up the speakers; not Boran talking
        if flags.contains("cloud_transcript"), !speaker.isEmpty, speaker != "unknown" { return speaker }  // cloud path stores human-readable cluster labels
        if let tail=speaker.split(separator:":").last, tail.hasPrefix("S"), let n=Int(tail.dropFirst()) { return "Konuşmacı \(n+1)" }
        return "İsimsiz konuşmacı"
    }
    var notices:String {
        let labels=["cloud_transcript":"Bulut transkript · OpenRouter", "cloud_diarization":"Konuşmacı ayrımı · sağlayıcı", "possible_echo":"Hoparlör yankısı olabilir · mikrofon sistem sesini almış", "coarse_timing":"Yaklaşık konuşma aralığı", "imported_text":"Elle aktarılan metin", "speaker_unverified":"Konuşmacı adı doğrulanmadı", "provisional":"Canlı metin · değişebilir", "short_context_diarization":"Konuşmacı için kısa ses örneği", "speaker_ambiguous":"Konuşmacı belirsiz / sesler çakışıyor", "low_asr_confidence":"Bu bölümü dinleyerek kontrol edin", "possible_non_speech":"Konuşma dışı ses olabilir", "repetition":"Tekrar algılandı", "confidence_unavailable":"Güven ölçümü yok", "baseline_diarization":"Temel konuşmacı ayrımı"]
        let shown=flags.contains("cloud_transcript") ? flags.filter { !TranscriptBlocks.meetingWideFlags.contains($0) } : flags
        return shown.filter { $0 != "untimed" }.map { labels[$0] ?? $0 }.joined(separator:" · ")
    }
    var time:String { flags.contains("untimed") ? "" : String(format:"%02d:%02d",Int(start)/60,Int(start)%60) }
}
struct Profile:Identifiable { let name:String; let model:String; let samples:Int; var id:String { name+model } }
struct Runtime:Decodable { let python:String; let repo:String }

func invoke(_ runtime:Runtime,_ request:[String:Any]) throws -> [String:Any] {
    let p=Process(); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os.desktop"]; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo)
    let input=Pipe(), output=Pipe(); p.standardInput=input; p.standardOutput=output; p.standardError=FileHandle.nullDevice
    try p.run()
    let deadline=DispatchWorkItem { if p.isRunning { kill(-p.processIdentifier,SIGTERM); p.terminate() } }
    DispatchQueue.global().asyncAfter(deadline:.now()+10, execute:deadline)
    defer { deadline.cancel() }
    try input.fileHandleForWriting.write(contentsOf:JSONSerialization.data(withJSONObject:request)); try input.fileHandleForWriting.close()
    let data=output.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    guard let result=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Invalid local response"]) }
    if let message=result["error"] as? String { throw NSError(domain:"MeetingOS",code:2,userInfo:[NSLocalizedDescriptionKey:message]) }
    return result
}

@MainActor final class Model:ObservableObject {
    @Published var meetings:[Meeting]=[]; @Published var rows:[Row]=[] { didSet { rebuildBlocks() } }; @Published var profiles:[Profile]=[]
    @Published var selected:String? { didSet { if selected != oldValue { recordingNavigation.selectionChanged(); error=""; rows=[]; analysis=nil; search=""; pendingEvidence=nil; focusedSegment=nil } } }; @Published var search="" { didSet { focusedSegment=nil; pendingEvidence=nil; rebuildBlocks() } }; @Published var title=""; @Published var error=""
    @Published var activity="Hazır · Ses ve metin bu Mac’te kalır"; @Published var recording=false; @Published var busy=false
    @Published var showOpenRouter=false
    @Published var deleteCandidate:Meeting?
    /// Meeting auto-selected on this launch because its processing was interrupted; drives the one-line restore banner.
    @Published var restoredMeeting:String?; var restoredOnLaunch=false
    @Published var storage:StorageReport?
    @Published var transcriptionMode=UserDefaults.standard.string(forKey:CloudTranscription.modeKey) ?? "openrouter" { didSet { UserDefaults.standard.set(transcriptionMode,forKey:CloudTranscription.modeKey) } }
    @Published var cloudModel=UserDefaults.standard.string(forKey:CloudTranscription.modelKey) ?? CloudTranscription.defaultModel { didSet { UserDefaults.standard.set(cloudModel,forKey:CloudTranscription.modelKey) } }
    @Published var cloudModels:[OpenRouterModelOption]=[]
    @Published var vocabulary=""; @Published var showSettings=false; @Published var editRow:Row?; @Published var editName=""; @Published var editText=""; @Published var clean=false
    @Published var tab="transcript" { didSet { if tab != "transcript" { pendingEvidence=nil } } }; @Published var analysis:[String:Any]?; @Published var actions:[ActionItem]=[]; @Published var drafts:[DraftItem]=[]
    @Published var memoryQuery=""; @Published var hits:[Evidence]=[]; @Published var answer=""; @Published var answerEvidence:[Evidence]=[]
    let runtime:Runtime; let dataDir=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MeetingOS")
    @Published var focusedSegment:Int? { didSet { rebuildBlocks() } }
    @Published var pendingEvidence:Evidence?
    var recordingNavigation=RecordingNavigation()
    @Published var jobProgress=""
    var progressURL:URL?;var jobStarted:Date?
    var resourceStopMessage=""
    var pressureSource:DispatchSourceMemoryPressure?
    var requestedQuit=false
    @Published var jobKind:String?; @Published var jobCanceled=false
    @Published var job:Process?; var recordingDir:URL?; var timer:Timer?; var player:AVAudioPlayer?; var refreshing=false
    init() {
        let url=Bundle.main.resourceURL!.appendingPathComponent("runtime.json")
        runtime=(try? JSONDecoder().decode(Runtime.self,from:Data(contentsOf:url))) ?? Runtime(python:"/usr/bin/false",repo:"/tmp")
        AppDelegate.model=self
        let pressure=DispatchSource.makeMemoryPressureSource(eventMask:[.warning,.critical],queue:.main)
        pressure.setEventHandler { [weak self] in Task { @MainActor in self?.stopForResources() } }
        pressure.resume();pressureSource=pressure
        timer=Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in Task { @MainActor in
            guard let self=self else { return }
            self.pollTick+=1
            if RefreshCadence.shouldRefresh(tick:self.pollTick,recording:self.recording,busy:self.busy,active:NSApp.isActive) { await self.refresh() }
        } }
        Task { await refresh() }
    }
    var meeting:Meeting? { meetings.first { $0.id==selected } }
    @Published var showEchoRows=false { didSet { rebuildBlocks() } }
    @Published var review:[ReviewItem]=[]
    @Published var scorecard=""
    @Published var markerCount=0
    /// ⌘M while recording: append one line to markers.jsonl in the capture folder; nothing else changes.
    func markMoment(_ kind:String) {
        guard recording, let dir=recordingDir, let started=jobStarted else { return }
        let seconds=Date().timeIntervalSince(started)
        let url=dir.appendingPathComponent("markers.jsonl")
        let line=Markers.line(seconds:seconds,kind:kind)+"\n"
        if let handle=try? FileHandle(forWritingTo:url) { handle.seekToEndOfFile();handle.write(Data(line.utf8));try? handle.close() }
        else { try? line.write(to:url,atomically:true,encoding:.utf8) }
        markerCount+=1
        activity="İşaretlendi · \(Marker.labels[kind] ?? "Önemli an") · \(String(format:"%02d:%02d",Int(seconds)/60,Int(seconds)%60))"
    }
    /// Draft agenda for the next meeting from recent open tasks, questions and decisions; saved where the user chooses.
    func exportAgenda() async {
        let panel=NSSavePanel();panel.nameFieldStringValue="sonraki-toplanti-gundemi.md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"agenda","path":url.path,"limit":5]); activity="Gündem taslağı kaydedildi · \(r["open_tasks"] as? Int ?? 0) açık görev, \(r["questions"] as? Int ?? 0) soru, \(r["decisions"] as? Int ?? 0) karar" }
        catch { self.error=error.localizedDescription }
    }
    /// End-of-day personal digest: today's tasks, expected answers and decisions that concern the user, with sources; saved where the user chooses.
    func exportDigest() async {
        let formatter=DateFormatter();formatter.dateFormat="yyyy-MM-dd"
        let panel=NSSavePanel();panel.nameFieldStringValue="gun-sonu-ozeti-\(formatter.string(from:Date())).md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"digest","path":url.path]); activity="Gün sonu özeti kaydedildi · \(r["meetings"] as? Int ?? 0) toplantı, \(r["tasks"] as? Int ?? 0) söz, \(r["questions"] as? Int ?? 0) soru, \(r["decisions"] as? Int ?? 0) karar" }
        catch { self.error=error.localizedDescription }
    }
    @Published var showShare=false
    func loadScorecard() async {
        guard let r=try? await request(["action":"quality_report"]), let i=r["identity"] as? [String:Any] else { scorecard=""; return }
        let ok=i["auto_correct"] as? Int ?? 0, wrong=i["auto_wrong"] as? Int ?? 0, conf=i["suggestion_confirmed"] as? Int ?? 0, rej=i["suggestion_rejected"] as? Int ?? 0, missed=i["missed_known"] as? Int ?? 0, edits=r["text_edits"] as? Int ?? 0
        scorecard="Kimlik karnesi · otomatik \(ok) doğru / \(wrong) yanlış · öneri \(conf) onay / \(rej) red · \(missed) kaçırılan · \(edits) metin düzeltmesi"
    }
    @Published var analysisModel=UserDefaults.standard.string(forKey:"cloudAnalysisModel") ?? "openai/gpt-4.1-mini" { didSet { UserDefaults.standard.set(analysisModel,forKey:"cloudAnalysisModel") } }
    /// analyze/prepare/ask run through OpenRouter whenever transcription does; the local Qwen path stays for local mode.
    var cloudAnalysisArguments:[String] { transcriptionMode=="openrouter" ? ["--openrouter-model",analysisModel] : [] }
    /// One line under the title: when, how long, who, what still needs a look. Built from data already loaded.
    var headerStrip:String? {
        guard let m=meeting, m.status=="complete" else { return nil }
        var parts=[MeetingDates.label(m.created)]
        if m.segments>0 { parts.append(m.seconds>=60 ? "\(Int(m.seconds/60)) dk" : "\(Int(m.seconds)) sn"); if m.speakers>0 { parts.append("\(m.speakers) kişi") } } else { parts.append("konuşma yok") }
        let open=openTaskCount; if open>0 { parts.append("\(open) açık görev") }
        if !review.isEmpty { parts.append("\(review.count) kontrol maddesi") }
        return parts.joined(separator:" · ")
    }
    var openTaskCount:Int { actions.filter { $0.meeting==selected && !$0.stale && !["done","dismissed"].contains($0.state) }.count }
    func loadReview() async {
        guard let mid=selected else { review=[]; return }
        do { let r=try await request(["action":"review_queue","meeting":mid]); review=(r["items"] as? [[String:Any]] ?? []).map(ReviewItem.init) } catch { review=[] }
    }
    func confirmReview(_ item:ReviewItem) async {
        guard let mid=selected, !item.suggested.isEmpty, !item.speakerKey.isEmpty else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":item.speakerKey,"name":item.suggested,"enroll":true]); activity="“\(item.suggested)” onaylandı · profil güncellendi"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Name a diarized cluster straight from Kontrol (calendar attendee chip). Enrolls like a confirmed suggestion.
    func nameSpeaker(_ speakerKey:String,_ name:String) async {
        guard let mid=selected, !speakerKey.isEmpty, !name.isEmpty else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":speakerKey,"name":name,"enroll":true]); activity="“\(name)” adlandırıldı · profil güncellendi"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    var calendarAttendees:[String] { (meeting?.metadata["calendar"] as? [String:Any])?["attendees"] as? [String] ?? [] }
    @Published var readingMode=true
    @Published var showAsides=false
    @Published var hideFillers=UserDefaults.standard.object(forKey:"hideFillers") as? Bool ?? true { didSet { UserDefaults.standard.set(hideFillers,forKey:"hideFillers") } }
    var filteredRows:[Row] {
        if let id=focusedSegment { return rows.filter { $0.id==id } }
        let visible=CloudTranscription.visibleRows(rows,showEcho:showEchoRows)
        return search.isEmpty ? visible : visible.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) }
    }
    /// Reading-view paragraphs, rebuilt only when their inputs change. The 2-second status poll must not
    /// re-run block building for every published field (a 1500-row day would pin the CPU again).
    @Published private(set) var blocks:[TranscriptBlock]=[]
    private var blocksKey:Int=0
    func rebuildBlocks() {
        var h=Hasher(); h.combine(rows.count); h.combine(rows.last?.id ?? -1); h.combine(showEchoRows); h.combine(search); h.combine(focusedSegment ?? -1); h.combine(rows.map { $0.name+$0.text }.joined().hashValue)
        let key=h.finalize(); if key==blocksKey && !blocks.isEmpty { return }
        blocksKey=key; blocks=TranscriptBlocks.build(filteredRows)
    }
    func request(_ req:[String:Any]) async throws -> [String:Any] { try await Bridge.call(runtime,req) }
    var jobStopsOnPressure=false
    func stopForResources() {
        guard let process=job, jobStopsOnPressure, resourceStopMessage.isEmpty else { return }
        resourceStopMessage="Bellek baskısı nedeniyle işlem durduruldu. Kaynak ses korunuyor; ağır uygulamaları kapatıp yeniden deneyin."
        error=resourceStopMessage
        if recording { stop() } else { process.terminate() }
    }
    @Published var microphoneHint=""
    func refresh() async {
        microphoneHint=MicrophoneHint.current()
        if let process=job, let bytes=ResourceGuard.footprint(pid:process.processIdentifier), bytes>ResourceGuard.budget(physical:ProcessInfo.processInfo.physicalMemory) { stopForResources() }
        if job != nil, let started=jobStarted {
            let elapsed=Int(Date().timeIntervalSince(started))
            let progress=progressURL.flatMap { try? Data(contentsOf:$0) }.flatMap { try? JSONDecoder().decode(JobProgress.self,from:$0) }
            jobProgress=(progress?.label ?? activity)+" · \(elapsed/60) dk \(elapsed%60) sn"
        }
        guard !refreshing else { return }; refreshing=true
        let wanted=selected ?? ""
        defer {
            refreshing=false
            // A selection change during an awaited snapshot must load immediately.
            if wanted != (selected ?? "") { Task { await self.refresh() } }
        }
        do {
            let result=try await request(["action":"snapshot","meeting":wanted])
            meetings=(result["meetings"] as? [[String:Any]] ?? []).map(Meeting.init)
            profiles=(result["profiles"] as? [[String:Any]] ?? []).map { Profile(name:$0["name"] as? String ?? "",model:$0["model"] as? String ?? "",samples:$0["samples"] as? Int ?? 0) }
            if recording, let dir=recordingDir, let active=meetings.first(where:{ $0.metadata["capture_dir"] as? String==dir.path }) {
                if let target=recordingNavigation.resolve(active:active.id) { selected=target }
                activity=CaptureSignalPresentation.label(active.capture)
                captureDots=["mic":CaptureSignalPresentation.dotState(active.capture,key:"mic"),"system":CaptureSignalPresentation.dotState(active.capture,key:"system")]
            }
            if !restoredOnLaunch {
                restoredOnLaunch=true
                if !recording, job==nil, let restore=RelaunchRestore.pick(meetings:meetings) { selected=restore.id; restoredMeeting=restore.id }
            }
            if selected==nil && !recording { selected=meetings.first?.id }
            let zoomState=ZoomWatch.state(); let zoomNow=zoomState.open
            if zoomNow && !zoomMeetingOpen && !recording && zoomNotify && !zoomAutoRecord { ZoomNotifier.notifyIfNeeded() }
            if !zoomNow { ZoomNotifier.reset() }
            zoomMeetingOpen=zoomNow
            applyLivePriority(zoomOpen:zoomState.strict)
            heartbeatIfDue()
            switch zoomAuto.evaluate(zoomOpen:zoomState.strict,recording:recording,busy:busy,enabled:zoomAutoRecord && !requestedQuit) {
            case .start: start(); activity="Zoom toplantısı açıldı · kayıt kendiliğinden başladı"; notifyDone("Kayıt başladı","Zoom toplantısı açık; bitirmek için ⌃⌥R veya menü çubuğu.")
            case .stop: stop(); activity="Zoom toplantısı kapandı · kayıt bitiriliyor"
            case nil: break
            }
            if recording, let started=jobStarted { let s=Int(Date().timeIntervalSince(started)); elapsedText=String(format:"%02d:%02d",s/60,s%60) }
            if lastUpdateCheck==nil || Date().timeIntervalSince(lastUpdateCheck!) >= 6*3600 { Task { await checkForUpdates() } }
            if NSApp.isActive, let last=lastUpdateCheck, Date().timeIntervalSince(last) >= 60*60 { Task { await checkForUpdates() } }
            if wanted==selected { let nextRows=(result["segments"] as? [[String:Any]] ?? []).map(Row.init); let changed=rows != nextRows; if changed { rows=nextRows }; resolvePendingEvidence(); try await refreshIntelligence(wanted); if changed, !recording, meeting?.status=="complete" { await loadReview() } }
        } catch { self.error=error.localizedDescription }
    }
    func launch(_ args:[String], complete:@escaping (Bool)->Void) {
        guard job==nil else { return }
        do {
            try FileManager.default.createDirectory(at:dataDir,withIntermediateDirectories:true)
            let log=dataDir.appendingPathComponent("last-job.log")
            FileManager.default.createFile(atPath:log.path,contents:nil)
            let handle=try FileHandle(forWritingTo:log)
            resourceStopMessage="";jobCanceled=false;jobKind=args.first;jobStopsOnPressure=ResourceGuard.stopsOnPressure(jobArguments:args)
            let progress=dataDir.appendingPathComponent("progress/"+UUID().uuidString+".json")
            progressURL=progress;jobStarted=Date();jobProgress="İşlem başlatılıyor"
            let p=Process();p.environment=ProcessInfo.processInfo.environment.merging(["MEETING_OS_PROGRESS_PATH":progress.path]) { _,new in new }.merging(JobPriority.environment(args:args,zoomOpen:zoomMeetingOpen)) { _,new in new }.merging(["MEETING_OS_LOW_PRIORITY_FLAG":lowPriorityFlag.path]) { _,new in new };p.qualityOfService=JobPriority.qos(args:args,zoomOpen:zoomMeetingOpen); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os"]+args; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo); p.standardOutput=handle; p.standardError=handle
            p.terminationHandler={ [weak self] process in
                try? handle.close()
                let jobError=ErrorPresentation.logSummary(log)
                Task { @MainActor in
                    guard let self=self else { return }; self.job=nil; self.jobKind=nil; self.busy=false; self.jobProgress=""; self.progressURL=nil; self.jobStarted=nil; try? FileManager.default.removeItem(at:progress)
                    if process.terminationStatus != 0 && !self.jobCanceled { self.error=self.resourceStopMessage.isEmpty ? jobError : self.resourceStopMessage }
                    complete(process.terminationStatus==0 && self.resourceStopMessage.isEmpty && !self.jobCanceled); await self.refresh(); if self.requestedQuit && self.job==nil { NSApp.reply(toApplicationShouldTerminate:true) }
                }
            }
            try p.run(); job=p; busy=true; error=""; jobBackgrounded=false
        } catch { self.error=error.localizedDescription; busy=false; jobKind=nil; recording=false; recordingNavigation.cancel() }
    }
    func start() {
        guard job==nil else { return }
        recordingNavigation.begin()
        let dir=dataDir.appendingPathComponent("recordings/"+UUID().uuidString)
        recordingDir=dir; recording=true; markerCount=0; activity="Kayıt hazırlanıyor · macOS izinleri açık olmalı"; DisplaySleepGuard.begin(); if showRecorderPanel { RecorderPanel.show(model:self) }
        pendingCalendar=useCalendar ? CalendarContext.current() : nil
        let name=title.isEmpty ? (pendingCalendar?.title ?? Date().formatted(Date.FormatStyle(date:.abbreviated,time:.shortened,locale:Locale(identifier:"tr_TR")))) : title   // "9 Eyl 2026 14:05"
        if title.isEmpty, let cal=pendingCalendar { activity="Takvimden: \(cal.title)"+(cal.attendees.isEmpty ? "" : " · \(cal.attendees.count) katılımcı") }
        recordingTitle=name
        let receipt=dataDir.appendingPathComponent("record-\(UUID().uuidString).json")
        launch(CloudTranscription.recordArguments(mode:transcriptionMode,directory:dir.path,title:name,receipt:receipt.path)) { [weak self] ok in
            guard let self=self else { return }; self.recording=false; self.recordingNavigation.cancel(); DisplaySleepGuard.end(); RecorderPanel.hide()
            let result=(try? Data(contentsOf:receipt)).flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] } ?? [:]
            try? FileManager.default.removeItem(at:receipt)
            if !ok { self.activity="Kayıt tamamlanamadı · Arşivdeki kayıt durumunu kontrol edin" }
            else if let mid=RecordingCompletion.retryMeeting(result,capture:dir.path) {
                if self.requestedQuit { self.activity="Kayıt saklandı · Son işlemi arşivden başlatabilirsiniz" }
                else { self.finishRecordedMeeting(mid) }
            } else if ok && result["status"] as? String == "canceled" { self.activity="Kayıt iptal edildi · Ses alınmadı" }
            else { self.activity="Kayıt saklandı · Son işlem otomatik başlatılamadı" }
        }
    }
    func stop() { guard recording else { return }; recordingNavigation.cancel(); activity="Ses parçaları tamamlanıyor…"; recording=false; job?.interrupt() }
    func finishRecordedMeeting(_ mid:String) {
        if let cal=pendingCalendar { pendingCalendar=nil; Task { _=try? await request(["action":"meeting_context","meeting":mid,"calendar":cal.payload]) } }
        if transcriptionMode=="openrouter" { finalizeWithOpenRouter(mid,model:cloudModel); return }
        activity="Aynı toplantının son transkripti hazırlanıyor…"
        launch(["retry",mid]) { [weak self] ok in
            guard let self=self else { return }
            if ok {
                if self.requestedQuit { self.activity="Transkript hazır" }
                else { self.analyzeAutomatically(mid) }
            }
            else { self.activity=self.jobCanceled ? "İşlem durduruldu · Kaynak kayıt korunuyor" : "Son işlem başarısız · Önceki metin ve ses korunuyor" }
        }
    }
    /// Cloud-only transcription of a stopped recording. Pass a model only for a recording that has not started in the cloud yet.
    func finalizeWithOpenRouter(_ mid:String,model:String?) {
        guard job==nil else { return }
        let result=dataDir.appendingPathComponent("openrouter-\(UUID().uuidString).json")
        let stored=meetings.first(where:{ $0.id==mid })?.metadata["cloud_mode"] != nil
        activity="Ses OpenRouter’a gönderiliyor · Bu Mac’te model yüklenmiyor"
        launch(CloudTranscription.finalizeArguments(meeting:mid,model:stored ? nil : model,output:result.path)) { [weak self] ok in
            guard let self else { return }
            defer { try? FileManager.default.removeItem(at:result) }
            if ok {
                self.selected=mid;self.tab="transcript"
                let count=(try? Data(contentsOf:result)).flatMap { try? JSONSerialization.jsonObject(with:$0) as? [String:Any] }?["segments"] as? Int ?? 0
                if count==0 { self.activity="Kayıtta konuşma bulunmadı · analiz başlatılmadı" }
                else { self.activity="Transkript OpenRouter’dan alındı · Konuşmacı adlarını kontrol edin"; if !NSApp.isActive { self.notifyDone("Transkript hazır","Konuşmacı adlarını Kontrol sekmesinden onaylayın.") }; if !self.requestedQuit { self.analyzeAutomatically(mid) } }
            }
            else { self.activity=self.jobCanceled ? "İşlem durduruldu · Ses ve tamamlanan parçalar korunuyor" : "OpenRouter işlemi tamamlanamadı · Tamamlanan parçalar korunuyor, ‘OpenRouter ile yazıya çevir’ ile sürdürün" }
        }
    }
    func loadCloudModels() async {
        guard cloudModels.isEmpty else { return }
        do {
            let response=try await request(["action":"openrouter_models"])
            let data=try JSONSerialization.data(withJSONObject:response["models"] ?? [])
            cloudModels=try JSONDecoder().decode([OpenRouterModelOption].self,from:data)
            if !cloudModels.contains(where:{ $0.id==cloudModel }) { cloudModel=(response["diarization_default"] as? String) ?? CloudTranscription.defaultModel }
        } catch { self.error=error.localizedDescription }
    }
    var canCancelJob:Bool { RecoveryPresentation.canCancel(jobKind:jobKind,running:job?.isRunning == true,requested:jobCanceled) }
    func cancelJob() {
        guard canCancelJob else { return }
        jobCanceled=true;activity="İşlem durduruluyor · Kaynak kayıt korunuyor";job?.interrupt()
    }
    func recover() {
        guard job==nil, let m=meeting, RecoveryPresentation.canRetry(status:m.status,hasCapture:!m.captureSourcesEmpty,owner:m.recoveryState) else { return }
        let mid=m.id;activity="Kayıt kontrol ediliyor ve aynı toplantı yeniden işleniyor…"
        launch(["retry",mid]) { [weak self] ok in
            guard let self=self else { return }
            self.activity=ok ? "Toplantı kurtarıldı" : self.jobCanceled ? "İşlem durduruldu · Kaynak kayıt korunuyor" : "Kurtarma tamamlanamadı · Önceki metin korunuyor"
        }
    }
    func exportDiagnostics() async {
        let panel=NSSavePanel();panel.nameFieldStringValue="MeetingOS-tanilama-\(UUID().uuidString.prefix(8)).json"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        var payload:[String:Any]=["action":"diagnostics","path":url.path]
        if let progress=progressURL { payload["progress"]=progress.path }
        do { _=try await request(payload);activity="Tanılama raporu kaydedildi · Toplantı içeriği dahil değil" }
        catch { self.error=error.localizedDescription }
    }
    func saveLabel(enroll:Bool) async {
        guard let row=editRow, let mid=selected else { return }
        guard !enroll || meeting?.metadata["text_only"] as? Bool != true else { return }
        do {
            _=try await request(["action":enroll ? "enroll":"label","meeting":mid,"segment":row.id,"name":editName,"confirmed_clean":clean])
            editRow=nil; await refresh()
        } catch { self.error=error.localizedDescription }
    }
    /// Names a provider-diarized speaker cluster for the whole meeting; with enroll, the cluster centroid becomes a voice profile.
    func saveSpeaker(enroll:Bool) async {
        guard let row=editRow, let mid=selected, !row.speaker.isEmpty else { return }
        do {
            let result=try await request(["action":"label_speaker","meeting":mid,"speaker":row.speaker,"name":editName,"enroll":enroll])
            editRow=nil
            if enroll { activity=(result["profile_saved"] as? Bool)==true ? "Konuşmacı adlandırıldı · Ses profili kaydedildi, sonraki toplantılarda otomatik tanınır" : "Konuşmacı adlandırıldı · Yeterli temiz ses olmadığı için profil kaydedilmedi" }
            await refresh()
        } catch { self.error=error.localizedDescription }
    }
    /// One click turns a “Sol Üst?” suggestion into the cluster name and, when there is enough speech, a profile sample.
    func confirmSuggestion(_ row:Row) async {
        guard !row.suggested.isEmpty, let mid=selected, !busy else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":row.speaker,"name":row.suggested,"enroll":true]); activity="“\(row.suggested)” onaylandı · profil güncellendi"; await refresh() }
        catch { self.error=error.localizedDescription }
    }
    func saveText() async {
        guard let row=editRow, let mid=selected else { return }
        do { _=try await request(["action":"edit_text","meeting":mid,"segment":row.id,"text":editText]); editRow=nil; await refresh() } catch { self.error=error.localizedDescription }
    }
    func deleteMeeting(_ meeting:Meeting) async {
        guard !busy else { return }
        do {
            _=try await request(["action":"delete_meeting","meeting":meeting.id])
            if selected==meeting.id { selected=nil;rows=[] }
            activity="Toplantı silindi · Ses profilleri korundu"
            await refresh()
        } catch { self.error=error.localizedDescription }
    }
    func deleteProfile(_ name:String) async { do { _=try await request(["action":"delete_profile","name":name]); await refresh() } catch { self.error=error.localizedDescription } }
    func export(_ format:String) async {
        guard let mid=selected else { return }; let panel=NSSavePanel(); panel.nameFieldStringValue="Meeting.\(format)"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { _=try await request(["action":format=="analysis.md" ? "export_analysis":"export","meeting":mid,"path":url.path,"format":format]); activity="Dışa aktarıldı: \(url.lastPathComponent)" } catch { self.error=error.localizedDescription }
    }
    /// Sidebar search: matches title, date and the auto-title words, case- and diacritic-insensitively.
    @Published var filter=""
    var visibleMeetings:[Meeting] {
        let q=filter.trimmingCharacters(in:.whitespaces)
        if q.isEmpty { return meetings }
        return meetings.filter { ($0.title+" "+$0.created+" "+$0.names.joined(separator:" ")+" "+MeetingDates.label($0.created)).range(of:q,options:[.caseInsensitive,.diacriticInsensitive]) != nil }
    }
    /// Sidebar sections in display order; empty groups are omitted.
    var groupedMeetings:[(String,[Meeting])] {
        let now=Date(); let byGroup=Dictionary(grouping:visibleMeetings) { MeetingDates.group($0.created,now:now) }
        return MeetingDates.order.compactMap { g in byGroup[g].map { (g,$0) } }
    }
    /// Bumped by ⌘F / ⌘⇧F; the field that owns the token takes focus.
    @Published var searchFocusToken=0; @Published var memoryFocusToken=0
    func focusTranscriptSearch() { tab="transcript"; searchFocusToken+=1 }
    func focusMemorySearch() { tab="memory"; memoryFocusToken+=1 }
    @Published var cost:[String:Any]?
    @Published var setupChecks:[SetupCheck]=[]
    func loadSetupStatus() async {
        var checks=SetupStatus.permissionChecks(calendarWanted:useCalendar)
        let settings=await UNUserNotificationCenter.current().notificationSettings()
        checks.append(SetupStatus.notificationCheck(settings))
        if let r=try? await request(["action":"setup_status"]) { checks+=SetupStatus.serviceChecks(r) }
        setupChecks=checks
    }
    @Published var glossaryCount=0; @Published var glossaryFromFile=0; @Published var glossarySample:[String]=[]
    @Published var zoomMeetingOpen=false; @Published var elapsedText="00:00"
    /// Read the calendar when a recording starts: the live event names the meeting and its attendees become naming shortcuts.
    @Published var useCalendar=UserDefaults.standard.object(forKey:"useCalendar") as? Bool ?? false {
        didSet {
            UserDefaults.standard.set(useCalendar,forKey:"useCalendar")
            if useCalendar && !CalendarContext.authorized { CalendarContext.requestAccess { [weak self] ok in if !ok { self?.useCalendar=false; self?.error="Takvim erişimi verilmedi · Sistem Ayarları → Gizlilik ve Güvenlik → Takvimler" } } }
        }
    }
    var pendingCalendar:CalendarEvent?
    var pollTick=0
    /// Hourly heartbeat into the shared iCloud folder so a day without a finished meeting still leaves a trace.
    var lastHeartbeat:Date?
    func heartbeatIfDue() {
        guard !recording, job==nil, lastHeartbeat.map({ Date().timeIntervalSince($0) >= 3600 }) ?? true else { return }
        lastHeartbeat=Date()
        Task {
            _=try? await request(["action":"heartbeat","app":["version":Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "","bridge":BridgeStats.shared.snapshot]])
            if !recording, job==nil, let r=try? await request(["action":"storage_housekeeping"]) {
                let archived=r["archived_bytes"] as? Int ?? 0, removed=r["removed_bytes"] as? Int ?? 0
                if archived+removed>0 { activity="Depolama · \(StorageReport.format(bytes:archived)) sıkıştırıldı, \(StorageReport.format(bytes:removed)) eski ses silindi" }
            }
        }
    }
    // Cross-meeting PM views (loaded on demand, never while recording)
    @Published var decisions:[DecisionEntry]=[]; @Published var waiting:[WaitingPerson]=[]; @Published var debt:[DebtItem]=[]; @Published var debtSummary=""
    func loadDecisions(query:String) async {
        guard !recording else { return }
        if let r=try? await request(["action":"decision_log","query":query,"limit":200]) { decisions=(r["decisions"] as? [[String:Any]] ?? []).enumerated().map { DecisionEntry($0.element,index:$0.offset) } }
    }
    func exportDecisions(query:String) async {
        let panel=NSSavePanel(); panel.nameFieldStringValue="karar-defteri.md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"decision_log_export","path":url.path,"query":query]); activity="Karar defteri kaydedildi · \(r["decisions"] as? Int ?? 0) karar" } catch { self.error=error.localizedDescription }
    }
    func loadWaiting() async {
        guard !recording else { return }
        if let r=try? await request(["action":"waiting_board"]) { waiting=(r["people"] as? [[String:Any]] ?? []).map(WaitingPerson.init) }
    }
    func loadReviewDebt() async {
        guard !recording else { return }
        if let r=try? await request(["action":"review_debt","days":7]) {
            debt=(r["items"] as? [[String:Any]] ?? []).map(DebtItem.init)
            let counts=r["counts"] as? [String:Int] ?? [:]
            let names=["unnamed_speaker":"isimsiz konuşmacı","suggested_name":"isim onayı","glossary":"sözlük","task_owner":"sahipsiz görev","short_match":"kısa eşleşme","ambiguous":"çakışma","marker":"işaret"]
            debtSummary=counts.sorted { $0.value>$1.value }.map { "\($0.value) \(names[$0.key] ?? $0.key)" }.joined(separator:", ")
        }
    }
    func exportWeeklyDigest() async {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd"; let to=Date(); let from=Calendar.current.date(byAdding:.day,value:-6,to:to) ?? to
        let panel=NSSavePanel(); panel.nameFieldStringValue="hafta-ozeti-\(f.string(from:to)).md"; panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"digest","path":url.path,"from":f.string(from:from),"to":f.string(from:to)]); activity="Hafta özeti kaydedildi · \(r["meetings"] as? Int ?? 0) toplantı, \(r["decisions"] as? Int ?? 0) karar, \(r["tasks"] as? Int ?? 0) söz" }
        catch { self.error=error.localizedDescription }
    }
    /// Evidence / review navigation: scroll the reading view to the paragraph and flash it, keeping context around it.
    @Published var revealTarget:Int?; @Published var revealToken=0; @Published var highlighted:Int?
    func reveal(segment id:Int) {
        tab="transcript"; search=""; focusedSegment=nil; revealTarget=id; revealToken+=1; highlighted=id
        let token=revealToken
        DispatchQueue.main.asyncAfter(deadline:.now()+2.5) { [weak self] in if self?.revealToken==token { self?.highlighted=nil } }
    }
    /// Paragraph that contains a segment (evidence may point at a non-lead row of a block).
    func blockId(containing id:Int)->Int? { blocks.first { $0.rows.contains { $0.id==id } || $0.asides.contains { $0.id==id } }?.id }
    /// Live capture health for the floating panel (mic / system audio), refreshed with every poll while recording.
    @Published var captureDots:[String:String]=[:]
    /// A job that started before the next Zoom meeting opened is pushed to Darwin background (CPU, I/O and
    /// network throttled) and told to upload one piece at a time; both are undone when the meeting ends.
    var jobBackgrounded=false
    var lowPriorityFlag:URL { dataDir.appendingPathComponent("low-priority.flag") }
    func applyLivePriority(zoomOpen:Bool) {
        guard let p=job, jobKind != "record" else { if jobBackgrounded { jobBackgrounded=false; try? FileManager.default.removeItem(at:lowPriorityFlag) }; return }
        guard zoomOpen != jobBackgrounded else { return }
        jobBackgrounded=zoomOpen
        setpriority(PRIO_DARWIN_PROCESS,id_t(p.processIdentifier),zoomOpen ? PRIO_DARWIN_BG : 0)   // 0 = PRIO_DARWIN_NORMAL (not exported to Swift)
        if zoomOpen { try? Data().write(to:lowPriorityFlag); activity="Zoom toplantısı açıldı · arka plan işi yavaşlatıldı, tek yükleyici" }
        else { try? FileManager.default.removeItem(at:lowPriorityFlag); activity="Zoom toplantısı bitti · arka plan işi normal hızda" }
    }
    /// Send one task to Apple Reminders; asks for reminders access on first use.
    func addReminder(_ item:ActionItem) {
        let go={ [weak self] in
            guard let self=self else { return }
            do { try RemindersBridge.add(title:item.title,meetingTitle:item.meetingTitle,owner:item.owner,due:item.due); self.activity="Hatırlatıcılar’a eklendi · “\(item.title.prefix(60))”" }
            catch { self.error="Hatırlatıcı eklenemedi: \(error.localizedDescription)" }
        }
        if RemindersBridge.authorized { go() }
        else { RemindersBridge.requestAccess { [weak self] ok in if ok { go() } else { self?.error="Hatırlatıcılar erişimi verilmedi · Sistem Ayarları → Gizlilik ve Güvenlik → Hatırlatıcılar" } } }
    }
    /// Title of the recording in progress, shown on the floating panel.
    @Published var recordingTitle=""
    /// Hands-free Zoom: start when a meeting window has been open ~10 s, stop an auto-started recording 60 s after it closes.
    @Published var zoomAutoRecord=UserDefaults.standard.object(forKey:"zoomAutoRecord") as? Bool ?? false { didSet { UserDefaults.standard.set(zoomAutoRecord,forKey:"zoomAutoRecord") } }
    var zoomAuto=ZoomAutoRecord()
    @Published var showRecorderPanel=UserDefaults.standard.object(forKey:"showRecorderPanel") as? Bool ?? true { didSet { UserDefaults.standard.set(showRecorderPanel,forKey:"showRecorderPanel"); if !showRecorderPanel { RecorderPanel.hide() } else if recording { RecorderPanel.show(model:self) } } }
    @Published var zoomNotify=UserDefaults.standard.object(forKey:"zoomNotify") as? Bool ?? true { didSet { UserDefaults.standard.set(zoomNotify,forKey:"zoomNotify"); if zoomNotify { ZoomNotifier.register() } } }
    @Published var explanation:IdentityExplanation?
    @Published var continuity=Continuity()
    @Published var renaming=false; @Published var renameText=""
    func renameMeeting() async {
        guard let mid=selected else { return }
        do { _=try await request(["action":"rename_meeting","meeting":mid,"title":renameText]); renaming=false; await refresh() } catch { self.error=error.localizedDescription }
    }
    /// Finished work reaches the user even when Zoom or another app is in front.
    func notifyDone(_ title:String,_ body:String) {
        let content=UNMutableNotificationContent(); content.title=title; content.body=body
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier:"done-"+UUID().uuidString,content:content,trigger:nil))
    }
    struct CleanupPreview:Equatable { let days:Int; let count:Int; let bytes:Int; let titles:[String] }
    @Published var cleanupPreview:CleanupPreview?
    @Published var cleanupDays=30
    /// Dry run first; nothing is removed until the confirmation button calls with dryRun=false.
    func previewCleanup() async {
        do { let r=try await request(["action":"storage_cleanup","days":cleanupDays,"dry_run":true]); let list=r["meetings"] as? [[String:Any]] ?? []
            cleanupPreview=CleanupPreview(days:cleanupDays,count:list.count,bytes:r["bytes"] as? Int ?? 0,titles:list.prefix(6).compactMap { $0["title"] as? String }) }
        catch { self.error=error.localizedDescription }
    }
    func runCleanup() async {
        do { let r=try await request(["action":"storage_cleanup","days":cleanupDays,"dry_run":false]); activity="Eski sesler temizlendi · \((r["meetings"] as? [[String:Any]])?.count ?? 0) toplantı, \(StorageReport.format(bytes:r["bytes"] as? Int ?? 0)) boşaldı · transkriptler duruyor"; cleanupPreview=nil; storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse) }
        catch { self.error=error.localizedDescription }
    }
    func compactStorage() async {
        do { let r=try await request(["action":"storage_compact"]); let ab=r["archived_bytes"] as? Int ?? 0; activity="Sesler sıkıştırıldı · parçalardan \(StorageReport.format(bytes:r["bytes"] as? Int ?? 0)), FLAC’ten \(StorageReport.format(bytes:ab)) boşaldı (\(r["archived_meetings"] as? Int ?? 0) toplantı)"; storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse) }
        catch { self.error=error.localizedDescription }
    }
    func keepMeeting(_ id:String,keep:Bool) async { do { _=try await request(["action":"keep_meeting","meeting":id,"keep":keep]); await refresh() } catch { self.error=error.localizedDescription } }
    /// Meeting → PRD / bug report / customer request / Claude Code prompt, saved where the user chooses. Cloud mode only.
    func exportDocument(kind:String) async {
        guard let mid=selected, transcriptionMode=="openrouter" else { self.error="Belge hazırlama OpenRouter modunda çalışır (Yazıya çevirme: OpenRouter)"; return }
        let names=["prd":"prd","bug":"hata-raporu","customer":"musteri-talebi","claude":"claude-code-istemi"]
        let panel=NSSavePanel();panel.nameFieldStringValue="\(names[kind] ?? kind)-\(mid.prefix(6)).md";panel.allowedContentTypes=[UTType.plainText]
        guard panel.runModal() == .OK, let url=panel.url else { return }
        busy=true; activity="Belge hazırlanıyor (\(analysisModel))…"
        defer { busy=false }
        do { let r=try await request(["action":"document","meeting":mid,"kind":kind,"path":url.path,"openrouter_model":analysisModel]); activity="Belge kaydedildi · \(r["title"] as? String ?? "") · \(r["sources"] as? Int ?? 0) kaynak bölüm" }
        catch { self.error=error.localizedDescription }
    }
    func loadContinuity() async { guard let mid=selected else { continuity=Continuity(); return }; continuity=(try? await request(["action":"continuity","meeting":mid])).map(Continuity.parse) ?? Continuity() }
    func supersede(old:String,new:String) async {
        do { _=try await request(["action":"supersede_task","old":old,"new":new]); activity="Önceki görev kapatıldı; bu görev devamı sayılıyor"; if let mid=selected { try await refreshIntelligence(mid) }; await loadContinuity() } catch { self.error=error.localizedDescription }
    }
    func loadSamples(_ name:String) async -> [VoiceSample] { ((try? await request(["action":"profile_samples","name":name]))?["samples"] as? [[String:Any]] ?? []).map(VoiceSample.init) }
    func deleteSample(_ id:Int) async { do { _=try await request(["action":"delete_sample","sample":id]); await refresh() } catch { self.error=error.localizedDescription } }
    func renameProfile(_ name:String,to newName:String) async {
        do { let r=try await request(["action":"rename_profile","name":name,"new_name":newName]); activity=(r["merged"] as? Bool)==true ? "“\(name)” → “\(newName)” birleştirildi" : "“\(name)” → “\(newName)” yeniden adlandırıldı"; await refresh() } catch { self.error=error.localizedDescription }
    }
    func explainIdentity(_ row:Row) async {
        guard let mid=selected else { return }
        explanation=(try? await request(["action":"explain_identity","meeting":mid,"speaker":row.speaker])).map(IdentityExplanation.parse)
    }
    func showMainWindow() { NSApp.activate(ignoringOtherApps:true); NSApp.windows.first(where:{ $0.title=="Meeting OS" })?.makeKeyAndOrderFront(nil) }
    /// Global hot key dispatch (⌃⌥R / ⌃⌥M) — same guards as the buttons.
    func hotkey(_ id:UInt32) {
        if id==GlobalHotkeys.record { if recording { stop() } else if !busy { start(); activity="Kayıt başladı · ⌃⌥R ile bitir, ⌃⌥M ile an işaretle" } }
        else if id==GlobalHotkeys.mark, recording { markMoment("important") }
    }
    @Published var update:UpdateInfo?; @Published var updating=false; @Published var reportSettings=ReportSettings(shareReports:true,shareText:false,autoUpdate:false,reportDir:"")
    var lastUpdateCheck:Date?
    /// Called after the first snapshot and every six hours; a fetch, nothing more.
    func checkForUpdates(force:Bool=false) async {
        if !force, let last=lastUpdateCheck, Date().timeIntervalSince(last) < 60*60 { return }   // on launch, on activation, at most hourly
        lastUpdateCheck=Date()
        if let status=try? await request(["action":"update_status"]), let state=status["state"] as? String, let msg=status["message"] as? String, state != "running", UserDefaults.standard.string(forKey:"lastShownUpdate") != (status["time"] as? String ?? "") {
            UserDefaults.standard.set(status["time"] as? String ?? "",forKey:"lastShownUpdate"); activity=(state=="done" ? "Güncelleme tamam · " : "Güncelleme başarısız · ")+msg
        }
        if let r=try? await request(["action":"update_check"]) { update=UpdateInfo.parse(r) }
        if let r=try? await request(["action":"report_settings"]) { reportSettings=ReportSettings.parse(r) }
        if reportSettings.autoUpdate, update?.available==true, job==nil, !recording, !zoomMeetingOpen { startUpdate() }
    }
    /// Hands over to the detached updater and quits; the updater rebuilds, re-signs and relaunches.
    func startUpdate() {
        guard job==nil, !recording, !updating else { return }
        if zoomMeetingOpen { activity="Zoom toplantısı açıkken güncelleme yapılmaz · toplantı bitince tekrar deneyin"; return }   // a rebuild would steal the meeting's CPU
        updating=true; activity="Güncelleniyor · uygulama kapanıp yeniden açılacak"
        Task { do { _=try await request(["action":"update_start"]); try? await Task.sleep(nanoseconds:600_000_000); NSApp.terminate(nil) } catch { self.error=error.localizedDescription; updating=false } }
    }
    func saveReportSettings() async {
        do { let r=try await request(["action":"report_settings_set","changes":reportSettings.changes]); reportSettings=ReportSettings.parse(r) } catch { self.error=error.localizedDescription }
    }
    func loadGlossarySummary() async {
        guard let r=try? await request(["action":"glossary_summary"]) else { return }
        glossaryCount=r["count"] as? Int ?? 0; glossaryFromFile=r["from_file"] as? Int ?? 0; glossarySample=r["sample"] as? [String] ?? []
    }
    /// Import a Slack-agent glossary (JSON Lines with a "term" field) into the data folder.
    func importGlossary() async {
        let panel=NSOpenPanel();panel.canChooseDirectories=false;panel.allowsMultipleSelection=false
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { let r=try await request(["action":"glossary_import","path":url.path]); activity="Sözlük içe aktarıldı · \(r["imported"] as? Int ?? 0) terim, \(r["skipped"] as? Int ?? 0) satır atlandı"; await loadGlossarySummary() }
        catch { self.error=error.localizedDescription }
    }
    /// Re-scan the selected meeting against the glossary; in cloud mode the analysis model reviews each proposal.
    func scanGlossary() async {
        guard let mid=selected, !busy else { return }
        var req:[String:Any]=["action":"glossary_suggest","meeting":mid]
        if transcriptionMode=="openrouter" { req["openrouter_model"]=analysisModel }
        do { let r=try await request(req); let n=(r["suggestions"] as? [[String:Any]])?.count ?? 0; activity="Sözlük taraması bitti · \(n) öneri"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    func applyGlossary(_ item:ReviewItem) async {
        guard let mid=selected, let seg=item.segment else { return }
        do { _=try await request(["action":"glossary_apply","meeting":mid,"segment":seg,"original":item.original,"replacement":item.replacement]); activity="Uygulandı · “\(item.original)” → “\(item.replacement)”"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Apply every model-verified glossary proposal of the selected meeting in one pass; local-only guesses stay for manual review.
    func applyAllGlossary() async {
        guard let mid=selected, !busy else { return }
        do { let r=try await request(["action":"glossary_apply_all","meeting":mid,"verified_only":true]); activity="Sözlük · \(r["applied"] as? Int ?? 0) düzeltme uygulandı, \(r["remaining"] as? Int ?? 0) öneri elle kontrol bekliyor"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    /// Drop one glossary proposal without changing the text.
    func dismissGlossary(_ item:ReviewItem) async {
        guard let mid=selected, let seg=item.segment else { return }
        do { _=try await request(["action":"glossary_dismiss","meeting":mid,"segment":seg,"original":item.original]); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    func settings() async {
        do {
            vocabulary=try await request(["action":"vocabulary"])["text"] as? String ?? ""
            await loadGlossarySummary()
            storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse)   // read-only walk; a failure hides the section only
            cost=try? await request(["action":"cost_report"])
            await loadSetupStatus()
            showSettings=true
        } catch { self.error=error.localizedDescription }
    }
    /// From the storage list: close the sheet first so the sidebar's confirmation dialog can present.
    func requestDelete(meetingID:String) {
        guard let meeting=meetings.first(where:{ $0.id==meetingID }) else { return }
        showSettings=false
        DispatchQueue.main.asyncAfter(deadline:.now()+0.35) { [weak self] in self?.deleteCandidate=meeting }
    }
    func saveVocabulary() async { do { _=try await request(["action":"vocabulary","text":vocabulary]); showSettings=false } catch { self.error=error.localizedDescription } }
    func play(_ row:Row) {
        guard let m=meeting else { return }
        do {
            var path=(m.metadata["paths"] as? [String:String])?[row.source]; var start=row.start
            if path==nil, let dir=m.metadata["capture_dir"] as? String {
                let base=URL(fileURLWithPath:dir); let native=base.appendingPathComponent("capture-native.jsonl")
                let journal=FileManager.default.fileExists(atPath:native.path) ? native : base.appendingPathComponent("events.jsonl")
                let lines=try String(contentsOf:journal,encoding:.utf8).split(separator:"\n")
                for line in lines {
                    if let d=try? JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any], d["source"] as? String==row.source, let a=d["start"] as? Double, let duration=d["duration"] as? Double, row.start>=a, row.start<a+duration { path=d["path"] as? String; start=row.start-a; break }
                }
            }
            guard let path=path else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Ses dosyası bulunamadı"]) }
            player?.stop(); let p=try AVAudioPlayer(contentsOf:URL(fileURLWithPath:path)); player=p; p.currentTime=start; p.play()
            Task { try? await Task.sleep(for:.seconds(max(0.1,row.end-row.start))); if self.player===p { p.stop() } }
        } catch { self.error=error.localizedDescription }
    }
}

func statusLabel(_ status:String)->String {
    ["not_started":"Kayıt başlayamadı", "pending_finalization":"Son işlem bekliyor", "capture_unknown":"Kayıt durumu belirsiz", "capturing":"Kaydediliyor", "complete":"Hazır", "processing":"İşleniyor", "provisional":"Canlı kayıt", "incomplete":"Kurtarılabilir", "failed":"İşlem başarısız", "canceled":"İptal edildi"][status] ?? status
}
@MainActor final class AppDelegate:NSObject,NSApplicationDelegate,UNUserNotificationCenterDelegate {
    static weak var model:Model?
    func applicationDidFinishLaunching(_ notification:Notification) {
        UNUserNotificationCenter.current().delegate=self
        if UserDefaults.standard.object(forKey:"zoomNotify") as? Bool ?? true { ZoomNotifier.register() }
    }
    nonisolated func userNotificationCenter(_ center:UNUserNotificationCenter,didReceive response:UNNotificationResponse,withCompletionHandler completionHandler:@escaping ()->Void) {
        let action=response.actionIdentifier
        Task { @MainActor in
            if action==ZoomNotifier.startAction || action==UNNotificationDefaultActionIdentifier, let m=Self.model, !m.recording, !m.busy { m.start(); m.showMainWindow() }
            completionHandler()
        }
    }
    func applicationShouldTerminate(_ sender:NSApplication) -> NSApplication.TerminateReply {
        guard let m=Self.model, m.job != nil else { return .terminateNow }
        m.requestedQuit=true
        if m.recording { m.stop() }
        m.activity="İşlem güvenle tamamlandıktan sonra kapanacak…"
        return .terminateLater
    }
}
@main struct MeetingOSApp:App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject var model=Model()
    var body:some Scene {
        Window("Meeting OS",id:"main") { MeetingContent(m:model).onAppear { GlobalHotkeys.install { id in Task { @MainActor in AppDelegate.model?.hotkey(id) } } } }.windowStyle(.titleBar).defaultSize(width:1100,height:780).commands {
            CommandMenu("Git") {
                Button("Konuşmada ara") { model.focusTranscriptSearch() }.keyboardShortcut("f",modifiers:.command)
                Button("Hafızada ara") { model.focusMemorySearch() }.keyboardShortcut("f",modifiers:[.command,.shift])
                Divider()
                Text("Sekmeler: ⌘1 Transkript · ⌘2 Özet · ⌘3 Görevlerim · ⌘4 Kontrol · ⌘5 Hafıza")
            }
        }
        MenuBarExtra { QuickMenu(model:model) } label: {
            if model.recording { Label(model.elapsedText,systemImage:"record.circle.fill") } else { Image(systemName:model.zoomMeetingOpen ? "video.badge.waveform" : "waveform") }
        }.menuBarExtraStyle(.menu)
    }
}
