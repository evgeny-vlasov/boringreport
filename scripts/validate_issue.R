#!/usr/bin/env Rscript

is_scalar_string <- function(x) {
  is.character(x) && length(x) == 1L && !is.na(x) && nzchar(x)
}

is_valid_utf8 <- function(x) {
  is.character(x) && all(!is.na(iconv(x, from = "UTF-8", to = "UTF-8", sub = NA_character_)))
}

is_iso_date <- function(x) {
  is_scalar_string(x) &&
    grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", x) &&
    !is.na(as.Date(x, format = "%Y-%m-%d"))
}

validate_issue <- function(path) {
  errors <- character()
  add_error <- function(...) errors <<- c(errors, sprintf(...))

  if (!file.exists(path)) {
    stop(sprintf("Issue file does not exist: %s", path), call. = FALSE)
  }

  issue <- tryCatch(
    jsonlite::fromJSON(path, simplifyVector = FALSE),
    error = function(e) stop(sprintf("Could not parse issue JSON: %s", conditionMessage(e)), call. = FALSE)
  )

  require_key <- function(object, key, context) {
    if (!key %in% names(object)) add_error("%s is missing required field '%s'.", context, key)
  }
  require_text <- function(object, key, context) {
    require_key(object, key, context)
    if (key %in% names(object) && !is_scalar_string(object[[key]])) {
      add_error("%s.%s must be a non-empty string.", context, key)
    }
  }
  optional_text <- function(object, key, context) {
    require_key(object, key, context)
    if (key %in% names(object) && !is.null(object[[key]]) && !is_scalar_string(object[[key]])) {
      add_error("%s.%s must be null or a non-empty string.", context, key)
    }
  }
  if_present_text <- function(object, key, context) {
    if (key %in% names(object) && !is.null(object[[key]]) && !is_scalar_string(object[[key]])) {
      add_error("%s.%s must be a non-empty string when present.", context, key)
    }
  }
  reject_unknown <- function(object, allowed, context) {
    unknown <- setdiff(names(object), allowed)
    if (length(unknown)) {
      add_error("%s contains unknown field(s): %s.", context, paste(unknown, collapse = ", "))
    }
  }
  check_ru <- function(value, context) {
    if (!is.null(value) && (!is_scalar_string(value) || !is_valid_utf8(value))) {
      add_error("%s must be valid UTF-8 text or null.", context)
    }
  }

  top_fields <- c(
    "schema_version", "issue_id", "issue_number", "window_start", "window_end",
    "generated_at", "title_en", "title_ru", "subtitle_en", "subtitle_ru",
    "bottom_line_en", "bottom_line_ru", "framework_changed",
    "framework_change_note_en", "framework_change_note_ru", "date_display_en",
    "date_display_ru", "brand", "credit", "events"
  )
  reject_unknown(issue, top_fields, "issue")
  for (field in top_fields) require_key(issue, field, "issue")
  for (field in c(
    "schema_version", "issue_id", "generated_at", "title_en", "title_ru",
    "subtitle_en", "subtitle_ru", "bottom_line_en", "bottom_line_ru",
    "date_display_en", "date_display_ru", "brand", "credit"
  )) require_text(issue, field, "issue")
  optional_text(issue, "framework_change_note_en", "issue")
  optional_text(issue, "framework_change_note_ru", "issue")

  if (!is.null(issue$issue_number) &&
      (!is.numeric(issue$issue_number) || length(issue$issue_number) != 1L ||
       !is.finite(issue$issue_number) || issue$issue_number < 1 || issue$issue_number %% 1 != 0)) {
    add_error("issue.issue_number must be a positive integer.")
  }
  if (!is.null(issue$framework_changed) &&
      (!is.logical(issue$framework_changed) || length(issue$framework_changed) != 1L || is.na(issue$framework_changed))) {
    add_error("issue.framework_changed must be true or false.")
  }
  if (!is.null(issue$window_start) && !is_iso_date(issue$window_start)) {
    add_error("issue.window_start must be a valid YYYY-MM-DD date.")
  }
  if (!is.null(issue$window_end) && !is_iso_date(issue$window_end)) {
    add_error("issue.window_end must be a valid YYYY-MM-DD date.")
  }
  if (!is.null(issue$window_start) && !is.null(issue$window_end) &&
      is_iso_date(issue$window_start) && is_iso_date(issue$window_end) &&
      as.Date(issue$window_start) > as.Date(issue$window_end)) {
    add_error("issue.window_start must not be after issue.window_end.")
  }
  if (!is.null(issue$generated_at) &&
      !grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", issue$generated_at)) {
    add_error("issue.generated_at must be an ISO-8601 UTC timestamp such as 2026-09-05T16:27:01Z.")
  }
  for (field in c("title_ru", "subtitle_ru", "bottom_line_ru", "framework_change_note_ru", "date_display_ru")) {
    if (field %in% names(issue)) check_ru(issue[[field]], paste0("issue.", field))
  }

  events <- issue$events
  if (!is.list(events) || length(events) == 0L) {
    add_error("issue.events must be a non-empty array.")
    events <- list()
  }

  event_fields <- c(
    "id", "event_key", "status", "category", "event_date", "first_seen_issue",
    "last_checked_issue", "actors", "location", "headline_en", "headline_ru",
    "map_label_en", "map_label_ru", "previous_state_en", "previous_state_ru",
    "what_changed_en", "what_changed_ru", "why_it_matters_en", "why_it_matters_ru",
    "deployment_evidence_en", "deployment_evidence_ru", "counter_evidence_en",
    "counter_evidence_ru", "watch_next_en", "watch_next_ru", "confidence",
    "filter_reason_en", "filter_reason_ru", "sources", "related_event_keys",
    "follow_up_status", "published_order"
  )
  nullable_text_fields <- c(
    "previous_state_en", "previous_state_ru", "what_changed_en", "what_changed_ru",
    "why_it_matters_en", "why_it_matters_ru", "deployment_evidence_en",
    "deployment_evidence_ru", "counter_evidence_en", "counter_evidence_ru",
    "watch_next_en", "watch_next_ru", "filter_reason_en", "filter_reason_ru"
  )
  status_values <- c("published", "filtered", "watchlist")
  follow_up_values <- c("none", "watch", "resolved", "superseded")
  location_fields <- c("type", "name", "name_en", "name_ru", "lat", "lon", "note_en", "note_ru")
  source_fields <- c("type", "publisher", "title", "url", "published_at")

  ids <- character()
  event_keys <- character()
  for (i in seq_along(events)) {
    event <- events[[i]]
    context <- sprintf("issue.events[%d]", i)
    if (!is.list(event)) {
      add_error("%s must be an object.", context)
      next
    }
    reject_unknown(event, event_fields, context)
    for (field in event_fields) require_key(event, field, context)
    for (field in c(
      "id", "event_key", "status", "category", "event_date", "first_seen_issue",
      "last_checked_issue", "headline_en", "headline_ru", "map_label_en", "map_label_ru",
      "follow_up_status"
    )) require_text(event, field, context)
    for (field in nullable_text_fields) optional_text(event, field, context)

    if (is_scalar_string(event$id)) ids <- c(ids, event$id)
    if (is_scalar_string(event$event_key)) event_keys <- c(event_keys, event$event_key)
    if (is_scalar_string(event$status) && !event$status %in% status_values) {
      add_error("%s.status '%s' is unknown; expected %s.", context, event$status, paste(status_values, collapse = ", "))
    }
    if (is_scalar_string(event$follow_up_status) && !event$follow_up_status %in% follow_up_values) {
      add_error("%s.follow_up_status '%s' is unknown; expected %s.", context, event$follow_up_status, paste(follow_up_values, collapse = ", "))
    }
    for (field in c("event_date", "first_seen_issue", "last_checked_issue")) {
      if (!is.null(event[[field]]) && !is_iso_date(event[[field]])) {
        add_error("%s.%s must be a valid YYYY-MM-DD date.", context, field)
      }
    }
    if (!is.null(event$actors) &&
        (!is.list(event$actors) || any(!vapply(event$actors, is_scalar_string, logical(1))))) {
      add_error("%s.actors must be an array of non-empty strings.", context)
    }
    if (!is.null(event$related_event_keys) &&
        (!is.list(event$related_event_keys) || any(!vapply(event$related_event_keys, is_scalar_string, logical(1))))) {
      add_error("%s.related_event_keys must be an array of non-empty strings.", context)
    }
    if (!is.null(event$confidence) &&
        (!is_scalar_string(event$confidence) || !event$confidence %in% c("low", "medium", "high"))) {
      add_error("%s.confidence must be null, low, medium, or high.", context)
    }

    if (identical(event$status, "published")) {
      for (field in c("headline_en", "headline_ru", "map_label_en", "map_label_ru")) {
        if (!is_scalar_string(event[[field]])) add_error("Published %s requires %s.", context, field)
      }
      order <- event$published_order
      if (is.null(order) || !is.numeric(order) || length(order) != 1L ||
          !is.finite(order) || order < 1 || order %% 1 != 0) {
        add_error("Published %s requires a positive integer published_order.", context)
      }
    } else if (!is.null(event$published_order)) {
      add_error("Non-published %s must use null for published_order.", context)
    }

    location <- event$location
    if (!is.list(location)) {
      add_error("%s.location must be an object.", context)
    } else {
      reject_unknown(location, location_fields, paste0(context, ".location"))
      for (field in c("type", "name")) require_text(location, field, paste0(context, ".location"))
      for (field in c("name_en", "name_ru", "note_en", "note_ru")) {
        if_present_text(location, field, paste0(context, ".location"))
      }
      if (is_scalar_string(location$type) && !location$type %in% c("point", "region")) {
        add_error("%s.location.type '%s' is unknown; expected point or region.", context, location$type)
      }
      if (identical(location$type, "point")) {
        for (field in c("lat", "lon")) require_key(location, field, paste0(context, ".location"))
        if (!is.numeric(location$lat) || length(location$lat) != 1L ||
            !is.finite(location$lat) || location$lat < -90 || location$lat > 90) {
          add_error("%s.location.lat must be a number from -90 to 90.", context)
        }
        if (!is.numeric(location$lon) || length(location$lon) != 1L ||
            !is.finite(location$lon) || location$lon < -180 || location$lon > 180) {
          add_error("%s.location.lon must be a number from -180 to 180.", context)
        }
      }
      if (identical(location$type, "region") &&
          ((!is.null(location$lat) && length(location$lat)) || (!is.null(location$lon) && length(location$lon)))) {
        add_error("%s region location must not claim point coordinates.", context)
      }
      if ("name_ru" %in% names(location)) check_ru(location$name_ru, paste0(context, ".location.name_ru"))
      if ("note_ru" %in% names(location)) check_ru(location$note_ru, paste0(context, ".location.note_ru"))
    }

    sources <- event$sources
    if (!is.list(sources) || length(sources) == 0L) {
      add_error("%s.sources must be a non-empty array.", context)
    } else {
      for (j in seq_along(sources)) {
        source <- sources[[j]]
        source_context <- sprintf("%s.sources[%d]", context, j)
        if (!is.list(source)) {
          add_error("%s must be an object.", source_context)
          next
        }
        reject_unknown(source, source_fields, source_context)
        for (field in source_fields) require_text(source, field, source_context)
        if (is_scalar_string(source$published_at) && !is_iso_date(source$published_at)) {
          add_error("%s.published_at must be a valid YYYY-MM-DD date.", source_context)
        }
        if (is_scalar_string(source$url) && !grepl("^https://", source$url)) {
          add_error("%s.url must be an HTTPS URL.", source_context)
        }
      }
    }

    for (field in grep("_ru$", event_fields, value = TRUE)) {
      if (field %in% names(event)) check_ru(event[[field]], paste0(context, ".", field))
    }
  }

  if (anyDuplicated(ids)) add_error("Event IDs must be unique within an issue.")
  if (anyDuplicated(event_keys)) add_error("event_key values must be unique within an issue.")

  published_orders <- vapply(events, function(event) {
    if (is.list(event) && identical(event$status, "published") && is.numeric(event$published_order)) {
      as.integer(event$published_order)
    } else {
      NA_integer_
    }
  }, integer(1))
  published_orders <- sort(published_orders[!is.na(published_orders)])
  if (length(published_orders) && !identical(published_orders, seq_along(published_orders))) {
    add_error("Published-event ordering must be unique and contiguous from 1.")
  }

  if (length(errors)) {
    stop(paste(c("Issue validation failed:", paste0("- ", unique(errors))), collapse = "\n"), call. = FALSE)
  }

  statuses <- vapply(events, `[[`, character(1), "status")
  location_types <- vapply(events, function(event) event$location$type, character(1))
  counts <- c(
    candidates = length(events),
    published = sum(statuses == "published"),
    filtered = sum(statuses == "filtered"),
    watchlist = sum(statuses == "watchlist"),
    points = sum(location_types == "point"),
    regions = sum(location_types == "region")
  )

  structure(list(issue = issue, events = events, counts = counts), class = "boring_report_issue")
}

print_validation_summary <- function(validated) {
  cat(sprintf("Valid issue: %s (schema %s)\n", validated$issue$issue_id, validated$issue$schema_version))
  cat(sprintf("Events: %d\n", validated$counts[["candidates"]]))
  cat(sprintf("Published: %d\n", validated$counts[["published"]]))
  cat(sprintf("Filtered: %d\n", validated$counts[["filtered"]]))
  cat(sprintf("Watchlist: %d\n", validated$counts[["watchlist"]]))
  cat(sprintf("Point locations: %d\n", validated$counts[["points"]]))
  cat(sprintf("Region locations: %d\n", validated$counts[["regions"]]))
}

if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) != 1L) {
    stop("Usage: Rscript scripts/validate_issue.R <issue.json>", call. = FALSE)
  }
  validated <- validate_issue(args[[1]])
  print_validation_summary(validated)
}
