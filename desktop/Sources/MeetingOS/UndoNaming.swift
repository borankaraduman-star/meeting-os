import Foundation

/// ⌘Z after a naming. "Tümünü onayla" names N voices at once, so one undo must take the whole batch back;
/// a single naming keeps its detailed line (which name, what it was before).
enum UndoNaming {
    static func message(_ results:[[String:Any]])->String {
        guard results.count==1, let r=results.first else { return "\(results.count) adlandırma geri alındı · öğrenilen örnekler silindi" }
        let name=r["name"] as? String ?? ""; let previous=r["previous"] as? String
        return "Geri alındı · “\(name)”"+(previous.map { " yeniden “\($0)”" } ?? " isimsiz")+" · öğrenilen örnek silindi"
    }
}
