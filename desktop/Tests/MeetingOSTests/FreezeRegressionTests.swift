import XCTest
import SwiftUI
import AppKit
@testable import MeetingOS
final class FreezeRegressionTests:XCTestCase {
    @MainActor func testLongFailureAndLargeTranscriptRemainLayoutable() {
        _ = NSApplication.shared
        let model=Model()
        model.timer?.invalidate()
        model.meetings=[Meeting(["id":"fixture","title":"Yerleşim testi","status":"incomplete","metadata":["capture_dir":"/tmp/fixture"]])]
        model.selected="fixture"
        model.rows=(0..<300).map { Row(["id":$0,"start":Double($0*12),"end":Double($0*12+10),"text":"Türkçe toplantı örneği. Sprint planı ve sonraki adımlar konuşuluyor.","source":"mic","speaker":"S0"]) }
        model.error=String(repeating:"Mac bellek baskısı altında. Ses dosyaları korunuyor.; ",count:500)
        let host=NSHostingView(rootView:MeetingContentForTest(model:model))
        let started=Date()
        for size in [NSSize(width:900,height:620),NSSize(width:1100,height:780),NSSize(width:900,height:620)] {
            host.frame=NSRect(origin:.zero,size:size)
            host.layoutSubtreeIfNeeded()
        }
        XCTAssertLessThan(Date().timeIntervalSince(started),10)
    }
}
private struct MeetingContentForTest:View {
    let model:Model
    var body:some View {
        HStack(spacing:0) {
            SidebarView(model:model).frame(width:264)
            DetailView(model:model).frame(minWidth:640,maxWidth:.infinity,maxHeight:.infinity)
        }
    }
}
