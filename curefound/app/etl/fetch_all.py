"""
Phase 1 download orchestrator.

Downloads raw data files for all enabled ingest sources into `data/raw/`.
Supports per-source enable/disable (from Settings), resume (skip files that
are already present and size-match), and a `--dry-run` mode that prints
what would be downloaded without touching the filesystem.

Usage
-----
    python -m app.etl.fetch_all                  # all enabled sources
    python -m app.etl.fetch_all --source hpo     # single source
    python -m app.etl.fetch_all --dry-run        # list files only
    python -m app.etl.fetch_all --force          # re-download even if present
    python -m app.etl.fetch_all --source primekg --force

Environment variables (from .env / Settings):
    INGEST_PRIMEKG=1, INGEST_DRUGCENTRAL=1, INGEST_HPO=1,
    INGEST_ORPHANET=1, INGEST_REACTOME=1
    DATAVERSE_API_TOKEN=<token>   # optional; speeds up Harvard Dataverse
    DRUGCENTRAL_FORMAT=csv        # 'csv' or 'pg_dump' (default csv)
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

_log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Download manifest
# ---------------------------------------------------------------------------


@dataclass
class SourceFile:
    """One file to download for a given source."""

    url: str
    dest: Path  # relative to settings.raw_dir / source_name
    description: str = ""
    # Optional: if set, a secondary URL tried if the primary fails
    fallback_url: str = ""
    # Optional: expected SHA-256 hex. If set, verified after download.
    sha256: str = ""
    # Some URLs require an Authorization header (Dataverse API token)
    auth_token_env: str = ""


@dataclass
class SourceManifest:
    name: str
    enabled_flag: str  # attribute name on Settings, e.g. "INGEST_PRIMEKG"
    files: list[SourceFile] = field(default_factory=list)
    notes: str = ""  # printed for click-wall sources


def _build_manifests(settings: Settings) -> dict[str, SourceManifest]:
    """Build the download manifest. Paths are relative to raw_dir/source."""
    raw = settings.raw_dir

    # ------------------------------------------------------------------ #
    # PrimeKG — Harvard Dataverse                                         #
    # Dataset DOI: 10.7910/DVN/IXA7BM                                    #
    # The Dataverse native API supports resumable range-request downloads #
    # once you have a personal API token (free, no institutional account  #
    # required). Without a token, the download still works but may be     #
    # throttled.                                                           #
    # ------------------------------------------------------------------ #
    # PrimeKG persistent IDs for individual files (found via the Dataverse
    # JSON metadata endpoint).
    # Base URL: https://dataverse.harvard.edu/api/access/datafile/:persistentId
    #           ?persistentId=doi:10.7910/DVN/IXA7BM/{file_id}
    PRIMEKG_FILES = [
        SourceFile(
            url="https://dataverse.harvard.edu/api/access/datafile/:persistentId"
                "?persistentId=doi:10.7910/DVN/IXA7BM/MIOVBQ",
            dest=raw / "primekg" / "kg.csv",
            description="PrimeKG knowledge graph edges (~8M rows, ~700 MB)",
            auth_token_env="DATAVERSE_API_TOKEN",
        ),
        SourceFile(
            url="https://dataverse.harvard.edu/api/access/datafile/:persistentId"
                "?persistentId=doi:10.7910/DVN/IXA7BM/FMBSCD",
            dest=raw / "primekg" / "drug_features.csv",
            description="PrimeKG drug feature table",
            auth_token_env="DATAVERSE_API_TOKEN",
        ),
        SourceFile(
            url="https://dataverse.harvard.edu/api/access/datafile/:persistentId"
                "?persistentId=doi:10.7910/DVN/IXA7BM/RGF2KI",
            dest=raw / "primekg" / "disease_features.csv",
            description="PrimeKG disease feature table (MONDO, OMIM, DrugBank xrefs)",
            auth_token_env="DATAVERSE_API_TOKEN",
        ),
    ]

    # ------------------------------------------------------------------ #
    # DrugCentral — drug-indication + approval metadata                   #
    # ------------------------------------------------------------------ #
    if settings.DRUGCENTRAL_FORMAT == "csv":
        dc_files = [
            SourceFile(
                url="https://unmtid-shinyapps.net/download/DrugCentral/drug_indications.csv",
                dest=raw / "drugcentral" / "drug_indications.csv",
                description="DrugCentral drug-indication pairs with references",
                fallback_url=(
                    "https://drugcentral.org/static/data/drug_indications.csv"
                ),
            ),
            SourceFile(
                url="https://unmtid-shinyapps.net/download/DrugCentral/structures.smiles.csv",
                dest=raw / "drugcentral" / "structures.smiles.csv",
                description="DrugCentral drug structures (InChIKey, DrugBank xref)",
            ),
            SourceFile(
                url="https://unmtid-shinyapps.net/download/DrugCentral/approval.csv",
                dest=raw / "drugcentral" / "approval.csv",
                description="DrugCentral FDA approval years",
            ),
        ]
    else:
        dc_files = [
            SourceFile(
                url="https://unmtid-shinyapps.net/download/drugcentral.dump.11012023.sql.gz",
                dest=raw / "drugcentral" / "drugcentral.dump.sql.gz",
                description="DrugCentral full Postgres dump (~200 MB)",
            ),
        ]

    # ------------------------------------------------------------------ #
    # HPO — Human Phenotype Ontology                                      #
    # ------------------------------------------------------------------ #
    HPO_FILES = [
        SourceFile(
            url=(
                "https://github.com/obophenotype/human-phenotype-ontology"
                "/releases/latest/download/hp.obo"
            ),
            dest=raw / "hpo" / "hp.obo",
            description="HPO ontology in OBO format",
        ),
        SourceFile(
            url="https://hpo.jax.org/data/annotations/phenotype.hpoa",
            dest=raw / "hpo" / "phenotype.hpoa",
            description="HPO disease-to-phenotype annotations",
        ),
        SourceFile(
            url="https://hpo.jax.org/data/annotations/genes_to_phenotype.txt",
            dest=raw / "hpo" / "genes_to_phenotype.txt",
            description="HPO gene-to-phenotype associations",
        ),
    ]

    # ------------------------------------------------------------------ #
    # Orphanet — rare disease nomenclature                                #
    # Product 1 (disease list) is freely redistributable.                #
    # Product 4 (phenotypes) requires a free Orphanet account.           #
    # We fall back to HPO annotations for disease-phenotype edges.       #
    # ------------------------------------------------------------------ #
    ORPHANET_FILES = [
        SourceFile(
            url="https://www.orphadata.com/data/xml/en_product1.xml",
            dest=raw / "orphanet" / "en_product1.xml",
            description="Orphanet disease nomenclature (disease names + ORPHA IDs)",
            fallback_url="https://www.orphadata.org/data/xml/en_product1.xml",
        ),
    ]

    # ------------------------------------------------------------------ #
    # Reactome — biological pathways                                      #
    # ------------------------------------------------------------------ #
    REACTOME_FILES = [
        SourceFile(
            url="https://reactome.org/download/current/ReactomePathways.txt",
            dest=raw / "reactome" / "ReactomePathways.txt",
            description="Reactome pathway list (R-HSA IDs + names)",
        ),
        SourceFile(
            url="https://reactome.org/download/current/NCBI2Reactome.txt",
            dest=raw / "reactome" / "NCBI2Reactome.txt",
            description="NCBI gene → Reactome pathway membership",
        ),
        SourceFile(
            url="https://reactome.org/download/current/UniProt2Reactome.txt",
            dest=raw / "reactome" / "UniProt2Reactome.txt",
            description="UniProt → Reactome pathway membership",
        ),
        SourceFile(
            url="https://reactome.org/download/current/ReactomePathwaysRelation.txt",
            dest=raw / "reactome" / "ReactomePathwaysRelation.txt",
            description="Reactome pathway hierarchy (parent→child)",
        ),
    ]

    return {
        "primekg": SourceManifest(
            name="primekg",
            enabled_flag="INGEST_PRIMEKG",
            files=PRIMEKG_FILES,
            notes=(
                "If downloads are slow or fail, a free Dataverse account lets you "
                "generate an API token — set DATAVERSE_API_TOKEN in .env."
            ),
        ),
        "drugcentral": SourceManifest(
            name="drugcentral",
            enabled_flag="INGEST_DRUGCENTRAL",
            files=dc_files,
            notes=(
                "If the CSV download fails, visit https://drugcentral.org/downloads "
                "and place the files in data/raw/drugcentral/."
            ),
        ),
        "hpo": SourceManifest(
            name="hpo",
            enabled_flag="INGEST_HPO",
            files=HPO_FILES,
        ),
        "orphanet": SourceManifest(
            name="orphanet",
            enabled_flag="INGEST_ORPHANET",
            files=ORPHANET_FILES,
            notes=(
                "en_product1.xml (disease names) downloads freely. "
                "Product 4 (phenotypes) requires a free account at "
                "https://www.orphadata.com — place en_product4.xml in "
                "data/raw/orphanet/ if you have it."
            ),
        ),
        "reactome": SourceManifest(
            name="reactome",
            enabled_flag="INGEST_REACTOME",
            files=REACTOME_FILES,
        ),
    }


# ---------------------------------------------------------------------------
# Downloader
# ---------------------------------------------------------------------------


def _download_file(
    src_file: SourceFile,
    *,
    force: bool = False,
    dry_run: bool = False,
    token: str = "",
) -> bool:
    """Download a single file. Returns True if the file was (re)downloaded.

    Implements:
    - Skip if file already exists and is non-empty (unless force=True).
    - Resume: if a partial .part file exists, issue a Range request.
    - Optional SHA-256 verification after download.
    """
    dest = src_file.dest
    part = dest.with_suffix(dest.suffix + ".part")

    if dest.exists() and dest.stat().st_size > 0 and not force:
        _log.info("fetch.skip_existing", path=str(dest))
        return False

    if dry_run:
        _log.info("fetch.dry_run", url=src_file.url, dest=str(dest))
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Lazy import so the module is importable even without requests installed.
    try:
        import requests  # type: ignore[import-untyped]
    except ImportError:
        _log.error(
            "fetch.requests_missing",
            hint="pip install requests tqdm",
        )
        raise

    headers: dict[str, str] = {}

    # Dataverse personal API token (optional but recommended for large files).
    if src_file.auth_token_env:
        t = token or os.environ.get(src_file.auth_token_env, "")
        if t:
            headers["X-Dataverse-key"] = t

    # Resume support: send a Range header if a partial download exists.
    resume_pos = 0
    if part.exists() and not force:
        resume_pos = part.stat().st_size
        if resume_pos > 0:
            headers["Range"] = f"bytes={resume_pos}-"
            _log.info("fetch.resume", path=str(part), offset_mb=resume_pos // 1_048_576)

    url = src_file.url
    for attempt in (1, 2):
        try:
            resp = requests.get(url, headers=headers, stream=True, timeout=60)
            if resp.status_code == 416:
                # Range not satisfiable — file already fully downloaded.
                part.rename(dest)
                return True
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 1 and src_file.fallback_url:
                _log.warning("fetch.primary_failed_trying_fallback", error=str(exc))
                url = src_file.fallback_url
            else:
                raise

    total = int(resp.headers.get("content-length", 0))
    mode = "ab" if resume_pos else "wb"

    _log.info(
        "fetch.start",
        url=url,
        dest=str(dest),
        size_mb=round((total + resume_pos) / 1_048_576, 1) if total else "?",
    )
    t0 = time.monotonic()
    downloaded = resume_pos

    try:
        # Optional tqdm progress bar
        try:
            from tqdm import tqdm  # type: ignore[import-untyped]

            pbar: Any = tqdm(
                total=(total + resume_pos) or None,
                initial=resume_pos,
                unit="B",
                unit_scale=True,
                desc=dest.name,
            )
        except ImportError:
            pbar = None

        with open(part, mode) as fh:
            for chunk in resp.iter_content(chunk_size=1 << 20):  # 1 MB chunks
                fh.write(chunk)
                downloaded += len(chunk)
                if pbar is not None:
                    pbar.update(len(chunk))

        if pbar is not None:
            pbar.close()

    except Exception:
        # Leave the .part file in place for future resume.
        _log.error("fetch.interrupted", path=str(part))
        raise

    part.rename(dest)
    elapsed = time.monotonic() - t0
    speed = downloaded / elapsed / 1_048_576
    _log.info(
        "fetch.done",
        dest=str(dest),
        size_mb=round(downloaded / 1_048_576, 1),
        elapsed_s=round(elapsed, 1),
        speed_mb_s=round(speed, 2),
    )

    # Optional checksum verification
    if src_file.sha256:
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        if digest != src_file.sha256:
            dest.unlink()
            raise ValueError(
                f"SHA-256 mismatch for {dest.name}: "
                f"expected {src_file.sha256}, got {digest}"
            )
        _log.info("fetch.checksum_ok", file=dest.name)

    return True


def fetch_source(
    name: str,
    settings: Settings,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Download all files for one source. Returns list of local paths."""
    manifests = _build_manifests(settings)
    if name not in manifests:
        raise ValueError(f"Unknown source {name!r}. Known: {sorted(manifests)}")
    manifest = manifests[name]
    token = settings.DATAVERSE_API_TOKEN

    if manifest.notes:
        _log.info("fetch.source_notes", source=name, notes=manifest.notes)

    results = []
    for sf in manifest.files:
        _download_file(sf, force=force, dry_run=dry_run, token=token)
        results.append(sf.dest)
    return results


def fetch_all(
    settings: Settings | None = None,
    *,
    only: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """Download all enabled sources (or just `only` if specified)."""
    if settings is None:
        settings = get_settings()
    manifests = _build_manifests(settings)
    token = settings.DATAVERSE_API_TOKEN

    sources = [only] if only else list(manifests.keys())
    for name in sources:
        manifest = manifests[name]
        # Check the Settings enable flag (INGEST_PRIMEKG etc.)
        flag = getattr(settings, manifest.enabled_flag, True)
        if not flag:
            _log.info("fetch.source_disabled", source=name, flag=manifest.enabled_flag)
            continue

        _log.info("fetch.source_start", source=name, n_files=len(manifest.files))
        if manifest.notes:
            _log.info("fetch.source_notes", source=name, notes=manifest.notes)

        n_downloaded = 0
        for sf in manifest.files:
            try:
                did_download = _download_file(
                    sf, force=force, dry_run=dry_run, token=token
                )
                if did_download:
                    n_downloaded += 1
            except Exception as exc:
                _log.error(
                    "fetch.file_error",
                    source=name,
                    url=sf.url,
                    dest=str(sf.dest),
                    error=str(exc),
                )
                _log.warning(
                    "fetch.continuing_after_error",
                    hint=f"Manually download {sf.url!r} → {sf.dest}",
                )

        _log.info("fetch.source_done", source=name, n_downloaded=n_downloaded)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m app.etl.fetch_all",
        description="Download Phase 1 raw data into data/raw/",
    )
    p.add_argument(
        "--source",
        metavar="NAME",
        help="Fetch only this source (primekg|drugcentral|hpo|orphanet|reactome)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if files already exist",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be downloaded without doing it",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List all files and URLs in the manifest, then exit",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    settings = get_settings()

    if args.list:
        manifests = _build_manifests(settings)
        for sname, manifest in manifests.items():
            flag = getattr(settings, manifest.enabled_flag, True)
            status = "enabled" if flag else "disabled"
            print(f"\n[{sname}] ({status})")
            for sf in manifest.files:
                size_str = ""
                if sf.dest.exists():
                    size_str = f"  [{sf.dest.stat().st_size // 1024:,} KB on disk]"
                print(f"  {sf.description}")
                print(f"    URL : {sf.url}")
                print(f"    dest: {sf.dest}{size_str}")
        sys.exit(0)

    fetch_all(settings, only=args.source, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
