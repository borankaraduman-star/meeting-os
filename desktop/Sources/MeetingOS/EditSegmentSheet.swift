import SwiftUI

/// "Düzelt": one field, one primary action. Naming a voice is the everyday task; text edits and
/// the identity explanation live under "Gelişmiş" so the sheet never reads like a form.
struct EditSegmentSheet:View {
    @ObservedObject var model:Model
    let row:Row
    @State private var advanced=false
    private var textOnly:Bool { model.meeting?.metadata["text_only"] as? Bool == true }
    private var cluster:Bool { row.flags.contains("cloud_diarization") && !row.speaker.isEmpty }
    private var name:String { model.editName.trimmingCharacters(in:.whitespaces) }
    private var choices:[String] { Array(NSOrderedSet(array:model.calendarAttendees+model.profiles.map(\.name))) as? [String] ?? [] }
    var body:some View {
        VStack(alignment:.leading,spacing:16) {
            HStack(alignment:.firstTextBaseline) {
                Text("Düzelt").font(.title2.bold())
                Text(String(format:"%02d:%02d",Int(row.start)/60,Int(row.start)%60)).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                Spacer()
                if !textOnly && !model.recording { Button { model.play(row) } label: { Label("Dinle",systemImage:"play.circle") }.controlSize(.small) }
            }
            Text("“"+row.text.prefix(180)+(row.text.count>180 ? "…" : "")+"”").font(.callout).foregroundStyle(.secondary).lineLimit(3)
            VStack(alignment:.leading,spacing:8) {
                TextField("Kim konuşuyor?",text:$model.editName).textFieldStyle(.roundedBorder).accessibilityIdentifier("editSpeakerNameField")
                    .onSubmit { Task { await primary() } }
                if !choices.isEmpty { FlowChips(items:Array(choices.prefix(12))) { model.editName=$0 } }
            }
            Text(cluster ? "Bu toplantıdaki bütün “\(row.speaker)” bölümleri bu adı alır; ses profili kaydedilir ve sonraki toplantılarda kendiliğinden tanınır." : (textOnly ? "Bu toplantı yalnızca metin içerir; isim yalnız bu bölüme yazılır." : "İsim bu bölüme yazılır. Sesi öğrenmesi için “Gelişmiş” altında temiz ses onayı verin.")).font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Vazgeç") { model.editRow=nil }.keyboardShortcut(.cancelAction).accessibilityIdentifier("cancelEditButton")
                Spacer()
                if cluster { Button("Yalnız bu toplantıda") { Task { await model.saveSpeaker(enroll:false) } }.disabled(name.isEmpty) }
                Button(cluster ? "Adlandır ve öğren" : "Adlandır") { Task { await primary() } }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(name.isEmpty).accessibilityIdentifier("nameSpeakerButton")
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
                        HStack {
                            Button("Yalnız bu bölümü adlandır") { Task { await model.saveLabel(enroll:false) } }.disabled(name.isEmpty).controlSize(.small)
                            Button("Bu bölümden ses profili kaydet") { Task { await model.saveLabel(enroll:true) } }.disabled(!model.clean || name.isEmpty).controlSize(.small).help("Yalnız temiz, tek kişilik bir bölümden profil kaydedin; belirsiz sesler profili bozar")
                        }
                    }
                    if cluster {
                        HStack { Button("Neden bu isim?") { Task { await model.explainIdentity(row) } }.controlSize(.small); Text("Ses profillerine benzerlik puanları").font(.caption2).foregroundStyle(.secondary) }
                        if let ex=model.explanation {
                            VStack(alignment:.leading,spacing:3) {
                                if !ex.reason.isEmpty { Text(ex.reason).font(.caption) }
                                ForEach(Array(ex.candidates.enumerated()),id:\.element.id) { i,c in
                                    VStack(alignment:.leading,spacing:1) {
                                        Text("\(c.name): \(String(format:"%.2f",c.score)) (merkez \(String(format:"%.2f",c.centroid)), en yakın örnek \(String(format:"%.2f",c.bestSample)), \(c.samples) örnek) \(ex.verdict(for:c,rank:i))").font(.caption.monospacedDigit())
                                        if !c.personNote.isEmpty { Text(c.personNote).font(.caption2).foregroundStyle(.secondary) }   // why this person is hard or easy to hit
                                    }
                                }
                                Text("İsim eşiği \(String(format:"%.2f",ex.threshold)), öneri eşiği \(String(format:"%.2f",ex.suggest)), ikinci adaya en az \(String(format:"%.2f",ex.margin)) fark · bu kümede \(String(format:"%.0f",ex.seconds)) sn ses").font(.caption2).foregroundStyle(.secondary)
                            }
                        }
                    }
                }.padding(.top,8)
            }.font(.callout)
            if !model.error.isEmpty { Text(ErrorPresentation.summary(model.error)).foregroundStyle(.red).font(.caption) }
        }.padding(24).frame(width:520)
    }
    /// The default action: name the whole cluster and learn the voice; for a plain segment, just the label.
    private func primary() async {
        guard !name.isEmpty else { return }
        if cluster { await model.saveSpeaker(enroll:true) } else { await model.saveLabel(enroll:false) }
    }
}
