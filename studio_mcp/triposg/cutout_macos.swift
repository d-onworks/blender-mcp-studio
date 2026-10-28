// macOS 14+ Vision 전경 마스크로 그림 배경을 투명하게 만든다(RGBA PNG).
// TripoSG 기본 배경 제거기(BRIA RMBG-1.4)는 비상업 라이선스라, 입력을 미리 투명 배경으로 만들어 넣는다.
//   swift cutout_macos.swift <입력.png> <출력.png> [x y w h]   # 뒤 네 숫자 = 먼저 잘라낼 영역(픽셀, 왼쪽 위 기준)
import AppKit
import CoreImage
import Vision

let args = CommandLine.arguments
guard args.count == 3 || args.count == 7 else {
    print("usage: swift cutout_macos.swift <in.png> <out.png> [x y w h]"); exit(2)
}
guard var image = CIImage(contentsOf: URL(fileURLWithPath: args[1])) else { print("cannot read \(args[1])"); exit(1) }
if args.count == 7 {
    let v = args[3...6].map { CGFloat(Double($0)!) }
    let h = image.extent.height  // CIImage 는 왼쪽 아래 원점
    image = image.cropped(to: CGRect(x: v[0], y: h - v[1] - v[3], width: v[2], height: v[3]))
    image = image.transformed(by: CGAffineTransform(translationX: -v[0], y: -(h - v[1] - v[3])))
}
let handler = VNImageRequestHandler(ciImage: image)
let req = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([req])
guard let obs = req.results?.first else { print("no foreground found"); exit(1) }
let buf = try obs.generateMaskedImage(ofInstances: obs.allInstances, from: handler, croppedToInstancesExtent: false)
let out = CIImage(cvPixelBuffer: buf)
let ctx = CIContext()
try ctx.writePNGRepresentation(of: out, to: URL(fileURLWithPath: args[2]), format: .RGBA8,
                               colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
print("saved \(args[2]) \(Int(out.extent.width))x\(Int(out.extent.height))")
