import SwiftUI
import AppKit

// Root layout is a fixed-width sidebar + flexible detail HStack rather than
// NavigationSplitView: this guarantees the sidebar (and the recording
// stop control it holds) can never be collapsed or dragged to zero width,
// and keeps every region's height bounded so long content scrolls inside
// its own region instead of pushing headers/footers off-window.
struct MeetingContent:View {
    @StateObject var m=Model()
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
        .sheet(isPresented:$m.showTranscriptImport) { TranscriptImportSheet(model:m) }
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
                .accessibilityIdentifier("recordButton")
                .accessibilityLabel(RecoveryPresentation.recordingLabel(recording:model.recording,jobKind:model.jobKind))
                Button(action:model.importAudio) { Label("Ses dosyası aç",systemImage:"square.and.arrow.down").frame(maxWidth:.infinity) }
                    .controlSize(.large).disabled(model.busy)
                    .accessibilityIdentifier("importButton")
                    .accessibilityLabel("Ses dosyası aç")
                Button { model.showOpenRouter=true } label: { Label("OpenRouter ile ses aç",systemImage:"cloud").frame(maxWidth:.infinity) }.controlSize(.large).disabled(model.busy)
                Button { model.showTranscriptImport=true } label: { Label("ChatGPT metni aktar",systemImage:"doc.text.badge.plus").frame(maxWidth:.infinity) }
                    .controlSize(.large).disabled(model.busy)
                    .accessibilityIdentifier("transcriptImportButton")
            }.padding(18)
            HStack { Text("TOPLANTILAR").font(.system(size:10,weight:.semibold)).tracking(1.5);Spacer();Text("\(model.meetings.count)").monospacedDigit().font(.caption) }
                .foregroundStyle(.secondary).padding(.horizontal,18).padding(.bottom,6)
                .accessibilityHidden(true)
            List(selection:$model.selected) {
                ForEach(model.meetings) { meeting in
                    MeetingLibraryRow(meeting:meeting)
                        .tag(meeting.id)
                        .accessibilityIdentifier("meetingRow-\(meeting.id)")
                        .accessibilityLabel("\(meeting.title.isEmpty ? "Adsız toplantı" : meeting.title), \(statusLabel(meeting.displayStatus))")
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)
            .frame(maxHeight:.infinity)
            .accessibilityIdentifier("meetingLibraryList")
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
                Button { Task { await model.settings() } } label:{ Label("Sözlük ve ses profilleri",systemImage:"slider.horizontal.3").frame(maxWidth:.infinity,alignment:.leading) }
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
            if let meeting=model.meeting, meeting.metadata["capture_dir"] is String, !["complete","canceled"].contains(meeting.status), !model.busy {
                RecoveryBanner(model:model,meeting:meeting)
            }
            if model.meeting?.metadata["text_only"] as? Bool == true {
                Text(model.meeting?.metadata["imported_from"] as? String == "chatgpt_manual" ? "ChatGPT’den elle aktarılan metin · Ses kaydı ve doğrulanmış ses profili içermez" : "Kurgu metin örneği · Ses kaydı değildir").font(.caption).foregroundStyle(.secondary).padding(.horizontal,24).padding(.bottom,8)
            }
            if let meeting=model.meeting,meeting.metadata["engine"] as? String=="openrouter" {
                HStack {
                    Text("GPT Transcribe · OpenRouter | Konuşmacı ayrımı bu Mac’te").font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    if meeting.status != "complete" { Button("İşlemi sürdür") { model.showOpenRouter=true }.disabled(model.busy || meeting.recoveryState=="active") }
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
                case "memory": MemoryView(m:model)
                default: TranscriptView(model:model)
                }
            }.frame(maxWidth:.infinity,maxHeight:.infinity)
            Divider()
            HStack { Label("Yerel işleme",systemImage:"lock.shield"); Text("•"); Text("\(model.rows.count) bölüm"); Spacer(); Text("İsim düzeltmek ses profilini otomatik eğitmez.") }
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
                Text(model.meeting?.title ?? "Bir sonraki iyi fikri kaçırmayın.").font(.system(size:27,weight:.bold,design:.rounded)).lineLimit(2)
                HStack(spacing:6) {
                    Circle().fill(MeetingStyle.statusColor(model.meeting?.displayStatus ?? "")).frame(width:6,height:6)
                    Text(model.meeting.map { statusLabel($0.displayStatus) } ?? "Toplantı seçilmedi").font(.caption).foregroundStyle(.secondary)
                }.padding(.top,5)
            }
            Spacer(minLength:12)
            if model.busy { ProgressView().controlSize(.small) }
            Menu("Dışa aktar") {
                Button("Özet ve görevler (Markdown)") { Task { await model.export("analysis.md") } }
                Button("Transkript (Markdown)") { Task { await model.export("md") } }
                Button("Altyazı (SRT)") { Task { await model.export("srt") } }
                Button("JSON") { Task { await model.export("json") } }
            }
            .disabled(model.selected==nil)
            .accessibilityIdentifier("exportMenu")
            .accessibilityLabel("Dışa aktar")
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
            if canRetry {
                Button(meeting.displayStatus == "pending_finalization" ? "Transkripti tamamla" : "Toplantıyı kurtar",action:model.recover)
                    .accessibilityIdentifier("recoverButton")
            }
        }.padding(.horizontal,24).padding(.bottom,12)
    }
}

struct TranscriptSearchBar:View {
    @ObservedObject var model:Model
    var body:some View {
        HStack {
            Image(systemName:"magnifyingglass").foregroundStyle(.secondary)
            TextField("Bu konuşmada ara",text:$model.search)
                .textFieldStyle(.plain)
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
                if model.meeting?.metadata["text_only"] as? Bool != true {
                Button("Önce bölümü dinle") { model.play(row) }
                Toggle("Dinledim: en az 3 saniye, tek kişi, temiz ses",isOn:$model.clean)
                Text("Profili kaydedersen sonraki toplantılarda bu sesle eşleşen kişiye isim önerilir. Belirsiz eşleşmeler isimsiz kalır.").font(.caption).foregroundStyle(.secondary)
                } else {
                    Text("Bu toplantı yalnızca metin içerir. İsim düzeltmesi ses profili oluşturmaz.").font(.caption).foregroundStyle(.secondary)
                }
                HStack {
                    Button("Vazgeç") { model.editRow=nil }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelEditButton")
                    Spacer()
                    Button("Yalnızca ismi kaydet") { Task { await model.saveLabel(enroll:false) } }.disabled(model.editName.trimmingCharacters(in:.whitespaces).isEmpty)
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
                Text("Kişi adlarını ve özel terimleri her satıra bir tane yazın.")
                TextEditor(text:$model.vocabulary).font(.body.monospaced()).frame(height:160).border(.quaternary)
                Text("Kaydedilmiş sesler").font(.headline)
                Text("Aynı isimde farklı kişiler için ayırt edici bir ad kullanın (ör. Ali Tasarım). Yeni bir profil, aynı isimdeki mevcut kişinin ses örneklerine eklenir.").font(.caption).foregroundStyle(.secondary)
                if model.profiles.isEmpty {
                    VStack(alignment:.leading,spacing:6) {
                        Label("Henüz ses profili yok",systemImage:"person.wave.2")
                        Text("Bir transkript bölümünde Düzelt düğmesine basarak temiz bir konuşma örneğinden profil kaydedebilirsiniz.").font(.caption).foregroundStyle(.secondary)
                    }.frame(maxWidth:.infinity,alignment:.leading).padding(16).meetingCard()
                } else { List(model.profiles) { p in
                    HStack {
                        VStack(alignment:.leading) { Text(p.name);Text("\(p.samples) örnek · \(p.model)").font(.caption).foregroundStyle(.secondary) }
                        Spacer()
                        Button("Profili sil",role:.destructive) { Task { await model.deleteProfile(p.name) } }.accessibilityIdentifier("deleteProfile-\(p.name)")
                    }
                }.frame(height:140) }
                HStack {
                    Button("Veri klasörünü aç") { NSWorkspace.shared.open(model.dataDir) }
                    Spacer()
                    Button("Vazgeç") { model.showSettings=false }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelSettingsButton")
                    Button("Kaydet") { Task { await model.saveVocabulary() } }.buttonStyle(.borderedProminent).accessibilityIdentifier("saveSettingsButton")
                }
            }.padding(28)
        }.frame(width:600,height:560)
    }
}
