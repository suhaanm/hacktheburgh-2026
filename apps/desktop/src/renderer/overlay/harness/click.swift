// Posts one synthetic left click at a global point (DIPs) and puts the pointer back where it was.
// Used by real-check.mjs to prove the overlay is click-through. Needs Accessibility trust for the calling process.
import ApplicationServices
import CoreGraphics
import Foundation

let args = CommandLine.arguments
guard args.count >= 3, let x = Double(args[1]), let y = Double(args[2]) else {
  FileHandle.standardError.write(Data("usage: click.swift <x> <y>\n".utf8))
  exit(2)
}
guard AXIsProcessTrusted() else {
  FileHandle.standardError.write(Data("not trusted for accessibility\n".utf8))
  exit(3)
}
let source = CGEventSource(stateID: .hidSystemState)
let original = CGEvent(source: nil)?.location ?? CGPoint(x: 0, y: 0)
let point = CGPoint(x: x, y: y)
CGWarpMouseCursorPosition(point)
usleep(120_000)
for type in [CGEventType.leftMouseDown, CGEventType.leftMouseUp] {
  CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point, mouseButton: .left)?.post(tap: .cghidEventTap)
  usleep(80_000)
}
usleep(150_000)
CGWarpMouseCursorPosition(original)
print("clicked \(x),\(y)")
