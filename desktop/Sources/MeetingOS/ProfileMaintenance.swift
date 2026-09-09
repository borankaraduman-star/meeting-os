import SwiftUI
import UserNotifications

struct VoiceSample:Identifiable, Equatable {
    let id:Int; let seconds:Double; let kind:String; let meetingTitle:String; let model:String
    init(_ d:[String:Any]) { id=d["id"] as? Int ?? 0; seconds=d["seconds"] as? Double ?? 0; kind=d["kind"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? "bilinmeyen toplantı"; model=d["model"] as? String ?? "" }
}

struct IdentityCandidate:Identifiable, Equatable {
    let name:String; let score:Double; let centroid:Double; let bestSample:Double; let samples:Int
    var id:String { name }
    init(_ d:[String:Any]) { name=d["name"] as? String ?? ""; score=d["score"] as? Double ?? 0; centroid=d["centroid"] as? Double ?? 0; bestSample=d["best_sample"] as? Double ?? 0; samples=d["samples"] as? Int ?? 0 }
}

/// "Why did it think this was Ayşe?" — scores against every saved person, with the thresholds that decide.
struct IdentityExplanation:Equatable {
    let candidates:[IdentityCandidate]; let threshold:Double; let margin:Double; let suggest:Double; let seconds:Double; let reason:String
    static func parse(_ d:[String:Any])->IdentityExplanation {
        IdentityExplanation(candidates:(d["candidates"] as? [[String:Any]] ?? []).map(IdentityCandidate.init),threshold:d["threshold"] as? Double ?? 0.87,margin:d["margin"] as? Double ?? 0.05,suggest:d["suggest"] as? Double ?? 0.83,seconds:d["seconds"] as? Double ?? 0,reason:d["reason"] as? String ?? "")
    }
    func verdict(for c:IdentityCandidate,rank:Int)->String {
        let gap=rank==0 && candidates.count>1 ? c.score-candidates[1].score : 1.0
        if rank>0 { return "" }
        if c.score>=threshold && gap>=margin { return "isim verildi" }
        if c.score>=suggest && gap>=margin { return "öneri (soru işaretli)" }
        if c.score>=threshold && gap<margin { return "ikinci adaya çok yakın, isim verilmedi" }
        return "eşik altı, isim verilmedi"
    }
}

/// Per-person sample list with delete and rename/merge, shown inside the settings sheet.
struct ProfileMaintenanceRow:View {
    @ObservedObject var model:Model
    let profile:Profile
    @State private var samples:[VoiceSample]=[]
    @State private var expanded=false
    @State private var newName=""
    var body:some View {
        DisclosureGroup(isExpanded:$expanded) {
            VStack(alignment:.leading,spacing:6) {
                ForEach(samples) { s in
                    HStack {
                        Text("\(s.kind) · \(s.meetingTitle) · \(String(format:"%.0f",s.seconds)) sn").font(.caption)
                        Spacer()
                        Button("Örneği sil",role:.destructive) { Task { await model.deleteSample(s.id); samples=await model.loadSamples(profile.name) } }.controlSize(.small)
                    }
                }
                if samples.isEmpty { Text("Örnek yok").font(.caption).foregroundStyle(.secondary) }
                HStack {
                    TextField("Yeni isim (var olan bir isim yazarsanız birleştirilir)",text:$newName).textFieldStyle(.roundedBorder)
                    Button("Yeniden adlandır") { Task { await model.renameProfile(profile.name,to:newName); newName="" } }.disabled(newName.trimmingCharacters(in:.whitespaces).isEmpty)
                }
                Text("Yanlış kişiden gelen örneği silmek sonraki tanımaları düzeltir; profil silinmez. Aynı kişiyi iki isimle kaydettiyseniz yeniden adlandırarak birleştirin.").font(.caption2).foregroundStyle(.secondary)
            }.padding(.leading,8)
        } label: {
            HStack { Text(profile.name); Text("\(profile.samples) örnek").font(.caption).foregroundStyle(.secondary); Spacer(); Button("Profili sil",role:.destructive) { Task { await model.deleteProfile(profile.name) } }.controlSize(.small).accessibilityIdentifier("deleteProfile-\(profile.name)") }
        }
        .onChange(of:expanded) { open in if open { Task { samples=await model.loadSamples(profile.name) } } }
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
        content.title="Zoom toplantısı açık"; content.body="Meeting OS kaydı başlatmak için tıkla ya da ⌃⌥R."; content.categoryIdentifier=category
        UNUserNotificationCenter.current().add(UNNotificationRequest(identifier:"zoom-"+UUID().uuidString,content:content,trigger:nil))
    }
    static func reset() { lastNotified=nil }
}
