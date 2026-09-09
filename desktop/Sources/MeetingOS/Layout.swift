import SwiftUI
import AppKit

// Root layout is a fixed-width sidebar + flexible detail HStack rather than
// NavigationSplitView: this guarantees the sidebar (and the recording
// stop control it holds) can never be collapsed or dragged to zero width,
// and keeps every region's height bounded so long content scrolls inside
// its own region instead of pushing headers/footers off-window.
struct MeetingContent:View {
    @ObservedObject var m:Model
    var body:some View {
        HStack(spacing:0) {
            SidebarView(model:m).frame(width:MeetingStyle.sidebarWidth)
            Divider()
            DetailView(model:m).frame(minWidth:MeetingStyle.minDetailWidth,maxWidth:.infinity,maxHeight:.infinity)
        }
        .frame(minWidth:MeetingStyle.minWindowWidth,minHeight:MeetingStyle.minWindowHeight)
        .tint(MeetingStyle.accent)
        .onChange(of:m.selected) { _,_ in Task { await m.refresh() } }
        .sheet(isPresented:$m.showOpenRouter) { OpenRouterImportView(model:m) }
        .sheet(item:$m.editRow) { row in EditSegmentSheet(model:m,row:row) }
        .sheet(isPresented:$m.showSettings) { SettingsSheet(model:m) }
        .sheet(isPresented:$m.showShare) { ShareSheet(model:m) }
    }
}

struct SidebarView:View {
    @ObservedObject var model:Model
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            VStack(alignment:.leading,spacing:14) {
                HStack(spacing:11) {
                    Image(systemName:"waveform").font(.system(size:23,weight:.semibold)).foregroundStyle(MeetingStyle.accent).frame(width:45,height:45).background(MeetingStyle.accent.opacity(0.13),in:RoundedRectangle(cornerRadius:14))
                    VStack(alignment:.leading,spacing:3) { Text("Meeting OS").font(.system(size:23,weight:.bold,design:.rounded));Text("Boran’ın toplantı hafızası").font(.caption).foregroundStyle(.secondary) }
                }.padding(.bottom,4).accessibilityElement(children:.combine)
                TextField("Toplantıya bir ad ver",text:$model.title)
                    .textFieldStyle(.roundedBorder)
                    .accessibilityIdentifier("meetingTitleField")
                    .accessibilityLabel("Toplantı adı")
                Button(action:{ model.recording ? model.stop() : model.start() }) {
                    Label(RecoveryPresentation.recordingLabel(recording:model.recording,jobKind:model.jobKind),systemImage:model.recording ? "stop.circle.fill":"mic.circle.fill").frame(maxWidth:.infinity)
                }
                .buttonStyle(.borderedProminent).controlSize(.large).tint(model.recording ? .red:MeetingStyle.accent)
                .disabled(model.busy && !model.recording)
                .keyboardShortcut("r",modifiers:.command)   // ⌘R starts or ends the recording without touching the mouse
                .help(model.recording ? "Kaydı bitir (⌘R)" : "Yeni kayıt (⌘R)")
                .accessibilityIdentifier("recordButton")
                .accessibilityLabel(RecoveryPresentation.recordingLabel(recording:model.recording,jobKind:model.jobKind))
                Button { model.showOpenRouter=true } label: { Label("OpenRouter ile ses aç",systemImage:"cloud").frame(maxWidth:.infinity) }.controlSize(.large).disabled(model.busy)
                if model.zoomMeetingOpen && !model.recording { Label("Zoom toplantısı açık · ⌃⌥R ile kaydı başlat",systemImage:"video.fill").font(.caption).foregroundStyle(MeetingStyle.accent) }
                if model.update?.available != true {
                    HStack(spacing:6) {
                        Image(systemName:"checkmark.circle").foregroundStyle(.secondary).font(.caption)
                        Text(model.update.map { $0.error.isEmpty ? "Sürüm güncel" : $0.error } ?? "Sürüm kontrol edilmedi").font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        Spacer()
                        Button("Kontrol et") { Task { await model.checkForUpdates(force:true) } }.controlSize(.mini).disabled(model.busy || model.recording).help("GitHub’daki v0.1 dalıyla karşılaştırır; yeni sürüm varsa burada “Güncelle ve yeniden başlat” çıkar").accessibilityIdentifier("checkUpdateButton")
                    }.padding(.horizontal,4)
                }
                if let u=model.update, u.available {
                    VStack(alignment:.leading,spacing:6) {
                        Label(u.headline,systemImage:"arrow.down.circle").font(.caption).lineLimit(2)
                        Button(model.updating ? "Güncelleniyor…" : (model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat")) { model.startUpdate() }.controlSize(.small).disabled(model.zoomMeetingOpen || model.busy || model.recording || model.updating).accessibilityIdentifier("updateButton")
                    }.padding(10).meetingCard()
                }
                if model.recording {
                    VStack(alignment:.leading,spacing:6) {
                        Text("ÖNEMLİ AN İŞARETLE").font(.system(size:10,weight:.semibold)).tracking(1.5).foregroundStyle(.secondary)
                        HStack(spacing:6) {
                            Button("⌘M An") { model.markMoment("important") }.keyboardShortcut("m",modifiers:.command)
                            Button("Karar") { model.markMoment("decision") }.keyboardShortcut("m",modifiers:[.command,.shift])
                            Button("Görev") { model.markMoment("task") }.keyboardShortcut("m",modifiers:[.command,.option])
                            Button("Sonra") { model.markMoment("later") }.keyboardShortcut("m",modifiers:[.command,.control])
                        }.controlSize(.small)
                        Text(model.markerCount==0 ? "Konuşmayı bölmeden işaretle; kayıt bitince Kontrol sekmesinde sırayla görürsün. ⌘⇧M karar, ⌘⌥M görev, ⌘⌃M sonra bak." : "\(model.markerCount) an işaretlendi · Kontrol sekmesinde görünecek").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                VStack(alignment:.leading,spacing:6) {
                    Text("YAZIYA ÇEVİRME").font(.system(size:10,weight:.semibold)).tracking(1.5).foregroundStyle(.secondary)
                    Picker("Yazıya çevirme",selection:$model.transcriptionMode) { Text("OpenRouter").tag("openrouter");Text("Yerel model").tag("local") }
                        .pickerStyle(.segmented).labelsHidden().disabled(model.recording || model.busy).accessibilityIdentifier("transcriptionModePicker")
                    if model.transcriptionMode=="openrouter" {
                        if model.cloudModels.isEmpty { Text("Model listesi yükleniyor…").font(.caption).foregroundStyle(.secondary) }
                        else {
                            Picker("Model",selection:$model.cloudModel) { ForEach(model.cloudModels) { Text($0.name).tag($0.id) } }
                                .labelsHidden().disabled(model.recording || model.busy).accessibilityIdentifier("cloudModelPicker")
                        }
                        Text("Kayıt bitince ses OpenRouter’a gider; bu Mac’te model yüklenmez, canlı metin olmaz. Her yerden ⌃⌥R başlat/bitir, ⌃⌥M an işaretle.").font(.caption2).foregroundStyle(.secondary)
                    } else {
                        Text("Yerel model bu Mac’te çalışır ve bellek baskısında durur.").font(.caption2).foregroundStyle(.secondary)
                    }
                }.task { await model.loadCloudModels() }
            }.padding(18)
            HStack { Text("TOPLANTILAR").font(.system(size:10,weight:.semibold)).tracking(1.5);Spacer();Text(model.filter.isEmpty ? "\(model.meetings.count)" : "\(model.visibleMeetings.count)/\(model.meetings.count)").monospacedDigit().font(.caption) }
                .foregroundStyle(.secondary).padding(.horizontal,18).padding(.bottom,6)
                .accessibilityHidden(true)
            if !model.meetings.isEmpty {
                HStack(spacing:6) {
                    Image(systemName:"magnifyingglass").foregroundStyle(.secondary).font(.caption)
                    TextField("Toplantı, kişi veya tarih ara",text:$model.filter).textFieldStyle(.plain).font(.callout).accessibilityIdentifier("meetingFilter")
                    if !model.filter.isEmpty { Button { model.filter="" } label:{ Image(systemName:"xmark.circle.fill").foregroundStyle(.secondary) }.buttonStyle(.plain) }
                }.padding(.horizontal,10).padding(.vertical,6).background(.primary.opacity(0.05),in:RoundedRectangle(cornerRadius:8)).padding(.horizontal,14).padding(.bottom,6)
            }
            List(selection:$model.selected) {
                ForEach(model.groupedMeetings,id:\.0) { group,items in
                    Section { ForEach(items) { meeting in
                        MeetingLibraryRow(meeting:meeting)
                            .tag(meeting.id)
                            .contextMenu { Button("Toplantıyı sil…",role:.destructive) { model.deleteCandidate=meeting }.disabled(model.busy || meeting.recoveryState=="active") }
                            .accessibilityIdentifier("meetingRow-\(meeting.id)")
                            .accessibilityLabel("\(meeting.title.isEmpty ? "Adsız toplantı" : meeting.title), \(meeting.sidebarDetail)")
                    } } header: { Text(group).font(.system(size:10,weight:.semibold)).tracking(1.2).foregroundStyle(.secondary) }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
            .frame(maxHeight:.infinity)
            .accessibilityIdentifier("meetingLibraryList")
            .confirmationDialog("“\(model.deleteCandidate?.title ?? "")” silinsin mi?",isPresented:Binding(get:{ model.deleteCandidate != nil },set:{ if !$0 { model.deleteCandidate=nil } }),titleVisibility:.visible) {
                Button("Sil",role:.destructive) { if let meeting=model.deleteCandidate { model.deleteCandidate=nil;Task { await model.deleteMeeting(meeting) } } }
                Button("Vazgeç",role:.cancel) { model.deleteCandidate=nil }
            } message: { Text("Transkript, düzeltmeler, özet ve görevler ile bu toplantıya ait ses dosyaları kalıcı olarak silinir. Kaydedilmiş ses profilleri korunur.") }
            Divider()
            VStack(alignment:.leading,spacing:8) {
                ApplicationActivityView(model:model).accessibilityIdentifier("activitySummary")
                if model.canCancelJob {
                    Button("İşlemi iptal et",action:model.cancelJob).disabled(model.jobCanceled).accessibilityIdentifier("cancelJobButton")
                }
                Button { Task { await model.exportDiagnostics() } } label: { Label("Tanılama raporu kaydet",systemImage:"doc.badge.gearshape") }
                    .buttonStyle(.plain).font(.caption).frame(minHeight:28)
                    .accessibilityIdentifier("diagnosticsButton")
                    .accessibilityLabel("Tanılama raporu kaydet")
                Divider()
                Button { Task { await model.settings() } } label:{ Label("Sözlük ve ses profilleri",systemImage:"slider.horizontal.3").frame(maxWidth:.infinity,alignment:.leading) }.keyboardShortcut(",",modifiers:.command).help("Ayarlar (⌘,)")
                    .buttonStyle(.plain).font(.callout).frame(minHeight:28)
                    .accessibilityIdentifier("settingsButton")
                    .accessibilityLabel("Ayarlar: sözlük ve ses profilleri")
            }.padding(18)
        }
        .background(.regularMaterial)
    }
}

struct DetailView:View {
    @ObservedObject var model:Model
    var body:some View {
        VStack(alignment:.leading,spacing:0) {
            DetailHeader(model:model)
            if let meeting=model.meeting, model.restoredMeeting==meeting.id, RelaunchRestore.restorableStates.contains(meeting.status) {
                HStack(spacing:10) {
                    Image(systemName:"arrow.counterclockwise.circle.fill").foregroundStyle(MeetingStyle.accent)
                    Text(RelaunchRestore.headline(meeting)).font(.callout.weight(.semibold)).lineLimit(1)
                    Spacer()
                    Button { model.restoredMeeting=nil } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(.secondary) }
                        .buttonStyle(.plain).accessibilityLabel("Kurtarma bildirimini kapat")
                }.padding(.horizontal,24).padding(.bottom,8).accessibilityIdentifier("relaunchRestoreBanner")
            }
            if let meeting=model.meeting, meeting.metadata["capture_dir"] is String, !["complete","canceled"].contains(meeting.status), !model.busy {
                RecoveryBanner(model:model,meeting:meeting)
            }
            if model.meeting?.metadata["text_only"] as? Bool == true {
                Text(model.meeting?.metadata["imported_from"] as? String == "chatgpt_manual" ? "ChatGPT’den elle aktarılan metin · Ses kaydı ve doğrulanmış ses profili içermez" : "Kurgu metin örneği · Ses kaydı değildir").font(.caption).foregroundStyle(.secondary).padding(.horizontal,24).padding(.bottom,8)
            }
            if let meeting=model.meeting,meeting.metadata["engine"] as? String=="openrouter" {
                HStack {
                    Text("\(meeting.metadata["model"] as? String ?? "") · OpenRouter | Konuşmacı ayrımı bu Mac’te").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if meeting.status != "complete" { Button("İşlemi sürdür") { if meeting.metadata["cloud_mode"] != nil { model.finalizeWithOpenRouter(meeting.id,model:nil) } else { model.showOpenRouter=true } }.disabled(model.busy || meeting.recoveryState=="active") }
                }.padding(.horizontal,24).padding(.bottom,8)
            }
            MeetingNavigation(model:model).padding(.horizontal,24).padding(.bottom,16)
            if model.tab=="transcript" {
                TranscriptSearchBar(model:model).padding(.horizontal,24).padding(.bottom,12)
            }
            if model.tab=="transcript", model.pendingEvidence != nil {
                HStack { ProgressView().controlSize(.small);Text("Kaynak bölümü bekleniyor…").font(.callout);Spacer();Button("Vazgeç") { model.pendingEvidence=nil } }
                    .padding(.horizontal,24).padding(.bottom,12)
            }
            Divider()
            if !model.error.isEmpty { ErrorBanner(model:model) }
            Group {
                switch model.tab {
                case "analysis": AnalysisView(m:model)
                case "actions": ActionsView(m:model)
                case "review": ReviewView(model:model)
                case "memory": MemoryView(m:model)
                default: TranscriptView(model:model)
                }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
            Divider()
            HStack {
                if model.meeting?.metadata["engine"] as? String=="openrouter" { Label("Transkript OpenRouter · Ses profili eşleştirme bu Mac’te",systemImage:"cloud") } else { Label("Yerel işleme",systemImage:"lock.shield") }
                Text("•"); Text("\(model.rows.count) bölüm"); Spacer()
                if let e=model.meeting?.metadata["identity_error"] as? String { Text(e).foregroundStyle(.orange) }
                else { Text(model.meeting?.metadata["engine"] as? String=="openrouter" ? "Bir konuşmacıyı bir kez adlandırın; profil kaydedilir ve sonraki toplantılarda otomatik tanınır." : "İsim düzeltmek ses profilini otomatik eğitmez.") }
            }
                .font(.caption).foregroundStyle(.secondary).padding(12)
        }
        .background(MeetingStyle.canvas)
    }
}

struct DetailHeader:View {
    @ObservedObject var model:Model
    var body:some View {
        HStack(alignment:.top) {
            VStack(alignment:.leading) {
                if model.renaming, model.meeting != nil {
                    HStack { TextField("Toplantı adı",text:$model.renameText).textFieldStyle(.roundedBorder).font(.title3).onSubmit { Task { await model.renameMeeting() } }.accessibilityIdentifier("renameField"); Button("Kaydet") { Task { await model.renameMeeting() } }; Button("Vazgeç") { model.renaming=false } }
                } else {
                    HStack(alignment:.firstTextBaseline,spacing:8) {
                        Text(model.meeting?.title ?? "Bir sonraki iyi fikri kaçırmayın.").font(.system(size:27,weight:.bold,design:.rounded)).lineLimit(2)
                        if let m=model.meeting { Button { model.renameText=m.title; model.renaming=true } label: { Image(systemName:"pencil") }.buttonStyle(.plain).foregroundStyle(.secondary).help("Toplantıyı yeniden adlandır").accessibilityIdentifier("renameButton") }
                    }
                }
                HStack(spacing:6) {
                    Circle().fill(MeetingStyle.statusColor(model.meeting?.displayStatus ?? "")).frame(width:6,height:6)
                    Text(model.meeting.map { statusLabel($0.displayStatus) } ?? "Toplantı seçilmedi").font(.caption).foregroundStyle(.secondary)
                    if let strip=model.headerStrip { Text("· "+strip).font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("headerStrip") }
                }.padding(.top,5)
            }
            Spacer(minLength:12)
            if model.busy { ProgressView().controlSize(.small) }
            Menu("Dışa aktar") {
                Button("Özet ve görevler (Markdown)") { Task { await model.export("analysis.md") } }
                Button("Transkript (Markdown)") { Task { await model.export("md") } }
                Button("Altyazı (SRT)") { Task { await model.export("srt") } }
                Button("JSON") { Task { await model.export("json") } }
                Divider()
                Menu("Belge hazırla (bulut)") {
                    Button("Ürün gereksinimi (PRD)…") { Task { await model.exportDocument(kind:"prd") } }
                    Button("Hata raporu…") { Task { await model.exportDocument(kind:"bug") } }
                    Button("Müşteri talebi…") { Task { await model.exportDocument(kind:"customer") } }
                    Button("Claude Code istemi…") { Task { await model.exportDocument(kind:"claude") } }
                }.disabled(model.meeting?.status != "complete" || model.busy)
                Button("Paylaş…") { model.showShare=true }.accessibilityIdentifier("shareMenuItem")
            }
            .disabled(model.selected==nil)
            .accessibilityIdentifier("exportMenu")
            .accessibilityLabel("Dışa aktar")
            Button { if let meeting=model.meeting { model.deleteCandidate=meeting } } label: { Label("Sil",systemImage:"trash") }
                .disabled(model.meeting==nil || model.busy || model.meeting?.recoveryState=="active")
                .accessibilityIdentifier("deleteMeetingButton")
                .accessibilityLabel("Toplantıyı sil")
        }.padding(24)
    }
}

struct RecoveryBanner:View {
    @ObservedObject var model:Model
    let meeting:Meeting
    var canRetry:Bool { RecoveryPresentation.canRetry(status:meeting.status,hasCapture:!meeting.captureSourcesEmpty,owner:meeting.recoveryState) }
    var body:some View {
        HStack(alignment:.top) {
            Text(canRetry ? "Kurtarma aynı toplantıyı günceller; işlem bitene kadar önceki metin korunur." : (meeting.displayStatus == "not_started" ? "Ses alınamadı. macOS izinlerini kontrol edip yeni kayıt başlatın." : "İşlem sürüyor veya durumu doğrulanamıyor. Kayıt değiştirilmedi."))
                .font(.caption)
            Spacer()
            if CloudTranscription.canFinalize(meeting:meeting,busy:model.busy) {
                Button("OpenRouter ile yazıya çevir") { model.finalizeWithOpenRouter(meeting.id,model:model.cloudModel) }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("cloudFinalizeButton")
            }
            if canRetry {
                Button(meeting.displayStatus == "pending_finalization" ? "Yerel modelle tamamla" : "Yerel modelle kurtar",action:model.recover)
                    .accessibilityIdentifier("recoverButton")
            }
        }.padding(.horizontal,24).padding(.bottom,12)
    }
}

struct TranscriptSearchBar:View {
    @ObservedObject var model:Model
    @FocusState private var focused:Bool
    var body:some View {
        HStack {
            Image(systemName:"magnifyingglass").foregroundStyle(.secondary)
            TextField("Bu konuşmada ara",text:$model.search)
                .textFieldStyle(.plain)
                .focused($focused)
                .onChange(of:model.searchFocusToken) { _,_ in focused=true }
                .onExitCommand { model.search=""; focused=false }
                .accessibilityIdentifier("transcriptSearchField")
                .accessibilityLabel("Konuşmada ara")
            if model.focusedSegment != nil { Button("Tüm konuşmayı göster") { model.focusedSegment=nil } }
        }.padding(11).meetingCard()
    }
}

struct ErrorBanner:View {
    @ObservedObject var model:Model
    @State private var expanded=false
    var isLong:Bool { model.error.count>140 || model.error.contains("\n") }
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            HStack(alignment:.top,spacing:10) {
                Image(systemName:"exclamationmark.triangle.fill").foregroundStyle(.orange)
                if expanded && isLong {
                    ScrollView {
                        Text(ErrorPresentation.summary(model.error)).font(.callout).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading)
                    }.frame(maxHeight:160)
                } else {
                    Text(ErrorPresentation.summary(model.error)).font(.callout).lineLimit(2).truncationMode(.tail).textSelection(.enabled)
                }
                Spacer(minLength:12)
                if isLong {
                    Button(expanded ? "Daralt" : "Detaylar") { expanded.toggle() }
                        .buttonStyle(.plain).font(.caption.weight(.semibold))
                        .accessibilityIdentifier("errorDetailsToggle")
                }
                Button { model.error="";expanded=false } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(.secondary) }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("dismissErrorButton")
                    .accessibilityLabel("Hata mesajını kapat")
            }
        }.padding(16).background(.orange.opacity(0.12)).accessibilityIdentifier("errorBanner")
    }
}

struct EditSegmentSheet:View {
    @ObservedObject var model:Model
    let row:Row
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:18) {
                Text("Metin ve konuşmacı").font(.title2.bold())
                TextEditor(text:$model.editText).frame(height:100).border(.quaternary)
                Button("Metni kaydet") { Task { await model.saveText() } }.disabled(model.editText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
                TextField("İsim",text:$model.editName).accessibilityIdentifier("editSpeakerNameField")
                if let attendees=(model.meeting?.metadata["calendar"] as? [String:Any])?["attendees"] as? [String], !attendees.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Takvimdeki katılımcılar").font(.caption).foregroundStyle(.secondary)
                        FlowChips(items:attendees) { model.editName=$0 }
                    }
                }
                if model.meeting?.metadata["text_only"] as? Bool != true {
                Button("Önce bölümü dinle") { model.play(row) }
                Toggle("Dinledim: en az 3 saniye, tek kişi, temiz ses",isOn:$model.clean)
                Text("Profili kaydedersen sonraki toplantılarda bu sesle eşleşen kişiye isim önerilir. Belirsiz eşleşmeler isimsiz kalır.").font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("Bu toplantı yalnızca metin içerir. İsim düzeltmesi ses profili oluşturmaz.").font(.caption).foregroundStyle(.secondary)
                }
                if let row=model.editRow, row.flags.contains("cloud_diarization") {
                    Divider()
                    HStack { Button("Neden bu isim?") { Task { await model.explainIdentity(row) } }.controlSize(.small); Text("Ses profillerine benzerlik puanları").font(.caption2).foregroundStyle(.secondary) }
                    if let ex=model.explanation {
                        VStack(alignment:.leading,spacing:3) {
                            if !ex.reason.isEmpty { Text(ex.reason).font(.caption) }
                            ForEach(Array(ex.candidates.enumerated()),id:\.element.id) { i,c in
                                Text("\(c.name): \(String(format:"%.2f",c.score)) (merkez \(String(format:"%.2f",c.centroid)), en yakın örnek \(String(format:"%.2f",c.bestSample)), \(c.samples) örnek) \(ex.verdict(for:c,rank:i))").font(.caption.monospacedDigit())
                            }
                            Text("İsim eşiği \(String(format:"%.2f",ex.threshold)), öneri eşiği \(String(format:"%.2f",ex.suggest)), ikinci adaya en az \(String(format:"%.2f",ex.margin)) fark · bu kümede \(String(format:"%.0f",ex.seconds)) sn ses").font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                    Text("Bu bölüm sağlayıcı ayrımıyla “\(row.speaker)” kümesine ait. Kümeyi adlandırırsanız bu toplantıdaki tüm bölümleri isim alır ve kümeden bir ses profili kaydedilir; sonraki toplantılarda aynı ses otomatik tanınır.").font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Bu konuşmacıyı adlandır ve profili kaydet") { Task { await model.saveSpeaker(enroll:true) } }.buttonStyle(.borderedProminent).disabled(model.editName.trimmingCharacters(in:.whitespaces).isEmpty).accessibilityIdentifier("nameSpeakerButton")
                        Button("Yalnızca bu toplantıda adlandır") { Task { await model.saveSpeaker(enroll:false) } }.disabled(model.editName.trimmingCharacters(in:.whitespaces).isEmpty)
                    }
                }
                HStack {
                    Button("Vazgeç") { model.editRow=nil }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelEditButton")
                    Spacer()
                    Button("Yalnızca bu bölümün ismini kaydet") { Task { await model.saveLabel(enroll:false) } }.disabled(model.editName.trimmingCharacters(in:.whitespaces).isEmpty)
                    if model.meeting?.metadata["text_only"] as? Bool != true {
                        Button("Ses profilini kaydet") { Task { await model.saveLabel(enroll:true) } }.disabled(!model.clean || model.editName.trimmingCharacters(in:.whitespaces).isEmpty)
                    }
                }
                if !model.error.isEmpty { Text(ErrorPresentation.summary(model.error)).foregroundStyle(.red).font(.caption) }
            }.padding(28)
        }.frame(width:540,height:520)
    }
}

struct SettingsSheet:View {
    @ObservedObject var model:Model
    var body:some View {
        ScrollView {
            VStack(alignment:.leading,spacing:16) {
                Text("Sözlük ve ses profilleri").font(.title2.bold())
                if !model.setupChecks.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        HStack { Text("Kurulum durumu").font(.headline);Spacer();Button("Yenile") { Task { await model.loadSetupStatus() } }.controlSize(.small) }
                        ForEach(model.setupChecks) { c in
                            HStack(alignment:.top,spacing:8) {
                                Circle().fill(c.state == .ok ? MeetingStyle.accent : (c.state == .missing ? Color.red : (c.state == .unknown ? Color.orange : Color.secondary))).frame(width:8,height:8).padding(.top,5)
                                VStack(alignment:.leading,spacing:1) { Text(c.title).font(.callout); Text(c.hint).font(.caption2).foregroundStyle(.secondary) }
                                Spacer()
                                if SetupStatus.fixable(c) { Button(SetupStatus.fixLabel(c)) { SetupStatus.fix(c.id,calendarWanted:model.useCalendar) { Task { await model.loadSetupStatus() } } }.controlSize(.small).accessibilityIdentifier("fixSetup-\(c.id)") }
                            }
                        }
                        Text("Kırmızı: kayıt ya da güncelleme bu izin/ayar olmadan çalışmaz. Gri: isteğe bağlı.").font(.caption2).foregroundStyle(.secondary)
                        Text("Uygulama yoklaması · \(BridgeStats.shared.summary)").font(.caption2).foregroundStyle(.secondary).help("Python köprüsüne yapılan çağrıların süresi; p95 birkaç yüz ms üzerindeyse Mac yavaşlamış demektir")
                    }.padding(14).meetingCard().accessibilityElement(children:.contain).accessibilityIdentifier("setupStatus")
                }
                Text("Kişi adlarını ve özel terimleri her satıra bir tane yazın.")
                TextEditor(text:$model.vocabulary).font(.body.monospaced()).frame(height:160).border(.quaternary)
                Text("Proje sözlüğü (glossary.jsonl)").font(.headline)
                Text(model.glossaryFromFile>0 ? "\(model.glossaryFromFile) terim dosyadan, toplam \(model.glossaryCount) · örnek: \(model.glossarySample.prefix(6).joined(separator:", ")) · iCloud Drive ile bütün Mac’lerde aynı" : "Henüz sözlük dosyası yok. Slack agent’ın ürettiği JSON Lines dosyasını içe aktarın; iCloud Drive üzerinden bütün Mac’lere yayılır.").font(.caption).foregroundStyle(.secondary)
                HStack {
                    Button("glossary.jsonl içe aktar…") { Task { await model.importGlossary() } }.accessibilityIdentifier("importGlossaryButton")
                    Text("Sözlük üç yerde kullanılır: bulut STT’ye yazım ipucu (etkisi sağlayıcıya bağlı), transkript sonrası düzeltme önerileri (Kontrol), özetlerde kısaltma açılımı. Ham metin hiçbir zaman kendiliğinden değiştirilmez.").font(.caption2).foregroundStyle(.secondary)
                }
                if let cost=model.cost, let month=cost["month"] as? [String:Any], let all=cost["all"] as? [String:Any] {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Bulut maliyeti").font(.headline)
                        HStack(spacing:12) {
                            SmallMetric(value:String(format:"$%.2f",month["usd"] as? Double ?? 0),label:"Bu ay · \(month["meetings"] as? Int ?? 0) toplantı, \(Int(month["minutes"] as? Double ?? 0)) dk",icon:"cloud")
                            SmallMetric(value:String(format:"$%.2f",all["usd"] as? Double ?? 0),label:"Toplam · \(all["meetings"] as? Int ?? 0) toplantı, \(Int(all["minutes"] as? Double ?? 0)) dk",icon:"sum")
                        }
                        Text("OpenRouter’ın bildirdiği transkript ücretleri (≈ $0.10/saat MAI-Transcribe 2). Özet/görev analizi ve yankı olarak atlanan parçalar dahil değildir.").font(.caption2).foregroundStyle(.secondary)
                    }
                }
                Text("Güncelleme ve raporlar").font(.headline)
                Text(model.update?.headline ?? "Sürüm kontrolü yapılmadı").font(.caption).foregroundStyle(.secondary)
                Text("Yeni sürüm varsa kenar çubuğunda ve menü çubuğu simgesinde “Güncelle ve yeniden başlat” görünür; güncelken düğme yoktur. Kontrol açılışta, uygulama öne gelince ve 15 dakikada bir yapılır.").font(.caption2).foregroundStyle(.secondary)
                HStack {
                    Button("Şimdi kontrol et") { Task { await model.checkForUpdates(force:true) } }
                    if model.update?.available==true { Button(model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat") { model.startUpdate() }.disabled(model.busy || model.recording || model.zoomMeetingOpen) }
                }
                Toggle("Yeni sürüm bulununca açılışta kendiliğinden güncelle (kayıt yokken)",isOn:$model.reportSettings.autoUpdate).onChange(of:model.reportSettings.autoUpdate) { _ in Task { await model.saveReportSettings() } }
                Toggle("Her toplantıdan sonra teşhis raporunu paylaşılan klasöre yaz",isOn:$model.reportSettings.shareReports).onChange(of:model.reportSettings.shareReports) { _ in Task { await model.saveReportSettings() } }
                Toggle("Raporlara transkript metnini de ekle (varsayılan kapalı)",isOn:$model.reportSettings.shareText).onChange(of:model.reportSettings.shareText) { _ in Task { await model.saveReportSettings() } }
                HStack {
                    Text(model.reportSettings.reportDir.replacingOccurrences(of:NSHomeDirectory(),with:"~")).font(.caption2.monospaced()).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle)
                    Spacer()
                    Button("Rapor klasörünü aç") { NSWorkspace.shared.open(URL(fileURLWithPath:model.reportSettings.reportDir)) }
                }
                Text("Raporlar yalnız sayı, puan, maliyet, model adı ve hata satırı içerir; iCloud Drive üzerinden diğer Mac’e geçer. Geliştirme oradaki raporlara bakılarak sürer.").font(.caption2).foregroundStyle(.secondary)
                Text("Kaydedilmiş sesler").font(.headline)
                Text("Aynı isimde farklı kişiler için ayırt edici bir ad kullanın (ör. Ali Tasarım). Yeni bir profil, aynı isimdeki mevcut kişinin ses örneklerine eklenir.").font(.caption).foregroundStyle(.secondary)
                if model.profiles.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        Label("Henüz ses profili yok",systemImage:"person.wave.2")
                        Text("Bir transkript bölümünde Düzelt düğmesine basarak temiz bir konuşma örneğinden profil kaydedebilirsiniz.").font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
                } else { VStack(alignment:.leading,spacing:4) { ForEach(model.profiles) { p in ProfileMaintenanceRow(model:model,profile:p) } }.padding(12).meetingCard() }
                Text("Görünüm").font(.headline)
                HStack(spacing:10) {
                    Picker("Tema",selection:$model.appearance) { Text("Sistem").tag("system"); Text("Açık").tag("light"); Text("Koyu").tag("dark") }.pickerStyle(.segmented).frame(width:220).accessibilityIdentifier("appearancePicker")
                    Text("Vurgu").font(.callout).foregroundStyle(.secondary)
                    ForEach(Accents.all,id:\.key) { a in
                        Button { model.accentKey=a.key } label: { Circle().fill(a.color).frame(width:18,height:18).overlay(Circle().stroke(Color.primary.opacity(model.accentKey==a.key ? 0.8 : 0),lineWidth:2)) }.buttonStyle(.plain).help(a.name).accessibilityIdentifier("accent-\(a.key)").accessibilityLabel(a.name)
                    }
                }
                Text("Tema uygulama penceresi ve yüzen paneli etkiler; menü çubuğu simgesi sistemi izler.").font(.caption2).foregroundStyle(.secondary)
                Text("Kayıt sırasında").font(.headline)
                Toggle("Zoom toplantısı açılınca bildirim gönder (kayıt yokken, 20 dakikada en fazla bir)",isOn:$model.zoomNotify)
                Toggle("Zoom toplantı penceresi açılınca kaydı kendiliğinden başlat, pencere kapanınca 1 dk sonra bitir (elle başlatılan kayıtlara dokunmaz)",isOn:$model.zoomAutoRecord)
                Toggle("Kayıt sırasında her pencerenin üstünde küçük kayıt paneli göster (süre, an işaretleri, bitir)",isOn:$model.showRecorderPanel)
                Toggle("Kayıt başlarken takvimdeki toplantının adını başlık yap, katılımcılarını adlandırmada öner (takvim yalnız okunur)",isOn:$model.useCalendar)
                if let storage=model.storage { StorageSection(model:model,storage:storage) }
                HStack {
                    Button("Veri klasörünü aç") { NSWorkspace.shared.open(model.dataDir) }
                    Spacer()
                    Button("Vazgeç") { model.showSettings=false }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelSettingsButton")
                    Button("Kaydet") { Task { await model.saveVocabulary() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("saveSettingsButton")
                }
            }.padding(28)
        }.scrollIndicators(.visible).frame(width:640,height:min(940,(NSScreen.main?.visibleFrame.height ?? 900)-80))
    }
}

/// Read-only disk usage; deletion goes through the sidebar's existing confirmation. No automatic cleanup.
struct StorageSection:View {
    @ObservedObject var model:Model
    let storage:StorageReport
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            Text("Depolama").font(.headline)
            Text("Toplam \(StorageReport.format(bytes:storage.total)) · Kayıtlar \(StorageReport.format(bytes:storage.recordings)) · İçe aktarımlar \(StorageReport.format(bytes:storage.imports)) · Veritabanı \(StorageReport.format(bytes:storage.database))")
                .font(.caption).foregroundStyle(.secondary)
            if storage.meetings.isEmpty {
                Text("Ses dosyası olan toplantı yok.").font(.caption).foregroundStyle(.secondary)
            } else {
                Text("En büyük toplantılar").font(.caption.weight(.semibold))
                ForEach(storage.largest(5)) { entry in
                    HStack {
                        Text(entry.title.isEmpty ? "Adsız toplantı" : entry.title).lineLimit(1)
                        Spacer()
                        Text(StorageReport.format(bytes:entry.bytes)).monospacedDigit().foregroundStyle(.secondary)
                        Button("Sil…",role:.destructive) { model.requestDelete(meetingID:entry.meeting) }
                            .disabled(model.busy || entry.active)
                            .accessibilityIdentifier("storageDelete-\(entry.meeting)")
                    }.font(.callout)
                }
                Text("Silme, arşivdeki onay penceresinden yapılır.").font(.caption2).foregroundStyle(.secondary)
            }
            Divider()
            HStack { Button("Sesleri sıkıştır") { Task { await model.compactStorage() } }.disabled(model.busy || model.recording).accessibilityIdentifier("compactStorageButton"); Text("Tamamlanmış kayıtlarda ham 12 saniyelik parçalar silinir ve birleştirilmiş ses kayıpsız FLAC’e çevrilir (≈3–4× küçülür; çalma ve ses profili aynen çalışır). Yeni kayıtlarda kendiliğinden yapılır.").font(.caption2).foregroundStyle(.secondary) }
            HStack(spacing:8) {
                Text("Eski toplantıların sesi").font(.callout)
                Picker("",selection:Binding(get:{ model.reportSettings.audioRetentionDays },set:{ v in model.reportSettings.audioRetentionDays=v; Task { await model.saveReportSettings() } })) { Text("silinmesin").tag(0); Text("14 gün sonra").tag(14); Text("30 gün sonra").tag(30); Text("60 gün sonra").tag(60); Text("90 gün sonra").tag(90) }.labelsHidden().frame(width:150).accessibilityIdentifier("audioRetentionPicker")
                Text("silinir; yazı, özet ve görevler kalır. “Sesi koru” işaretli toplantılara dokunulmaz. Saatte bir, kayıt yokken çalışır.").font(.caption2).foregroundStyle(.secondary)
            }
            Divider()
            Text("Eski sesleri temizle").font(.caption.weight(.semibold))
            Text("Transkript, özet, görevler ve ses profilleri kalır; yalnız tamamlanmış eski toplantıların ses dosyaları silinir. “Sesi koru” işaretli toplantılara dokunulmaz. Önce liste gösterilir.").font(.caption2).foregroundStyle(.secondary)
            HStack {
                Picker("Şundan eski",selection:$model.cleanupDays) { Text("30 gün").tag(30);Text("60 gün").tag(60);Text("90 gün").tag(90);Text("180 gün").tag(180) }.frame(width:200)
                Button("Silineceklere bak") { Task { await model.previewCleanup() } }.disabled(model.busy)
            }
            if let p=model.cleanupPreview {
                if p.count==0 { Text("\(p.days) günden eski, sesi silinebilecek toplantı yok.").font(.caption) }
                else {
                    Text("\(p.count) toplantının sesi silinecek · \(StorageReport.format(bytes:p.bytes)) boşalır · \(p.titles.joined(separator:", "))\(p.count>p.titles.count ? " …" : "")").font(.caption)
                    Button("Sesleri sil (\(StorageReport.format(bytes:p.bytes)))",role:.destructive) { Task { await model.runCleanup() } }.disabled(model.busy).accessibilityIdentifier("runCleanupButton")
                }
            }
            if let meeting=model.meeting {
                Toggle("Seçili toplantının sesini koru (“\(meeting.title)”)",isOn:Binding(get:{ meeting.metadata["keep"] as? Bool ?? false },set:{ v in Task { await model.keepMeeting(meeting.id,keep:v) } })).font(.caption)
            }
        }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
    }
}


/// Wrapping row of small tappable name chips (calendar attendees in the naming sheet).
struct FlowChips:View {
    let items:[String]; let pick:(String)->Void
    var body:some View {
        LazyVGrid(columns:[GridItem(.adaptive(minimum:110),spacing:6)],alignment:.leading,spacing:6) {
            ForEach(items,id:\.self) { name in
                Button(name) { pick(name) }.buttonStyle(.bordered).controlSize(.small).lineLimit(1).accessibilityIdentifier("attendee-\(name)")
            }
        }
    }
}
