# DJI Library Coverage Notes

The active DJI entries in `drones_library.json` include DJI drones where NIWA has a usable wind value from an official DJI page, official DJI manual, DJI safety guideline, clearly documented DJI aircraft-family specification, or a reputable structured retailer/dealer specification marked as non-official.

Because `max_wind_ms` drives the Drone Panel safety indicator, DJI values are always marked with `source_quality`, `source_url`, `uncertainty` and explanatory `notes`.

## DJI models moved into the active library in recent passes

- DJI Spark
- DJI Mavic Pro
- DJI Mavic Pro Platinum
- DJI Mini 5 Pro
- DJI Mavic 4 Pro
- DJI Phantom 1, Phantom FC40, Phantom 2, Phantom 2 Vision and Phantom 2 Vision+
- DJI Phantom 3 Standard, Advanced, Professional, 4K and SE
- DJI Phantom 4 RTK
- DJI P4 Multispectral
- DJI Agras MG-1, MG-1S and MG-1S RTK
- DJI Agras T25P, T60, T70, T70P and T100
- DJI Wind 1, Wind 2, Wind 4 and Wind 8

## Remaining DJI caveats

- The Wind series is active, but marked with medium uncertainty where values come from dealer pages or mirrored manuals rather than a DJI-hosted product page.
- Phantom 1/2/FC40 values are active, but mapped from DJI manual wording such as `moderate breeze` or `category 4`, not from a modern `Max Wind Speed Resistance` spec field.
- Mini 5 Pro and Mavic 4 Pro are active, but marked with `reliable_retailer_spec` until a DJI-hosted spec page with the same wind value is verified.
- Retail bundles, controller bundles and plus packages are not separate active records unless the aircraft wind limit differs. Examples: Phantom 4 Pro+, Phantom 4 Advanced+, Mavic 4 Pro Creator Combo and similar kits should reuse the base aircraft entry.

## Rule

Do not add or change a DJI wind value unless a reliable source gives a numeric wind value, a Beaufort/category value that can be conservatively mapped, or a conservative operational value that can be clearly documented in `notes`.
