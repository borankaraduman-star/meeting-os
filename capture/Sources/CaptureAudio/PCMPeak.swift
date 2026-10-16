import AVFoundation

/// The largest absolute sample in a buffer, 0...1. ScreenCaptureKit hands over stereo that may be interleaved:
/// then `floatChannelData` has ONE valid pointer holding frames×channels samples, and reading `data[1]` as a
/// second channel walked past the buffer list and could crash the helper mid-meeting. Planar buffers have one
/// pointer per channel, `frames` samples each. Both layouts are scanned exactly over their own samples.
public func pcmPeak(_ buffer: AVAudioPCMBuffer) -> Float {
    let frames = Int(buffer.frameLength), channels = Int(buffer.format.channelCount)
    guard frames > 0, channels > 0 else { return 0 }
    let interleaved = buffer.format.isInterleaved && channels > 1
    let pointers = interleaved ? 1 : channels, count = interleaved ? frames * channels : frames
    var peak: Float = 0
    if let data = buffer.floatChannelData {
        for c in 0..<pointers { let p = data[c]; for i in 0..<count { let v = abs(p[i]); if v > peak { peak = v } } }
    } else if let data = buffer.int16ChannelData {
        for c in 0..<pointers { let p = data[c]; for i in 0..<count { peak = max(peak, abs(Float(p[i]))/32768) } }
    } else if let data = buffer.int32ChannelData {
        for c in 0..<pointers { let p = data[c]; for i in 0..<count { peak = max(peak, abs(Float(p[i]))/2147483648) } }
    }
    return min(peak, 1)
}
