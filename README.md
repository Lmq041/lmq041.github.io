# Ming-Qiang Liang's academic homepage

The existing static website is preserved. A verified publication database generates the publication cards and complete searchable CV.

- [Audit and migration decisions](docs/AUDIT.md)
- [Operation, first activation and recovery](docs/MAINTENANCE.md)
- [Validation and remaining acceptance checks](docs/VALIDATION.md)
- [Publication database](data/publications.json)
- [Review queue](data/pending-publications.json), excluded from Pages artifacts

Production automation is **off until the author confirms the PR and sets `PUBLICATIONS_AUTOMATION_ENABLED=true`**. Original CV, paper and image assets are retained.

## Local use

CI uses Python 3.12 and Node.js 24. Dependencies and third-party Actions are pinned.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --test monitor/worker.test.mjs
python scripts/sync_publications.py
python scripts/build.py --stage _site
```

No ResearchGate scraping is performed. A paper found only on ResearchGate may not be discovered. New publications require identifier-based author evidence and official Crossref journal metadata. Missing/conflicting evidence enters the review queue and does not become a new public entry.
