# Sample data

Everything in this folder is **synthetic demo content** for the LOOPMESH hackathon
build. None of it describes a real organisation, contract, delivery or
environmental outcome.

## `materials.csv`

A four-row example of the CSV contract accepted by
`POST /api/v1/materials/import`.

- Organisation slugs match the demo dataset created by
  `python -m app.scripts.seed_demo`, so the file imports cleanly after seeding.
- Reference codes (`LM-9001` … `LM-9004`) are intentionally outside the seeded
  range so they never collide.
- Required columns: `organization_slug`, `reference_code`, `name`, `category`,
  `unit`, `quantity_available`.
- Optional columns: `condition`, `hazard_class`, `description`,
  `handling_requirements`, `origin_process`, `availability_start`,
  `availability_end`, `purity_pct`, `moisture_pct`, `contamination_pct`,
  `ph_value`, `particle_size_mm`, `calorific_value_mj_kg`, `assay_method`.
- Dates use ISO `YYYY-MM-DD`. Units are `kg`, `tonne`, `m3`, `litre`, `mwh`.
  Categories are `metals`, `polymers`, `minerals`, `organics`, `chemicals`,
  `glass`, `paper`, `textiles`, `water`, `energy`, `other`.

Rows imported through the API are stored as user-supplied data
(`data_source=csv`, `is_demo=false`). They are not marked demo simply because
the file came from this folder — the provenance flag describes how the data
entered the system, while the UI banner describes the seeded dataset.

## What is deliberately absent

No image datasets, no camera captures and no computer-vision annotations exist
anywhere in this project. Material characteristics must arrive as structured
fields.
