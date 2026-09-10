import SwiftUI
import AppKit

/// "Kelimeyi tıkla, düzelt": the transcript renders every word as a link to a private `meetingos://word`
/// URL, and the click opens a popover on that paragraph. No hover state, no per-word view, no timer —
/// one AttributedString per paragraph and one @Published that only moves when the user clicks.
struct WordRef:Equatable {
    let segment:Int      // segment (Row) id — the piece `edit_text` writes
    let index:Int        // index of the whitespace token inside that segment's *raw* text
    let word:String      // the token without its surrounding punctuation: what the user sees quoted
}

/// The clicked word plus the paragraph (or row) that anchors its popover.
struct WordFix:Identifiable, Equatable {
    let segmentID:Int
    let index:Int
    let original:String
    let blockID:Int      // reading mode: the paragraph's id; bölümler view: the row's own id
    var id:String { "\(blockID):\(segmentID):\(index)" }
}

enum WordClick {
    static let scheme="meetingos"
    static let host="word"
    /// Punctuation and symbols are stripped for the *value* of a token, never from what is drawn.
    static let strip=CharacterSet.punctuationCharacters.union(.symbols)

    // MARK: - URL
    /// Percent-encodes on the strict side (alphanumerics only) so Turkish letters and apostrophes survive
    /// the round trip through URLComponents unchanged.
    static func url(_ ref:WordRef)->URL? {
        let w=ref.word.addingPercentEncoding(withAllowedCharacters:.alphanumerics) ?? ""
        return URL(string:"\(scheme)://\(host)?seg=\(ref.segment)&i=\(ref.index)&w=\(w)")
    }
    static func parse(_ url:URL)->WordRef? {
        guard url.scheme==scheme, url.host==host,
              let items=URLComponents(url:url,resolvingAgainstBaseURL:false)?.queryItems else { return nil }
        var q:[String:String]=[:]
        for i in items { q[i.name]=i.value ?? "" }
        guard let seg=Int(q["seg"] ?? ""), let idx=Int(q["i"] ?? ""), idx>=0, let w=q["w"], !w.isEmpty else { return nil }
        return WordRef(segment:seg,index:idx,word:w)
    }

    // MARK: - Tokens
    struct Token:Equatable {
        let index:Int
        let raw:String                 // the token exactly as written, punctuation included
        let core:String                // the word inside it
        let range:Range<String.Index>  // where it sits in the segment text
    }
    private static func strippable(_ c:Character)->Bool { c.unicodeScalars.allSatisfy { strip.contains($0) } }
    static func core(_ raw:String)->String {
        var lo=raw.startIndex, hi=raw.endIndex
        while lo<hi, strippable(raw[lo]) { lo=raw.index(after:lo) }
        while hi>lo, strippable(raw[raw.index(before:hi)]) { hi=raw.index(before:hi) }
        return String(raw[lo..<hi])
    }
    /// Whitespace tokens with their positions: the index is what a `meetingos://word` link carries, so it must
    /// always count the *raw* text — hiding fillers changes what is drawn, never what an index means.
    static func tokens(_ text:String)->[Token] {
        var out:[Token]=[]; var i=text.startIndex; var n=0
        while i<text.endIndex {
            if text[i].isWhitespace { i=text.index(after:i); continue }
            var j=i
            while j<text.endIndex, !text[j].isWhitespace { j=text.index(after:j) }
            let raw=String(text[i..<j])
            out.append(Token(index:n,raw:raw,core:core(raw),range:i..<j))
            n+=1; i=j
        }
        return out
    }
    /// The same rule `Fillers.clean` applies, asked one token at a time so the raw indices stay intact.
    static func isFiller(_ raw:String)->Bool {
        guard !raw.isEmpty else { return false }
        let ns=raw as NSString
        guard let m=Fillers.pattern.firstMatch(in:raw,options:[],range:NSRange(location:0,length:ns.length)) else { return false }
        return m.range.location==0 && m.range.length==ns.length
    }

    // MARK: - Replace one occurrence
    /// "Yalnız burada": swap the word at `index` and leave everything else — the punctuation glued to it,
    /// the spacing, the rest of the sentence — exactly as it was. Out-of-range asks for nothing.
    static func replacing(_ text:String,index:Int,with replacement:String)->String {
        let to=replacement.trimmingCharacters(in:.whitespacesAndNewlines)
        guard !to.isEmpty, index>=0 else { return text }
        let toks=tokens(text)
        guard index<toks.count else { return text }
        let t=toks[index]
        guard !t.core.isEmpty else { return text }
        var lo=t.raw.startIndex, hi=t.raw.endIndex
        while lo<hi, strippable(t.raw[lo]) { lo=t.raw.index(after:lo) }
        while hi>lo, strippable(t.raw[t.raw.index(before:hi)]) { hi=t.raw.index(before:hi) }
        var out=text
        out.replaceSubrange(t.range,with:String(t.raw[t.raw.startIndex..<lo])+to+String(t.raw[hi...]))
        return out
    }

    // MARK: - Clickable paragraph
    /// One AttributedString per paragraph: every word carries its own link and the body colour, so the text
    /// reads exactly as before — no blue, no underline, no hover chrome — until a word is clicked.
    static func attributedText(_ rows:[Row],hideFillers:Bool)->AttributedString {
        var out=AttributedString()
        var emitted=false
        for row in rows {
            if emitted { out.append(AttributedString(" ")) }   // the same join the plain paragraph used
            append(row:row,hideFillers:hideFillers,into:&out,emitted:&emitted)
        }
        while let f=out.characters.first, f.isWhitespace { out.removeSubrange(out.startIndex..<out.index(afterCharacter:out.startIndex)) }
        out.foregroundColor = .primary   // links inherit the tint otherwise; the transcript must not turn blue
        return out
    }
    private static func append(row:Row,hideFillers:Bool,into out:inout AttributedString,emitted:inout Bool) {
        let text=row.text
        let all=tokens(text)
        let dropped=hideFillers ? all.filter { isFiller($0.raw) }.count : 0
        // A piece that is nothing but disfluency stays readable, exactly as Fillers.clean leaves it alone.
        let hiding=hideFillers && dropped>0 && dropped<all.count
        var cursor=text.startIndex
        var first=true
        for t in all {
            if hiding, isFiller(t.raw) { cursor=t.range.upperBound; continue }   // the gap before it goes with it
            // The gap before a kept token is drawn verbatim, so newlines in imported text survive.
            out.append(AttributedString(String(text[cursor..<t.range.lowerBound])))
            var raw=t.raw
            if hiding, !emitted, first, t.index != 0, let f=raw.first, f.isLowercase, text.first?.isUppercase==true {
                raw=f.uppercased()+raw.dropFirst()   // Fillers.clean re-capitalises a sentence it beheaded
            }
            var piece=AttributedString(raw)
            let shown=core(raw)   // what the reader sees (re-capitalised when a filler was beheaded), so the popover quotes the same word
            if !shown.isEmpty, let u=url(WordRef(segment:row.id,index:t.index,word:shown)) { piece.link=u }
            out.append(piece)
            emitted=true; first=false
            cursor=t.range.upperBound
        }
        out.append(AttributedString(String(text[cursor...])))
    }
}

/// Paragraphs are rebuilt on every poll; their attributed text is not. Keyed by paragraph id, the filler
/// switch and a hash of the text, so an edit invalidates it and a 1200-row meeting still costs one build
/// per visible paragraph.
@MainActor enum WordTextCache {
    private struct Key:Hashable { let block:Int; let hideFillers:Bool; let hash:Int }
    private static var store:[Key:AttributedString]=[:]
    private static var order:[Key]=[]
    private static let limit=400
    static func text(block:Int,rows:[Row],hideFillers:Bool)->AttributedString {
        var h=Hasher()
        for r in rows { h.combine(r.id); h.combine(r.text) }
        let key=Key(block:block,hideFillers:hideFillers,hash:h.finalize())
        if let hit=store[key] { return hit }
        let built=WordClick.attributedText(rows,hideFillers:hideFillers)
        store[key]=built; order.append(key)
        if order.count>limit { store.removeValue(forKey:order.removeFirst()) }
        return built
    }
}

/// The popover a clicked word opens: the wrong spelling, the right one, and the only two answers that
/// matter — this sentence, or every sentence plus the dictionary.
struct WordFixPopover:View {
    @ObservedObject var model:Model
    let fix:WordFix
    @State private var replacement=""
    @FocusState private var focused:Bool
    private var trimmed:String { replacement.trimmingCharacters(in:.whitespacesAndNewlines) }
    private var ready:Bool { !model.busy && !trimmed.isEmpty && trimmed != fix.original }
    var body:some View {
        VStack(alignment:.leading,spacing:10) {
            Text("Kelimeyi düzelt").font(.headline)
            Text("“\(fix.original)”").font(.callout).foregroundStyle(.secondary).lineLimit(1)
            TextField("doğrusu",text:$replacement).textFieldStyle(.roundedBorder).focused($focused).accessibilityIdentifier("wordFixField")
            HStack(spacing:8) {
                Button("Vazgeç") { model.wordFix=nil }.keyboardShortcut(.cancelAction).accessibilityIdentifier("wordFixCancelButton")
                Spacer(minLength:8)
                Button("Düzelt ve öğret") { Task { await model.learnClickedWord(fix,replacement:trimmed) } }
                    .disabled(!ready).help("Bu toplantıdaki bütün geçişleri düzeltir ve kelimeyi öğrenir").accessibilityIdentifier("wordFixLearnButton")
                Button("Yalnız burada") { Task { await model.fixWordHere(fix,replacement:trimmed) } }
                    .buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction).disabled(!ready)
                    .help("Sadece bu cümledeki bu kelime değişir").accessibilityIdentifier("wordFixHereButton")
            }
            Text("Enter “Yalnız burada”yı çalıştırır; öğretmek her yerde ve sonraki toplantılarda geçerlidir.").font(.caption2).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
        }.padding(16).frame(width:320)
        .onAppear {
            replacement=fix.original
            focused=true
            // Prefilled *and* selected: typing replaces the wrong word instead of appending to it.
            DispatchQueue.main.asyncAfter(deadline:.now()+0.08) { NSApp?.sendAction(#selector(NSText.selectAll(_:)),to:nil,from:nil) }
        }
    }
}
