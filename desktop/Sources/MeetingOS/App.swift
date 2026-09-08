import SwiftUI
import AppKit
import AVFoundation

struct Meeting: Identifiable {
    let id: String; let title: String; let status: String; let created: String; let capture:[String:Any]; let metadata: [String:Any]
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; status=d["status"] as? String ?? ""; created=d["created"] as? String ?? ""; metadata=d["metadata"] as? [String:Any] ?? [:]; capture=d["capture"] as? [String:Any] ?? [:] }
}
struct Row: Identifiable {
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
    @Published var selected:String? { didSet { if selected != oldValue { recordingNavigation.selectionChanged(); rows=[]; analysis=nil; search=""; pendingEvidence=nil; focusedSegment=nil } } }; @Published var search="" { didSet { focusedSegment=nil; pendingEvidence=nil } }; @Published var title=""; @Published var error=""
    @Published var activity="Hazır · Ses ve metin bu Mac’te kalır"; @Published var recording=false; @Published var busy=false
    @Published var vocabulary=""; @Published var showSettings=false; @Published var editRow:Row?; @Published var editName=""; @Published var editText=""; @Published var clean=false
    @Published var tab="transcript" { didSet { if tab != "transcript" { pendingEvidence=nil } } }; @Published var analysis:[String:Any]?; @Published var actions:[ActionItem]=[]; @Published var drafts:[DraftItem]=[]
    @Published var memoryQuery=""; @Published var hits:[Evidence]=[]; @Published var answer=""; @Published var answerEvidence:[Evidence]=[]
    let runtime:Runtime; let dataDir=FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/MeetingOS")
    @Published var focusedSegment:Int?
    @Published var pendingEvidence:Evidence?
    var recordingNavigation=RecordingNavigation()
    var requestedQuit=false
    var job:Process?; var recordingDir:URL?; var timer:Timer?; var player:AVAudioPlayer?; var refreshing=false
    init() {
        let url=Bundle.main.resourceURL!.appendingPathComponent("runtime.json")
        runtime=(try? JSONDecoder().decode(Runtime.self,from:Data(contentsOf:url))) ?? Runtime(python:"/usr/bin/false",repo:"/tmp")
        AppDelegate.model=self
        timer=Timer.scheduledTimer(withTimeInterval:2,repeats:true) { [weak self] _ in Task { @MainActor in await self?.refresh() } }
        Task { await refresh() }
    }
    var meeting:Meeting? { meetings.first { $0.id==selected } }
    var filteredRows:[Row] { if let id=focusedSegment { return rows.filter { $0.id==id } }; return search.isEmpty ? rows : rows.filter { ($0.text+" "+$0.label).localizedCaseInsensitiveContains(search) } }
    func request(_ req:[String:Any]) async throws -> [String:Any] {
        let rt=runtime
        return try await Task.detached { try invoke(rt,req) }.value
    }
    func refresh() async {
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
                let seconds=active.capture["seconds"] as? Double ?? 0
                let sources=active.capture["sources"] as? [String:Double] ?? [:]
                activity=active.capture["state"] as? String=="capturing" ? "Kaydediliyor · \(Int(seconds)) sn · \(sources.keys.sorted().map { $0 == "mic" ? "Mikrofon" : "Sistem" }.joined(separator:" + "))" : "macOS izinleri ve ses aygıtı bekleniyor…"
            }
            if selected==nil && !recording { selected=meetings.first?.id }
            if wanted==selected { rows=(result["segments"] as? [[String:Any]] ?? []).map(Row.init); resolvePendingEvidence(); try await refreshIntelligence(wanted) }
        } catch { self.error=error.localizedDescription }
    }
    func launch(_ args:[String], complete:@escaping (Bool)->Void) {
        guard job==nil else { return }
        do {
            try FileManager.default.createDirectory(at:dataDir,withIntermediateDirectories:true)
            let log=dataDir.appendingPathComponent("last-job.log")
            FileManager.default.createFile(atPath:log.path,contents:nil)
            let handle=try FileHandle(forWritingTo:log)
            let p=Process(); p.executableURL=URL(fileURLWithPath:runtime.python); p.arguments=["-m","meeting_os"]+args; p.currentDirectoryURL=URL(fileURLWithPath:runtime.repo); p.standardOutput=handle; p.standardError=handle
            p.terminationHandler={ [weak self] process in
                try? handle.close()
                Task { @MainActor in
                    guard let self=self else { return }; self.job=nil; self.busy=false
                    if process.terminationStatus != 0 { self.error=(try? String(contentsOf:log,encoding:.utf8)).map { String($0.split(separator:"\n").last ?? "İşlem tamamlanamadı") } ?? "İşlem tamamlanamadı" }
                    complete(process.terminationStatus==0); await self.refresh(); if self.requestedQuit && self.job==nil { NSApp.reply(toApplicationShouldTerminate:true) }
                }
            }
            try p.run(); job=p; busy=true; error=""
        } catch { self.error=error.localizedDescription; busy=false; recording=false; recordingNavigation.cancel() }
    }
    func start() {
        guard job==nil else { return }
        recordingNavigation.begin()
        let dir=dataDir.appendingPathComponent("recordings/"+UUID().uuidString)
        recordingDir=dir; recording=true; activity="Kayıt hazırlanıyor · macOS izinleri açık olmalı"
        let name=title.isEmpty ? Date().formatted(date:.abbreviated,time:.shortened) : title
        launch(["record",dir.path,"--live","--seconds","14400","--title",name]) { [weak self] ok in
            guard let self=self else { return }; self.recording=false; self.recordingNavigation.cancel()
            let journal=(try? String(contentsOf:dir.appendingPathComponent("capture-native.jsonl"),encoding:.utf8)) ?? ""
            if ok && journal.contains("\"chunk\"") { self.finalize(dir,name:name) } else if ok { self.activity="Kayıt iptal edildi · Ses alınmadı" } else { self.activity="Kayıt kesildi · Arşivden sesi kurtarabilirsiniz" }
        }
    }
    func stop() { guard recording else { return }; recordingNavigation.cancel(); activity="Ses parçaları tamamlanıyor…"; recording=false; job?.interrupt() }
    func finalize(_ dir:URL,name:String) {
        activity="Son transkript ve konuşmacılar hazırlanıyor…"
        let result=dataDir.appendingPathComponent("final-\(UUID().uuidString).json")
        launch(["finalize",dir.path,"--title",name,"--output",result.path]) { [weak self] ok in
            guard let self=self else { return }
            if ok, let mid=self.resultMeeting(result) { self.selected=mid; self.analyzeMeeting(mid) } else { self.activity="Son işlem başarısız · Ses korunuyor" }
        }
    }
    func recover() { guard let m=meeting, let dir=m.metadata["capture_dir"] as? String else { return }; finalize(URL(fileURLWithPath:dir),name:m.title) }
    func importAudio() {
        let panel=NSOpenPanel(); panel.canChooseDirectories=false; panel.allowsMultipleSelection=false
        if panel.runModal() == .OK, let url=panel.url {
            activity="Dosya yazıya dönüştürülüyor…"
            let result=dataDir.appendingPathComponent("import-\(UUID().uuidString).json")
            launch(["import",url.path,"--title",url.deletingPathExtension().lastPathComponent,"--output",result.path]) { [weak self] ok in
                guard let self=self else { return }
                if ok, let mid=self.resultMeeting(result) { self.selected=mid;self.analyzeMeeting(mid) } else { self.activity="Dosya işlenemedi" }
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
    ["complete":"Hazır", "processing":"İşleniyor", "provisional":"Canlı kayıt", "incomplete":"Kurtarılabilir", "failed":"İşlem başarısız", "canceled":"İptal edildi"][status] ?? status
}
struct MeetingContent:View {
    @StateObject var m=Model()
    var body:some View {
        NavigationSplitView {
            VStack(alignment:.leading,spacing:14) {
                HStack(spacing:11) { Image(systemName:"waveform").font(.system(size:23,weight:.semibold)).foregroundStyle(MeetingStyle.accent).frame(width:45,height:45).background(MeetingStyle.accent.opacity(0.13),in:RoundedRectangle(cornerRadius:14));VStack(alignment:.leading,spacing:3) { Text("Meeting OS").font(.system(size:23,weight:.bold,design:.rounded));Text("Boran’ın toplantı hafızası").font(.caption).foregroundStyle(.secondary) } }.padding(.bottom,12)
                TextField("Toplantıya bir ad ver",text:$m.title).textFieldStyle(.roundedBorder)
                Button(action:{ m.recording ? m.stop() : m.start() }) { Label(m.recording ? "Kaydı bitir":"Yeni kayıt",systemImage:m.recording ? "stop.circle.fill":"mic.circle.fill").frame(maxWidth:.infinity) }.buttonStyle(.borderedProminent).controlSize(.large).tint(m.recording ? .red:MeetingStyle.accent).disabled(m.busy && !m.recording)
                Button(action:m.importAudio) { Label("Ses dosyası aç",systemImage:"square.and.arrow.down").frame(maxWidth:.infinity) }.controlSize(.large).disabled(m.busy)
                HStack { Text("TOPLANTILAR").font(.system(size:10,weight:.semibold)).tracking(1.5);Spacer();Text("\(m.meetings.count)").monospacedDigit().font(.caption) }.foregroundStyle(.secondary).padding(.top,14)
                List(selection:$m.selected) { ForEach(m.meetings) { meeting in MeetingLibraryRow(meeting:meeting).tag(meeting.id) } }.listStyle(.sidebar)
                ApplicationActivityView(model:m)
                Divider()
                Button { Task { await m.settings() } } label:{ Label("Sözlük ve ses profilleri",systemImage:"slider.horizontal.3").frame(maxWidth:.infinity,alignment:.leading) }.buttonStyle(.plain).font(.callout).padding(.vertical,8)
            }.padding().navigationSplitViewColumnWidth(min:240,ideal:280)
        } detail: {
            VStack(alignment:.leading,spacing:0) {
                HStack { VStack(alignment:.leading) { Text(m.meeting?.title ?? "Bir sonraki iyi fikri kaçırmayın.").font(.system(size:27,weight:.bold,design:.rounded)).lineLimit(2); HStack(spacing:6) { Circle().fill(MeetingStyle.statusColor(m.meeting?.status ?? "")).frame(width:6,height:6);Text(m.meeting.map { statusLabel($0.status) } ?? "Toplantı seçilmedi").font(.caption).foregroundStyle(.secondary) }.padding(.top,5) }; Spacer(); if m.busy { ProgressView().controlSize(.small) }; Menu("Dışa aktar") { Button("Özet ve görevler (Markdown)") { Task { await m.export("analysis.md") } }; Button("Transkript (Markdown)") { Task { await m.export("md") } }; Button("Altyazı (SRT)") { Task { await m.export("srt") } }; Button("JSON") { Task { await m.export("json") } } }.disabled(m.selected==nil) }.padding(24)
                if let meeting=m.meeting, meeting.metadata["capture_dir"] != nil, meeting.status != "canceled", !m.busy { HStack { Text("Canlı kayıt geçicidir; son işlem ayrı ve kalıcı bir transkript oluşturur.").font(.caption); Spacer(); Button("Son transkripti oluştur / Kurtar",action:m.recover) }.padding(.horizontal,24).padding(.bottom,12) }
                if m.meeting?.metadata["text_only"] as? Bool == true { Text("Kurgu metin örneği · Ses kaydı değildir").font(.caption).foregroundStyle(.secondary).padding(.horizontal,24).padding(.bottom,8) }
                MeetingNavigation(model:m).padding(.horizontal,24).padding(.bottom,18)
                if m.tab=="transcript" { HStack { Image(systemName:"magnifyingglass").foregroundStyle(.secondary);TextField("Bu konuşmada ara",text:$m.search).textFieldStyle(.plain); if m.focusedSegment != nil { Button("Tüm konuşmayı göster") { m.focusedSegment=nil } } }.padding(11).meetingCard().padding(.horizontal,24).padding(.bottom,16) }
                if m.tab=="transcript", m.pendingEvidence != nil { HStack { ProgressView().controlSize(.small);Text("Kaynak bölümü bekleniyor…").font(.callout);Spacer();Button("Vazgeç") { m.pendingEvidence=nil } }.padding(.horizontal,24).padding(.bottom,12) }
                Divider()
                if !m.error.isEmpty { HStack(alignment:.top) { Image(systemName:"exclamationmark.triangle"); Text(m.error).font(.caption).textSelection(.enabled); Spacer(); Button("Kapat") { m.error="" } }.padding().background(.orange.opacity(0.12)) }
                if m.tab=="analysis" { AnalysisView(m:m) } else if m.tab=="actions" { ActionsView(m:m) } else if m.tab=="memory" { MemoryView(m:m) } else {
                ScrollView { LazyVStack(alignment:.leading,spacing:20) { ForEach(m.filteredRows) { row in HStack(alignment:.top,spacing:14) {
                    Button { m.play(row) } label:{ VStack(spacing:8) { Image(systemName:"play.circle.fill").font(.title2).foregroundStyle(MeetingStyle.accent); Text(row.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary) }.frame(width:48) }.buttonStyle(.plain).help("Bu bölümü dinle").disabled(m.recording || m.meeting?.metadata["text_only"] as? Bool == true)
                    VStack(alignment:.leading,spacing:7) { HStack { Text(row.label).font(.headline); Text(row.source=="mic" ? "Mikrofon":"Sistem sesi").font(.caption).foregroundStyle(.secondary); Spacer(); Button("Düzelt") { m.editRow=row; m.editName=row.name; m.editText=row.text; m.clean=false }.disabled(m.meeting?.status != "complete") }; Text(row.text).font(.system(size:15)).textSelection(.enabled).lineSpacing(6); if !row.flags.isEmpty { Label(row.notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange) } }
                }.padding(20).meetingCard() } }.padding(24)
                    if m.filteredRows.isEmpty { TranscriptEmptyView(model:m).padding(32) }
                }
                }
                Divider(); HStack { Label("Yerel işleme",systemImage:"lock.shield"); Text("•"); Text("\(m.rows.count) bölüm"); Spacer(); Text("İsim düzeltmek ses profilini otomatik eğitmez.") }.font(.caption).foregroundStyle(.secondary).padding(12)
            }.frame(minWidth:660).background(MeetingStyle.canvas)
        }.frame(minWidth:1000,minHeight:720).tint(MeetingStyle.accent)
        .onChange(of:m.selected) { _,_ in Task { await m.refresh() } }
        .sheet(item:$m.editRow) { row in VStack(alignment:.leading,spacing:18) { Text("Metin ve konuşmacı").font(.title2.bold()); TextEditor(text:$m.editText).frame(height:100).border(.quaternary); Button("Metni kaydet") { Task { await m.saveText() } }.disabled(m.editText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty); TextField("İsim",text:$m.editName); Button("Önce bölümü dinle") { m.play(row) }; Toggle("Dinledim: en az 3 saniye, tek kişi, temiz ses",isOn:$m.clean); Text("Profili kaydedersen sonraki toplantılarda bu sesle eşleşen kişiye isim önerilir. Belirsiz eşleşmeler isimsiz kalır.").font(.caption).foregroundStyle(.secondary); HStack { Button("Vazgeç") { m.editRow=nil }; Spacer(); Button("Yalnızca ismi kaydet") { Task { await m.saveLabel(enroll:false) } }.disabled(m.editName.trimmingCharacters(in:.whitespaces).isEmpty); Button("Ses profilini kaydet") { Task { await m.saveLabel(enroll:true) } }.disabled(!m.clean || m.editName.trimmingCharacters(in:.whitespaces).isEmpty) }; if !m.error.isEmpty { Text(m.error).foregroundStyle(.red).font(.caption) } }.padding(28).frame(width:540) }
        .sheet(isPresented:$m.showSettings) { VStack(alignment:.leading,spacing:16) { Text("Sözlük ve ses profilleri").font(.title2.bold()); Text("Kişi adlarını ve özel terimleri her satıra bir tane yazın."); TextEditor(text:$m.vocabulary).font(.body.monospaced()).frame(height:180).border(.quaternary); Text("Kaydedilmiş sesler").font(.headline); Text("Aynı isimde farklı kişiler için ayırt edici bir ad kullanın (ör. Ali Tasarım). Yeni bir profil, aynı isimdeki mevcut kişinin ses örneklerine eklenir.").font(.caption).foregroundStyle(.secondary); List(m.profiles) { p in HStack { VStack(alignment:.leading) { Text(p.name); Text("\(p.samples) örnek · \(p.model)").font(.caption).foregroundStyle(.secondary) }; Spacer(); Button("Profili sil",role:.destructive) { Task { await m.deleteProfile(p.name) } } } }.frame(height:160); HStack { Button("Veri klasörünü aç") { NSWorkspace.shared.open(m.dataDir) }; Spacer(); Button("Kaydet") { Task { await m.saveVocabulary() } }.buttonStyle(.borderedProminent) } }.padding(28).frame(width:600) }
    }
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
    var body:some Scene { Window("Meeting OS",id:"main") { MeetingContent() }.windowStyle(.titleBar) }
}
