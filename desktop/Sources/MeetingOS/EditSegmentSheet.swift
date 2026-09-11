import SwiftUI

/// "Konuşanı adlandır": one field, one question, one button. The name goes in, the scope picker says what the
/// name should touch (and a single line says what that means), and **Adlandır** does it. Word fixes are not here
/// at all — a wrong word is corrected by clicking the word in the transcript, which is both shorter and the only
/// place where the user can see which occurrence they mean. Text edits, the clean-sample toggle and the identity
/// explanation stay under "Gelişmiş" so the sheet never reads like a form.
struct EditSegmentSheet:View {
    @ObservedObject var model:Model
    let row:Row
    @State private var advanced=false
    @State private var scope:NamingScope = .speaker
    @State private var target:Row?   // the one piece "Yalnız bu bölüm" writes; defaults to the clicked paragraph's first piece
    /// Every piece of the paragraph this row opens: a wrong piece is usually one sentence inside a long paragraph.
    private var siblings:[Row] {
        // The same grouping the reading view uses ("3 bölüm"), built from the full row list rather than
        // `model.blocks` (those follow the ⌘F filter). Asides and hidden echo rows never split a paragraph here.
        TranscriptBlocks.build(CloudTranscription.visibleRows(model.rows,showEcho:model.showEchoRows)).first(where:{ b in b.rows.contains(where:{ $0.id==row.id }) })?.rows ?? [row]
    }
    private var textOnly:Bool { model.meeting?.metadata["text_only"] as? Bool == true }
    private var cluster:Bool { row.flags.contains("cloud_diarization") && !row.speaker.isEmpty }
    private var name:String { model.editName.trimmingCharacters(in:.whitespaces) }
    private var choices:[String] {
        let offered=Array(NSOrderedSet(array:model.calendarAttendees+model.profiles.map(\.name))) as? [String] ?? []
        return NameOrdering.order(choices:offered,ranked:cluster ? (model.explanation?.candidates ?? []) : [])
    }
    private var rankedByVoice:Bool { cluster && !(model.explanation?.candidates.isEmpty ?? true) }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            HStack(alignment:.firstTextBaseline) {
                Text(String(format:"%02d:%02d",Int(row.start)/60,Int(row.start)%60)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Spacer()
                if !textOnly && !model.recording { Button { model.play(row) } label: { PlayGlyph(playback:model.playback,key:"row:\(row.id)",text:"Dinle") }.controlSize(.small) }
            }
            Text("“"+row.text.prefix(180)+(row.text.count>180 ? "…" : "")+"”").font(.callout).foregroundStyle(.secondary).lineLimit(3)
            VStack(alignment:.leading,spacing:8) {
                TextField("Kim konuşuyor?",text:$model.editName).textFieldStyle(.roundedBorder).accessibilityIdentifier("editSpeakerNameField")
                    .onSubmit { Task { await primary() } }
                if !choices.isEmpty { FlowChips(items:Array(choices.prefix(12))) { model.editName=$0 } }
                if rankedByVoice { Text("İsimler bu sese benzerliğe göre sıralı; en benzeyen başta.").font(.caption2).foregroundStyle(.secondary).accessibilityIdentifier("nameOrderNote") }
            }
            // The one question the sheet asks: what should this name touch? Three answers, one line of
            // explanation for the selected one — never three paragraphs competing for the same attention.
            VStack(alignment:.leading,spacing:6) {
                if cluster {
                    Picker("Kapsam",selection:$scope) {
                        ForEach(NamingScope.options(cluster:true)) { s in Text(s.label).tag(s) }
                    }.pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("namingScopePicker")
                }
                Text(cluster ? scope.explanation : NamingScope.plainExplanation(textOnly:textOnly))
                    .font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                    .accessibilityIdentifier("namingScopeExplanation")
                if NamingScope.showsPiecePicker(scope:scope,cluster:cluster,pieces:siblings.count) {
                    Picker("Hangi bölüm?",selection:Binding(get:{ target?.id ?? row.id },set:{ id in target=siblings.first(where:{ $0.id==id }) })) {
                        ForEach(siblings) { r in Text("\(r.time) · \(String(r.text.prefix(60)))").tag(r.id) }
                    }.pickerStyle(.menu).controlSize(.small).accessibilityIdentifier("segmentPiecePicker")
                }
            }
            HStack {
                Button("Vazgeç") { model.editRow=nil }.accessibilityIdentifier("cancelEditButton")
                Spacer()
                Button("Adlandır") { Task { await primary() } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(name.isEmpty).accessibilityIdentifier("nameSpeakerButton")
            }
            // Word fixes live on the word itself: one click in the transcript, with the occurrence in view.
            Text("Yanlış yazılmış bir kelime için transkriptte kelimeye tıklayın.").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier("wordFixHint")
            DisclosureGroup("Gelişmiş",isExpanded:$advanced) {
                VStack(alignment:.leading,spacing:12) {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Metin").font(.caption).foregroundStyle(.secondary)
                        TextEditor(text:$model.editText).frame(height:90).border(.quaternary)
                        Button("Metni kaydet") { Task { await model.saveText() } }.disabled(model.editText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || model.editText==row.text).controlSize(.small)
                    }
                    if !textOnly {
                        Toggle("Dinledim: en az 6 saniye, tek kişi, temiz ses",isOn:$model.clean).font(.callout)
                            .help("İşaretliyken “Adlandır” bu bölümden ses profili de kaydeder; belirsiz sesler profili bozar")
                    }
                    if cluster {
                        Button("Neden bu isim?") { Task { await model.explainIdentity(row) } }.controlSize(.small).help("Bu sesin kayıtlı profillere ne kadar benzediğini tek cümleyle söyler")
                        if let ex=model.explanation {
                            Text(ex.sentence).font(.caption).fixedSize(horizontal:false,vertical:true)
                                .help(ex.detail).accessibilityIdentifier("identityExplanation")
                        }
                    }
                }.padding(.top,8)
            }.font(.callout)
            if !model.error.isEmpty { Text(ErrorPresentation.summary(model.error)).foregroundStyle(.red).font(.caption) }
        }.padding(.horizontal,24).padding(.top,14).padding(.bottom,24)
        .sheetChrome(title:"Konuşanı adlandır") { model.editRow=nil }
        .frame(width:520)
        // The ranking is the same call "Neden bu isim?" makes; fetched on open so the chips are ordered by the time
        // the user looks at them. A previous row's answer is cleared first so a stale order never shows.
        .task(id:row.id) { scope=NamingScope.initial(cluster:cluster); target=nil; model.explanation=nil; if cluster { await model.explainIdentity(row) } }
    }
    /// The one action: the scope decides which of the three model calls runs, and each of them already leaves a
    /// result line in `model.activity` saying what was named and what was learned.
    private func primary() async {
        guard !name.isEmpty else { return }
        switch scope.action(cluster:cluster,clean:model.clean) {
        case .speakerWithVoice:   await model.saveSpeaker(enroll:true)
        case .speakerThisMeeting: await model.saveSpeaker(enroll:false)
        case .segmentOnly:        await model.saveSegmentOnly(target ?? row)
        case .label(let enroll):  await model.saveLabel(enroll:enroll)
        }
    }
}
