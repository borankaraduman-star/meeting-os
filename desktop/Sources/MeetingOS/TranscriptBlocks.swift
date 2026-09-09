import Foundation

/// Reading view: consecutive turns of one speaker become a paragraph; one-or-two-word interjections
/// from someone else (“Hı hı”, “Tabii”) become asides of the paragraph they interrupt instead of
/// separate cards. Every original segment stays addressable for editing and playback.
struct TranscriptBlock:Identifiable, Equatable {
    var rows:[Row]          // the speaker's own segments, in order
    var asides:[Row]        // brief interjections by others inside this paragraph
    var id:Int { rows[0].id }
    var lead:Row { rows[0] }
    var label:String { lead.label }
    var text:String { rows.map(\.text).joined(separator:" ") }
    var start:Double { lead.start }
    var end:Double { rows.last?.end ?? lead.end }
}

enum Fillers {
    /// MAI-Transcribe keeps disfluencies (“eee”, “ııı”, “Bi-”) verbatim. Reading mode hides them; the stored
    /// transcript, search and evidence quotes keep the original words.
    static let pattern=try! NSRegularExpression(pattern:"(?<![\\p{L}\\p{N}])(?:[eEaAıIiİuUoOöÖüÜ]{2,}|[hH][ıiI]+(?:\\s?[hH][ıiI]+)?|[\\p{L}]{1,3}-)(?=[\\s.,;!?…]|$)[.,]?\\s*",options:[])
    static func clean(_ text:String)->String {
        let range=NSRange(text.startIndex..., in:text)
        var out=pattern.stringByReplacingMatches(in:text,options:[],range:range,withTemplate:"")
        out=out.replacingOccurrences(of:"  ",with:" ").trimmingCharacters(in:.whitespaces)
        if let first=out.first, first.isLowercase, text.first?.isUppercase==true { out=first.uppercased()+out.dropFirst() }
        return out.isEmpty ? text : out
    }
}

enum TranscriptBlocks {
    static let asideSeconds=1.5
    static func isBackchannel(_ row:Row)->Bool {
        row.text.split(separator:" ").count<=2 && row.end-row.start<asideSeconds && !row.flags.contains("untimed")
    }
    static func build(_ rows:[Row])->[TranscriptBlock] {
        var blocks:[TranscriptBlock]=[]
        var index=0
        while index<rows.count {
            let row=rows[index]
            if var current=blocks.last, current.label==row.label, row.source==current.lead.source {
                current.rows.append(row); blocks[blocks.count-1]=current; index+=1; continue
            }
            if !blocks.isEmpty, isBackchannel(row), index+1<rows.count, rows[index+1].label==blocks[blocks.count-1].label, rows[index+1].source==blocks[blocks.count-1].lead.source {
                blocks[blocks.count-1].asides.append(row); index+=1; continue
            }
            blocks.append(TranscriptBlock(rows:[row],asides:[])); index+=1
        }
        return blocks
    }
    static func asideCount(_ blocks:[TranscriptBlock])->Int { blocks.reduce(0) { $0+$1.asides.count } }
    /// Flags every cloud row carries are said once per meeting, not under every paragraph.
    static let meetingWideFlags:Set<String>=["cloud_transcript","cloud_diarization","confidence_unavailable","speaker_unverified","coarse_timing"]
    static func meetingNotice(_ rows:[Row])->String? {
        guard rows.contains(where:{ $0.flags.contains("cloud_transcript") }) else { return nil }
        var parts=["Bulut transkript · OpenRouter","güven ölçümü yok","konuşmacı adları doğrulanmadı"]
        if rows.contains(where:{ $0.flags.contains("cloud_diarization") }) { parts.append("konuşmacı ayrımı sağlayıcıdan") }
        if rows.contains(where:{ $0.flags.contains("coarse_timing") }) { parts.append("bazı zamanlar yaklaşık") }
        return parts.joined(separator:" · ")
    }
}
