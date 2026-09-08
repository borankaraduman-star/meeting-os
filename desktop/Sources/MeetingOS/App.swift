import SwiftUI
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
    let id:Int; let start:Double; let end:Double; let text:String; let speaker:String; let name:String; let source:String; let flags:[String]
    init(_ d:[String:Any]) { id=d["id"] as? Int ?? 0; start=d["start"] as? Double ?? 0; end=d["end"] as? Double ?? 0; text=d["text"] as? String ?? ""; speaker=d["speaker"] as? String ?? ""; name=d["speaker_name"] as? String ?? ""; source=d["source"] as? String ?? ""; flags=d["flags"] as? [String] ?? [] }
    var label:String {
        if !name.isEmpty { return name }
        if flags.contains("provisional") { return "Geçici konuşmacı" }
        if let tail=speaker.split(separator:":").last, tail.hasPrefix("S"), let n=Int(tail.dropFirst()) { return "Konuşmacı \(n+1)" }
        return "İsimsiz konuşmacı"
    }
    var notices:String {
        let labels=["provisional":"Canlı metin · değişebilir", "short_context_diarization":"Konuşmacı için kısa ses örneği", "speaker_ambiguous":"Konuşmacı belirsiz / sesler çakışıyor", "low_asr_confidence":"Bu bölümü dinleyerek kontrol edin", "possible_non_speech":"Konuşma dışı ses olabilir", "repetition":"Tekrar algılandı", "confidence_unavailable":"Güven ölçümü yok", "baseline_diarization":"Temel konuşmacı ayrımı"]
        return flags.map { labels[$0] ?? $0 }.joined(separator:" · ")
    }
    var time:String { String(format:"%02d:%02d",Int(start)/60,Int(start)%60) }
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
    var filteredRows:[Row] { if let id=focusedSegment { return rows.filter { $0.id==id } }; return search.isEmpty ? rows : rows.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) } }
    func request(_ req:[String:Any]) async throws -> [String:Any] {
        let rt=runtime
        return try await Task.detached { try invoke(rt,req) }.value
    }
    func stopForResources() {
        guard let process=job, resourceStopMessage.isEmpty else { return }
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
            if selected==nil && !recording { selected=meetings.first?.id }
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
            resourceStopMessage="";jobCanceled=false;jobKind=args.first
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
        recordingDir=dir; recording=true; activity="Kayıt hazırlanıyor · macOS izinleri açık olmalı"
        let name=title.isEmpty ? Date().formatted(date:.abbreviated,time:.shortened) : title
        let receipt=dataDir.appendingPathComponent("record-\(UUID().uuidString).json")
        launch(["record",dir.path,"--live","--seconds","14400","--title",name,"--output",receipt.path]) { [weak self] ok in
            guard let self=self else { return }; self.recording=false; self.recordingNavigation.cancel()
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
    func importAudio() {
        let panel=NSOpenPanel(); panel.canChooseDirectories=false; panel.allowsMultipleSelection=false
        if panel.runModal() == .OK, let url=panel.url {
            activity="Dosya yazıya dönüştürülüyor…"
            let result=dataDir.appendingPathComponent("import-\(UUID().uuidString).json")
            launch(["import",url.path,"--title",url.deletingPathExtension().lastPathComponent,"--output",result.path]) { [weak self] ok in
                guard let self=self else { return }
                if ok, let mid=self.resultMeeting(result) { self.selected=mid;self.analyzeAutomatically(mid) } else { self.activity="Dosya işlenemedi" }
            }
        }
    }
    func saveLabel(enroll:Bool) async {
        guard let row=editRow, let mid=selected else { return }
        do {
            _=try await request(["action":enroll ? "enroll":"label","meeting":mid,"segment":row.id,"name":editName,"confirmed_clean":clean])
            editRow=nil; await refresh()
        } catch { self.error=error.localizedDescription }
    }
    func saveText() async {
        guard let row=editRow, let mid=selected else { return }
        do { _=try await request(["action":"edit_text","meeting":mid,"segment":row.id,"text":editText]); editRow=nil; await refresh() } catch { self.error=error.localizedDescription }
    }
    func deleteProfile(_ name:String) async { do { _=try await request(["action":"delete_profile","name":name]); await refresh() } catch { self.error=error.localizedDescription } }
    func export(_ format:String) async {
        guard let mid=selected else { return }; let panel=NSSavePanel(); panel.nameFieldStringValue="Meeting.\(format)"
        guard panel.runModal() == .OK, let url=panel.url else { return }
        do { _=try await request(["action":format=="analysis.md" ? "export_analysis":"export","meeting":mid,"path":url.path,"format":format]); activity="Dışa aktarıldı: \(url.lastPathComponent)" } catch { self.error=error.localizedDescription }
    }
    func settings() async { do { vocabulary=try await request(["action":"vocabulary"])["text"] as? String ?? ""; showSettings=true } catch { self.error=error.localizedDescription } }
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
    var body:some Scene { Window("Meeting OS",id:"main") { MeetingContent() }.windowStyle(.titleBar).defaultSize(width:1100,height:780) }
}
