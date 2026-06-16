# YAML Schema Migration Guide: v2.0 -> v0.1

Status: archived guidance.

The migration from v2.0 to v0.1 has been completed for active datasets.
This file remains as a pointer so existing links do not break.

For the full historical migration document, see:

- [legacy/SCHEMA_MIGRATION_GUIDE_v2_to_v0p1.md](../legacy/SCHEMA_MIGRATION_GUIDE_v2_to_v0p1.md)

For active authoring and execution guidance, use:

- [config/README.md](README.md)
- [config/README_V0P1_SCHEMA.md](README_V0P1_SCHEMA.md)
- [config/YAML_V0P1_EXECUTION_GUIDE.md](YAML_V0P1_EXECUTION_GUIDE.md)
cp logs/migration_test/generated_configs/your-dataset.yaml config/datasets/your-dataset.yaml
git add config/datasets/your-dataset.yaml tools/scrape_config_builder/helper_input/your-dataset.json
git commit -m "chore: migrate your-dataset to v0.1 schema with multi-page discovery"
```

---

## Real Example: DQMI Migration

### v2.0 Config (Before)

**helper_input/data-quality-maturity-index.json** (v2.0):
```json
{
  "schema_version": "2.0",
  "dataset_id": "data-quality-maturity-index",
  "entry_url": "https://digital.nhs.uk/.../data-quality",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "samples": [
        {"file_url": "https://.../dqmi_99_csv-v2-did.csv"}
      ],
      "sample_subpage_url": "https://digital.nhs.uk/.../data-quality/archive",
      "include_extensions": ["csv"]
    }
  ]
}
```

**config/datasets/data-quality-maturity-index.yaml** (v2.0):
```yaml
targets:
  - sub_dataset_id: with-did
    scrape_steps:
      - link_selector: a[href$='.csv'][href*='did']
        text_filter: DQMI.*CSV.*DID
        file_extensions: [csv]
```

**Discovery Result**: ~3 files (entry page only; archive page ignored without sample there)

### v0.1 Config (After)

**helper_input/data-quality-maturity-index.json** (v0.1):
```json
{
  "schema_version": "0.1",
  "dataset_id": "data-quality-maturity-index",
  "entry_url": "https://digital.nhs.uk/.../data-quality",
  "targets": [
    {
      "sub_dataset_id": "with-did",
      "archive_pattern_hint": "general_archive_subpage",
      "sample_pages": [
        {
          "page_url": "https://digital.nhs.uk/.../data-quality",
          "page_role": "default",
          "partitioning_strategy": "none",
          "samples": [
            {"file_url": "https://.../dqmi_99_csv-v2-did.csv", "notes": "Current month"}
          ]
        },
        {
          "page_url": "https://digital.nhs.uk/.../data-quality/archive",
          "page_role": "archive",
          "partitioning_strategy": "subject_period",
          "samples": [
            {"file_url": "https://.../dqmi_98_csv-v2-did.csv", "notes": "Previous month"},
            {"file_url": "https://.../dqmi_97_csv-v2-did.csv", "notes": "Two months back"}
          ]
        }
      ],
      "include_extensions": ["csv"],
      "preferred_link_selector": "a[href*='did']",
      "preferred_text_filter": "DQMI.*CSV.*DID"
    }
  ]
}
```

**config/datasets/data-quality-maturity-index.yaml** (v0.1):
```yaml
targets:
  - sub_dataset_id: with-did
    source_pages:
      - page_url: https://digital.nhs.uk/.../data-quality
        page_role: default
        partitioning_strategy: none
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: false
      - page_url: https://digital.nhs.uk/.../data-quality/archive
        page_role: archive
        partitioning_strategy: subject_period
        scrape_steps:
          - link_selector: a[href*='did']
            text_filter: DQMI.*CSV.*DID
            file_extensions: [csv]
        sibling_discovery:
          enabled: true
          link_selector: a[href]
          url_pattern: (jan|feb|...|dec)[-_]?(2024|2025|2026)
          text_pattern: (FY|Q|Month)\s*(2024|2025|2026)
          max_pages: 25
```

**Discovery Result**: **19 files** (entry page + archive page with automatic month-year sibling pages)
- **Improvement**: 19 vs 3 = **633% increase**

---

## Troubleshooting

### Generated YAML has `sibling_discovery.enabled: false` when I need it enabled

**Cause**: Helper didn't recognize the archive pattern from samples provided.

**Fix**:
1. Verify `archive_pattern_hint` is set to non-`none` value
2. Add more diverse sample files (multiple months, different years)
3. Manually edit generated YAML to set `sibling_discovery.enabled: true` and adjust patterns

### File counts decreased after upgrade

**Cause**: Likely CSS selector or text filter is too restrictive on new page contexts.

**Fix**:
1. Check `matches_found.csv` for errors
2. Verify `preferred_link_selector` works on both entry and archive pages
3. Test selector manually on live pages using browser DevTools
4. Update `preferred_link_selector` or `preferred_text_filter` in JSON helper input
5. Re-run helper

### Sibling discovery finds too many false-positive pages

**Cause**: `url_pattern` or `text_pattern` is too loose.

**Fix**:
1. Review `matches_found.csv` for unexpected URLs
2. Tighten regex patterns manually in YAML
3. Reduce `max_pages` limit to avoid traversing unrelated pages

---

## Rollback to v2.0 (If Needed)

If v0.1 migration encounters blockers, revert to v2.0:

```bash
# Revert JSON helper input
git checkout HEAD -- tools/scrape_config_builder/helper_input/your-dataset.json

# Revert YAML config
git checkout HEAD -- config/datasets/your-dataset.yaml
```

---

## Additional Resources

- **Scrape Config Builder README**: [tools/scrape_config_builder/README.md](../tools/scrape_config_builder/README.md)
- **Helper Input Schema Docs**: Section "V0.1 Schema Details" in README
- **Function App YAML Interpreter**: [function_app/src/scraper.py](../function_app/src/scraper.py#L200) (search for `source_pages` array processing)

---

**Last Updated**: May 2026  
**Status**: v0.1 recommended for new datasets and archive-capable datasets; v2.0 still supported for backward compatibility
