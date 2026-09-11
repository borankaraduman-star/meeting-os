import Foundation

/// What to say after "Adlandır" with the default scope (the whole voice, and the voice learns). The sample length is the one number that predicts whether this voice
/// will be recognised next week, so it belongs in the line rather than in a support answer three meetings later.
enum EnrollNotice {
    /// `seconds` and `profile_saved` come from store.enroll_speaker through the label_speaker bridge action.
    static func line(_ result:[String:Any])->String {
        let seconds=result["seconds"] as? Double ?? 0
        let length=seconds>0 ? " (\(Int(seconds.rounded())) sn)" : ""
        guard (result["profile_saved"] as? Bool)==true else {
            return "Konuşmacı adlandırıldı · Yeterli temiz ses olmadığı için profil kaydedilmedi"+length
        }
        if seconds>0 && seconds<6 {
            return "Konuşmacı adlandırıldı · Ses profili kaydedildi\(length) · kısa örnek; Kontrol’de temiz ses onayıyla güçlendirin"
        }
        return "Konuşmacı adlandırıldı · Ses profili kaydedildi\(length), sonraki toplantılarda otomatik tanınır"
    }
}
