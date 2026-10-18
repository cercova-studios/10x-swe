"""Public PDF -> EPUB journey with layout counterexamples; needs test-only reportlab."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import random
import xml.etree.ElementTree as ET
from reportlab.pdfgen import canvas
from reportlab import rl_config
from reportlab.lib.utils import ImageReader
from io import BytesIO
from PIL import Image
from epub_journey import inspect, NS, PNG
from pdf_model_stub import ModelStub


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--epubcheck', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='distiller-pdf-journey-') as temporary, ModelStub() as model:
        root = Path(temporary)
        os.environ['OPENROUTER_BASE_URL'] = model.url
        os.environ['OPENROUTER_API_KEY'] = 'fixture-placeholder'
        os.environ['DISTILLER_PDF_CACHE'] = str(root/'reconstruction-cache')
        source, output = root/'book.pdf', root/'book.epub'
        cover = root/'cover.png'; cover.write_bytes(PNG)
        c = canvas.Canvas(str(source), pagesize=(612,792))
        c.setTitle('PDF journey'); c.setAuthor('Test Author')
        c.bookmarkPage('chapter'); c.addOutlineEntry('Chapter One', 'chapter')
        c.setFont('Times-Bold',24); c.drawString(72,720,'Chapter One')
        c.setFont('Times-Roman',12)
        for i, text in enumerate(['The body preserves 970 and 52 without mixing marginal notes.',
                                 'A second line keeps the reading order within the body column.',
                                 'A third line contains more body text to establish its font size.']):
            c.drawString(72,680-i*16,text)
        c.setFont('Times-Roman',8); c.drawString(430,680,'1 A retained margin note.')
        c.setFont('Times-Roman',12); c.drawString(72,110,'An inline callout')
        c.setFont('Times-Roman',8); c.drawString(160,114,'1')
        c.setFont('Times-Roman',36); c.drawString(72,590,'W')
        c.setFont('Times-Roman',12); c.drawString(106,610,'e have machines now')
        c.drawString(106,594,'that we can talk to.')
        c.setFont('Times-Roman',12); c.drawString(72,560,'A printed hyphen: GPT-')
        c.drawString(72,544,'3 remains visible.')
        c.drawString(72,520,'Ev-')
        c.drawString(72,504,'ery American institution retains 970 and 52.')
        c.drawImage(ImageReader(BytesIO(PNG)),72,450,width=80,height=80)
        c.beginForm('nested'); c.drawImage(ImageReader(BytesIO(PNG)),200,450,width=80,height=80); c.endForm(); c.doForm('nested')
        pixels = random.Random(42).randbytes(2000*1500*3)
        jpeg = BytesIO()
        Image.frombytes('RGB',(2000,1500),pixels).save(jpeg,format='JPEG',quality=50)
        rl_config.useA85 = False
        c.drawImage(ImageReader(BytesIO(jpeg.getvalue())),72,150,width=200,height=150)
        figure = Image.new('RGB',(40,20),'red')
        figure.paste('blue',(20,0,40,20))
        figure_bytes=BytesIO(); figure.save(figure_bytes,format='PNG')
        c.drawImage(ImageReader(BytesIO(figure_bytes.getvalue())),73.7,343.1,width=127.3,height=63.65)
        c.showPage()
        c.bookmarkPage('quotes'); c.addOutlineEntry("Why I'm optimistic", 'quotes')
        c.bookmarkPage('double'); c.addOutlineEntry("What ``supersecurity'' requires", 'double')
        c.bookmarkPage('wrapped'); c.addOutlineEntry('Intelligence Explosion', 'wrapped')
        c.setFont('Times-Roman',18); c.drawString(72,720,'Why I’m optimistic')
        c.drawString(72,670,'What “supersecurity” requires')
        c.drawString(72,620,'Intelligence Ex-'); c.drawString(72,598,'plosion')
        c.setFont('Times-Roman',12); c.drawString(72,560,'A body sentence retains GPT-3 and curly punctuation.')
        c.showPage(); c.showPage(); c.save()
        offline = {key: value for key, value in os.environ.items() if key not in ('MODEL_API_KEY', 'DISTILLER_MUSE_API_KEY')}
        offline['DISTILLER_COVER_CACHE'] = str(root/'empty-cover-cache')
        mandatory = root/'mandatory.epub'
        result = subprocess.run([str(args.binary.resolve()),str(source),'--mode','epub','-o',str(mandatory)], env=offline, capture_output=True,text=True,timeout=200)
        assert result.returncode != 0 and 'DISTILLER_MUSE_API_KEY' in result.stderr and not mandatory.exists(), result.stderr
        result = subprocess.run([str(args.binary.resolve()),str(source),'--mode','epub','--cover',str(cover),'-o',str(output)],capture_output=True,text=True,timeout=200)
        assert result.returncode == 0, result.stderr
        names, documents, opf, files = inspect(output)
        rendered=' '.join(' '.join(doc.find('h:body',NS).itertext()) for doc in documents.values())
        assert '970 and 52' in rendered and 'A retained margin note' in rendered
        assert 'We have machines now' in rendered, rendered
        assert 'GPT-3 remains visible.' in rendered, rendered
        assert 'Every American institution retains 970 and 52.' in rendered, rendered
        notes = [n for d in documents.values() for n in d.iter() if n.get('role')=='doc-footnote']
        assert any('A retained margin note' in ''.join(n.itertext()) for n in notes)
        callouts = [a for d in documents.values() for a in d.findall('.//h:a',NS)
                    if a.get('id','').startswith('ref-')]
        assert len(callouts) == 1 and ''.join(callouts[0].itertext()) == '1'
        assert any(a.get('href','').endswith('#'+callouts[0].get('id'))
                   for n in notes for a in n.findall('.//h:a',NS))
        assert all('The body preserves' not in ''.join(n.itertext()) for n in notes)
        assert rendered.index('The body preserves') < rendered.index('A retained margin note')
        assert 'This source page is blank.' not in rendered
        assert 'Source page ' not in rendered and 'Notes and captions' not in rendered
        assert any(n.get('id')=='page-1' for d in documents.values() for n in d.iter())
        assert any(''.join(h.itertext())=='Chapter One' for d in documents.values() for h in d.findall('.//h:h2',NS))
        navigation=[n for d in documents.values() for n in d.findall('.//h:nav',NS) if n.get('role')=='doc-toc']
        assert any(a.text=='Chapter One' for n in navigation for a in n.findall('.//h:a',NS)), 'Chapter missing from EPUB navigation'
        assert all('Notes and captions' not in ''.join(n.itertext()) for n in navigation)
        for title in ('Why I’m optimistic', 'What “supersecurity” requires', 'Intelligence Explosion'):
            assert any(''.join(a.itertext()) == title for n in navigation for a in n.findall('.//h:a',NS)), title
        assert 'Why I’m optimistic' in rendered and 'What “supersecurity” requires' in rendered
        assert 'GPT-3' in rendered
        assert opf.find('o:metadata/dc:title',NS).text=='PDF journey'
        assert sum('cover-image' in item.get('properties','').split() for item in opf.findall('o:manifest/o:item',NS)) == 1
        assert sum(len(d.findall('.//h:img',NS)) for d in documents.values()) == 4
        assert any(data == jpeg.getvalue() for name,data in files.items() if '/media/' in name)
        assert any(Image.open(BytesIO(data)).convert('RGB').tobytes()==figure.tobytes()
                   for name,data in files.items() if '/media/' in name)
        assert 'Conversion notes' not in rendered
        assert model.calls > 0
        for failure in ('missing','invented','incomplete'):
            model.mode = failure
            os.environ['DISTILLER_PDF_CACHE'] = str(root/failure)
            invalid = root/(failure+'.epub')
            result = subprocess.run([str(args.binary.resolve()),str(source),'--mode','epub','--cover',str(cover),'-o',str(invalid)],capture_output=True,text=True,timeout=200)
            assert result.returncode != 0 and not invalid.exists(), (failure,result.stderr)
        model.mode = 'valid'
        if args.epubcheck:
            subprocess.run(['java','-jar',str(args.epubcheck.resolve()),str(output)],check=True,timeout=60)
        scanned=root/'scanned.pdf'; rejected=root/'scanned.epub'
        c=canvas.Canvas(str(scanned)); c.drawImage(ImageReader(BytesIO(PNG)),72,450,width=80,height=80); c.save()
        result=subprocess.run([str(args.binary.resolve()),str(scanned),'--mode','epub','-o',str(rejected)],capture_output=True,text=True,timeout=200)
        assert result.returncode != 0 and 'OCR is unsupported' in result.stderr and not rejected.exists()
        nested=root/'nested-scan.pdf'
        c=canvas.Canvas(str(nested)); c.beginForm('scan'); c.drawImage(ImageReader(BytesIO(PNG)),72,450,width=80,height=80); c.endForm(); c.doForm('scan'); c.save()
        result=subprocess.run([str(args.binary.resolve()),str(nested),'--mode','epub','-o',str(rejected)],capture_output=True,text=True,timeout=200)
        assert result.returncode != 0 and 'OCR is unsupported' in result.stderr and not rejected.exists()
        vector=root/'vector.pdf'
        c=canvas.Canvas(str(vector)); c.rect(72,450,80,80); c.save()
        result=subprocess.run([str(args.binary.resolve()),str(vector),'--mode','epub','-o',str(rejected)],capture_output=True,text=True,timeout=200)
        assert result.returncode != 0 and 'graphic-only reflow is unsupported' in result.stderr and not rejected.exists()
        rotated=root/'rotated-form.pdf'
        c=canvas.Canvas(str(rotated)); c.setFont('Times-Roman',12); c.drawString(72,720,'Selectable body text.')
        c.beginForm('rotated'); c.drawImage(ImageReader(BytesIO(PNG)),72,450,width=80,height=80); c.endForm()
        c.rotate(90); c.doForm('rotated'); c.save()
        result=subprocess.run([str(args.binary.resolve()),str(rotated),'--mode','epub','-o',str(rejected)],capture_output=True,text=True,timeout=200)
        assert result.returncode != 0 and 'PDF Form objects are unsupported' in result.stderr and not rejected.exists()
        false_outline=root/'false-outline.pdf'; false_book=root/'false-outline.epub'
        c=canvas.Canvas(str(false_outline)); c.bookmarkPage('art'); c.addOutlineEntry('Art','art')
        c.setFont('Times-Roman',12); c.drawString(72,720,'A cartography tutorial has no art chapter title on this page.'); c.save()
        result=subprocess.run([str(args.binary.resolve()),str(false_outline),'--mode','epub','--cover',str(cover),'-o',str(false_book)],capture_output=True,text=True,timeout=200)
        assert result.returncode == 0, result.stderr
        _,docs,_,_=inspect(false_book)
        assert not any(''.join(h.itertext())=='Art' for d in docs.values() for h in d.findall('.//h:h2',NS))
        assert not any(''.join(a.itertext())=='Art' for d in docs.values() for a in d.findall('.//h:a',NS))
        print('PDF journey passed: chapter, page anchors, body numbers, margin note, drop cap, image, blank page and scan rejection.')


if __name__=='__main__':
    main()
