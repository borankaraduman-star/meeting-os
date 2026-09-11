import Foundation

/// "Konuşanı adlandır": what the name is supposed to touch.
///
/// The sheet used to ask this three times — one button per answer, each with its own paragraph — so the user
/// had to work out the difference between "öğren", "yalnız bu toplantıda" and "yalnız bu bölüm" *while* doing
/// the correction (Codex P2 #12). It is one question with three answers, so it is one control: pick the scope,
/// read the single line under it, press **Adlandır**. The dispatch below is the whole difference between the
/// old buttons and the new one, and it is pure so the mapping can be pinned down without a window server.
enum NamingScope:String,CaseIterable,Identifiable {
    /// Every piece of this voice, and the voice profile learns from it. The everyday answer, so it is the default.
    case speaker
    /// One piece of the paragraph went to the wrong person; the speaker itself is right.
    case segment
    /// The name belongs to this meeting only — nothing is learned, so next week's meeting starts clean.
    case meeting

    var id:String { rawValue }

    /// The segmented control's labels. Short enough that three of them fit across the sheet without truncating.
    var label:String {
        switch self {
        case .speaker: return "Bu konuşmacının tamamı"
        case .segment: return "Yalnız bu bölüm"
        case .meeting: return "Yalnız bu toplantıda"
        }
    }

    /// The one line under the picker: what the selected answer will actually do. Only the selected one is shown,
    /// so the sheet never carries three competing explanations at once.
    var explanation:String {
        switch self {
        case .speaker: return "Sesi öğrenir: bu konuşmacının bütün bölümleri bu adı alır ve kişi sonraki toplantılarda kendiliğinden tanınır. (varsayılan)"
        case .segment: return "Yalnız bu cümle yanlış kişiye gitti: sadece seçili bölüm değişir, konuşmacının geri kalanı ve profili olduğu gibi kalır."
        case .meeting: return "Öğrenme yok: isim yalnız bu toplantıya yazılır, ses profili oluşmaz."
        }
    }

    /// Which answers this row can even offer. Only a provider-diarized cluster has "the rest of the speaker" to
    /// talk about; a plain segment can only be labelled where it is, so the picker is not drawn at all.
    static func options(cluster:Bool)->[NamingScope] { cluster ? allCases : [.segment] }

    /// The selection the sheet opens with.
    static func initial(cluster:Bool)->NamingScope { cluster ? .speaker : .segment }

    /// The line a plain segment gets instead of the picker: nothing to choose, so it just says what will happen.
    static func plainExplanation(textOnly:Bool)->String {
        textOnly ? "Bu toplantı yalnızca metin içerir; isim yalnız bu bölüme yazılır."
                 : "İsim bu bölüme yazılır; bölüm en az 6 sn temiz tek kişilik konuşmaysa kişinin ses profili de bundan öğrenir. Kısa ya da karışık bölümde yalnız isim kaydedilir."
    }

    /// The piece picker only earns its place for a one-piece correction inside a paragraph that has pieces.
    static func showsPiecePicker(scope:NamingScope,cluster:Bool,pieces:Int)->Bool { cluster && scope == .segment && pieces>1 }

    /// One press of "Adlandır", resolved. A row with no cluster behind it ignores the scope entirely: there is
    /// only one thing a name can mean there, and `clean` (the Gelişmiş toggle) decides whether the voice learns.
    func action(cluster:Bool,clean:Bool)->NamingAction {
        guard cluster else { return .label(enroll:clean) }
        switch self {
        case .speaker: return .speakerWithVoice
        case .meeting: return .speakerThisMeeting
        case .segment: return .segmentOnly
        }
    }
}

/// The model call the primary button makes. One case per existing function, so the sheet gained a control and
/// the model gained nothing: `saveSpeaker(enroll:)`, `saveSegmentOnly(_:)`, `saveLabel(enroll:)`.
enum NamingAction:Equatable {
    case speakerWithVoice       // saveSpeaker(enroll:true)
    case speakerThisMeeting     // saveSpeaker(enroll:false)
    case segmentOnly            // saveSegmentOnly(target)
    case label(enroll:Bool)     // saveLabel(enroll:)
}
