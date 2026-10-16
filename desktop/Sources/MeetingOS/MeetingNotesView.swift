import SwiftUI

/// The user's own notes beside the transcript — kept apart from it: the finalizer, a retry and the AI summary write the
/// transcript and the summary, never this text. Saved on this Mac only; no cloud payload carries it.
struct MeetingNotesView:View {
    @ObservedObject var model:Model
    @FocusState private var editorFocused:Bool
    @State private var comparing=false
    var body:some View {
        let note=model.note
        VStack(alignment:.leading,spacing:10) {
            HStack(alignment:.firstTextBaseline,spacing:8) {
                Text("Notlarım").font(.headline)
                Spacer(minLength:4)
                Text(note.indicator).font(.caption).foregroundStyle(note.failed || note.state == .conflict ? Color.orange : Color.secondary).accessibilityIdentifier("noteIndicator")
                Button { model.flushNote(); model.showNotes=false } label: { Image(systemName:"sidebar.trailing") }.buttonStyle(.plain).foregroundStyle(.secondary).help("Notları gizle").accessibilityLabel("Notları gizle")
            }
            if note.revision>0 || !note.text.isEmpty { Text(note.authorLabel).font(.caption2).foregroundStyle(.secondary).accessibilityIdentifier("noteAuthor") }
            if note.key != model.noteTarget { Label("Önceki notunuz kaydediliyor…",systemImage:"clock").font(.caption).foregroundStyle(.secondary) }
            if note.state == .conflict, let theirs=note.conflict { conflictBar(theirs) }
            if !model.recording, model.noteOrphan != nil { orphanBar }
            if !model.noteNotice.isEmpty { Text(model.noteNotice).font(.caption).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
            TextEditor(text:Binding(get:{ model.note.text },set:{ model.noteEdited($0) }))
                .font(.body).scrollContentBackground(.hidden).padding(6)
                .background(MeetingStyle.surface,in:RoundedRectangle(cornerRadius:8))
                .overlay(RoundedRectangle(cornerRadius:8).strokeBorder(.primary.opacity(0.08)))
                .focused($editorFocused)
                .onChange(of:editorFocused) { _,focused in if !focused { model.flushNote() } }
                .accessibilityIdentifier("noteEditor").accessibilityLabel("Toplantı notu")
            anchorButton
            if !note.anchors.isEmpty {
                VStack(alignment:.leading,spacing:6) { ForEach(note.anchors) { anchorRow($0) } }
            }
            Text("Notlar yalnız bu Mac’te saklanır, buluta gönderilmez.").font(.caption2).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
        }
        .padding(14)
        .popover(isPresented:$comparing) { compareView }
    }

    @ViewBuilder func conflictBar(_ theirs:NoteConflict)->some View {
        VStack(alignment:.leading,spacing:6) {
            Label("Bu not başka yerde değişti. Sizin yazdığınız burada duruyor.",systemImage:"exclamationmark.triangle").font(.caption).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true)
            HStack(spacing:6) {
                Button("Benim sürümümü kaydet") { model.keepMyNote() }.accessibilityIdentifier("noteKeepMine")
                Button("Diğerini al") { model.takeTheirNote() }.accessibilityIdentifier("noteTakeTheirs")
                Button("Karşılaştır") { comparing=true }.accessibilityIdentifier("noteCompare")
            }.controlSize(.small)
        }.padding(8).background(Color.orange.opacity(0.08),in:RoundedRectangle(cornerRadius:8))
    }

    /// A note written while a recording was preparing that never became a meeting: never lost, and reachable now.
    @ViewBuilder var orphanBar:some View {
        VStack(alignment:.leading,spacing:6) {
            Label("Başlamayan bir kayıtta yazdığınız not saklı. Bir sonraki kayıtta burada açılır.",systemImage:"tray.full").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            if let mid=model.selected, model.note.key == .meeting(mid) {
                Button("Bu toplantıya taşı") { model.moveOrphanNote() }.controlSize(.small).accessibilityIdentifier("noteMoveOrphan")
            }
        }.padding(8).background(MeetingStyle.surface,in:RoundedRectangle(cornerRadius:8))
    }

    var compareView:some View {
        HStack(alignment:.top,spacing:12) {
            VStack(alignment:.leading,spacing:6) { Text("Sizin sürümünüz").font(.caption.weight(.semibold)); ScrollView { Text(model.note.text).textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading) } }
            Divider()
            VStack(alignment:.leading,spacing:6) { Text("Kayıtlı sürüm").font(.caption.weight(.semibold)); ScrollView { Text(model.note.conflict?.text ?? "").textSelection(.enabled).frame(maxWidth:.infinity,alignment:.leading) } }
        }.padding(14).frame(width:560,height:320)
    }

    /// While recording: the last fifteen seconds on the recording's clock, system audio by default. On a finished
    /// meeting: the segment the user last played or jumped to — its own source, start, end and id.
    @ViewBuilder var anchorButton:some View {
        if model.noteIsRecordingNote {
            Menu {
                Button("Sistem sesi (karşı taraf)") { liveAnchor("system") }
                Button("Mikrofon (siz)") { liveAnchor("mic") }
            } label: { Label("Bu ana bağla",systemImage:"link") } primaryAction: { liveAnchor("system") }
                .menuStyle(.borderlessButton).fixedSize().help("Notu kayıtta şu anki son 15 saniyeye bağlar").accessibilityIdentifier("noteAnchorButton")
        } else {
            let seg=NoteTarget.selectedSegment(lastPlayed:model.noteSegment,focused:model.focusedSegment,highlighted:model.highlighted)
            let row=seg.flatMap { id in model.rows.first { $0.id==id } }
            Button { if let row { model.addNoteAnchor(NoteTarget.segmentAnchor(id:row.id,source:row.source,start:row.start,end:row.end)) } } label: { Label("Bu ana bağla",systemImage:"link") }
                .controlSize(.small).disabled(row==nil || model.recording)
                .help(row==nil ? "Önce transkriptte bir bölümü dinleyin; not o bölümün sesine bağlanır" : "Notu dinlediğiniz bölüme bağlar")
                .accessibilityIdentifier("noteAnchorButton")
        }
    }
    func liveAnchor(_ source:String) {
        guard let started=model.recordStartedAt else { return }
        let now=Date()
        model.addNoteAnchor(NoteTarget.liveAnchor(elapsed:now.timeIntervalSince(started),source:source,wall:now.timeIntervalSince1970))
    }

    @ViewBuilder func anchorRow(_ a:NoteAnchor)->some View {
        HStack(spacing:6) {
            Image(systemName:a.available ? "waveform" : "exclamationmark.triangle").foregroundStyle(a.available ? MeetingStyle.accent : .orange)
            VStack(alignment:.leading,spacing:1) {
                Text(a.label).font(.caption).monospacedDigit()
                if !a.available { Text("Kaynak kullanılamıyor").font(.caption2).foregroundStyle(.orange) }
            }
            Spacer(minLength:4)
            if a.available, !model.recording, model.note.key==model.selected.map({ NoteKey.meeting($0) }), let m=model.meeting {
                if let seg=a.transcriptRow(in:model.rows) {
                    Button { model.tab="transcript"; model.navigate { model.reveal(segment:seg) } } label: { Image(systemName:"text.magnifyingglass") }.buttonStyle(.plain).help("Transkriptte göster")
                }
                Button { model.play(source:a.source,start:a.start,seconds:a.end-a.start,metadata:m.metadata,key:"note:\(a.id)") } label: { PlayGlyph(playback:model.playback,key:"note:\(a.id)",text:"") }.buttonStyle(.plain).help("Bu aralığı dinle")
            }
            Button { model.removeNoteAnchor(a.id) } label: { Image(systemName:"xmark.circle") }.buttonStyle(.plain).foregroundStyle(.secondary).help("Bağı kaldır").accessibilityLabel("Bağı kaldır")
        }.accessibilityElement(children:.combine)
    }
}
