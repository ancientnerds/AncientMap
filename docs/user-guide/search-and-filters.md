# Searching and filtering sites

[← Guide contents](README.md)

Search finds named records. Filters control which records are displayed. They can be used independently or combined.

## Search by site name

1. Open the **Search** tab.
2. Enter a site name in **Search sites…**.
3. Select a result to locate it on the globe.
4. Click the result or marker to open the site record.

Search results are limited to 100 displayed entries. Refine a broad query when necessary.

The crossed-arrows button beside the search field selects a random site.

### Search options

| Option | Meaning |
| --- | --- |
| **All sources** | Searches across available sources rather than only the normal working selection |
| **Apply filters** | Restricts name-search results using the active age, country, category, and source filters |
| **Within proximity** | Restricts results to the circle created in the **Proximity** tab |
| **Within empires** | Restricts results to visible empire boundaries and the appropriate historical period |

**Within proximity** remains unavailable until a proximity centre is set. **Within empires** remains unavailable until at least one empire overlay is visible.

Coordinates can also be pasted into the main search box. Press **Enter** to create a 10 km proximity search around valid coordinates.

## Apply filters

The **Filter By** panel has four modes. Selecting a mode changes both the available controls and the colour legend used for site dots.

### Age

Move the two handles to set the earliest and latest dates. Dates are displayed as BC or AD. The map includes records whose dating intersects the chosen interval.

Dating in aggregated datasets is often approximate. A record may have a broad period, an estimated start date, or incomplete chronology. Treat the age filter as a discovery tool rather than proof of exact contemporaneity.

### Country

- Select a flag or country badge to show only that country when all countries are active.
- Select additional countries to build a multi-country set.
- Select the only active country again to restore all countries.
- Use **All**, **None**, or **Invert** for bulk selection.
- Use the text field to find a country in a long list.
- Switch between flag and named-badge views with the display button.

Modern country fields describe present-day location; they do not imply ancient political identity.

### Category

Categories are grouped into related site types and colour-coded.

- Select one category to isolate it.
- Select additional categories to combine them.
- Select the only active category again to restore all categories.
- Use **All**, **None**, or **Invert** for bulk selection.
- Use the category text field to narrow the control list.

Category names originate in multiple datasets and may not use identical archaeological typologies.

### Source

The source filter controls which contributing datasets take part in the working map.

- The primary **Ancient Nerds** source is initially available.
- Other sources may show a download/load icon before their records are in memory.
- Selecting such a source starts loading it.
- **Load all** requests the remaining sources; this can use substantial memory and bandwidth.
- A number beside a loaded source is its available record count.
- In offline mode, uncached sources are unavailable.

Use the source filter when comparing coverage, checking provenance, or avoiding duplicate records from overlapping catalogues.

## Active-filter indicators and reset

A dot on a filter-mode button indicates that its setting differs from the default. The indicator beside **Filter By** means at least one filter is active.

Use the reset button in the filter header to restore default age, category, country, and source settings. Clearing a name search does not necessarily reset these filters.

## Recommended research workflows

### Regional survey

1. Select one or more countries.
2. Narrow the age range.
3. Select relevant categories.
4. Compare the result with different sources enabled.

### Cross-source verification

1. Search for a site by name with **All sources** enabled.
2. Open likely matching records.
3. Use the source switcher in the site record when alternate records are detected.
4. Compare coordinates, descriptions, chronology, and original source links.

### Historical-boundary query

1. Enable one or more empire borders.
2. Choose a year or use the global **By Period** timeline.
3. Return to **Search** and enable **Within empires**.
4. Apply age and category filters if required.

