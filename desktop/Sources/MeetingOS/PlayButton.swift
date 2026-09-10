import SwiftUI
import AVFoundation

/// Which audio span is playing right now. Lives outside `Model` so a play/stop toggle repaints only the play
/// glyphs that observe it, never the whole transcript.
final class PlaybackState:ObservableObject { @Published var key:String? }

/// The glyph (and optional text) of a play button: turns into a stop symbol while its own span is playing.
struct PlayGlyph:View {
    @ObservedObject var playback:PlaybackState
    let key:String
    var idle:String="play.circle"
    var text:String?=nil
    var font:Font?=nil
    var playing:Bool { playback.key==key }
    var body:some View {
        let image=Image(systemName:playing ? "stop.circle.fill" : idle).foregroundStyle(playing ? Color.red : MeetingStyle.accent)
        if let text { Label { Text(playing ? "Durdur" : text) } icon: { image } } else if let font { image.font(font) } else { image }
    }
}

/// AVAudioPlayer delegate: reports the natural end of a clip so the play glyph does not stay ■ for the rest of the span.
final class PlaybackEnd:NSObject,AVAudioPlayerDelegate {
    let ended:(AVAudioPlayer)->Void
    init(_ ended:@escaping (AVAudioPlayer)->Void) { self.ended=ended }
    func audioPlayerDidFinishPlaying(_ player:AVAudioPlayer,successfully flag:Bool) { ended(player) }
    func audioPlayerDecodeErrorDidOccur(_ player:AVAudioPlayer,error:Error?) { ended(player) }
}
