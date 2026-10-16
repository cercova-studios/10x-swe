import Foundation
import PDFKit
import AppKit

// Render one physical PDF page; output dimensions stay bounded for agent vision.
let args = CommandLine.arguments
func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(1)
}
guard args.count == 4, let number = Int(args[2]), number > 0 else {
    fail("Usage: render_pdf.swift source.pdf page-number output.png")
}
guard let document = PDFDocument(url: URL(fileURLWithPath: args[1])),
      !document.isLocked, let page = document.page(at: number - 1) else {
    fail("Cannot open PDF page")
}
let bounds = page.bounds(for: .mediaBox)
guard bounds.width > 0, bounds.height > 0 else { fail("Invalid page size") }
let scale = min(1800 / bounds.width, 2400 / bounds.height)
let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
let image = page.thumbnail(of: size, for: .mediaBox)
guard let tiff = image.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let png = bitmap.representation(using: .png, properties: [:]) else {
    fail("Cannot render page")
}
do { try png.write(to: URL(fileURLWithPath: args[3]), options: .atomic) }
catch { fail(error.localizedDescription) }
