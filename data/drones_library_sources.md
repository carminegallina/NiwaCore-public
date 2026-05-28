# NIWA Drone Library Source Policy

This file documents how `drones_library.json` should be maintained.

## Required fields

Every library drone should include:

- `id`
- `brand`
- `model`
- `name`
- `category`
- `max_wind_ms`
- `max_wind_kmh`
- `source`
- `source_quality`
- `source_url`
- `uncertainty`
- `notes`

`max_wind_ms` is the safety-critical value. `max_wind_kmh` should match it as closely as possible, rounded to one decimal unless the source publishes only km/h.

## Source quality values

- `official_spec`: official manufacturer specification with a numeric wind value.
- `official_range`: official manufacturer range; NIWA stores the upper published value unless notes say otherwise.
- `official_scale_derived`: official manufacturer Beaufort/level/category wording without numeric m/s; NIWA stores a conservative numeric mapping and marks uncertainty as `medium`.
- `official_support_faq`: official support article or FAQ rather than a formal spec sheet.
- `official_product_sheet`: official PDF/product sheet.
- `official_brochure`: official brochure.
- `official_manual`: official DJI/manufacturer user manual, quick start guide, or flight manual.
- `manufacturer_partner_spec`: manufacturer-related partner specification or OEM-facing product sheet, used only when the value aligns with manufacturer documentation.
- `reliable_retailer_spec`: structured product specification from a reputable retailer or distributor, used only when official manufacturer pages are missing or incomplete.
- `operational_guidance`: manufacturer guidance for safe operation, not a formal max wind resistance claim.
- `operational_setting`: manual/configuration value that is useful operationally, not a full wind resistance claim.

## Uncertainty policy

- `low`: numeric value is directly stated in an official source.
- `medium`: value comes from an official range, official Beaufort/level wording, payload caveat, reliable non-official specification, or operational guidance.
- Avoid `high` in the active library. If a value would be high uncertainty, leave the model out until a better source is found.

## Expansion rules

Prefer smaller verified batches over huge unreliable dumps.

Do not add a drone only because the model exists. Add it when a reliable wind value exists, because the Drone Panel uses this value in the safety indicator.

If a manufacturer publishes different values for takeoff/landing, cruise, gusts, or payload/no-payload, keep the most useful conservative value for NIWA in `max_wind_ms` and explain the source nuance in `notes`.
