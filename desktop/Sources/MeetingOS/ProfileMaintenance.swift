import SwiftUI
import UserNotifications

/// A sample can outlive the meeting it was cut from: the bridge then sends "toplantı silindi" (and older
/// bridges send nothing at all). Either way a row must never print a bare " · · 12 sn".
enum MeetingLabel {
    static let unknown="bilinmeyen toplantı"
    static func title(_ raw:Any?)->String {
        let t=(raw as? String ?? "").trimmingCharacters(in:.whitespacesAndNewlines)
        return t.isEmpty ? unknown : t
    }
}

struct VoiceSample:Identifiable, Equatable {
    let id:Int; let seconds:Double; let kind:String; let meetingTitle:String; let model:String
    /// Team samples only: the Mac that enrolled this voice. They carry no meeting at all — the shared file has a
    /// name, a model and a vector, and never says which meeting the person was heard in.
    let host:String
    var isTeam:Bool { kind=="ekip" }
    /// The card above says "N otomatik, M elle"; a row must use the same words, not the storage `kind`.
    var origin:String { isTeam ? "ekipten (\(host))" : (kind=="otomatik" ? "otomatik" : "elle") }
    /// A team sample has no meeting to name, so the row says where it came from instead of "bilinmeyen toplantı".
    var where_:String { isTeam ? "ekip klasörü" : meetingTitle }
    init(_ d:[String:Any]) { id=d["id"] as? Int ?? 0; seconds=d["seconds"] as? Double ?? 0; kind=d["kind"] as? String ?? ""; meetingTitle=MeetingLabel.title(d["meeting_title"]); model=d["model"] as? String ?? ""; host=d["host"] as? String ?? "" }
}

struct IdentityCandidate:Identifiable, Equatable {
    let name:String; let score:Double; let centroid:Double; let bestSample:Double; let samples:Int
    /// Why this person is hard or easy to hit: one sample, a sample that does not fit, or a bar the user's own
    /// corrections have moved. The bar itself is `thresholdUsed` (0 when the bridge did not send one).
    let personNote:String; let thresholdUsed:Double
    var id:String { name }
    init(_ d:[String:Any]) { name=d["name"] as? String ?? ""; score=d["score"] as? Double ?? 0; centroid=d["centroid"] as? Double ?? 0; bestSample=d["best_sample"] as? Double ?? 0; samples=d["samples"] as? Int ?? 0; personNote=d["person_note"] as? String ?? ""; thresholdUsed=d["threshold_used"] as? Double ?? 0 }
}

/// "Why did it think this was Ayşe?" — scores against every saved person, with the thresholds that decide.
struct IdentityExplanation:Equatable {
    let candidates:[IdentityCandidate]; let threshold:Double; let margin:Double; let suggest:Double; let seconds:Double; let reason:String
    /// `explain_identity` sends threshold/margin/suggest on every branch; these stand in only for an answer from
    /// an older bridge that did not. They are a last resort, never a second opinion about what the bars are.
    static let legacyThreshold=0.87, legacyMargin=0.05, legacySuggest=0.83
    static func parse(_ d:[String:Any])->IdentityExplanation {
        IdentityExplanation(candidates:(d["candidates"] as? [[String:Any]] ?? []).map(IdentityCandidate.init),threshold:d["threshold"] as? Double ?? legacyThreshold,margin:d["margin"] as? Double ?? legacyMargin,suggest:d["suggest"] as? Double ?? legacySuggest,seconds:d["seconds"] as? Double ?? 0,reason:d["reason"] as? String ?? "")
    }
    /// The bar this person actually had to clear: their own when corrections have moved it, otherwise the global one.
    func bar(for c:IdentityCandidate)->Double { c.thresholdUsed>0 ? c.thresholdUsed : threshold }
    /// "Neden bu isim?" in one sentence. Who this voice sounds like, and why that was — or was not — enough.
    var sentence:String {
        guard let top=candidates.first else { return "Karşılaştırılacak kayıtlı ses yok, bu yüzden isim verilmedi." }
        let pct=Int((top.score*100).rounded())
        let gap=candidates.count>1 ? top.score-candidates[1].score : 1.0
        if top.score>=bar(for:top) && gap>=margin { return "Bu ses “\(top.name)” profiline %\(pct) benziyor ve ikinci adaydan açık ara önde — bu yüzden bu isim verildi." }
        if top.score>=suggest && gap>=margin { return "Bu ses “\(top.name)” profiline %\(pct) benziyor ama emin olacak kadar değil — bu yüzden yalnızca önerildi." }
        if gap<margin && candidates.count>1 { return "Bu ses “\(top.name)” profiline %\(pct) benziyor, ikinci adaya farkı az — bu yüzden isim verilmedi." }
        return "En yakın kayıtlı ses “\(top.name)”, %\(pct) — yeterince benzemiyor, bu yüzden isim verilmedi."
    }
    /// The numbers behind that sentence: every candidate, the bars they had to clear, and how much voice there was.
    var detail:String {
        let rows=candidates.map { c in "\(c.name): \(String(format:"%.2f",c.score)) (merkez \(String(format:"%.2f",c.centroid)), en yakın örnek \(String(format:"%.2f",c.bestSample)), \(c.samples) örnek, eşik \(String(format:"%.2f",bar(for:c))))"+(c.personNote.isEmpty ? "" : " · "+c.personNote) }
        let bars="İsim eşiği \(String(format:"%.2f",threshold)), öneri eşiği \(String(format:"%.2f",suggest)), ikinci adaya en az \(String(format:"%.2f",margin)) fark · bu kümede \(String(format:"%.0f",seconds)) sn ses"
        return (rows+[bars]).joined(separator:"\n")
    }
    func verdict(for c:IdentityCandidate,rank:Int)->String {
        let gap=rank==0 && candidates.count>1 ? c.score-candidates[1].score : 1.0
        if rank>0 { return "" }
        let bar=bar(for:c)
        if c.score>=bar && gap>=margin { return "isim verildi" }
        if c.score>=suggest && gap>=margin { return "öneri (soru işaretli)" }
        if c.score>=bar && gap<margin { return "ikinci adaya çok yakın, isim verilmedi" }
        return "eşik altı, isim verilmedi"
    }
}

/// Q8: one person's profile as the maintenance screen sees it — how it is built, how well it holds together,
/// and when this voice was last heard. Comes from `store.profile_health()` via the `maintenance` action.
struct ProfileHealth:Equatable {
    let name:String; let model:String; let samples:Int; let autoSamples:Int; let seconds:Double; let rejections:Int
    /// Samples a teammate's Mac enrolled and this one imported through the team folder.
    let teamSamples:Int
    let weakestFit:Double?; let weakestSample:Int?; let weak:Bool; let lastMeetingTitle:String
    init(_ d:[String:Any]) {
        name=d["name"] as? String ?? ""; model=d["model"] as? String ?? ""; samples=d["samples"] as? Int ?? 0
        autoSamples=d["auto_samples"] as? Int ?? 0; seconds=d["seconds"] as? Double ?? 0; rejections=d["rejections"] as? Int ?? 0
        teamSamples=d["team_samples"] as? Int ?? 0
        weakestFit=d["weakest_fit"] as? Double; weakestSample=d["weakest_sample"] as? Int; weak=d["weak"] as? Bool ?? false
        lastMeetingTitle=d["last_meeting_title"] as? String ?? ""
    }
    /// The number itself only belongs in a tooltip: the everyday line says whether something is wrong, not how wrong.
    var fitHelp:String { weakestFit.map { "En zayıf örnek benzerliği "+String(format:"%.2f",$0).replacingOccurrences(of:".",with:",") } ?? "" }
    /// One line under the name; everything a person needs before deciding to add or drop a sample.
    var line:String {
        var parts=["\(samples) örnek (\(autoSamples) otomatik, \(max(0,samples-autoSamples-teamSamples)) elle"+(teamSamples>0 ? ", \(teamSamples) ekipten" : "")+")"]
        parts.append(seconds>=60 ? "\(Int(seconds/60)) dk ses" : "\(Int(seconds)) sn ses")
        if weak { parts.append("bir örnek diğerlerine benzemiyor") }
        if rejections>0 { parts.append("\(rejections) ret") }
        parts.append(lastMeetingTitle.isEmpty ? "hiç duyulmadı" : "son: "+lastMeetingTitle)
        return parts.joined(separator:" · ")
    }
}

/// A turn that could become a voice sample: long enough, no uncertainty flag, vector already stored.
struct CleanCandidate:Identifiable, Equatable {
    let id:Int; let meeting:String; let meetingTitle:String; let start:Double; let seconds:Double; let source:String; let text:String
    init(_ d:[String:Any]) {
        id=d["id"] as? Int ?? 0; meeting=d["meeting"] as? String ?? ""; meetingTitle=MeetingLabel.title(d["meeting_title"])
        start=d["start"] as? Double ?? 0; seconds=d["seconds"] as? Double ?? 0; source=d["source"] as? String ?? ""; text=d["text"] as? String ?? ""
    }
}

/// Q8: "Temiz örnek ekle…" — the person's own longest clean turns, so a thin profile can be thickened
/// without hunting through transcripts. Listening first is the point; the button below each row enrolls it.
struct CleanSamplePicker:View {
    @ObservedObject var model:Model
    let name:String
    @Binding var open:Bool
    @State private var candidates:[CleanCandidate]?=nil
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            Text("Bu kişinin adıyla kayıtlı, en az 6 saniyelik, belirsizlik işareti taşımayan en uzun bölümler. Dinleyip emin olun; seçtiğiniz bölüm ses profiline eklenir.").font(.caption).foregroundStyle(.secondary)
            if let list=candidates {
                if list.isEmpty { Text("Uygun bölüm yok · bu kişinin uzun ve temiz bir bölümü henüz kaydedilmemiş ya da hepsi zaten örnek olmuş.").font(.caption).foregroundStyle(.secondary) }
                ForEach(list) { c in
                    HStack(spacing:8) {
                        VStack(alignment:.leading,spacing:1) {
                            Text("\(Int(c.seconds)) sn · \(c.meetingTitle)").font(.caption.weight(.medium))
                            Text(c.text).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                        }
                        Spacer(minLength:8)
                        if !model.recording { Button { model.playCandidate(c) } label: { PlayGlyph(playback:model.playback,key:"cand:\(c.id):\(c.meeting):\(c.start)") }.buttonStyle(.plain).help("Bu bölümü dinle · durdurmak için yine tıklayın") }
                        Button("Bu bölümü örnek yap") { Task { await model.enrollCandidate(c,name:name); candidates=await model.loadCleanCandidates(name) } }.controlSize(.small).disabled(model.busy)
                    }
                }
            } else { Text("Yükleniyor…").font(.caption).foregroundStyle(.secondary) }
        }.padding(.horizontal,18).padding(.top,12).padding(.bottom,18)
        .sheetChrome(title:SheetChrome.cleanSample(name:name)) { open=false }
        .frame(width:480).task { candidates=await model.loadCleanCandidates(name) }
        .accessibilityElement(children:.contain).accessibilityIdentifier("cleanSamplePicker")
    }
}

/// Q8: one person as a compact card — how the profile is built, how well it holds together, when the voice was
/// last heard — with the three things anyone ever wants to do to it: rename, drop the weak sample, add a clean one.
struct ProfileMaintenanceRow:View {
    @ObservedObject var model:Model
    let profile:Profile
    @State private var samples:[VoiceSample]=[]
    @State private var expanded=false
    @State private var newName=""
    @State private var picking=false
    private var health:ProfileHealth? {
        (model.maintenance?["profiles"] as? [[String:Any]] ?? []).map(ProfileHealth.init).first { NameFold.same($0.name,profile.name) && $0.model==profile.model }
    }
    var body:some View {
        DisclosureGroup(isExpanded:$expanded) {
            VStack(alignment:.leading,spacing:6) {
                HStack(spacing:8) {
                    Button("Temiz örnek ekle…") { picking=true }.controlSize(.small).accessibilityIdentifier("addCleanSample-\(profile.name)").help("Bu kişinin en uzun temiz bölümlerinden birini profile ekleyin; ikinci bir iyi örnek isabeti belirgin artırır")
                    if let h=health, h.weak, let weakest=h.weakestSample {
                        Button("Zayıf örneği sil",role:.destructive) { Task { await model.deleteWeakSample(weakest); samples=await model.loadSamples(profile.name) } }.controlSize(.small).help("Başka bir ses ya da bozuk kayıt olabilir; silmek profili keskinleştirir")
                    }
                    Spacer()
                }
                ForEach(samples) { s in
                    HStack {
                        Text("\(s.origin) · \(s.where_) · \(String(format:"%.0f",s.seconds)) sn").font(.caption).help(s.isTeam ? "Bu ses vektörü ekip klasöründen geldi; ses kaydı ve toplantı bilgisi paylaşılmaz" : (s.origin=="otomatik" ? "Bu örneği uygulama kendiliğinden kaydetti" : "Bu örneği siz adlandırırken kaydettiniz"))
                        Spacer()
                        Button("Örneği sil",role:.destructive) { Task { await model.deleteSample(s.id); samples=await model.loadSamples(profile.name); await model.loadMaintenance() } }.controlSize(.small)
                    }
                }
                if samples.isEmpty { Text("Örnek yok").font(.caption).foregroundStyle(.secondary) }
                HStack {
                    TextField("Yeni isim (var olan bir isim yazarsanız birleştirilir)",text:$newName).textFieldStyle(.roundedBorder)
                    Button("Yeniden adlandır") { Task { await model.renameProfile(profile.name,to:newName); newName=""; await model.loadMaintenance() } }.disabled(newName.trimmingCharacters(in:.whitespaces).isEmpty)
                }
                Text("Yanlış kişiden gelen örneği silmek sonraki tanımaları düzeltir; profil silinmez. Aynı kişiyi iki isimle kaydettiyseniz yeniden adlandırarak birleştirin.").font(.caption2).foregroundStyle(.secondary)
            }.padding(.leading,8)
        } label: {
            HStack(alignment:.firstTextBaseline,spacing:8) {
                VStack(alignment:.leading,spacing:2) {
                    HStack(spacing:5) {
                        Text(profile.name)
                        if health?.weak==true { Image(systemName:"exclamationmark.triangle.fill").font(.caption2).foregroundStyle(.orange).help("Bu profilde diğerlerine uymayan bir örnek var") }
                    }
                    Text(health?.line ?? "\(profile.samples) örnek").font(.caption2).foregroundStyle(.secondary).help(health?.fitHelp ?? "")
                }
                Spacer()
                Button("Profili sil",role:.destructive) { Task { await model.deleteProfile(profile.name); await model.loadMaintenance() } }.controlSize(.small).accessibilityIdentifier("deleteProfile-\(profile.name)")
            }.accessibilityIdentifier("profileCard-\(profile.name)")
        }
        .onChange(of:expanded) { open in if open { Task { samples=await model.loadSamples(profile.name) } } }
        .sheet(isPresented:$picking) { CleanSamplePicker(model:model,name:profile.name,open:$picking) }
    }
}

/// macOS notification when a Zoom meeting window appears and nothing is recording (opt-in).
enum ZoomNotifier {
    static let category="meetingos.zoom"
    static let startAction="meetingos.zoom.start"
    static var lastNotified:Date?
    static func register() {
        let start=UNNotificationAction(identifier:startAction,title:"Kaydı başlat",options:[.foreground])
        UNUserNotificationCenter.current().setNotificationCategories([UNNotificationCategory(identifier:category,actions:[start],intentIdentifiers:[],options:[])])
        UNUserNotificationCenter.current().requestAuthorization(options:[.alert,.sound]) { _,_ in }
    }
    static func notifyIfNeeded() {
        if let last=lastNotified, Date().timeIntervalSince(last) < 20*60 { return }   // one reminder per meeting, not one per poll
        lastNotified=Date()
        let content=UNMutableNotificationContent()
        content.title="Zoom toplantısı açık"; content.body="Meeting OS kaydı başlatmak için tıklayın ya da ⌃⌥R."; content.categoryIdentifier=category
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier:"zoom-"+UUID().uuidString,content:content,trigger:nil))
    }
    static func reset() { lastNotified=nil }
}
