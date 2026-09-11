// Two read-only helpers for scripts/verify-privacy.sh. Nothing here clicks, types, records or needs an
// Accessibility grant: `rect` reads the app's own window frame from the window list (the same call
// QuickControl.swift already makes for Zoom) and `compare` reads two PNG files.
//
//   swift scripts/privacy-probe.swift rect [bundle-id]
//   swift scripts/privacy-probe.swift compare <off.png> <on.png> <x> <y> <w> <h> <displayW> <displayH>
//
// Both print one JSON object on stdout and exit 0; problems print {"error":"…"} and exit 1.
import Foundation
import CoreGraphics
import ImageIO
import AppKit

func fail(_ message:String)->Never {
    print("{\"error\":\(quoted(message))}")
    exit(1)
}
func quoted(_ s:String)->String {
    let escaped=s.replacingOccurrences(of:"\\",with:"\\\\").replacingOccurrences(of:"\"",with:"\\\"")
    return "\"\(escaped)\""
}

// MARK: - rect

/// The app's biggest ordinary window, brought to the front first. `NSRunningApplication.activate` is the
/// app-to-app call every Dock click makes; it needs no permission and touches no UI element.
func rect(bundle:String) {
    guard let app=NSRunningApplication.runningApplications(withBundleIdentifier:bundle).first
            ?? NSWorkspace.shared.runningApplications.first(where:{ $0.localizedName=="MeetingOS" || $0.localizedName=="Meeting OS" })
    else { fail("Meeting OS çalışmıyor") }
    app.activate(options:[.activateAllWindows])
    usleep(700_000)
    let pid=app.processIdentifier
    // Front-to-back, on-screen only: the order is what tells us whether something else covers the window.
    let list=(CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]]) ?? []
    func bounds(_ w:[String:Any])->CGRect? {
        guard let d=w["kCGWindowBounds"] as? [String:Any] else { return nil }
        return CGRect(x:d["X"] as? CGFloat ?? 0,y:d["Y"] as? CGFloat ?? 0,width:d["Width"] as? CGFloat ?? 0,height:d["Height"] as? CGFloat ?? 0)
    }
    let mine=list.enumerated().filter { (_,w) in
        (w["kCGWindowOwnerPID"] as? Int32 ?? -1)==pid && (w["kCGWindowLayer"] as? Int ?? 1)==0
            && (bounds(w)?.width ?? 0)>=200 && (bounds(w)?.height ?? 0)>=200
    }
    guard let (index,window)=mine.max(by:{ (bounds($0.1)?.width ?? 0)*(bounds($0.1)?.height ?? 0) < (bounds($1.1)?.width ?? 0)*(bounds($1.1)?.height ?? 0) }),
          let frame=bounds(window) else { fail("Meeting OS penceresi ekranda değil (simge durumunda ya da kapalı olabilir)") }
    // Anything drawn in front of the window and overlapping it would hide the app's content from the OFF
    // capture too, which would make the comparison meaningless. Say so rather than report a false PASS.
    let covering=list.prefix(index).filter { w in
        (w["kCGWindowOwnerPID"] as? Int32 ?? -1) != pid && (w["kCGWindowLayer"] as? Int ?? 1)==0
            && (w["kCGWindowAlpha"] as? Double ?? 1)>0.05 && (bounds(w).map { $0.intersects(frame) } ?? false)
    }.compactMap { $0["kCGWindowOwnerName"] as? String }
    // `x`/`y` are reported relative to the main display, which is what `screencapture -x` writes; `screen_*`
    // keep the global coordinates so the printed rect matches what the user sees in a window inspector.
    let display=CGDisplayBounds(CGMainDisplayID())
    let onMain=display.intersects(frame)
    print("""
    {"pid":\(pid),"x":\(Int(frame.minX-display.minX)),"y":\(Int(frame.minY-display.minY)),"w":\(Int(frame.width)),"h":\(Int(frame.height)),\
    "screen_x":\(Int(frame.minX)),"screen_y":\(Int(frame.minY)),\
    "display_w":\(Int(display.width)),"display_h":\(Int(display.height)),"on_main_display":\(onMain),\
    "covered_by":[\(covering.map(quoted).joined(separator:","))],"title":\(quoted(window["kCGWindowName"] as? String ?? ""))}
    """)
}

// MARK: - compare

func pixels(_ path:String)->(data:[UInt8],w:Int,h:Int) {
    guard let src=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),
          let image=CGImageSourceCreateImageAtIndex(src,0,nil) else { fail("PNG okunamadı: \(path)") }
    let w=image.width, h=image.height
    var buffer=[UInt8](repeating:0,count:w*h*4)
    buffer.withUnsafeMutableBytes { raw in
        guard let ctx=CGContext(data:raw.baseAddress,width:w,height:h,bitsPerComponent:8,bytesPerRow:w*4,
                                space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue) else { return }
        ctx.draw(image,in:CGRect(x:0,y:0,width:w,height:h))
    }
    return (buffer,w,h)
}

/// Two captures of the same screen, one with the app's windows excluded from capture and one without.
/// Everything is reported; the shell script decides PASS/FAIL. `threshold` is per channel out of 255: JPEG-free
/// PNG captures of a static desktop are bit-identical outside the rect, so anything above noise counts.
func compare(off:String,on:String,rect r:CGRect,display:CGSize) {
    let a=pixels(off), b=pixels(on)
    guard a.w==b.w, a.h==b.h else { fail("İki ekran görüntüsü aynı boyutta değil (\(a.w)x\(a.h) vs \(b.w)x\(b.h))") }
    guard display.width>0, display.height>0 else { fail("Ekran boyutu okunamadı") }
    let scale=CGFloat(a.w)/display.width
    let px=Int((r.minX*scale).rounded()), py=Int((r.minY*scale).rounded())
    let pw=Int((r.width*scale).rounded()), ph=Int((r.height*scale).rounded())
    // Three zones, not two. INSIDE is the window inset by 8 px — the rounded corners and the 1 px border sit on
    // the edge and nothing else does. Around the window there is a band that is counted in neither: macOS draws
    // a wide soft shadow outside the frame, and a window excluded from capture takes its shadow with it, so
    // those pixels change for the right reason and would otherwise read as "the rest of the screen moved".
    // OUTSIDE is everything past that band: it must be identical, which is what proves the capture itself is
    // real and only the window went missing.
    let inset=8, margin=96
    let x0=max(0,px+inset), y0=max(0,py+inset), x1=min(a.w,px+pw-inset), y1=min(a.h,py+ph-inset)
    let mx0=px-margin, my0=py-margin, mx1=px+pw+margin, my1=py+ph+margin
    guard x1>x0, y1>y0 else { fail("Pencere dikdörtgeni ekranın dışında") }
    let threshold=12
    var insideTotal=0, insideDiff=0, insideSum=0
    var outsideTotal=0, outsideDiff=0, outsideSum=0
    var ignored=0
    var minX=a.w, minY=a.h, maxX=0, maxY=0
    for y in stride(from:0,to:a.h,by:2) {
        for x in stride(from:0,to:a.w,by:2) {
            let i=(y*a.w+x)*4
            let d=max(abs(Int(a.data[i])-Int(b.data[i])),max(abs(Int(a.data[i+1])-Int(b.data[i+1])),abs(Int(a.data[i+2])-Int(b.data[i+2]))))
            if x>=x0 && x<x1 && y>=y0 && y<y1 { insideTotal+=1; insideSum+=d; if d>threshold { insideDiff+=1 } }
            else if x>=mx0 && x<mx1 && y>=my0 && y<my1 { ignored+=1 }
            else { outsideTotal+=1; outsideSum+=d; if d>threshold { outsideDiff+=1 } }
            if d>threshold { minX=min(minX,x); minY=min(minY,y); maxX=max(maxX,x); maxY=max(maxY,y) }
        }
    }
    let box=maxX>=minX ? "[\(minX),\(minY),\(maxX-minX+1),\(maxY-minY+1)]" : "[]"
    func ratio(_ n:Int,_ total:Int)->String { total>0 ? String(format:"%.4f",Double(n)/Double(total)) : "0" }
    func mean(_ sum:Int,_ total:Int)->String { total>0 ? String(format:"%.3f",Double(sum)/Double(total)) : "0" }
    print("""
    {"image":[\(a.w),\(a.h)],"scale":\(String(format:"%.2f",Double(scale))),"rect_px":[\(px),\(py),\(pw),\(ph)],\
    "inside_changed":\(ratio(insideDiff,insideTotal)),"inside_mean":\(mean(insideSum,insideTotal)),"inside_samples":\(insideTotal),\
    "outside_changed":\(ratio(outsideDiff,outsideTotal)),"outside_mean":\(mean(outsideSum,outsideTotal)),"outside_samples":\(outsideTotal),\
    "ignored_margin_samples":\(ignored),"changed_box":\(box)}
    """)
}

// MARK: - entry

let args=Array(CommandLine.arguments.dropFirst())
switch args.first {
case "rect":
    rect(bundle:args.count>1 ? args[1] : "local.boran.meeting-os")
case "compare":
    guard args.count==9, let x=Double(args[3]), let y=Double(args[4]), let w=Double(args[5]), let h=Double(args[6]),
          let dw=Double(args[7]), let dh=Double(args[8]) else { fail("compare <off.png> <on.png> <x> <y> <w> <h> <displayW> <displayH>") }
    compare(off:args[1],on:args[2],rect:CGRect(x:x,y:y,width:w,height:h),display:CGSize(width:dw,height:dh))
default:
    fail("kullanım: rect | compare")
}
