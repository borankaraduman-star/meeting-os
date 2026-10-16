import AVFoundation
import XCTest
@testable import CaptureAudio

final class PCMPeakTests: XCTestCase {
    func buffer(_ format: AVAudioCommonFormat, channels: AVAudioChannelCount, interleaved: Bool, frames: Int) -> AVAudioPCMBuffer {
        let f = AVAudioFormat(commonFormat: format, sampleRate: 48000, channels: channels, interleaved: interleaved)!
        let b = AVAudioPCMBuffer(pcmFormat: f, frameCapacity: AVAudioFrameCount(frames))!
        b.frameLength = AVAudioFrameCount(frames)
        return b
    }

    func testInterleavedStereoFloatScansEveryFrameOfBothChannelsThroughTheOnePointer() {
        let b = buffer(.pcmFormatFloat32, channels: 2, interleaved: true, frames: 480)
        XCTAssertTrue(b.format.isInterleaved); XCTAssertEqual(b.stride, 2)
        let p = b.floatChannelData![0]
        for i in 0..<960 { p[i] = 0.01 }
        p[959] = -0.75   // the right channel's last frame: only reachable as interleaved sample 2*480-1
        XCTAssertEqual(pcmPeak(b), 0.75, accuracy: 1e-6)
    }

    func testPlanarStereoFloatReadsEachChannelPointer() {
        let b = buffer(.pcmFormatFloat32, channels: 2, interleaved: false, frames: 480)
        XCTAssertFalse(b.format.isInterleaved)
        for c in 0..<2 { for i in 0..<480 { b.floatChannelData![c][i] = 0 } }
        b.floatChannelData![1][479] = 0.5
        XCTAssertEqual(pcmPeak(b), 0.5, accuracy: 1e-6)
    }

    func testInterleavedInt16AndSilenceAndEmptyBuffers() {
        let b = buffer(.pcmFormatInt16, channels: 2, interleaved: true, frames: 100)
        let p = b.int16ChannelData![0]
        for i in 0..<200 { p[i] = 0 }
        XCTAssertEqual(pcmPeak(b), 0)   // a silent buffer is evidence too: peak 0, not "no data"
        p[199] = -16384
        XCTAssertEqual(pcmPeak(b), 0.5, accuracy: 1e-4)
        b.frameLength = 0
        XCTAssertEqual(pcmPeak(b), 0)
    }

    func testMonoIsTheSameEitherWay() {
        let b = buffer(.pcmFormatFloat32, channels: 1, interleaved: true, frames: 64)
        for i in 0..<64 { b.floatChannelData![0][i] = Float(i) / 128 }
        XCTAssertEqual(pcmPeak(b), 63.0 / 128, accuracy: 1e-6)
    }
}
