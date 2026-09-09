import SwiftUI
import UniformTypeIdentifiers
import AppKit
import AVFoundation

struct Meeting: Identifiable {
    let id: String; let title: String; let status: String; let displayStatus:String; let recoveryState:String; let created: String; let capture:[String:Any]; let metadata: [String:Any]
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; status=d["status"] as? String ?? ""; displayStatus=d["display_status"] as? String ?? status; recoveryState=d["recovery_state"] as? String ?? "unknown"; created=d["created"] as? String ?? ""; metadata=d["metadata"] as? [String:Any] ?? [:]; capture=d["capture"] as? [String:Any] ?? [:] }
}
extension Meeting {
    var captureSourcesEmpty:Bool { (capture["sources"] as? [String:Any] ?? [:]).isEmpty }
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
    let deadline=DispatchWorkItem { if p.isRunning { p.terminate() } }
    DispatchQueue.global().asyncAfter(deadline:.now()+10, execute:deadline)
    defer { deadline.cancel() }
    try input.fileHandleForWriting.write(contentsOf:JSONSerialization.data(withJSONObject:request)); try input.fileHandleForWriting.close()
    let data=output.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
    guard let result=try JSONSerialization.jsonObject(with:data) as? [String:Any] else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Invalid local response"]) }
    if let message=result["error"] as? String { throw NSError(domain:"MeetingOS",code:2,userInfo:[NSLocalizedDescriptionKey:message]) }
    return result
}

@MainActor final class Model:ObservableObject {
    @Published var meetings:[Meeting]=[]; @Published var rows:[Row]=[]; @Published var profiles:[Profile]=[]
    @Published var selected:String? { didSet { if selected != oldValue { recordingNavigation.selectionChanged(); error=""; rows=[]; analysis=nil; search=""; pendingEvidence=nil; focusedSegment=nil } } }; @Published var search="" { didSet { focusedSegment=nil; pendingEvidence=nil } }; @Published var title=""; @Published var error=""
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
    @Published var focusedSegment:Int?
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
        timer=Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in Task { @MainActor in await self?.refresh() } }
        Task { await refresh() }
    }
    var meeting:Meeting? { meetings.first { $0.id==selected } }
    @Published var showEchoRows=false
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
    func loadReview() async {
        guard let mid=selected else { review=[]; return }
        do { let r=try await request(["action":"review_queue","meeting":mid]); review=(r["items"] as? [[String:Any]] ?? []).map(ReviewItem.init) } catch { review=[] }
    }
    func confirmReview(_ item:ReviewItem) async {
        guard let mid=selected, !item.suggested.isEmpty, !item.speakerKey.isEmpty else { return }
        do { _=try await request(["action":"label_speaker","meeting":mid,"speaker":item.speakerKey,"name":item.suggested,"enroll":true]); activity="“\(item.suggested)” onaylandı · profil güncellendi"; await refresh(); await loadReview() }
        catch { self.error=error.localizedDescription }
    }
    @Published var readingMode=true
    @Published var showAsides=false
    @Published var hideFillers=UserDefaults.standard.object(forKey:"hideFillers") as? Bool ?? true { didSet { UserDefaults.standard.set(hideFillers,forKey:"hideFillers") } }
    var filteredRows:[Row] {
        if let id=focusedSegment { return rows.filter { $0.id==id } }
        let visible=CloudTranscription.visibleRows(rows,showEcho:showEchoRows)
        return search.isEmpty ? visible : visible.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) }
    }
    func request(_ req:[String:Any]) async throws -> [String:Any] {
        let rt=runtime
        return try await Task.detached { try invoke(rt,req) }.value
    }
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
            }
            if !restoredOnLaunch {
                restoredOnLaunch=true
                if !recording, job==nil, let restore=RelaunchRestore.pick(meetings:meetings) { selected=restore.id; restoredMeeting=restore.id }
            }
            if selected==nil && !recording { selected=meetings.first?.id }
            zoomMeetingOpen=ZoomWatch.current()
            if recording, let started=jobStarted { let s=Int(Date().timeIntervalSince(started)); elapsedText=String(format:"%02d:%02d",s/60,s%60) }
            if lastUpdateCheck==nil || Date().timeIntervalSince(lastUpdateCheck!) >= 6*3600 { Task { await checkForUpdates() } }
            if NSApp.isActive, let last=lastUpdateCheck, Date().timeIntervalSince(last) >= 15*60 { Task { await checkForUpdates() } }
            if wanted==selected { let nextRows=(result["segments"] as? [[String:Any]] ?? []).map(Row.init); if rows != nextRows { rows=nextRows }; resolvePendingEvidence(); try await refreshIntelligence(wanted) }
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
            let p=Process();p.environment=ProcessInfo.processInfo.environment.merging(["MEETING_OS_PROGRESS_PATH":progress.path]) { _,new in new }; p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os"]+args; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo); p.standardOutput=handle; p.standardError=handle
            p.terminationHandler={ [weak self] process in
                try? handle.close()
                let jobError=ErrorPresentation.logSummary(log)
                Task { @MainActor in
                    guard let self=self else { return }; self.job=nil; self.jobKind=nil; self.busy=false; self.jobProgress=""; self.progressURL=nil; self.jobStarted=nil; try? FileManager.default.removeItem(at:progress)
                    if process.terminationStatus != 0 && !self.jobCanceled { self.error=self.resourceStopMessage.isEmpty ? jobError : self.resourceStopMessage }
                    complete(process.terminationStatus==0 && self.resourceStopMessage.isEmpty && !self.jobCanceled); await self.refresh(); if self.requestedQuit && self.job==nil { NSApp.reply(toApplicationShouldTerminate:true) }
                }
            }
            try p.run(); job=p; busy=true; error=""
        } catch { self.error=error.localizedDescription; busy=false; jobKind=nil; recording=false; recordingNavigation.cancel() }
    }
    func start() {
        guard job==nil else { return }
        recordingNavigation.begin()
        let dir=dataDir.appendingPathComponent("recordings/"+UUID().uuidString)
        recordingDir=dir; recording=true; markerCount=0; activity="Kayıt hazırlanıyor · macOS izinleri açık olmalı"; DisplaySleepGuard.begin()
        let name=title.isEmpty ? Date().formatted(date:.abbreviated,time:.shortened) : title
        let receipt=dataDir.appendingPathComponent("record-\(UUID().uuidString).json")
        launch(CloudTranscription.recordArguments(mode:transcriptionMode,directory:dir.path,title:name,receipt:receipt.path)) { [weak self] ok in
            guard let self=self else { return }; self.recording=false; self.recordingNavigation.cancel(); DisplaySleepGuard.end()
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
            try? FileManager.default.removeItem(at:result)
            if ok { self.selected=mid;self.tab="transcript";self.activity="Transkript OpenRouter’dan alındı · Konuşmacı adlarını kontrol edin";if !self.requestedQuit { self.analyzeAutomatically(mid) } }
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
    @Published var glossaryCount=0; @Published var glossaryFromFile=0; @Published var glossarySample:[String]=[]
    @Published var zoomMeetingOpen=false; @Published var elapsedText="00:00"
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
        if !force, let last=lastUpdateCheck, Date().timeIntervalSince(last) < 15*60 { return }   // on launch, on activation, at most every 15 minutes
        lastUpdateCheck=Date()
        if let status=try? await request(["action":"update_status"]), let state=status["state"] as? String, let msg=status["message"] as? String, state != "running", UserDefaults.standard.string(forKey:"lastShownUpdate") != (status["time"] as? String ?? "") {
            UserDefaults.standard.set(status["time"] as? String ?? "",forKey:"lastShownUpdate"); activity=(state=="done" ? "Güncelleme tamam · " : "Güncelleme başarısız · ")+msg
        }
        if let r=try? await request(["action":"update_check"]) { update=UpdateInfo.parse(r) }
        if let r=try? await request(["action":"report_settings"]) { reportSettings=ReportSettings.parse(r) }
        if reportSettings.autoUpdate, update?.available==true, job==nil, !recording { startUpdate() }
    }
    /// Hands over to the detached updater and quits; the updater rebuilds, re-signs and relaunches.
    func startUpdate() {
        guard job==nil, !recording, !updating else { return }
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
    func settings() async {
        do {
            vocabulary=try await request(["action":"vocabulary"])["text"] as? String ?? ""
            await loadGlossarySummary()
            storage=(try? await request(["action":"storage_report"])).map(StorageReport.parse)   // read-only walk; a failure hides the section only
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
@MainActor final class AppDelegate:NSObject,NSApplicationDelegate {
    static weak var model:Model?
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
        Window("Meeting OS",id:"main") { MeetingContent(m:model).onAppear { GlobalHotkeys.install { id in Task { @MainActor in AppDelegate.model?.hotkey(id) } } } }.windowStyle(.titleBar).defaultSize(width:1100,height:780)
        MenuBarExtra { QuickMenu(model:model) } label: {
            if model.recording { Label(model.elapsedText,systemImage:"record.circle.fill") } else { Image(systemName:model.zoomMeetingOpen ? "video.badge.waveform" : "waveform") }
        }.menuBarExtraStyle(.menu)
    }
}
