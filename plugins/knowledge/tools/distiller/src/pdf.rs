//! Bounded deterministic PDF evidence extraction, followed by validated cloud reconstruction.
use crate::{
    pdf_reconstruct::{Layout, Raster, Span},
    types::DistillerResponse,
};
use anyhow::{ensure, Context, Result};
use image::ImageEncoder;
use pdfium_render::prelude::*;
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, path::Path, process::Stdio, time::Duration};
use tokio::process::Command;

struct Glyph {
    text: char,
    x: f32,
    right: f32,
    y: f32,
    size: f32,
    hyphen: bool,
}

fn spans(mut glyphs: Vec<Glyph>, page: usize, first_id: usize) -> Vec<Span> {
    glyphs.sort_by(|a, b| b.y.total_cmp(&a.y).then(a.x.total_cmp(&b.x)));
    let mut lines: Vec<Vec<Glyph>> = Vec::new();
    for glyph in glyphs {
        if let Some(line) = lines
            .iter_mut()
            .rev()
            .find(|l| (l[0].y - glyph.y).abs() < l[0].size.min(glyph.size) * 0.25)
        {
            line.push(glyph);
        } else {
            lines.push(vec![glyph]);
        }
    }
    let mut result: Vec<Span> = Vec::new();
    for mut line in lines {
        line.sort_by(|a, b| a.x.total_cmp(&b.x));
        let mut right = None;
        for glyph in line {
            let split = right.is_none()
                || result.last().is_some_and(|span| {
                    (span.size - glyph.size).abs() > glyph.size * 0.25
                        || glyph.x - right.unwrap_or(glyph.x) > glyph.size * 0.6
                });
            if split {
                result.push(Span {
                    id: first_id + result.len(),
                    page,
                    x: glyph.x,
                    y: glyph.y,
                    size: glyph.size,
                    text: String::new(),
                    hyphen: false,
                });
            }
            let span = result.last_mut().unwrap();
            if right.is_some_and(|r| glyph.x - r > glyph.size * 0.15)
                && !span.text.is_empty()
                && !span.text.ends_with(char::is_whitespace)
                && !glyph.text.is_whitespace()
            {
                span.text.push(' ');
            }
            span.text.push(glyph.text);
            if !glyph.text.is_whitespace() {
                span.hyphen = glyph.hyphen;
            }
            right = Some(glyph.right);
        }
    }
    for span in &mut result {
        span.text = span.text.trim().into();
    }
    result.retain(|s| !s.text.is_empty());
    for (index, span) in result.iter_mut().enumerate() {
        span.id = first_id + index;
    }
    result
}

fn visit_objects(
    object: &mut PdfPageObject<'_>,
    depth: u8,
    visited: &mut usize,
    visit: &mut impl FnMut(&mut PdfPageObject<'_>) -> Result<()>,
) -> Result<()> {
    *visited += 1;
    ensure!(
        depth <= 16 && *visited <= 100_000,
        "PDF page object tree exceeds limits"
    );
    if let Some(form) = object.as_x_object_form_object() {
        let matrix = form.matrix()?;
        ensure!(
            matrix.a().is_finite()
                && matrix.d().is_finite()
                && matrix.a() > 0.
                && matrix.d() > 0.
                && matrix.b().abs() < 0.00001
                && matrix.c().abs() < 0.00001
                && (matrix.a() - matrix.d()).abs() < 0.00001,
            "Rotated, skewed or stretched PDF Form objects are unsupported"
        );
        for index in form.as_range() {
            visit_objects(&mut form.get(index)?, depth + 1, visited, visit)?;
        }
    } else {
        visit(object)?;
    }
    Ok(())
}

/// Internal worker writes source spans/geometry and unmodified raster assets, without a model call.
pub fn extract(input: &Path, output: &Path) -> Result<()> {
    ensure!(
        input.is_file() && fs::metadata(input)?.len() <= 200 * 1024 * 1024,
        "PDF must be a regular file of at most 200 MiB"
    );
    let library = std::env::var_os("HOME").map(|h| {
        Pdfium::pdfium_platform_library_name_at_path(
            &Path::new(&h).join(".local/share/distiller/lib"),
        )
    });
    let bindings=if let Some(path)=library.filter(|p|p.is_file()){Pdfium::bind_to_library(path)}else{Pdfium::bind_to_system_library()}.context("PDF export requires PDFium 7881 in ~/.local/share/distiller/lib or the system library path")?;
    let pdfium = Pdfium::new(bindings);
    let document = pdfium
        .load_pdf_from_file(input, None)
        .context("Load unencrypted PDF")?;
    ensure!(document.pages().len() <= 400, "PDF exceeds 400 pages");
    let metadata = document.metadata();
    let title = metadata
        .get(PdfDocumentMetadataTagType::Title)
        .map(|m| m.value().to_string())
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| input.file_stem().unwrap().to_string_lossy().into());
    let author = metadata
        .get(PdfDocumentMetadataTagType::Author)
        .map(|m| m.value().to_string())
        .unwrap_or_default();
    let mut layout = Layout {
        title,
        author,
        source_sha256: format!("{:x}", Sha256::digest(fs::read(input)?)),
        pages: Vec::new(),
        spans: Vec::new(),
        images: Vec::new(),
        outline: Vec::new(),
        warnings: Vec::new(),
    };
    for bookmark in document.bookmarks().iter() {
        if let (Some(title), Some(destination)) = (bookmark.title(), bookmark.destination()) {
            let mut depth = 2;
            let mut parent = bookmark.parent();
            while let Some(p) = parent {
                depth += 1;
                parent = p.parent();
            }
            layout
                .outline
                .push((destination.page_index()? as usize + 1, depth.min(6), title));
        }
    }
    let mut image_total = 0usize;
    for (index, page) in document.pages().iter().enumerate() {
        layout.pages.push([page.width().value, page.height().value]);
        let text = page.text()?;
        ensure!(
            text.chars().len() <= 100_000,
            "Page {} exceeds 100000 glyphs",
            index + 1
        );
        let mut glyphs = Vec::new();
        for character in text.chars().iter() {
            let hyphen = character.is_hyphen()?;
            let value = if hyphen {
                '-'
            } else {
                character
                    .unicode_char()
                    .context("PDF character lacks a Unicode mapping")?
            };
            if value.is_control() {
                continue;
            }
            let bounds = character.loose_bounds()?;
            let (x, y) = character.origin()?;
            let size = character.scaled_font_size().value;
            ensure!(
                [
                    x.value,
                    y.value,
                    size,
                    bounds.left().value,
                    bounds.right().value
                ]
                .iter()
                .all(|n| n.is_finite()),
                "Invalid PDF glyph geometry"
            );
            glyphs.push(Glyph {
                text: value,
                x: x.value,
                right: bounds.right().value,
                y: y.value,
                size,
                hyphen,
            });
        }
        let expected: BTreeMap<char, usize> = glyphs
            .iter()
            .filter(|g| !g.text.is_whitespace())
            .fold(BTreeMap::new(), |mut m, g| {
                *m.entry(g.text).or_default() += 1;
                m
            });
        let page_spans = spans(glyphs, index + 1, layout.spans.len());
        let retained: BTreeMap<char, usize> = page_spans
            .iter()
            .flat_map(|s| s.text.chars())
            .filter(|c| !c.is_whitespace())
            .fold(BTreeMap::new(), |mut m, c| {
                *m.entry(c).or_default() += 1;
                m
            });
        ensure!(
            expected == retained,
            "Page {} glyph coverage changed during span extraction",
            index + 1
        );
        layout.spans.extend(page_spans);
        let mut images = 0;
        let mut graphics = 0;
        let mut visited = 0;
        let mut visit = |object: &mut PdfPageObject<'_>| -> Result<()> {
            if matches!(
                object.object_type(),
                PdfPageObjectType::Path
                    | PdfPageObjectType::Shading
                    | PdfPageObjectType::Unsupported
            ) {
                graphics += 1;
                ensure!(!expected.is_empty(), "Page {} has graphics without selectable text; graphic-only reflow is unsupported", index + 1);
            }
            if let Some(image) = object.as_image_object_mut() {
                ensure!(
                    !expected.is_empty(),
                    "Page {} has images without selectable text; OCR is unsupported",
                    index + 1
                );
                ensure!(
                    image.width()? <= 12000
                        && image.height()? <= 12000
                        && (image.width()? as u64) * (image.height()? as u64) <= 32_000_000,
                    "PDF raster image exceeds pixel limits"
                );
                let matrix = image.matrix()?;
                ensure!(
                    matrix.a() > 0.
                        && matrix.d() > 0.
                        && matrix.b().abs() < 0.00001
                        && matrix.c().abs() < 0.00001,
                    "Rotated, mirrored or skewed PDF images are unsupported"
                );
                // Render at integer source-pixel scale to avoid placement-dependent resampling.
                image.reset_matrix(PdfMatrix::new(
                    image.width()? as f32,
                    0.,
                    0.,
                    image.height()? as f32,
                    0.,
                    0.,
                ))?;
                let decoded = image.get_processed_image(&document);
                image.reset_matrix(matrix)?;
                let decoded = decoded?;
                let raw = image.get_raw_image_data()?;
                // Preserve JPEG compression only when PDFium confirms masks/transforms do not change pixels.
                let (bytes, extension) = if raw.starts_with(b"\xff\xd8\xff")
                    && image.get_raw_image()?.to_rgba8() == decoded.to_rgba8()
                {
                    (raw, "jpg")
                } else {
                    let mut bytes = Vec::new();
                    image::codecs::png::PngEncoder::new_with_quality(
                        &mut bytes,
                        image::codecs::png::CompressionType::Best,
                        image::codecs::png::FilterType::Adaptive,
                    )
                    .write_image(
                        decoded.as_bytes(),
                        decoded.width(),
                        decoded.height(),
                        decoded.color().into(),
                    )?;
                    (bytes, "png")
                };
                image_total += bytes.len();
                ensure!(
                    bytes.len() <= 4 * 1024 * 1024 && image_total <= 64 * 1024 * 1024,
                    "Page {} raster image ({} bytes, {} total) exceeds EPUB byte limits",
                    index + 1,
                    bytes.len(),
                    image_total
                );
                images += 1;
                let name = format!("page-{}-image-{images}.{extension}", index + 1);
                fs::write(output.parent().unwrap().join(&name), bytes)?;
                layout.images.push(Raster {
                    id: layout.images.len(),
                    page: index + 1,
                    x: matrix.e(),
                    y: matrix.f(),
                    width: matrix.a(),
                    height: matrix.d(),
                    file: name,
                });
            }
            Ok(())
        };
        for number in page.objects().as_range() {
            visit_objects(
                &mut page.objects().get(number)?,
                0,
                &mut visited,
                &mut visit,
            )?;
        }
        if graphics > 0 {
            layout.warnings.push(format!("Page {} contains {graphics} vector/shading objects; only raster assets are preserved.",index+1));
        }
        let preview = page
            .render_with_config(
                &PdfRenderConfig::new()
                    .set_target_width(1200)
                    .set_maximum_height(1800),
            )?
            .as_image()?
            .to_luma8();
        let mut bytes = Vec::new();
        image::codecs::jpeg::JpegEncoder::new_with_quality(&mut bytes, 80)
            .encode_image(&image::DynamicImage::ImageLuma8(preview))?;
        ensure!(bytes.len() <= 1024 * 1024, "PDF preview exceeds 1 MiB");
        fs::write(
            output
                .parent()
                .unwrap()
                .join(format!("page-{}-preview.jpg", index + 1)),
            bytes,
        )?;
    }
    fs::write(output, serde_json::to_vec(&layout)?)?;
    Ok(())
}

pub async fn write_epub(input: &Path, output: &Path, cover: Option<&Path>) -> Result<()> {
    ensure!(
        !output.try_exists()? && fs::symlink_metadata(output).is_err(),
        "Output already exists: {}",
        output.display()
    );
    let work = tempfile::tempdir()?;
    let source = work.path().join("source.json");
    let errors = work.path().join("adapter.stderr");
    let mut child = Command::new(std::env::current_exe()?)
        .arg(input)
        .args(["--mode", "epub", "--pdf-worker", "-o"])
        .arg(&source)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(fs::File::create(&errors)?)
        .kill_on_drop(true)
        .spawn()?;
    let status = tokio::time::timeout(Duration::from_secs(180), child.wait())
        .await
        .context("PDF extraction exceeded 180 seconds")??;
    ensure!(
        status.success(),
        "PDF extraction failed: {}",
        fs::read_to_string(errors)?
            .chars()
            .take(4000)
            .collect::<String>()
    );
    let layout: Layout = serde_json::from_slice(&fs::read(source)?)?;
    let html = crate::pdf_reconstruct::reconstruct(&layout, work.path()).await?;
    let article = DistillerResponse {
        content: html,
        title: layout.title,
        author: layout.author,
        language: "en".into(),
        ..Default::default()
    };
    crate::epub::write_epub(&article, None, Some(work.path()), false, output, cover).await?;
    eprintln!(
        "PDF reconstruction completed: {} pages. Semantic fidelity requires source comparison.",
        layout.pages.len()
    );
    Ok(())
}
