import SwiftUI

/// Weekly maintenance in one place: profiles that need a look, learned text rules, disk, and meetings the cloud refused.
/// Read-only summary with one action per row; nothing here runs on its own.
struct MaintenanceView:View {
    @ObservedObject var m:Model
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            HStack { Text("Haftalık bakım").font(.headline); Spacer(); Button("Yenile") { Task { await m.loadMaintenance() } }.controlSize(.small).accessibilityIdentifier("refreshMaintenance") }
            if let mt=m.maintenance {
                let profiles=mt["profiles"] as? [[String:Any]] ?? []
                let weak=profiles.filter { $0["weak"] as? Bool == true }
                let rules=mt["rules"] as? [[String:Any]] ?? []
                let blocked=mt["blocked"] as? [[String:Any]] ?? []
                let storage=(mt["storage"] as? [String:Any]).map(StorageReport.parse)
                Label("\(profiles.count) ses profili · \(profiles.reduce(0) { $0+($1["samples"] as? Int ?? 0) }) örnek"+(weak.isEmpty ? " · hepsi tutarlı" : " · \(weak.count) kişide zayıf örnek"),systemImage:"person.2").font(.callout)
                ForEach(weak,id:\.description) { p in
                    HStack(spacing:8) {
                        Text("\(p["name"] as? String ?? "") · en zayıf örnek benzerliği \(String(format:"%.2f",p["weakest_fit"] as? Double ?? 0))").font(.caption)
                        Spacer()
                        if let sid=p["weakest_sample"] as? Int { Button("Zayıf örneği sil") { Task { await m.deleteWeakSample(sid) } }.controlSize(.mini).help("Başka bir ses ya da bozuk kayıt olabilir; silmek profili keskinleştirir") }
                    }.padding(.leading,24)
                }
                Label(rules.isEmpty ? "Öğrenilmiş metin kuralı yok · aynı düzeltmeyi iki toplantıda yapınca kural olur" : "\(rules.count) öğrenilmiş metin kuralı · yeni transkriptlere kendiliğinden uygulanır",systemImage:"text.badge.checkmark").font(.callout)
                ForEach(rules.prefix(8),id:\.description) { r in
                    HStack(spacing:8) {
                        Text("“\(r["original"] as? String ?? "”")” → “\(r["replacement"] as? String ?? "")” · \(r["meetings"] as? Int ?? 0) toplantı").font(.caption)
                        Spacer()
                        Button("Kapat") { Task { await m.rejectRule(r["original"] as? String ?? "") } }.controlSize(.mini).help("Bu kural bir daha uygulanmaz")
                    }.padding(.leading,24)
                }
                if let s=storage { Label("Disk · \(StorageReport.format(bytes:s.total)) (ses \(StorageReport.format(bytes:s.recordings))) · Ayarlar → Sistem",systemImage:"internaldrive").font(.callout) }
                if !blocked.isEmpty { Label("\(blocked.count) toplantı bulutta bekliyor · anahtar ya da kredi sorunu · Ayarlar → Sistem",systemImage:"exclamationmark.icloud").font(.callout).foregroundStyle(.orange) }
            } else { Text("Yükleniyor…").font(.caption).foregroundStyle(.secondary) }
        }.task { if m.maintenance==nil { await m.loadMaintenance() } }
    }
}
