import Foundation

/// Ayarlar is three sections, not five: who you are (Genel), who speaks and how words are spelled
/// (Sesler ve sözlük), and everything the machine does on its own (Sistem). The old five-way choice is
/// still on disk in @AppStorage, so a stored value has to be folded into the new set or the sheet opens blank.
enum SettingsSections {
    static let all=["genel","sesler","sistem"]
    /// Height per section as before: the sheet is as tall as its own content, clamped to the screen.
    static let heights=["genel":540,"sesler":940,"sistem":760]
    static func normalize(_ raw:String)->String {
        if all.contains(raw) { return raw }
        switch raw {
        case "sozluk": return "sesler"
        case "depolama","guncelleme","durum": return "sistem"
        default: return "genel"
        }
    }
    static func height(_ raw:String)->Int { heights[normalize(raw)] ?? 700 }
    /// The pinned title bar (title + ✕) lives outside the scroll area, so the sheet window is that much taller
    /// than the content heights above — otherwise the chrome would eat a strip of every section.
    static let chromeHeight:Double=52
    /// What the sheet window is actually sized to. Never taller than what the screen can show, so the ✕ in the
    /// header is on screen at every section and on every Mac; never so short that a section is a slit.
    static func sheetHeight(_ raw:String,screen:Double)->Double {
        max(360,min(Double(height(raw))+chromeHeight,max(360,screen-80)))
    }
}
