import Foundation

/// One comparison key for a person's name, matching `store.fold_name` / `memory.owner_key` on the Python side.
/// The two sides must agree: the bridge decides which owner a task belongs to, and "Bana ait" in the app has to
/// reach the same verdict for "Ayşe", "ayse" and "AYSE". Turkish is the whole difference — `lowercased()` alone
/// keeps "İlker" and "ilker" apart, and diacritics keep "Ayşe" and "Ayse" apart.
/// Folding is for comparison only: what is stored and shown is always exactly what the user typed.
enum NameFold {
    private static let turkish=Locale(identifier:"tr_TR")
    /// 'İ' → i and 'I' → ı first, exactly as fold_name does; then diacritics go, then the two i's become one.
    static func key(_ value:String?)->String {
        let seeded=(value ?? "").replacingOccurrences(of:"İ",with:"i").replacingOccurrences(of:"I",with:"ı")
        let folded=seeded.folding(options:[.diacriticInsensitive,.caseInsensitive],locale:turkish)
        return folded.replacingOccurrences(of:"ı",with:"i").trimmingCharacters(in:.whitespacesAndNewlines)
    }
    /// Are these two names the same person? Empty names never match anybody, including each other.
    static func same(_ a:String?,_ b:String?)->Bool {
        let left=key(a); return !left.isEmpty && left==key(b)
    }
    /// De-duplicate a name list by folded key, keeping the first spelling the user saw.
    static func unique(_ names:[String])->[String] {
        var seen=Set<String>()
        return names.filter { let k=key($0); return !k.isEmpty && seen.insert(k).inserted }
    }
}
