import SwiftUI

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
