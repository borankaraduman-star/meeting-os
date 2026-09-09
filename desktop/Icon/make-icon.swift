import AppKit
// Generates the Meeting OS app icon: deep teal rounded square, soft highlight, white waveform bars.
let sizes=[16,32,64,128,256,512,1024]
let out=URL(fileURLWithPath:CommandLine.arguments[1])
try? FileManager.default.createDirectory(at:out,withIntermediateDirectories:true)
func draw(_ px:Int)->NSImage {
    let s=CGFloat(px); let img=NSImage(size:NSSize(width:s,height:s))
    img.lockFocus()
    let ctx=NSGraphicsContext.current!.cgContext
    let inset=s*0.05; let rect=CGRect(x:inset,y:inset,width:s-2*inset,height:s-2*inset)
    let path=CGPath(roundedRect:rect,cornerWidth:s*0.22,cornerHeight:s*0.22,transform:nil)
    ctx.addPath(path); ctx.clip()
    let colors=[CGColor(red:0.09,green:0.42,blue:0.36,alpha:1),CGColor(red:0.16,green:0.62,blue:0.50,alpha:1)] as CFArray
    let grad=CGGradient(colorsSpace:CGColorSpaceCreateDeviceRGB(),colors:colors,locations:[0,1])!
    ctx.drawLinearGradient(grad,start:CGPoint(x:0,y:0),end:CGPoint(x:s,y:s),options:[])
    // highlight arc
    ctx.setFillColor(CGColor(red:1,green:1,blue:1,alpha:0.08))
    ctx.fillEllipse(in:CGRect(x:-s*0.2,y:s*0.55,width:s*1.4,height:s*0.9))
    // waveform bars
    let heights:[CGFloat]=[0.22,0.40,0.62,0.44,0.72,0.50,0.30]
    let n=CGFloat(heights.count); let gap=s*0.045; let barW=(rect.width*0.62-gap*(n-1))/n
    let x0=rect.midX-(barW*n+gap*(n-1))/2
    ctx.setFillColor(CGColor(red:1,green:1,blue:1,alpha:0.96))
    for (i,h) in heights.enumerated() {
        let bh=rect.height*h; let bar=CGRect(x:x0+CGFloat(i)*(barW+gap),y:rect.midY-bh/2,width:barW,height:bh)
        ctx.addPath(CGPath(roundedRect:bar,cornerWidth:barW/2,cornerHeight:barW/2,transform:nil)); ctx.fillPath()
    }
    img.unlockFocus()
    return img
}
for px in sizes {
    let img=draw(px)
    let rep=NSBitmapImageRep(data:img.tiffRepresentation!)!
    let png=rep.representation(using:.png,properties:[:])!
    try! png.write(to:out.appendingPathComponent("icon_\(px)x\(px).png"))
    if px<=512 { let rep2=NSBitmapImageRep(data:draw(px*2).tiffRepresentation!)!; try! rep2.representation(using:.png,properties:[:])!.write(to:out.appendingPathComponent("icon_\(px)x\(px)@2x.png")) }
}
print("icons written to",out.path)
