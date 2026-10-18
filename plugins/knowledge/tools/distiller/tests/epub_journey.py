#!/usr/bin/env python3
"""Exercise the installed/debug CLI and inspect the resulting EPUB package."""
import argparse
import base64
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZipFile, ZIP_STORED

NS = {"h": "http://www.w3.org/1999/xhtml", "m": "http://www.w3.org/1998/Math/MathML", "o": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/", "c": "urn:oasis:names:tc:opendocument:xmlns:container"}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC")


def inspect(path):
    with ZipFile(path) as book:
        first = book.infolist()[0]
        assert first.filename == "mimetype" and first.compress_type == ZIP_STORED
        assert book.read("mimetype") == b"application/epub+zip"
        container = ET.fromstring(book.read("META-INF/container.xml"))
        opf_path = container.find(".//c:rootfile", NS).get("full-path")
        opf = ET.fromstring(book.read(opf_path))
        assert opf.get("version") == "3.0"
        manifest = {item.get("id"): item for item in opf.findall("o:manifest/o:item", NS)}
        for itemref in opf.findall("o:spine/o:itemref", NS):
            assert itemref.get("idref") in manifest
        assert sum("nav" in item.get("properties", "").split() for item in manifest.values()) == 1
        documents = {name: ET.fromstring(book.read(name)) for name in book.namelist() if name.endswith(".xhtml")}
        for name, document in documents.items():
            ids = [node.get('id') for node in document.iter() if node.get('id')]
            assert len(ids) == len(set(ids)), (name, 'Duplicate document IDs')
            for link in document.findall(".//h:a", NS):
                href = link.get("href", "")
                if "#" in href and not href.startswith(("https:", "http:", "mailto:")):
                    file, anchor = href.split("#", 1)
                    target = str(Path(os.path.normpath(str(Path(name).parent / file)))) if file else name
                    assert target in documents, (name, href)
                    assert any(node.get("id") == anchor for node in documents[target].iter()), (name, href)
        return book.namelist(), documents, opf, {name: book.read(name) for name in book.namelist()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--epubcheck", type=Path)
    args = parser.parse_args()
    binary = args.binary.resolve()
    assert shutil.which("pandoc"), "Pandoc is required for the EPUB journey"
    with tempfile.TemporaryDirectory(prefix="distiller-epub-test-") as temporary:
        root = Path(temporary)
        assets = root / "article"
        assets.mkdir()
        (assets / "figure.png").write_bytes(PNG)
        (assets / "figure.webp").write_bytes(base64.b64decode("UklGRh4AAABXRUJQVlA4TBEAAAAvAAAAAAfQ//73v/+BiOh/AAA="))
        source = assets / "article.html"
        destination = root / "article.epub"
        code = "fn example() {\n\tlet n = 970;\n\n    n >> 52\n}\n"
        schema = "unstructured replacement " * 250
        html = f"""<!doctype html><html lang="en"><head><title>Reader test</title>
        <meta name="author" content="Test Author"><meta property="article:published_time" content="2024-12-19T00:00:00Z"><script type="application/ld+json">{{"@type":"Article","articleBody":"{schema}"}}</script></head>
        <body><article><h1>Reader test</h1><p>This introduction explains why sections and equations should remain readable.</p>
        <div id="wrapper"><div><h2 id="first">First section</h2><p><a href="#second">Continue</a> x<sup>2</sup> + y<sub>1</sub>.</p>
        <pre><code>{code.replace('>', '&gt;')}</code></pre>
        <figure><img src="figure.png" alt="A pixel"><figcaption>A retained caption</figcaption></figure>
        <figure><img src="figure.webp" alt="A WebP pixel"><figcaption>A converted WebP figure</figcaption></figure>
        <p><math><mfrac><mi>x</mi><mn>2</mn></mfrac></math></p>
        <table><tr><th colspan="2">Spanning header</th></tr><tr><td rowspan="2">left</td><td>right</td></tr><tr><td>bottom</td></tr></table>
        <h2 id="second">Second section</h2><p>This second section discusses the examples and includes a footnote<a id="ref" href="#note">1</a>.</p>
        <p id="note">The footnote text. <a class="footnote-backref" href="#ref">Return</a> <a href="#wrapper">Wrapper</a></p></div></div>
        </article></body></html>"""
        source.write_text(html)
        # Default EPUB creation must fail closed without credentials or cache.
        offline = {key: value for key, value in os.environ.items() if key not in ('MODEL_API_KEY', 'DISTILLER_MUSE_API_KEY')}
        offline['DISTILLER_COVER_CACHE'] = str(root/'empty-cover-cache')
        missing_cover = root/'mandatory-cover.epub'
        for inputs in ([str(source)], ['--stdin', '--base-url', 'https://example.test/blog/']):
            inline_html = html.replace('figure.png', 'data:image/png;base64,'+base64.b64encode(PNG).decode()).replace('figure.webp', 'data:image/png;base64,'+base64.b64encode(PNG).decode())
            result = subprocess.run([str(binary), *inputs, '--mode', 'epub', '-o', str(missing_cover)], input=inline_html if inputs[0] == '--stdin' else None, env=offline, capture_output=True, text=True, timeout=45)
            assert result.returncode != 0 and 'DISTILLER_MUSE_API_KEY' in result.stderr and not missing_cover.exists(), result.stderr
        assert not list((root/'empty-cover-cache').iterdir()), 'No paid reservation without credentials'
        command = [str(binary), str(source), "--mode", "epub", "--base-url", "https://example.test/blog/", "--cover", str(assets/'figure.png'), "-o", str(destination)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        assert result.returncode == 0, result.stderr
        names, documents, opf, files = inspect(destination)
        assert opf.find("o:metadata/dc:title", NS).text == "Reader test"
        assert opf.find("o:metadata/dc:creator", NS).text == "Test Author"
        assert opf.find("o:metadata/dc:language", NS).text == "en"
        assert opf.find("o:metadata/dc:source", NS).text == "https://example.test/blog/"
        assert opf.find("o:metadata/dc:date", NS).text == "2024-12-19"
        covers = [item for item in opf.findall('o:manifest/o:item', NS) if 'cover-image' in item.get('properties','').split()]
        assert len(covers) == 1 and covers[0].get('media-type') == 'image/png'
        assert files['EPUB/' + covers[0].get('href')] == PNG
        rendered = "\n".join(ET.tostring(doc, encoding="unicode") for doc in documents.values())
        assert "unstructured replacement" not in rendered
        blocks = [pre for doc in documents.values() for pre in doc.findall(".//h:pre", NS)]
        assert any("".join(pre.itertext()).rstrip("\n") == code.rstrip("\n") for pre in blocks)
        assert sum(len(doc.findall(".//m:math", NS)) for doc in documents.values()) == 1
        assert 'colspan="2"' in rendered and 'rowspan="2"' in rendered
        assert "A retained caption" in rendered
        assert any(data == PNG for name, data in files.items() if "/media/" in name)
        assert sum(len(d.findall('.//h:img',NS)) for d in documents.values()) == 2
        assert all(data.startswith(b'\x89PNG\r\n\x1a\n') for name,data in files.items() if '/media/' in name)
        assert all("font-family: serif" in ET.tostring(doc, encoding="unicode") for doc in documents.values())
        assert sum(len(doc.findall(".//h:h2", NS)) for doc in documents.values()) >= 2
        navigation = [a for doc in documents.values() for nav in doc.findall('.//h:nav', NS) if nav.get('role') == 'doc-toc' for a in nav.findall('.//h:a', NS)]
        assert [''.join(a.itertext()) for a in navigation if ''.join(a.itertext()) in ('First section', 'Second section')] == ['First section', 'Second section'], 'Nested headings missing or out of order in navigation'
        assert any(a.text == "Return" for doc in documents.values() for a in doc.findall(".//h:a", NS))
        original = destination.read_bytes()
        assert subprocess.run(command, capture_output=True).returncode != 0
        assert destination.read_bytes() == original

        source.write_text(html.replace('<div id="wrapper">', '<div id="wrapper" lang="ar" dir="rtl">'))
        rejected = root / 'language-wrapper.epub'
        result = subprocess.run([str(binary), str(source), '--mode', 'epub', '-o', str(rejected)], capture_output=True, text=True, timeout=45)
        assert result.returncode != 0 and 'language/direction' in result.stderr and not rejected.exists()
        source.write_text(html)

        outside = root / "outside.png"
        outside.write_bytes(PNG)
        (assets / "escape.png").symlink_to(outside)
        (assets / "fake.png").write_text("not an image")
        corrupt = bytearray(PNG)
        corrupt[29] ^= 1  # IHDR checksum: valid signature, corrupt image.
        (assets / "corrupt.png").write_bytes(corrupt)
        os.mkfifo(assets / "pipe.png")
        for cover in ('corrupt.png', 'pipe.png', 'missing.png', 'figure.webp'):
            rejected = root / 'bad-cover.epub'
            result = subprocess.run([str(binary), str(source), '--mode', 'epub', '--cover', str(assets/cover), '-o', str(rejected)], capture_output=True, text=True, timeout=45)
            assert result.returncode != 0 and not rejected.exists(), cover
        assert subprocess.run([str(binary), str(source), '--cover', str(assets/'figure.png'), '--stdout'], capture_output=True, timeout=45).returncode != 0
        for image in ("../outside.png", str(outside), "escape.png", "fake.png", "corrupt.png", "pipe.png", "missing.png", "https://example.invalid/image.png"):
            source.write_text(html.replace("figure.png", image))
            rejected = root / "rejected.epub"
            result = subprocess.run([str(binary), str(source), "--mode", "epub", "-o", str(rejected)], capture_output=True, text=True, timeout=45)
            assert result.returncode != 0, (image, result.stderr)
            assert not rejected.exists(), image
        source.write_text(html)
        # Missing Pandoc must fail without publishing a partial book.
        failed = root / "failed.epub"
        result = subprocess.run([str(binary), str(source), "--mode", "epub", "-o", str(failed)], env={**offline, "PATH": str(root)}, capture_output=True, text=True, timeout=45)
        assert result.returncode != 0 and not failed.exists()
        if args.epubcheck:
            subprocess.run(["java", "-jar", str(args.epubcheck.resolve()), str(destination)], check=True, timeout=60)
        print("EPUB journey passed: structure, navigation, metadata, math, code, images, containment and atomic failure.")


if __name__ == "__main__":
    main()
