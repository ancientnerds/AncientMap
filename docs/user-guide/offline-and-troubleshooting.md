# Offline use and troubleshooting

[← Guide contents](README.md)

## Prepare offline data

Open **Online Mode** in the upper-right settings panel to launch the **Offline Data Manager**.

The manager can download selected content to browser storage, including:

- site records by source;
- selected map or vector data;
- historical empire boundaries;
- optionally available images or supporting content.

Download while a reliable connection is available. Browser storage limits vary by device, browser, and free disk space. Keep the browser open until the manager reports completion.

After preparation, select **Go Offline** to test the field configuration before leaving your connection.

## Offline limitations

- Uncached sources and layers cannot be enabled.
- Satellite tiles may be unavailable outside the cached area.
- Historical maps, 3D models, artifact searches, papers, books, live webcams, and other connected research normally require internet access.
- The **Connectors** status can show reduced availability.
- Clearing site data, cookies, or browser storage can remove downloaded content.
- Private browsing is unsuitable for durable offline storage.

## Troubleshooting

### The expected sites are missing

1. Check the **Showing _n_ of _total_ sites** line.
2. Reset active filters.
3. Clear **Within proximity** and **Within empires**.
4. Open **Source** and confirm the required dataset is selected and loaded.
5. Broaden the age range.
6. Try **All sources** in the name search.

### A source shows a load icon

The source is known but its records are not yet loaded. Select it to load the records, or use the bulk load control. Large sources can take time and increase browser memory use.

### A layer cannot be selected

It may be:

- still loading;
- unavailable in the current detailed base-map mode;
- absent from the offline cache;
- dependent on another layer, as with feature labels.

Return online, disable the incompatible base map, or add the layer through the Offline Data Manager.

### The globe is slow or jerky

- Reduce **Dot Size**.
- Disable unused vector and historical layers.
- Avoid loading every source simultaneously.
- Close expanded site galleries.
- Leave fullscreen or reduce the browser window size.
- Check the FPS indicator and hardware warning.
- Update the browser and enable hardware acceleration/WebGL.

### Search returns too many or too few records

- Toggle **Apply filters** and compare the result.
- Check **All sources**.
- Clear proximity and empire restrictions.
- Search a shorter distinctive name or an alternate spelling.
- Remember that only the first 100 matching results are displayed.

### Location is inaccurate

**My location** may fall back to approximate network location. Enter verified coordinates or use **Set on globe**. Check hemisphere letters before submitting.

### The site record has little content

Coverage differs by source. Use the alternate-source selector, original source link, **References**, and connected media tabs. An empty tab can mean no verified result was returned, not that no external research exists.

## Report a problem

For reproducible bug reports, include:

- page URL and access date;
- browser and operating system;
- screenshot or short screen recording;
- active filters, sources, and layers;
- online/offline state;
- site record link or coordinates;
- exact steps and expected result.

Use the project’s [GitHub issue tracker](https://github.com/ancientnerds/AncientMap/issues) for software defects.

