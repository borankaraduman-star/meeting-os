import SwiftUI

/// Every sheet and popover closes the same way, so nobody has to hunt for the exit: a title on the left and one
/// round ✕ on the right, Esc, and ⌘W. Before this, three sheets closed with a footer button, one with a footer
/// button placed under a long scroll (Ayarlar — invisible unless you scrolled to the bottom), and the ⌘W a Mac
/// user reaches for closed the whole window instead of the sheet.
enum SheetChrome {
    static let closeIdentifier="closeSheet"
    static let closeLabel="Kapat"
    static let closeHelp="Kapat (Esc)"
    /// ✕ diameter. Big enough to hit without aiming, small enough not to compete with the title.
    static let glyph:CGFloat=19
    /// The same mark, one size down, for a popover: the panel is 320 pt wide and the title is a headline, not a title2.
    static let compactGlyph:CGFloat=15

    /// The fixed title of every sheet that wears this chrome, in the order a user meets them. Pure data so a test
    /// can assert the set is complete and that no title is blank or padded — the chrome renders it verbatim.
    /// The clean-sample picker is the one title built from a person's name; `cleanSample(name:)` produces it.
    static let titles=[
        "Ayarlar",
        "Paylaşım önizlemesi",
        "Konuşanı adlandır",
        "OpenRouter · Ses dosyasını yazıya çevir",
        "Görevi düzenle",
        "Taslağı düzenle",
        "Kelimeyi düzelt",
    ]
    static func cleanSample(name:String)->String {
        let n=name.trimmingCharacters(in:.whitespacesAndNewlines)
        return n.isEmpty ? "Temiz örnek" : "“\(n)” için temiz örnek"
    }
    /// A title is usable only if it is non-empty once trimmed; the header would otherwise show a bare ✕ floating
    /// over nothing and the sheet would read as a glitch.
    static func usable(_ raw:String)->Bool { !raw.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty }
}

/// The ✕ itself. Owns Esc for the sheet it sits in, so no other button in that sheet should claim `.cancelAction`.
/// The zero-sized twin behind it is what makes ⌘W close the sheet rather than the app window: while a sheet is up,
/// a shortcut declared inside it wins over the window's Close menu item.
struct SheetCloseButton:View {
    let onClose:()->Void
    var compact=false
    var help:String=SheetChrome.closeHelp
    var body:some View {
        Button(action:onClose) {
            Image(systemName:"xmark.circle.fill")
                .symbolRenderingMode(.hierarchical)
                .font(.system(size:compact ? SheetChrome.compactGlyph : SheetChrome.glyph,weight:.regular))
                .foregroundStyle(.secondary)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.cancelAction)
        .help(help)
        .accessibilityLabel(SheetChrome.closeLabel)
        .accessibilityIdentifier(SheetChrome.closeIdentifier)
        .background(
            Button(SheetChrome.closeLabel,action:onClose)
                .keyboardShortcut("w",modifiers:.command)
                .opacity(0).frame(width:0,height:0).allowsHitTesting(false).accessibilityHidden(true)
        )
    }
}

/// Title bar pinned above the sheet's own content. Applied to the scrolling body, so the ✕ stays on screen no
/// matter how tall the sheet's content grows (Ayarlar → Sesler ve sözlük is nearly a metre of it).
struct SheetChromeModifier:ViewModifier {
    let title:String
    /// A hint rendered next to the title, e.g. the "⌘," that opens Ayarlar. Optional.
    let hint:String?
    let onClose:()->Void
    func body(content:Content)->some View {
        VStack(spacing:0) {
            HStack(spacing:10) {
                Text(title).font(.title2.bold()).lineLimit(1).truncationMode(.tail)
                if let hint,SheetChrome.usable(hint) { Text(hint).font(.caption.monospaced()).foregroundStyle(.secondary) }
                Spacer(minLength:12)
                SheetCloseButton(onClose:onClose)
            }
            .padding(.horizontal,20).padding(.top,15).padding(.bottom,12)
            Divider()
            content
        }
    }
}

/// The popover version: same mark, one size down, no divider — a popover has no room for a rule and no scroll to
/// pin anything against.
struct PopoverChromeModifier:ViewModifier {
    let title:String
    let onClose:()->Void
    func body(content:Content)->some View {
        VStack(alignment:.leading,spacing:10) {
            HStack(spacing:8) {
                Text(title).font(.headline).lineLimit(1)
                Spacer(minLength:8)
                SheetCloseButton(onClose:onClose,compact:true)
            }
            content
        }
    }
}

extension View {
    func sheetChrome(title:String,hint:String?=nil,onClose:@escaping ()->Void)->some View {
        modifier(SheetChromeModifier(title:title,hint:hint,onClose:onClose))
    }
    func popoverChrome(title:String,onClose:@escaping ()->Void)->some View {
        modifier(PopoverChromeModifier(title:title,onClose:onClose))
    }
}
