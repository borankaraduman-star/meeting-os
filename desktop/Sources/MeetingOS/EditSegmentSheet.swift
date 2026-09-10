import SwiftUI

/// "Düzelt": one field, one primary action. Naming a voice is the everyday task; text edits and
/// the identity explanation live under "Gelişmiş" so the sheet never reads like a form.
struct EditSegmentSheet:View {
    @ObservedObject var model:Model
    let row:Row
    @State private var advanced=false
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
    private var choices:[String] { Array(NSOrderedSet(array:model.calendarAttendees+model.profiles.map(\.name))) as? [String] ?? [] }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            HStack(alignment:.firstTextBaseline) {
                Text("Konuşanı adlandır").font(.title2.bold())
                Text(String(format:"%02d:%02d",Int(row.start)/60,Int(row.start)%60)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Spacer()
                if !textOnly && !model.recording { Button { model.play(row) } label: { PlayGlyph(playback:model.playback,key:"row:\(row.id)",text:"Dinle") }.controlSize(.small) }
            }
            Text("“"+row.text.prefix(180)+(row.text.count>180 ? "…" : "")+"”").font(.callout).foregroundStyle(.secondary).lineLimit(3)
            VStack(alignment:.leading,spacing:8) {
                TextField("Kim konuşuyor?",text:$model.editName).textFieldStyle(.roundedBorder).accessibilityIdentifier("editSpeakerNameField")
                    .onSubmit { Task { await primary() } }
                if !choices.isEmpty { FlowChips(items:Array(choices.prefix(12))) { model.editName=$0 } }
            }
            if cluster && siblings.count>1 {
                Picker("Yalnız bir bölüm için: hangisi?",selection:Binding(get:{ target?.id ?? row.id },set:{ id in target=siblings.first(where:{ $0.id==id }) })) {
                    ForEach(siblings) { r in Text("\(r.time) · \(String(r.text.prefix(60)))").tag(r.id) }
                }.pickerStyle(.menu).controlSize(.small)
            }
            Text(cluster ? "“Adlandır ve öğren” bu toplantıdaki bütün “\(row.speaker)” bölümlerine bu adı verir ve sesi öğrenir. Yalnız bir cümle yanlış kişiye gittiyse “Yalnız bu bölüm”: sadece o bölüm değişir, geri kalanı ve kişinin profili olduğu gibi kalır, bölüm temizse doğru kişinin profili ondan öğrenir." : (textOnly ? "Bu toplantı yalnızca metin içerir; isim yalnız bu bölüme yazılır." : "İsim bu bölüme yazılır. Sesi öğrenmesi için “Gelişmiş” altında temiz ses onayı verin.")).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Vazgeç") { model.editRow=nil }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelEditButton")
                Spacer()
                if cluster { Button("Yalnız bu toplantıda") { Task { await model.saveSpeaker(enroll:false) } }.disabled(name.isEmpty) }
                if cluster { Button("Yalnız bu bölüm") { Task { await model.saveSegmentOnly(target ?? row) } }.disabled(name.isEmpty).help("Sadece bu bölüm bu kişiye ait; konuşmacının geri kalanı doğru").accessibilityIdentifier("segmentOnlyButton") }
                Button(cluster || model.clean ? "Adlandır ve öğren" : "Adlandır") { Task { await primary() } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(name.isEmpty).accessibilityIdentifier("nameSpeakerButton")
            }
            DisclosureGroup("Gelişmiş",isExpanded:$advanced) {
                VStack(alignment:.leading,spacing:12) {
                    VStack(alignment:.leading,spacing:6) {
                        Text("Metin").font(.caption).foregroundStyle(.secondary)
                        TextEditor(text:$model.editText).frame(height:90).border(.quaternary)
                        Button("Metni kaydet") { Task { await model.saveText() } }.disabled(model.editText.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty || model.editText==row.text).controlSize(.small)
                    }
                    if !textOnly {
                        Toggle("Dinledim: en az 6 saniye, tek kişi, temiz ses",isOn:$model.clean).font(.callout)
                            .help("İşaretliyken “Adlandır ve öğren” bu bölümden ses profili de kaydeder; belirsiz sesler profili bozar")
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
        }.padding(24).frame(width:520)
    }
    /// The default action: name the whole cluster and learn the voice. A plain segment gets the label, and the
    /// voice too when the user has confirmed the clip is clean — which is what the two extra buttons used to do.
    private func primary() async {
        guard !name.isEmpty else { return }
        if cluster { await model.saveSpeaker(enroll:true) } else { await model.saveLabel(enroll:model.clean) }
    }
}
