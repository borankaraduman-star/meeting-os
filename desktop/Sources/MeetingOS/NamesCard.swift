import SwiftUI

/// The one thing most meetings need after transcription: give each unnamed voice a name.
/// Lives above the transcript so nobody has to discover the Kontrol tab; one tap per person.
struct NamesCard:View {
    @ObservedObject var model:Model
    @State private var drafts:[String:String]=[:]
    /// One entry per speaker cluster still waiting for a name (suggested or unnamed); short matches stay in Kontrol.
    private var pending:[ReviewItem] {
        var seen=Set<String>()
        return model.review.filter { ($0.kind=="suggested_name" || $0.kind=="unnamed_speaker") && !$0.speakerKey.isEmpty && seen.insert($0.speakerKey).inserted }
    }
    private var suggested:[ReviewItem] { pending.filter { !$0.suggested.isEmpty } }
    private var choices:[String] { NameFold.unique(model.calendarAttendees+model.profiles.map(\.name)) }
    /// The very first meeting: nothing to suggest, nobody to pick from a list. Say why, once, instead of
    /// leaving a row of empty fields that looks like something failed.
    private var firstMeeting:Bool { suggested.isEmpty && choices.isEmpty }
    var body:some View {
        let items=pending
        if !items.isEmpty, model.meeting?.status=="complete" {
            VStack(alignment:.leading,spacing:10) {
                HStack(spacing:8) {
                    Image(systemName:"person.crop.circle.badge.questionmark").foregroundStyle(MeetingStyle.accent)
                    Text("İsimler · \(items.count) kişi bekliyor").font(.headline)
                    Spacer()
                    if suggested.count>1 { Button("Hepsini onayla (\(suggested.count))") { Task { await model.confirmAll(suggested) } }.buttonStyle(.borderedProminent).controlSize(.small).disabled(model.busy).accessibilityIdentifier("namesConfirmAll") }
                    Button("Kontrol") { model.tab="review" }.controlSize(.small).help("Şüpheli bölümlerin tam listesi")
                }
                Text(firstMeeting ? "İlk toplantı: henüz ses profili yok. Adları bir kez yazın; sonraki toplantılarda bu sesler kendiliğinden tanınır." : "Bir kez adlandırın; ses profili kaydedilir ve sonraki toplantılarda kendiliğinden tanınır.").font(.caption).foregroundStyle(.secondary).accessibilityIdentifier(firstMeeting ? "namesFirstMeeting" : "namesHint")
                ForEach(items) { item in
                    HStack(spacing:8) {
                        Button { if let seg=item.segment { model.reveal(segment:seg) } } label: { Label(item.speaker.isEmpty ? item.speakerKey : item.speaker,systemImage:"text.quote").lineLimit(1) }.buttonStyle(.plain).foregroundStyle(.secondary).frame(width:150,alignment:.leading).help(item.text)
                        if let seg=item.segment, !model.recording, model.rows.contains(where:{ $0.id==seg }) { Button { if let row=model.rows.first(where:{ $0.id==seg }) { model.play(row) } } label: { PlayGlyph(playback:model.playback,key:"row:\(seg)") }.buttonStyle(.plain).help("Bu sesi dinle · durdurmak için yine tıklayın") }
                        if !item.suggested.isEmpty {
                            Button("“\(item.suggested)” onayla") { Task { await model.confirmReview(item) } }.buttonStyle(.borderedProminent).controlSize(.small).disabled(model.busy).accessibilityIdentifier("namesConfirm-\(item.speakerKey)")
                        }
                        TextField(item.suggested.isEmpty ? "İsim yaz ve ⏎" : "Başka bir isim",text:Binding(get:{ drafts[item.speakerKey] ?? "" },set:{ drafts[item.speakerKey]=$0 }))
                            .textFieldStyle(.roundedBorder).controlSize(.small).frame(width:170)
                            .onSubmit { let n=(drafts[item.speakerKey] ?? "").trimmingCharacters(in:.whitespaces); guard !n.isEmpty else { return }; Task { await model.nameSpeaker(item.speakerKey,n); drafts[item.speakerKey]=nil } }
                            .accessibilityIdentifier("namesField-\(item.speakerKey)")
                        if !choices.isEmpty {
                            Menu { ForEach(choices,id:\.self) { n in Button(n) { Task { await model.nameSpeaker(item.speakerKey,n) } } } } label: { Image(systemName:"person.2") }.menuStyle(.borderlessButton).frame(width:28).help("Takvimdeki katılımcılar ve kayıtlı profiller")
                        }
                        Spacer(minLength:0)
                    }.font(.callout)
                }
            }.padding(14).meetingCard().accessibilityElement(children:.contain).accessibilityIdentifier("namesCard")
        }
    }
}
