# Video workflow

```sh
python3 "$SKILL_DIR/scripts/sources.py" prepare 'URL-or-local-path' \
  --work '/absolute/new/work-directory'
```

Uses yt-dlp for one public non-live video (up to four hours, 4 GB downloader limit).
Defaults to English platform captions, falling back to local Whisper large-v3-turbo,
and 24 evenly spaced 960px frames. Inspect manifest.json, transcript.vtt and actual
frame images. Platform captions may be automatic; ASR can hallucinate or mishear.

Options:
- `--backend whisper`: force local mlx-whisper.
- `--backend parakeet`: force local parakeet-mlx, TDT 0.6b v3. Check its supported
  languages; use Whisper for others.
- `--backend captions`: require captions; fail if absent.
- `--backend none`: visual-only, explicitly missing spoken evidence.
- `--language CODE`: known speech/caption language; unknown/mixed speech uses
  `--backend whisper --language auto`.
- `--model REPO-OR-PATH`: override the MLX model. First use downloads HF weights.
- `--frames 0`: transcript-only; up to 100 for a denser overview.

After reading the transcript, target moments with demos, charts, or deictic cues:

```sh
python3 "$SKILL_DIR/scripts/sources.py" frame '/absolute/work-directory' 152.5 --width 1920
```

Inspect the returned image; sampling it is not proof you viewed it. Track only
actually inspected frame times in analysis coverage. Sparse frames miss motion and
intermediate states; increase coverage where the question requires it. Review long
videos by chapter/topic. Timestamps remain on the original source timeline.

Identical completed requests can reuse their work directory. Incomplete/different
requests require a fresh directory. Check tools.log on failure. Do not repeatedly
retry login/403/rate limits. For a subtitle-specific 429, use the bounded
recovery below once; if it fails, request an accessible local copy instead.

Runtime dependencies already installed on this Mac: yt-dlp, ffmpeg/ffprobe,
mlx-whisper 0.4.3 and parakeet-mlx 0.5.2, with the latter two isolated by uv tool.
Check actual health, not only PATH discovery. Install missing prerequisites only
within user authorization; never configure cloud transcription keys as a fallback.

Official interfaces: [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper),
[Parakeet MLX](https://github.com/senstella/parakeet-mlx),
[yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Subtitle HTTP 429 recovery

First distinguish a subtitle endpoint failure from a metadata or media failure in
tools.log. A subtitle 429 does not establish that the video itself is inaccessible.
For one public video, without cookies or repeated retries:

1. List available tracks with `yt-dlp --ignore-config --list-subs 'URL'`.
   Select the exact original-language track actually listed; do not assume every
   video has `en-orig`. Distinguish translated tracks from source-language captions.
2. In an isolated work directory, try the selected track once with a subtitle
   delay. This example applies only when `en-orig` was listed:

   ```sh
   yt-dlp --ignore-config --no-playlist --skip-download --write-auto-subs \
     --sub-langs en-orig --sub-format vtt --sleep-subtitles 60 \
     -o '/absolute/work/source.%(ext)s' 'URL'
   ```

   `--sleep-subtitles` delays subtitle downloads; ordinary download sleep options
   do not serve the same purpose. If the installed yt-dlp executable cannot run,
   an authorized isolated `uv run --with yt-dlp yt-dlp ...` runtime can be used;
   record its version. This may fetch a package; do not change global installations.
3. Verify exit status, a nonempty WEBVTT file, timestamped cues and the actual
   caption language/content. Preserve automatic-caption provenance. A successful
   command or a track label alone does not prove complete or correct speech.
4. The helper accepts an exact caption selector through `--language en-orig`
   with `--backend captions` when that track exists. It does not currently expose
   `--sleep-subtitles`; do not claim the helper applies the delay. Keep separately
   acquired captions as evidence for follow-up rather than inventing a manifest.
   For local ASR, use a real speech code such as `en`, not a track ID like `en-orig`.
5. If caption recovery fails but public media remains downloadable, acquire media
   without requesting subtitles and prepare that local media with Whisper or
   Parakeet. Otherwise stop and request an accessible copy. Do not silently mark
   missing captions or transcription as success, use infinite retries, access
   browser cookies without explicit authorization, or rotate proxies to evade blocks.
6. Apply the main skill's teardown checks to track listings, logs, partial files,
   retry directories and temporary runtimes. Retain only evidence needed for the
   active analysis or diagnosis; preserve shared dependency caches.

Verified 2026-10-03: yt-dlp 2026.08.19, video `_U-O5lYhJ7Q`, original English
track plus `--sleep-subtitles 60`, no cookies, downloaded a 384282-byte VTT after
an earlier `en` request returned HTTP 429. This is a single-video observation;
the test does not isolate track selection from delay or guarantee future success.
An impersonation-target warning was present even in the successful test.

References: [yt-dlp subtitle 429 discussion](https://github.com/yt-dlp/yt-dlp/issues/13831),
[official options](https://github.com/yt-dlp/yt-dlp#general-options).
