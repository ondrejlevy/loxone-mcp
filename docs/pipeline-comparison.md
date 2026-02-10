# Porovnání GitHub Pipelines

**Datum analýzy:** 10. února 2026

## Přehled současného stavu

### Projekt: loxone-mcp (aktuální)
- **Soubory:** `.github/workflows/ci.yml`, `.github/workflows/security.yml`
- **Celkem jobů:** 7 (5 v CI + 2 security + 1 CodeQL)

### Projekt: loxone-prometheus-exporter (reference)
- **Soubory:** `.github/workflows/ci-cd.yml`
- **Celkem jobů:** 2 (test + build-and-push)

---

## Detailní porovnání

### 1. Struktura workflows

#### loxone-mcp (současný stav)
```yaml
# ci.yml
- lint (Ruff check + format check)
- typecheck (Mypy)
- test (Pytest s coverage)
- security (pip-audit)
- sbom (CycloneDX)

# security.yml
- trivy-container (skenování Docker image)
- trivy-fs (skenování filesystému)
- codeql (analýza kódu)
```

#### loxone-prometheus-exporter (reference)
```yaml
# ci-cd.yml
- test (pip-audit + ruff + mypy + pytest)
- build-and-push (Docker build + push + attestation + Trivy + SBOM)
```

---

## Rozdíly a analýza

### ✅ Výhody loxone-mcp

1. **Separace concerns**
   - CI a Security jsou oddělené workflows → lepší přehlednost
   - Jednodušší debugování jednotlivých částí

2. **CodeQL analýza**
   - GitHub Advanced Security analýza
   - Detekce bezpečnostních vzorů v kódu
   - **CHYBÍ v loxone-prometheus-exporter**

3. **Pravidelné security scany**
   - Schedule trigger pro týdenní scany
   - Proaktivní bezpečnost

4. **Filesystem scanning**
   - Trivy skenuje celý projekt (nejen Docker)
   - Odhaluje zranitelnosti v dependencies

### ❌ Nevýhody loxone-mcp

1. **Chybí Docker build pipeline**
   - Žádná automatická build image
   - Žádné publikování do registry
   - **KRITICKÝ ROZDÍL**

2. **Chybí artifact attestation**
   - Žádné SLSA provenance
   - Nižší důvěryhodnost artifacts

3. **Bez deployment flow**
   - Žádné tagy → release workflow
   - Nemožnost automatického publishování

4. **Redundantní joby v CI**
   - Security job v ci.yml i security.yml
   - pip-audit běží duplicitně

5. **Starší Python verze v security.yml**
   - ci.yml používá Python 3.14
   - security.yml nespecifikuje verzi explicitně

6. **Chybí multi-platform build**
   - loxone-prometheus-exporter: linux/amd64, linux/arm64
   - loxone-mcp: žádný build

### ⚠️ Výhody loxone-prometheus-exporter

1. **Kompletní CI/CD flow**
   - Test → Build → Push → Attest → Scan → SBOM
   - Vše v jednom workflow

2. **Docker Registry Integration**
   - Auto-push do GHCR (GitHub Container Registry)
   - Tagging strategie (version, latest, SHA, branch)

3. **Artifact Attestation**
   - SLSA provenance attestation
   - Zvýšená důvěryhodnost supply chain

4. **Multi-platform build**
   - linux/amd64 + linux/arm64
   - Širší kompatibilita

5. **Optimalizace CI cache**
   - Docker layer caching (gha)
   - Pip cache v setup-python

6. **Pinned action versions**
   - SHA místo tags → vyšší bezpečnost
   - Prevence supply chain útoků

### ⚠️ Nevýhody loxone-prometheus-exporter

1. **Chybí CodeQL**
   - Žádná statická analýza bezpečnosti
   - Pouze Trivy na Docker image

2. **Žádný filesystem scan**
   - Trivy skenuje pouze finální image
   - Ne source code dependencies

3. **Žádné pravidelné security scany**
   - Pouze on push/PR
   - Žádný schedule trigger

4. **Konsolidovaný workflow**
   - Těžší debugování
   - Pomalejší CI pro PRs (musí projít vším)

5. **Codecov dependency**
   - Vyžaduje externí službu + token
   - loxone-mcp používá artifacts

---

## Srovnávací tabulka

| Funkce | loxone-mcp | loxone-prometheus-exporter |
|--------|------------|----------------------------|
| **CI Tests** | ✅ Oddělené joby | ✅ Jeden job |
| **Linting** | ✅ Ruff check + format | ✅ Ruff check |
| **Type checking** | ✅ Mypy | ✅ Mypy |
| **Security audit** | ✅ pip-audit (duplicitní) | ✅ pip-audit |
| **Docker build** | ❌ CHYBÍ | ✅ Multi-platform |
| **Docker publish** | ❌ CHYBÍ | ✅ GHCR |
| **Trivy container** | ✅ Samostatný job | ✅ Po build |
| **Trivy filesystem** | ✅ Samostatný job | ❌ CHYBÍ |
| **CodeQL** | ✅ Python analýza | ❌ CHYBÍ |
| **SBOM** | ✅ CycloneDX | ✅ CycloneDX |
| **Attestation** | ❌ CHYBÍ | ✅ SLSA provenance |
| **Schedule scan** | ✅ Týdně | ❌ CHYBÍ |
| **Coverage upload** | ✅ Artifacts | ⚠️ Codecov (external) |
| **Action pinning** | ⚠️ Tags | ✅ SHA hashes |
| **Python version** | ⚠️ 3.14 (prerelease) | ✅ 3.13 (stable) |

---

## Doporučení pro optimalizaci

### Priorita 1: Kritické (bezpečnost + funkcionalita)

#### 1.1 loxone-mcp - Přidat Docker CI/CD
```yaml
# Nový job v ci.yml nebo nový soubor docker.yml
build-and-push:
  needs: [test, security]
  runs-on: ubuntu-latest
  permissions:
    contents: read
    packages: write
    id-token: write
    attestations: write
  steps:
    - Docker build
    - Push do GHCR
    - Artifact attestation
    - Multi-platform support
```

#### 1.2 loxone-prometheus-exporter - Přidat CodeQL
```yaml
# Nový soubor: .github/workflows/security.yml
codeql:
  runs-on: ubuntu-latest
  steps:
    - Initialize CodeQL (Python)
    - Analyze code
    - Upload SARIF
```

#### 1.3 Obě projekty - Pinned actions
- Nahradit všechny `@v4`, `@v5` za SHA hashes
- Prevence supply chain útoků

### Priorita 2: Důležité (kvalita + konzistence)

#### 2.1 loxone-mcp - Odstranit duplicitu
- Přesunout `pip-audit` pouze do `security.yml`
- Odstranit `security` job z `ci.yml`

#### 2.2 loxone-prometheus-exporter - Přidat Trivy FS
```yaml
trivy-fs:
  runs-on: ubuntu-latest
  steps:
    - Trivy scan filesystem
    - Upload SARIF to Security tab
```

#### 2.3 loxone-prometheus-exporter - Schedule scans
```yaml
on:
  schedule:
    - cron: "0 6 * * 1"  # Weekly Monday
```

#### 2.4 Obě projekty - Unified Python version
- Rozhodnout: Python 3.13 (stable) nebo 3.14 (prerelease)
- Použít konzistentně napříč všemi workflows

### Priorita 3: Nice-to-have (optimalizace)

#### 3.1 Obě projekty - Matrix testing
```yaml
strategy:
  matrix:
    python-version: ['3.11', '3.12', '3.13']
```

#### 3.2 loxone-mcp - Coverage reporting
- Zvážit Codecov integrace (jako reference projekt)
- Nebo zachovat artifacts (jednodušší, bez external dep)

#### 3.3 Obě projekty - Pre-commit hooks
- Integrovat ruff + mypy do pre-commit
- Konzistence před CI

---

## Implementační plán

### Fáze 1: Bezpečnost a funkcionalita (týden 1-2)

**loxone-mcp:**
1. ✅ Vytvořit Docker build workflow
2. ✅ Přidat SLSA attestation
3. ✅ Pin všechny actions na SHA
4. ✅ Odstranit duplicitní security job

**loxone-prometheus-exporter:**
1. ✅ Přidat CodeQL workflow
2. ✅ Přidat Trivy filesystem scan
3. ✅ Pin všechny actions na SHA
4. ✅ Přidat schedule trigger

### Fáze 2: Konzistence (týden 3)

**Obě projekty:**
1. ✅ Sjednotit Python verzi (doporučeno: 3.13)
2. ✅ Standardizovat permissions
3. ✅ Sjednotit naming conventions
4. ✅ Dokumentovat workflow v README

### Fáze 3: Optimalizace (týden 4)

**Obě projekty:**
1. ⚠️ Přidat matrix testing (optional)
2. ⚠️ Optimalizovat cache strategie
3. ⚠️ Přidat pre-commit hooks
4. ⚠️ Review a tuning

---

## Optimální stav - Template

### Doporučená struktura pro oba projekty

```
.github/workflows/
├── ci.yml          # Test, lint, type check
├── docker.yml      # Build, push, attest (pouze on push main/tags)
└── security.yml    # Trivy FS, Trivy Container, CodeQL (+ schedule)
```

### ci.yml (optimalizovaný)
```yaml
name: CI
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/setup-python@<SHA>
        with:
          python-version: "3.13"
          cache: 'pip'
      - run: pip install ruff
      - run: ruff check src/ tests/
      - run: ruff format --check src/ tests/

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/setup-python@<SHA>
        with:
          python-version: "3.13"
          cache: 'pip'
      - run: pip install -e ".[dev]"
      - run: mypy src/

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/setup-python@<SHA>
        with:
          python-version: "3.13"
          cache: 'pip'
      - run: pip install -e ".[dev]"
      - run: pytest --cov --cov-report=xml
      - uses: actions/upload-artifact@<SHA>
        with:
          name: coverage
          path: coverage.xml

  sbom:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/setup-python@<SHA>
      - run: pip install cyclonedx-bom
      - run: cyclonedx-py environment -o sbom.json
      - uses: actions/upload-artifact@<SHA>
```

### docker.yml (nový pro loxone-mcp)
```yaml
name: Docker Build

on:
  push:
    branches: [main]
    tags: ['v*']

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    needs: [test]  # Referuje CI workflow
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
      attestations: write
    
    steps:
      - uses: actions/checkout@<SHA>
      
      - uses: docker/setup-buildx-action@<SHA>
      
      - uses: docker/login-action@<SHA>
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      
      - uses: docker/metadata-action@<SHA>
        id: meta
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=ref,event=branch
            type=semver,pattern={{version}}
            type=raw,value=latest,enable={{is_default_branch}}
      
      - uses: docker/build-push-action@<SHA>
        id: build
        with:
          context: .
          file: docker/Dockerfile
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          platforms: linux/amd64,linux/arm64
          cache-from: type=gha
          cache-to: type=gha,mode=max
      
      - uses: actions/attest-build-provenance@<SHA>
        with:
          subject-name: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          subject-digest: ${{ steps.build.outputs.digest }}
          push-to-registry: true
      
      - uses: aquasecurity/trivy-action@<SHA>
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
          format: sarif
          output: trivy-results.sarif
      
      - uses: github/codeql-action/upload-sarif@<SHA>
        with:
          sarif_file: trivy-results.sarif
      
      - uses: anchore/sbom-action@<SHA>
        with:
          image: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}@${{ steps.build.outputs.digest }}
          format: cyclonedx-json
```

### security.yml (optimalizovaný pro oba)
```yaml
name: Security

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"

permissions:
  contents: read
  security-events: write

jobs:
  pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: actions/setup-python@<SHA>
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]" pip-audit
      - run: pip-audit --desc

  trivy-fs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: aquasecurity/trivy-action@<SHA>
        with:
          scan-type: fs
          format: sarif
          output: trivy-fs.sarif
      - uses: github/codeql-action/upload-sarif@<SHA>
        with:
          sarif_file: trivy-fs.sarif

  trivy-container:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - run: docker build -f docker/Dockerfile -t scan:local .
      - uses: aquasecurity/trivy-action@<SHA>
        with:
          image-ref: scan:local
          format: sarif
          output: trivy-container.sarif
      - uses: github/codeql-action/upload-sarif@<SHA>
        with:
          sarif_file: trivy-container.sarif

  codeql:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - uses: github/codeql-action/init@<SHA>
        with:
          languages: python
      - uses: github/codeql-action/analyze@<SHA>
```

---

## Závěr a roadmapa

### Klíčové rozdíly
1. **loxone-mcp:** Silná security (CodeQL, Trivy FS), ale chybí CI/CD
2. **loxone-prometheus-exporter:** Kompletní CI/CD, ale slabší security

### Doporučená strategie
1. **Kombinovat silné stránky obou**
2. **Standardizovat na společný template**
3. **Prioritizovat bezpečnost + funkcionalitu**

### Timeline
- **Týden 1-2:** Kritické změny (Docker CI/CD + CodeQL)
- **Týden 3:** Konzistence a cleanup
- **Týden 4:** Optimalizace a dokumentace

### Výsledek
Oba projekty budou mít:
- ✅ Kompletní CI/CD pipeline
- ✅ Multi-layered security (pip-audit + Trivy + CodeQL)
- ✅ SLSA attestation
- ✅ Pravidelné scany
- ✅ Konzistentní struktura
