# ==============================================================================
# Completeness Analysis of CTFB (Darwin Core Archive)
# Calculates per-species data completeness and aggregates by taxonomic level
# Adds responsible researcher from pesquisadores.xlsx
#
# Rules (regras.txt — Porcentômetro):
#   Filter  : taxonrank in ESPECIE, SUBESPECIE
#   Columns : 15 manual fields (Section 3)
#   Fill    : field is filled when != NA and != "" (Section 4)
#   Ecology : environment == "epicontinental" → exclude marinedomain (AO)
#             lifeform   == "herbivoro"       → exclude animalhostnames (AV)
#   Formula : completeness = filled / applicable_cols × 100 (Section 6)
# ==============================================================================

# --- Libraries ----------------------------------------------------------------
library(dplyr)
library(tidyr)
library(readxl)
library(ggplot2)
library(scales)
library(writexl)

# --- Configuration ------------------------------------------------------------
# output_dir <- "output" # This will be passed as an argument from Python
args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  stop("No arguments provided. Expected output_dir and optionally taxon_filter.")
}
output_dir <- args[1]
taxon_filter <- if (length(args) > 1) args[2] else NULL

# Create output directory if it doesn't exist
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)


# --- 15 manual columns evaluated by the Porcentômetro (regras.txt Section 3) --
MANUAL_COLS <- c(
  "bibliographicreference",   # AG
  "country",                  # AH
  "establishmentmeans",       # AJ
  "endemicbrazil",            # AK
  "environment",              # AL
  "locality",                 # AM
  "epicontinentaldomain",     # AN
  "marinedomain",             # AO
  "lifeform",                 # AP
  "habitat",                  # AQ
  "vernacularname",           # AR
  "vernacularnamelanguage",   # AS
  "vernacularnamelocality",   # AT
  "animalhostnames",          # AV
  "vegetalhostnames"          # AW
)

# --- Step 1: Read planilha_extendida.xlsx (regras.txt Section 8) --------------
# Assuming data files are in a 'data' directory relative to the script
data_dir <- file.path(dirname(sys.frame(1)$ofile), "data")
planilha_path <- file.path(data_dir, "planilha_extendida.xlsx")
pesquisadores_path <- file.path(data_dir, "pesquisadores.xlsx")

full_data <- read_xlsx(planilha_path, col_types = "text")

# --- Apply taxon filter if provided ---
if (!is.null(taxon_filter) && taxon_filter != "") {
  # This is a simplified filtering. A more robust solution would involve
  # checking all taxonomic hierarchy columns (phylum, class, order, family, genus)
  # and their subordinates. For now, it filters if the taxon_filter matches
  # any of the higher taxonomic ranks or the scientific name.
  full_data <- full_data %>%
    filter(
      tolower(phylum) == tolower(taxon_filter) |
      tolower(class) == tolower(taxon_filter) |
      tolower(order) == tolower(taxon_filter) |
      tolower(family) == tolower(taxon_filter) |
      tolower(genus) == tolower(taxon_filter) |
      tolower(scientificname) == tolower(taxon_filter)
    )
  if (nrow(full_data) == 0) {
    stop(paste("No data found for taxon filter:", taxon_filter))
  }
}


# --- Step 2: Read pesquisadores.xlsx ------------------------------------------
pesq_raw <- read_xlsx(pesquisadores_path, col_names = FALSE, col_types = "text")
colnames(pesq_raw) <- c("nome", "taxa_str", "instituicao")

# Parse researcher assignments: split taxa by ; and , to build lookup
pesq_lookup <- pesq_raw %>%
  filter(!is.na(taxa_str) & taxa_str != "") %>%
  mutate(taxa_list = strsplit(taxa_str, "[;,]")) %>%
  unnest(taxa_list) %>%
  mutate(taxa_list = trimws(taxa_list)) %>%
  filter(taxa_list != "") %>%
  group_by(taxon_name = taxa_list) %>%
  summarise(pesquisador = paste(unique(nome), collapse = "; "), .groups = "drop")

# --- Step 3: Filter for species-level records (regras.txt Section 1) ----------
species_data <- full_data %>%
  filter(taxonrank %in% c("ESPECIE", "SUBESPECIE"))

# --- Step 4: Calculate per-species completeness (regras.txt Sections 4–6) -----

# Helper: TRUE when a field is considered filled (regras.txt Section 4)
is_filled <- function(x) !is.na(x) & trimws(as.character(x)) != ""

# Verify which manual columns are present in the data
manual_present <- MANUAL_COLS[MANUAL_COLS %in% names(species_data)]
missing_cols   <- setdiff(MANUAL_COLS, names(species_data))
if (length(missing_cols) > 0)
  warning("Manual columns not found in data: ", paste(missing_cols, collapse = ", "))

# --- Per-row ecological adjustment (regras.txt Section 5) --------------------
# AL = environment: if "epicontinental" → remove AO (marinedomain) from denom
env_vec <- tolower(trimws(as.character(species_data$environment)))
env_vec[is.na(species_data$environment)] <- ""
remove_marine <- env_vec == "epicontinental"

# AP = lifeform: if "herbivoro" → remove AV (animalhostnames) from denom
lf_vec <- tolower(trimws(as.character(species_data$lifeform)))
lf_vec[is.na(species_data$lifeform)] <- ""
remove_animal <- lf_vec == "herbivoro"

# Build filled matrix: rows = species, cols = manual columns present
filled_matrix <- sapply(manual_present, function(col) is_filled(species_data[[col]]))
if (!is.matrix(filled_matrix))
  filled_matrix <- matrix(filled_matrix, nrow = nrow(species_data))

# Indices of conditionally excluded columns
marine_idx <- match("marinedomain",    manual_present)
animal_idx <- match("animalhostnames", manual_present)

# Sum filled fields; subtract excluded columns when they apply
filled_count <- rowSums(filled_matrix)
if (!is.na(marine_idx))
  filled_count <- filled_count -
    as.integer(remove_marine & filled_matrix[, marine_idx])
if (!is.na(animal_idx))
  filled_count <- filled_count -
    as.integer(remove_animal & filled_matrix[, animal_idx])

# Denominator: present manual columns minus ecological exclusions
denom_base       <- length(manual_present)
total_applicable <- denom_base - as.integer(remove_marine) - as.integer(remove_animal)

species_data$filled_count     <- filled_count
species_data$total_applicable <- total_applicable
species_data$completeness     <- (filled_count / total_applicable) * 100

# --- Step 5: Aggregate by taxonomic levels ------------------------------------

# Helper: get the most common non-empty value for a column within groups
most_common_val <- function(x) {
  x <- x[!is.na(x) & x != ""]
  if (length(x) == 0) return(NA_character_)
  names(sort(table(x), decreasing = TRUE))[1]
}

# Aggregate with full taxonomic hierarchy for sorting
by_family <- species_data %>%
  filter(!is.na(family) & family != "") %>%
  group_by(family) %>%
  summarise(
    phylum        = most_common_val(phylum),
    class         = most_common_val(class),
    order         = most_common_val(order),
    n_species     = n(),
    mean_complete = round(mean(completeness, na.rm = TRUE), 2),
    min_complete  = round(min(completeness, na.rm = TRUE), 2),
    max_complete  = round(max(completeness, na.rm = TRUE), 2),
    amplitude     = round(max(completeness, na.rm = TRUE) -
                            min(completeness, na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  arrange(phylum, class, order, family)

by_order <- species_data %>%
  filter(!is.na(order) & order != "") %>%
  group_by(order) %>%
  summarise(
    phylum        = most_common_val(phylum),
    class         = most_common_val(class),
    n_species     = n(),
    mean_complete = round(mean(completeness, na.rm = TRUE), 2),
    min_complete  = round(min(completeness, na.rm = TRUE), 2),
    max_complete  = round(max(completeness, na.rm = TRUE), 2),
    amplitude     = round(max(completeness, na.rm = TRUE) -
                            min(completeness, na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  arrange(phylum, class, order)

by_class <- species_data %>%
  filter(!is.na(class) & class != "") %>%
  group_by(class) %>%
  summarise(
    phylum        = most_common_val(phylum),
    n_species     = n(),
    mean_complete = round(mean(completeness, na.rm = TRUE), 2),
    min_complete  = round(min(completeness, na.rm = TRUE), 2),
    max_complete  = round(max(completeness, na.rm = TRUE), 2),
    amplitude     = round(max(completeness, na.rm = TRUE) -
                            min(completeness, na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  arrange(phylum, class)

by_subclass <- species_data %>%
  filter(!is.na(subclass) & subclass != "") %>%
  group_by(subclass) %>%
  summarise(
    phylum        = most_common_val(phylum),
    class         = most_common_val(class),
    n_species     = n(),
    mean_complete = round(mean(completeness, na.rm = TRUE), 2),
    min_complete  = round(min(completeness, na.rm = TRUE), 2),
    max_complete  = round(max(completeness, na.rm = TRUE), 2),
    amplitude     = round(max(completeness, na.rm = TRUE) -
                            min(completeness, na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  arrange(phylum, class, subclass)

by_phylum <- species_data %>%
  filter(!is.na(phylum) & phylum != "") %>%
  group_by(phylum) %>%
  summarise(
    n_species     = n(),
    mean_complete = round(mean(completeness, na.rm = TRUE), 2),
    min_complete  = round(min(completeness, na.rm = TRUE), 2),
    max_complete  = round(max(completeness, na.rm = TRUE), 2),
    amplitude     = round(max(completeness, na.rm = TRUE) -
                            min(completeness, na.rm = TRUE), 2),
    .groups = "drop"
  ) %>%
  arrange(phylum)

# --- Step 6: Add researcher names ---------------------------------------------

# Build a named vector for fast lookup
pesq_map <- setNames(pesq_lookup$pesquisador, pesq_lookup$taxon_name)

# Add researcher to family table (hierarchy columns already present)
by_family <- by_family %>%
  rowwise() %>%
  mutate(pesquisador = {
    res <- if (family %in% names(pesq_map)) pesq_map[[family]] else NA_character_
    if (is.na(res) && !is.na(order) && order %in% names(pesq_map))
      res <- paste0(pesq_map[[order]], " (via order)")
    if (is.na(res) && !is.na(class) && class %in% names(pesq_map))
      res <- paste0(pesq_map[[class]], " (via class)")
    if (is.na(res) && !is.na(phylum) && phylum %in% names(pesq_map))
      res <- paste0(pesq_map[[phylum]], " (via phylum)")
    res
  }) %>%
  ungroup()

# Add researcher to order table
by_order <- by_order %>%
  rowwise() %>%
  mutate(pesquisador = {
    res <- if (order %in% names(pesq_map)) pesq_map[[order]] else NA_character_
    if (is.na(res) && !is.na(class) && class %in% names(pesq_map))
      res <- paste0(pesq_map[[class]], " (via class)")
    if (is.na(res) && !is.na(phylum) && phylum %in% names(pesq_map))
      res <- paste0(pesq_map[[phylum]], " (via phylum)")
    res
  }) %>%
  ungroup()

# Add researcher to class table
by_class <- by_class %>%
  rowwise() %>%
  mutate(pesquisador = {
    res <- if (class %in% names(pesq_map)) pesq_map[[class]] else NA_character_
    if (is.na(res) && !is.na(phylum) && phylum %in% names(pesq_map))
      res <- paste0(pesq_map[[phylum]], " (via phylum)")
    res
  }) %>%
  ungroup()

# Add researcher to subclass table
by_subclass <- by_subclass %>%
  rowwise() %>%
  mutate(pesquisador = {
    res <- if (subclass %in% names(pesq_map)) pesq_map[[subclass]] else NA_character_
    if (is.na(res) && !is.na(class) && class %in% names(pesq_map))
      res <- paste0(pesq_map[[class]], " (via class)")
    if (is.na(res) && !is.na(phylum) && phylum %in% names(pesq_map))
      res <- paste0(pesq_map[[phylum]], " (via phylum)")
    res
  }) %>%
  ungroup()

# Add researcher to phylum table
by_phylum <- by_phylum %>%
  rowwise() %>%
  mutate(pesquisador = {
    if (phylum %in% names(pesq_map)) pesq_map[[phylum]] else NA_character_
  }) %>%
  ungroup()

# --- Step 7: Export CSV tables ------------------------------------------------

# Helper: put the row with the highest mean_complete at the top, then the rest
# sorted by taxonomy hierarchy. Add a marker column "***" for the top row.
top_first <- function(df, ...) {
  sort_cols <- enquos(...)
  max_row <- df %>% slice_max(mean_complete, n = 1, with_ties = FALSE) %>%
    mutate(max_flag = "<<< MAX")
  rest <- df %>% filter(mean_complete != max(mean_complete, na.rm = TRUE) |
                         row_number() != which.max(mean_complete)) %>%
    arrange(!!!sort_cols) %>%
    mutate(max_flag = "")
  bind_rows(max_row, rest)
}

# Reorder columns: higher categories first, then stats, then researcher, then max_flag
write.csv(top_first(by_phylum, phylum) %>%
            select(phylum, n_species, mean_complete,
                   min_complete, max_complete, amplitude, pesquisador, max_flag),
          file.path(output_dir, "completeness_by_phylum.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

write.csv(top_first(by_class, phylum, class) %>%
            select(phylum, class, n_species, mean_complete,
                   min_complete, max_complete, amplitude, pesquisador, max_flag),
          file.path(output_dir, "completeness_by_class.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

write.csv(top_first(by_subclass, phylum, class, subclass) %>%
            select(phylum, class, subclass, n_species, mean_complete,
                   min_complete, max_complete, amplitude, pesquisador, max_flag),
          file.path(output_dir, "completeness_by_subclass.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

write.csv(top_first(by_order, phylum, class, order) %>%
            select(phylum, class, order, n_species, mean_complete,
                   min_complete, max_complete, amplitude, pesquisador, max_flag),
          file.path(output_dir, "completeness_by_order.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

write.csv(top_first(by_family, phylum, class, order, family) %>%
            select(phylum, class, order, family, n_species, mean_complete,
                   min_complete, max_complete, amplitude,
                   pesquisador, max_flag),
          file.path(output_dir, "completeness_by_family.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# Per-species completeness sorted by hierarchy, with researcher lookup (vectorized)
species_export <- species_data %>%
  select(taxonid, scientificname, phylum, class, subclass, order, family,
         taxonrank, completeness, filled_count, total_applicable)

# Vectorized researcher lookup with hierarchical fallback
species_export <- species_export %>%
  mutate(
    pesq_family   = pesq_map[family],
    pesq_order    = pesq_map[order],
    pesq_class    = pesq_map[class],
    pesq_subclass = pesq_map[subclass],
    pesq_phylum   = pesq_map[phylum],
    pesquisador = case_when(
      !is.na(pesq_family)   ~ pesq_family,
      !is.na(pesq_order)    ~ paste0(pesq_order, " (via order)"),
      !is.na(pesq_subclass) ~ paste0(pesq_subclass, " (via subclass)"),
      !is.na(pesq_class)    ~ paste0(pesq_class, " (via class)"),
      !is.na(pesq_phylum)   ~ paste0(pesq_phylum, " (via phylum)"),
      TRUE ~ NA_character_
    )
  ) %>%
  select(-pesq_family, -pesq_order, -pesq_class, -pesq_subclass, -pesq_phylum) %>%
  arrange(phylum, class, subclass, order, family, scientificname)

write.csv(species_export, file.path(output_dir, "completeness_per_species.csv"),
          row.names = FALSE, fileEncoding = "UTF-8")

# --- Step 8: Generate PDF graphics --------------------------------------------

# Reusable plot function
# sort_cols: character vector of columns for taxonomic ordering (e.g. c("class","order","family"))
plot_completeness <- function(data, group_col, title_label,
                              sort_cols = NULL, top_n = NULL) {

  plot_data <- data
  subtitle_note <- "All groups"

  if (!is.null(top_n) && nrow(data) > top_n) {
    plot_data <- data %>% slice_max(order_by = n_species, n = top_n, with_ties = FALSE)
    subtitle_note <- paste("Top", top_n, "by species count")
  }

  # Flag the row with the highest mean_complete
  plot_data <- plot_data %>%
    mutate(is_max = mean_complete == max(mean_complete, na.rm = TRUE))

  # Build taxonomic ordering: sort by hierarchy columns, create composite labels
  # that show parent taxa, and set factor levels to preserve order in ggplot
  if (!is.null(sort_cols) && length(sort_cols) > 0) {
    plot_data <- plot_data %>% arrange(across(all_of(sort_cols)))
    # Build composite label: "ParentA > ParentB > Name" for hierarchy context
    parent_cols <- setdiff(sort_cols, group_col)
    if (length(parent_cols) > 0) {
      prefix <- plot_data %>%
        select(all_of(parent_cols)) %>%
        mutate(across(everything(), ~ replace_na(.x, ""))) %>%
        unite("prefix", everything(), sep = " > ") %>%
        pull(prefix)
      plot_data$plot_label <- paste0(prefix, " > ", plot_data[[group_col]])
    } else {
      plot_data$plot_label <- plot_data[[group_col]]
    }
    plot_data$plot_label <- factor(plot_data$plot_label,
                                   levels = rev(plot_data$plot_label))
  } else {
    # Fallback: sort by mean_complete
    plot_data <- plot_data %>% arrange(mean_complete)
    plot_data$plot_label <- factor(plot_data[[group_col]],
                                   levels = plot_data[[group_col]])
  }

  p <- ggplot(plot_data, aes(x = plot_label,
                             y = mean_complete,
                             fill = is_max)) +
    geom_col(alpha = 0.8, width = 0.7) +
    scale_fill_manual(values = c("FALSE" = "steelblue", "TRUE" = "firebrick"),
                      guide = "none") +
    geom_errorbar(aes(ymin = min_complete, ymax = max_complete),
                  width = 0.3, color = "gray30", linewidth = 0.4) +
    geom_text(aes(label = sprintf("%.1f%%", mean_complete)),
              hjust = -0.1, vjust = -0.6, size = 2.2, color = "gray20") +
    coord_flip() +
    labs(
      title = paste("Data Completeness by", title_label),
      subtitle = paste("Mean (bar) with amplitude min-max (error bars) |", subtitle_note),
      x = title_label,
      y = "Completeness (%)"
    ) +
    scale_y_continuous(limits = c(0, 120), breaks = seq(0, 100, 20)) +
    theme_minimal(base_size = 10) +
    theme(
      axis.text.y  = element_text(size = 7),
      plot.title    = element_text(face = "bold", size = 12),
      plot.subtitle = element_text(size = 9, color = "gray40"),
      panel.grid.major.y = element_blank()
    )

  return(p)
}

# --- Overall phylum chart (alphabetical) ---
p_phylum <- plot_completeness(by_phylum, "phylum", "Phylum",
                              sort_cols = c("phylum"))
ggsave(file.path(output_dir, "completeness_by_phylum.pdf"), p_phylum,
       width = 10, height = 8)

# --- One PDF per phylum for class, order, and family -------------------------
# Create output subdirectories
dir.create(file.path(output_dir, "pdf_by_class"),    showWarnings = FALSE)
dir.create(file.path(output_dir, "pdf_by_subclass"), showWarnings = FALSE)
dir.create(file.path(output_dir, "pdf_by_order"),    showWarnings = FALSE)
dir.create(file.path(output_dir, "pdf_by_family"),   showWarnings = FALSE)

# Sanitize phylum name for use as filename
safe_name <- function(x) gsub("[^A-Za-z0-9_-]", "_", x)

phyla <- sort(unique(by_family$phylum[!is.na(by_family$phylum)]))

for (phy in phyla) {
  phy_safe <- safe_name(phy)

  # --- Class chart for this phylum ---
  sub_class <- by_class %>% filter(phylum == phy)
  if (nrow(sub_class) > 0) {
    h <- max(4, nrow(sub_class) * 0.5 + 1.5)
    p <- plot_completeness(sub_class, "class",
                           paste("Class -", phy),
                           sort_cols = c("class"))
    ggsave(file.path(output_dir, "pdf_by_class",
                     paste0("class_", phy_safe, ".pdf")),
           p, width = 10, height = h, limitsize = FALSE)
  }

  # --- Subclass chart for this phylum ---
  sub_subclass <- by_subclass %>% filter(phylum == phy)
  if (nrow(sub_subclass) > 0) {
    h <- max(4, nrow(sub_subclass) * 0.35 + 1.5)
    p <- plot_completeness(sub_subclass, "subclass",
                           paste("Subclass -", phy),
                           sort_cols = c("class", "subclass"))
    ggsave(file.path(output_dir, "pdf_by_subclass",
                     paste0("subclass_", phy_safe, ".pdf")),
           p, width = 10, height = h, limitsize = FALSE)
  }

  # --- Order chart for this phylum ---
  sub_order <- by_order %>% filter(phylum == phy)
  if (nrow(sub_order) > 0) {
    h <- max(4, nrow(sub_order) * 0.35 + 1.5)
    p <- plot_completeness(sub_order, "order",
                           paste("Order -", phy),
                           sort_cols = c("class", "order"))
    ggsave(file.path(output_dir, "pdf_by_order",
                     paste0("order_", phy_safe, ".pdf")),
           p, width = 10, height = h, limitsize = FALSE)
  }

  # --- Family chart for this phylum ---
  sub_family <- by_family %>% filter(phylum == phy)
  if (nrow(sub_family) > 0) {
    h <- max(4, nrow(sub_family) * 0.25 + 1.5)
    p <- plot_completeness(sub_family, "family",
                           paste("Family -", phy),
                           sort_cols = c("class", "order", "family"))
    ggsave(file.path(output_dir, "pdf_by_family",
                     paste0("family_", phy_safe, ".pdf")),
           p, width = 10, height = h, limitsize = FALSE)
  }

}