#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(ggplot2)
  library(sf)
  library(rnaturalearth)
  library(rnaturalearthdata)
  library(dplyr)
  library(jsonlite)
  library(ggrepel)
  library(patchwork)
  library(svglite)
  library(ragg)
  library(stringr)
})

script_flag <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)
if (length(script_flag) != 1L) stop("Could not locate render_report.R.", call. = FALSE)
script_path <- normalizePath(sub("^--file=", "", script_flag), mustWork = TRUE)
source(file.path(dirname(script_path), "validate_issue.R"), local = TRUE)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 2L) {
  stop(
    "Usage: Rscript scripts/render_report.R <issue.json> <output-directory>",
    call. = FALSE
  )
}

input_path <- args[[1]]
output_dir <- args[[2]]

fail <- function(message) stop(message, call. = FALSE)
validated <- validate_issue(input_path)
issue <- validated$issue
issue_id <- issue$issue_id
issue_number <- issue$issue_number
date_range <- list(display_en = issue$date_display_en, display_ru = issue$date_display_ru)
brand <- issue$brand
credit <- issue$credit
candidates_raw <- validated$events

candidate_row <- function(candidate, index) {
  location <- candidate$location
  is_point <- identical(location$type, "point")

  data.frame(
    id = candidate$id,
    status = candidate$status,
    category = candidate$category,
    location_type = location$type,
    longitude = if (is_point) as.numeric(location$lon) else NA_real_,
    latitude = if (is_point) as.numeric(location$lat) else NA_real_,
    location_en = if (is.null(location$name_en)) location$name else location$name_en,
    location_ru = if (is.null(location$name_ru)) location$name else location$name_ru,
    label_en = candidate$headline_en,
    label_ru = candidate$headline_ru,
    map_label_en = candidate$map_label_en,
    map_label_ru = candidate$map_label_ru,
    reason_en = if (is.null(candidate$filter_reason_en)) "" else candidate$filter_reason_en,
    reason_ru = if (is.null(candidate$filter_reason_ru)) "" else candidate$filter_reason_ru,
    published_order = if (candidate$status == "published") as.integer(candidate$published_order) else NA_integer_,
    stringsAsFactors = FALSE
  )
}

candidates <- bind_rows(Map(candidate_row, candidates_raw, seq_along(candidates_raw)))
published <- candidates %>% filter(status == "published") %>% arrange(published_order)
filtered <- candidates %>% filter(status %in% c("filtered", "watchlist"))

if (!dir.exists(output_dir)) {
  created <- tryCatch(dir.create(output_dir, recursive = TRUE), warning = function(w) FALSE, error = function(e) FALSE)
  if (!isTRUE(created) || !dir.exists(output_dir)) fail(sprintf("Could not create output directory: %s", output_dir))
}
if (file.access(output_dir, 2) != 0) fail(sprintf("Output directory is not writable: %s", output_dir))

font_family <- "sans"
if (requireNamespace("systemfonts", quietly = TRUE)) {
  font_matches <- systemfonts::match_fonts(c("DejaVu Sans", "Liberation Sans"))
  for (i in seq_len(nrow(font_matches))) {
    glyphs <- systemfonts::glyph_info(c("A", "Б", "я"), path = font_matches$path[[i]], index = font_matches$index[[i]])
    if (all(glyphs$index > 0)) {
      font_family <- c("DejaVu Sans", "Liberation Sans")[[i]]
      break
    }
  }
}

ink <- "#17212B"
muted <- "#66717C"
paper <- "#F7F8F6"
land <- "#DDE2E1"
ocean <- "#EDF2F3"
rule <- "#AAB2B5"
published_colour <- "#164B70"
filtered_colour <- "#9B4B42"
projection <- "+proj=robin +datum=WGS84 +units=m +no_defs"

world <- rnaturalearth::ne_countries(scale = "small", returnclass = "sf") %>%
  filter(continent != "Antarctica") %>%
  st_transform(projection)

mappable_candidates <- candidates %>% filter(location_type == "point")
if (nrow(mappable_candidates)) {
  points_sf <- st_as_sf(mappable_candidates, coords = c("longitude", "latitude"), crs = 4326, remove = FALSE) %>%
    st_transform(projection)
  coordinates <- st_coordinates(points_sf)
  points <- bind_cols(st_drop_geometry(points_sf), data.frame(x = coordinates[, 1], y = coordinates[, 2]))
} else {
  points <- mappable_candidates %>% mutate(x = numeric(), y = numeric())
}

world_box <- st_bbox(world)
map_xlim <- c(world_box[["xmin"]], world_box[["xmax"]])
map_ylim <- c(world_box[["ymin"]] * 0.88, world_box[["ymax"]] * 0.93)

base_theme <- theme_void(base_family = font_family) +
  theme(
    plot.background = element_rect(fill = paper, colour = NA),
    plot.margin = margin(0, 0, 0, 0),
    text = element_text(colour = ink, lineheight = 0.95)
  )

language_text <- list(
  en = list(
    issue = "ISSUE",
    candidates = "CANDIDATES",
    published = "PUBLISHED",
    filtered = "FILTERED",
    selected = "SELECTED EVENTS",
    watchlist = "FILTERED / WATCHLIST",
    legend_published = "NUMBERED / PUBLISHED",
    legend_filtered = "CROSS / FILTERED",
    representative = "Beijing marker represents trials also announced for Guangzhou."
  ),
  ru = list(
    issue = "ВЫПУСК",
    candidates = "КАНДИДАТОВ",
    published = "ОПУБЛИКОВАНО",
    filtered = "ОТФИЛЬТРОВАНО",
    selected = "ОТОБРАННЫЕ СОБЫТИЯ",
    watchlist = "ФИЛЬТР / ЛИСТ НАБЛЮДЕНИЯ",
    legend_published = "НОМЕР / ОПУБЛИКОВАНО",
    legend_filtered = "КРЕСТ / ОТФИЛЬТРОВАНО",
    representative = "Маркер Пекина также представляет испытания, заявленные для Гуанчжоу."
  )
)

wrap_fixed <- function(text, width) stringr::str_wrap(text, width = width, whitespace_only = TRUE)

make_header <- function(lang) {
  title <- issue[[paste0("title_", lang)]]
  subtitle <- issue[[paste0("subtitle_", lang)]]
  date_display <- date_range[[paste0("display_", lang)]]
  t <- language_text[[lang]]
  ggplot() +
    annotate("text", x = 0, y = 0.72, label = title, hjust = 0, vjust = 0.5,
             family = font_family, fontface = "bold", size = 12.5, colour = ink) +
    annotate("text", x = 0, y = 0.20, label = subtitle, hjust = 0, vjust = 0.5,
             family = font_family, fontface = "bold", size = if (lang == "ru") 4.4 else 5.2,
             colour = published_colour) +
    annotate("text", x = 1, y = 0.70,
             label = sprintf("%s %02d  /  %s", t$issue, as.integer(issue_number), date_display),
             hjust = 1, vjust = 0.5, family = font_family, fontface = "bold", size = 4.3, colour = ink) +
    annotate("text", x = 1, y = 0.18, label = paste(brand, "·", credit), hjust = 1, vjust = 0.5,
             family = font_family, size = 3.25, colour = muted) +
    annotate("segment", x = 0, xend = 1, y = -0.05, yend = -0.05, linewidth = 0.7, colour = ink) +
    coord_cartesian(xlim = c(0, 1), ylim = c(-0.12, 1), clip = "off") + base_theme +
    theme(plot.margin = margin(12, 20, 3, 20))
}

make_map <- function(lang) {
  pub <- points %>% filter(status == "published")
  filt <- points %>% filter(status %in% c("filtered", "watchlist"))
  pub$display_label <- pub[[paste0("map_label_", lang)]]
  filt$display_label <- filt[[paste0("map_label_", lang)]]
  # Label anchors are nudged, never the event markers. The fixed offsets open up
  # the London/Brussels/Geneva/Basel cluster while ggrepel handles final boxes.
  pub_nudge_x <- c(
    "us-chatgpt-mil" = -900000, "eu-chatgpt-vlose" = 1500000,
    "uk-sovereign-ai-procurement" = -2300000, "fi-lumi-ai-contract" = 1900000
  )
  pub_nudge_y <- c(
    "us-chatgpt-mil" = -650000, "eu-chatgpt-vlose" = -1450000,
    "uk-sovereign-ai-procurement" = 1550000, "fi-lumi-ai-contract" = 950000
  )
  filt_nudge_x <- c(
    "ch-laws-negotiations" = -1900000, "ch-fsb-ai-cyber-risk" = 1600000,
    "cn-didi-r2-trials" = 1100000
  )
  filt_nudge_y <- c(
    "ch-laws-negotiations" = -1100000, "ch-fsb-ai-cyber-risk" = -350000,
    "cn-didi-r2-trials" = 900000
  )
  pub$nudge_x <- unname(pub_nudge_x[pub$id])
  pub$nudge_y <- unname(pub_nudge_y[pub$id])
  filt$nudge_x <- unname(filt_nudge_x[filt$id])
  filt$nudge_y <- unname(filt_nudge_y[filt$id])
  pub$nudge_x[is.na(pub$nudge_x)] <- 0
  pub$nudge_y[is.na(pub$nudge_y)] <- 0
  filt$nudge_x[is.na(filt$nudge_x)] <- 0
  filt$nudge_y[is.na(filt$nudge_y)] <- 0

  ggplot() +
    geom_sf(data = world, fill = land, colour = "#8C989B", linewidth = 0.18) +
    geom_point(data = filt, aes(x = x, y = y), shape = 4, size = 4.2,
               stroke = 1.25, colour = filtered_colour) +
    geom_point(data = pub, aes(x = x, y = y), shape = 21, size = 6.6,
               stroke = 1.15, fill = published_colour, colour = paper) +
    geom_text(data = pub, aes(x = x, y = y, label = published_order),
              family = font_family, fontface = "bold", size = 3.25, colour = "white") +
    ggrepel::geom_label_repel(
      data = pub,
      aes(x = x, y = y, label = display_label),
      family = font_family, fontface = "bold", size = 3.1, colour = ink,
      fill = paper, box.padding = 0.65, point.padding = 0.65,
      label.padding = unit(0.18, "lines"), label.r = unit(0, "lines"),
      label.size = 0.25, segment.colour = ink, segment.size = 0.35,
      min.segment.length = 0, seed = 20260901, max.overlaps = Inf,
      force = 2.2, max.time = Inf, max.iter = 10000,
      nudge_x = pub$nudge_x, nudge_y = pub$nudge_y
    ) +
    ggrepel::geom_label_repel(
      data = filt,
      aes(x = x, y = y, label = display_label),
      family = font_family, size = 2.7, colour = filtered_colour,
      fill = paper, box.padding = 0.55, point.padding = 0.5,
      label.padding = unit(0.14, "lines"), label.r = unit(0, "lines"),
      label.size = 0.2, segment.colour = filtered_colour, segment.size = 0.3,
      min.segment.length = 0, seed = 20260901, max.overlaps = Inf,
      force = 2.6, max.time = Inf, max.iter = 10000,
      nudge_x = filt$nudge_x, nudge_y = filt$nudge_y
    ) +
    coord_sf(crs = projection, xlim = map_xlim, ylim = map_ylim, expand = FALSE, datum = NA) +
    base_theme +
    theme(
      panel.background = element_rect(fill = ocean, colour = ink, linewidth = 0.45),
      plot.margin = margin(3, 10, 3, 20)
    )
}

make_side_panel <- function(lang) {
  t <- language_text[[lang]]
  location_field <- paste0("location_", lang)
  label_field <- paste0("label_", lang)
  list_lines <- paste0(
    published$published_order, ".  ", toupper(published[[location_field]]), "\n",
    vapply(published[[label_field]], wrap_fixed, character(1), width = if (lang == "ru") 31 else 34)
  )
  list_y <- c(0.48, 0.355, 0.23, 0.105)

  panel <- ggplot() +
    annotate("rect", xmin = 0, xmax = 1, ymin = 0.76, ymax = 1, fill = "#E7EAEB", colour = rule, linewidth = 0.35) +
    annotate("text", x = c(0.16, 0.50, 0.84), y = 0.91,
             label = c(nrow(candidates), nrow(published), nrow(filtered)),
             family = font_family, fontface = "bold", size = 8.0,
             colour = c(ink, published_colour, filtered_colour)) +
    annotate("text", x = c(0.16, 0.50, 0.84), y = 0.81,
             label = c(t$candidates, t$published, t$filtered),
             family = font_family, fontface = "bold", size = if (lang == "ru") 2.35 else 2.55,
             colour = muted) +
    annotate("segment", x = c(0.33, 0.67), xend = c(0.33, 0.67), y = 0.79, yend = 0.97,
             colour = rule, linewidth = 0.35) +
    annotate("text", x = 0, y = 0.68, label = t$selected, hjust = 0,
             family = font_family, fontface = "bold", size = 3.8, colour = ink) +
    annotate("segment", x = 0, xend = 1, y = 0.635, yend = 0.635, colour = ink, linewidth = 0.45) +
    annotate("point", x = 0.02, y = 0.59, shape = 21, size = 3.4, stroke = 0.8,
             fill = published_colour, colour = paper) +
    annotate("text", x = 0.06, y = 0.59, label = t$legend_published, hjust = 0, vjust = 0.5,
             family = font_family, fontface = "bold", size = 2.0, colour = published_colour) +
    annotate("point", x = 0.53, y = 0.59, shape = 4, size = 3.0, stroke = 0.9,
             colour = filtered_colour) +
    annotate("text", x = 0.57, y = 0.59, label = t$legend_filtered, hjust = 0, vjust = 0.5,
             family = font_family, fontface = "bold", size = 2.0, colour = filtered_colour)

  for (i in seq_along(list_lines)) {
    panel <- panel +
      annotate("text", x = 0, y = list_y[[i]], label = list_lines[[i]], hjust = 0, vjust = 0.5,
               family = font_family, size = if (lang == "ru") 2.7 else 2.85,
               lineheight = 0.95, colour = ink)
  }

  panel +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), clip = "off") + base_theme +
    theme(plot.margin = margin(3, 20, 3, 6))
}

make_footer <- function(lang) {
  t <- language_text[[lang]]
  location_field <- paste0("location_", lang)
  label_field <- paste0("label_", lang)
  reason_field <- paste0("reason_", lang)
  card_x <- c(0.005, 0.335, 0.665)
  card_width <- 0.32

  panel <- ggplot() +
    annotate("segment", x = 0, xend = 1, y = 0.98, yend = 0.98, colour = ink, linewidth = 0.7) +
    annotate("text", x = 0, y = 0.88, label = t$watchlist, hjust = 0,
             family = font_family, fontface = "bold", size = 3.5, colour = filtered_colour)

  for (i in seq_len(nrow(filtered))) {
    heading <- paste0(toupper(filtered[[location_field]][[i]]), "\n", toupper(filtered$category[[i]]))
    body <- paste(
      wrap_fixed(filtered[[label_field]][[i]], if (lang == "ru") 46 else 51),
      wrap_fixed(filtered[[reason_field]][[i]], if (lang == "ru") 46 else 51),
      sep = "\n"
    )
    panel <- panel +
      annotate("rect", xmin = card_x[[i]], xmax = card_x[[i]] + card_width, ymin = 0.31, ymax = 0.79,
               fill = "#EEF0F0", colour = rule, linewidth = 0.3) +
      annotate("text", x = card_x[[i]] + 0.012, y = 0.69, label = heading, hjust = 0, vjust = 0.5,
               family = font_family, fontface = "bold", size = 2.15,
               lineheight = 0.88, colour = filtered_colour) +
      annotate("text", x = card_x[[i]] + 0.012, y = 0.45,
               label = body, hjust = 0, vjust = 0.5,
               family = font_family, size = if (lang == "ru") 2.35 else 2.45,
               lineheight = 0.9, colour = ink)
  }

  bottom_line <- issue[[paste0("bottom_line_", lang)]]
  panel +
    annotate("text", x = 0, y = 0.18, label = bottom_line, hjust = 0, vjust = 0.5,
             family = font_family, fontface = "bold", size = if (lang == "ru") 3.2 else 3.45, colour = ink) +
    annotate("text", x = 1, y = 0.04, label = t$representative, hjust = 1, vjust = 0.5,
             family = font_family, size = 2.25, colour = muted) +
    coord_cartesian(xlim = c(0, 1), ylim = c(0, 1), clip = "off") + base_theme +
    theme(plot.margin = margin(4, 20, 10, 20))
}

make_report <- function(lang) {
  make_header(lang) /
    ((make_map(lang) | make_side_panel(lang)) + patchwork::plot_layout(widths = c(3.2, 1.35))) /
    make_footer(lang) +
    patchwork::plot_layout(heights = c(0.95, 4.9, 1.75)) &
    theme(plot.background = element_rect(fill = paper, colour = NA))
}

output_files <- character()
for (lang in c("en", "ru")) {
  report <- make_report(lang)
  svg_path <- file.path(output_dir, sprintf("boring-report-%s.svg", lang))
  png_path <- file.path(output_dir, sprintf("boring-report-%s.png", lang))

  # Both devices receive the same plot object at the same physical 16:9 size.
  # SVG is the canonical vector master; PNG is a direct 150 ppi R render.
  ggsave(
    svg_path, report,
    device = svglite::svglite,
    width = 16, height = 9, units = "in", bg = paper
  )
  ggsave(
    png_path, report,
    device = ragg::agg_png,
    width = 2400, height = 1350, units = "px", dpi = 150, bg = paper
  )
  output_files <- c(output_files, basename(svg_path), basename(png_path))
}

cat(sprintf("Issue: %s\n", issue_id))
cat(sprintf("Candidates: %d\n", nrow(candidates)))
cat(sprintf("Published: %d\n", nrow(published)))
cat(sprintf("Filtered: %d\n", validated$counts[["filtered"]]))
cat(sprintf("Watchlist: %d\n", validated$counts[["watchlist"]]))
cat("Rendered:\n")
cat(paste0("  ", output_files, collapse = "\n"), "\n", sep = "")
