# Boring Report V1

Boring Report is a deterministic bilingual infographic renderer and historical issue archive. One canonical `issue.json` is validated and rendered by R into matching English and Russian SVG and PNG views. There is no preprocessing, intermediate image, manual compositing, or postprocessing.

## Archive contract

Every completed issue is intentionally preserved in the repository:

```text
data/issues/YYYY-MM-DD/
  issue.json          Canonical historical research data
  report-en.html      English publication view
  report-ru.html      Russian publication view
  telegram-ru.html    Russian Telegram publication view

output/YYYY-MM-DD/
  boring-report-en.svg
  boring-report-en.png
  boring-report-ru.svg
  boring-report-ru.png
```

Research JSON is the source of truth for historical and future meta-analysis. HTML files are publication views. SVG and PNG files are generated visualization views. Completed issue directories and their generated publication assets are committed as the canonical archive; they are not transient build products.

## Canonical issue data

The current schema version is `1.0`. Top-level fields identify the issue and reporting window, hold bilingual publication metadata, record whether the research framework changed, and contain the complete `events` array. Candidate, published, filtered, and watchlist counts are never stored separately: validation and rendering derive them from event records.

Each event has a unique issue-local `id` and stable longitudinal `event_key`, status, category, dates, actors, bilingual analytical fields, confidence, sources, relationships, follow-up status, and published ordering. Supported statuses are `published`, `filtered`, and `watchlist`; supported follow-up states are `none`, `watch`, `resolved`, and `superseded`. Fields without established research content remain `null` or empty arrays.

Locations are honest geographic records:

- `type: "point"` requires valid WGS84 `lat` and `lon` values.
- `type: "region"` is valid without coordinates and is omitted from point plotting.

Each source is a structured object with `type`, `publisher`, `title`, HTTPS `url`, and `published_at`. Unknown fields are validation errors, so weekly data cannot silently alter renderer behavior. Every plotted marker must derive from an event point; decorative markers are prohibited.

## Fixed palette

The project palette is defined only in `scripts/render_report.R` and cannot be overridden by an issue:

```r
ink <- "#17212B"
muted <- "#66717C"
paper <- "#F7F8F6"
land <- "#DDE2E1"
ocean <- "#EDF2F3"
rule <- "#AAB2B5"
published_colour <- "#164B70"
filtered_colour <- "#9B4B42"
```

There are no palette or theme variants in V1.

## Requirements

The first archived issue is tested with R 4.2.2 and these package versions:

- `ggplot2` 4.0.3
- `sf` 1.1.2
- `rnaturalearth` 1.2.0
- `rnaturalearthdata` 1.0.0
- `dplyr` 1.2.1
- `jsonlite` 2.0.0
- `ggrepel` 0.9.8
- `patchwork` 1.3.2
- `svglite` 2.2.2
- `ragg` 1.5.2
- `stringr` 1.6.0
- `systemfonts` 1.3.2

DejaVu Sans or Liberation Sans must be installed with Latin and Cyrillic coverage. Natural Earth geometry is loaded from the installed R packages; rendering does not download assets.

## Validate

From the repository root:

```bash
Rscript scripts/validate_issue.R data/issues/2026-09-01/issue.json
```

Validation failures return a non-zero exit code with field-specific messages. The renderer sources the same validation implementation before reading data into the plotting layer.

## Render

```bash
Rscript scripts/render_report.R \
  data/issues/2026-09-01/issue.json \
  output/2026-09-01/
```

`scripts/render_report.R` is the only rendering implementation. It passes the same R plot composition to `svglite::svglite` for the canonical SVG master and `ragg::agg_png` for a direct 2400 × 1350 PNG render. No non-R image processing occurs.

## Continuous integration

The `Render Boring Report issue` workflow runs on pushes that change `data/issues/**`. V1 accepts exactly one changed `YYYY-MM-DD` issue directory per push and fails clearly if a push changes more than one. Changes confined to `output/**` do not trigger the workflow.

Rendering runs inside the immutable Debian 12.12 container `debian:12.12-slim@sha256:d5d3f9c23164ea16f31852f95bd5959aad1c5e854332fe00f7b3a20fcc9f635c`. R and native graphics/font libraries come from the pinned `20260906T000000Z` Debian Bookworm snapshot. The job verifies the canonical R/package versions and DejaVu Sans file hash before rendering.

Pull requests that change the workflow, `scripts/**`, the canonical `data/issues/2026-09-01/**` fixture, or this README always validate and render issue `2026-09-01`. The PR job uploads its artifact before comparing all four rendered hashes with the committed canonical outputs. It has read-only repository permission and never commits generated files.

For a manual render, open **Actions → Render Boring Report issue → Run workflow** and enter the issue directory name, for example `2026-09-01`. Manual runs validate, render, verify, and upload an artifact, but do not commit generated files.

The workflow uses the same commands as local production:

```bash
Rscript scripts/validate_issue.R data/issues/2026-09-01/issue.json

Rscript scripts/render_report.R \
  data/issues/2026-09-01/issue.json \
  output/2026-09-01/
```

Validation must pass before rendering. Output checks require all four non-empty files, valid SVG documents, and two PNGs measuring exactly 2400 × 1350. Successful push runs use a separate write-enabled job to commit only the four files under `output/<ISSUE>/` back to the same branch with a `build: render Boring Report <ISSUE>` commit; unchanged renders produce no commit. Output-only commits cannot retrigger this path-filtered workflow.

Each successful run uploads `boring-report-<ISSUE>` containing `issue.json`, `report-en.html`, `report-ru.html`, `telegram-ru.html`, and both English and Russian SVG/PNG renders. Validation, rendering, QA, or canonical V1 regression failures stop the job before any output commit.
