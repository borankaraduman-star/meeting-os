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
                .help(model.recording ? "Kaydı bitir (⌃⌥R her yerden)" : "Yeni kayıt (⌃⌥R her yerden)")
                .accessibilityIdentifier("recordButton")
                .accessibilityLabel(RecoveryPresentation.recordingLabel(recording:model.recording,jobKind:model.jobKind))
                Button { model.showOpenRouter=true } label: { Label("Ses dosyası aç…",systemImage:"waveform.badge.plus").frame(maxWidth:.infinity) }.controlSize(.small).disabled(model.busy).help("Bir ses dosyasını OpenRouter ile yazıya çevirip toplantı olarak ekler")
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
                DisclosureGroup(isExpanded:$model.showTranscriptionOptions) {
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
                } label: {
                    Text(model.transcriptionMode=="openrouter" ? "OpenRouter · \(model.cloudModels.first { $0.id==model.cloudModel }?.name ?? "model")" : "Yerel model").font(.caption).foregroundStyle(.secondary).lineLimit(1)
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
                Button { Task { await model.settings() } } label:{ Label("Ayarlar",systemImage:"slider.horizontal.3").frame(maxWidth:.infinity,alignment:.leading) }.keyboardShortcut(",",modifiers:.command).help("Ayarlar (⌘,)")
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
                if model.meetings.isEmpty && !model.recording { WelcomeView(model:model) } else {
                switch model.tab {
                case "analysis": AnalysisView(m:model)
                case "actions": ActionsView(m:model)
                case "review": ReviewView(model:model)
                case "memory": MemoryView(m:model)
                default: TranscriptView(model:model)
                } }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
            Divider()
            if let e=model.meeting?.metadata["identity_error"] as? String, !e.isEmpty {
                HStack { Label(e,systemImage:"exclamationmark.triangle").foregroundStyle(.orange); Spacer() }.font(.caption).padding(.horizontal,12).padding(.vertical,6)
            }
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
                Menu("Belge hazırla (OpenRouter)") {
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


