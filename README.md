# smart-street-lighting

AI-powered street lighting design library for Melbourne. Proposes
streetlight placements for parks, pathways, and streets by combining
real urban activity data, Australian lighting standards (AS/NZS 1158),
and a local LLM with Retrieval-Augmented Generation.

Capstone library for **Deakin University SIT764 — Project 2: Smart
Street Lighting Design System** (Melbourne Open Playground / Chameleon
initiative).

## What it does

Given a query like *"Design lighting for a 200 m pathway in Fitzroy
Gardens with moderate evening traffic"*, the library returns:

- An AS/NZS 1158 P-category recommendation (with the reasoning that
  led to it)
- Number of luminaires, spacing, pole height, lumen output, CCT
- Annual energy cost and CO₂, with LED-vs-HPS comparison and payback
- A CPTED-informed safety adjustment based on the area's crime
  statistics
- An adaptive dimming schedule built from the area's pedestrian
  temporal profile

The deterministic calculation engine produces every number; the LLM
explains and justifies — it never computes.

## How it maps to the SIT764 brief

| Brief objective | Implementation |
|---|---|
| Propose lighting layouts | `smart_street_lighting.llm.calculation_engine.design_lighting` |
| Use urban data (pedestrian activity, location maps) | `smart_street_lighting.data.load_melbourne_data`, `smart_street_lighting.data.spatial_analysis`, `smart_street_lighting.data.osm_loader` |
| Estimate energy + cost | `calculation_engine` produces kWh/yr, $/yr, LCC, payback |
| Provide explanations | `smart_street_lighting.rag` retrieves AS/NZS 1158 + CPTED context; LLM produces the justified report |
| D/HD — RAG over lighting standards | ChromaDB + nomic embeddings + LlamaIndex over 17 curated knowledge-base docs |
| D/HD — LLM reasoning for spatial design | LM Studio backend, intent classification, validated numeric output |

**Datasets used** (matches the brief): OpenStreetMap (Overpass +
Nominatim), Melbourne Open Data (pedestrian counts + streetlights),
Victoria crime statistics. ABS population density is on the roadmap.

## Install

```bash
pip install git+https://github.com/hashem59/smart-street-lighting-lib.git
```

Pinned:

```bash
pip install git+https://github.com/hashem59/smart-street-lighting-lib.git@v0.1.0
```

## Quick use

```python
from smart_street_lighting.llm.calculation_engine import design_lighting

design = design_lighting(
    location="Fitzroy Gardens",
    pathway_length_m=200,
    pedestrian_traffic="medium",
)
print(design)
```

## Package layout

```
smart_street_lighting/
├── core/   config, logging, optional PostgreSQL chat persistence
├── data/   Melbourne Open Data + OSM loaders, geometry helpers,
│           crime CSV loader + LGA lookups (the I/O layer)
├── llm/    deterministic AS/NZS 1158 calculation engine
└── rag/    ChromaDB ingestion + retrieval, LM Studio client
```

## v0.2.0 reshape — algorithms vs plumbing

As of v0.2.0, the plugin holds **plumbing**: data acquisition, RAG
infrastructure, the AS/NZS 1158 calculation engine, and geometric
helpers. The **algorithmic / data-science content** —
spatial k-NN matching, temporal dimming schedule, safety risk
scoring, intent classification, output validation, end-to-end
orchestration — moved out of the plugin and into the capstone
submission notebook, where it can be read directly by markers.

Use the plugin for the heavy lifting (data fetch, OSM resolve,
calculation engine, RAG retrieval); read the notebook for the
analysis methodology.

## Knowledge base

The 17 RAG knowledge-base markdown files (AS/NZS 1158 P/V categories,
CPTED, Melbourne lighting strategy, adaptive dimming, solar lighting,
energy benchmarks, etc.) are **not bundled in the wheel**. They ship as
a release asset so they can be re-versioned independently of the code:

```python
import urllib.request
urllib.request.urlretrieve(
    "https://github.com/hashem59/smart-street-lighting-lib/releases/download/v0.1.0/knowledge_base.zip",
    "knowledge_base.zip",
)
```

The companion notebook (`UC01_Smart_Street_Lighting_RAG_cloud.ipynb` in
the playground repo) does this automatically on first run.

## Environment

Requires LM Studio running locally with:

- LLM model loaded (e.g. `qwen2.5-7b-instruct`)
- Embedding model: `text-embedding-nomic-embed-text-v1.5`
- Endpoint: `http://localhost:1234/v1` (overridable via `.env`)

For environments without LM Studio (e.g. cloud notebooks), the
deterministic calculation engine still runs — only RAG and LLM
explanation cells need the local backend.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

146 tests covering the calculation engine, validators, intent
classification, OSM loading, safety scoring, data loading, and the
end-to-end design pipeline.

## License

MIT
