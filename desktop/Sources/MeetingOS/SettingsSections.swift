import Foundation

/// Ayarlar is three sections, not five: who you are (Genel), who speaks and how words are spelled
/// (Sesler ve sözlük), and everything the machine does on its own (Sistem). The old five-way choice is
/// still on disk in @AppStorage, so a stored value has to be folded into the new set or the sheet opens blank.
enum SettingsSections {
    static let all=["genel","sesler","sistem"]
    /// Height per section as before: the sheet is as tall as its own content, clamped to the screen.
    static let heights=["genel":540,"sesler":940,"sistem":980]
    static func normalize(_ raw:String)->String {
        if all.contains(raw) { return raw }
        switch raw {
        case "sozluk": return "sesler"
        case "depolama","guncelleme","durum": return "sistem"
        default: return "genel"
        }
    }
    static func height(_ raw:String)->Int { heights[normalize(raw)] ?? 700 }
}
