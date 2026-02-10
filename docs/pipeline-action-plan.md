# Akční plán: Sjednocení GitHub Pipelines

**Projekty:** loxone-mcp + loxone-prometheus-exporter  
**Cíl:** Optimální, konzistentní a bezpečné CI/CD pipelines

---

## 📋 Přehled změn

### loxone-mcp (7 úkolů)
- ✅ Přidat kompletní Docker CI/CD
- ✅ Odstranit duplicitní security job
- ✅ Pin všechny actions na SHA
- ✅ Sjednotit Python verzi
- ✅ Přidat multi-platform build
- ✅ Optimalizovat strukturu
- ✅ Dokumentace

### loxone-prometheus-exporter (6 úkolů)
- ✅ Přidat CodeQL analýzu
- ✅ Přidat Trivy filesystem scan
- ✅ Přidat schedule security scans
- ✅ Pin všechny actions na SHA
- ✅ Rozdělit workflow
- ✅ Dokumentace

---

## 🔴 Fáze 1: Kritické změny (bezpečnost + funkcionalita)

### Projekt: loxone-mcp

#### Úkol 1.1: Vytvořit Docker build workflow ⭐ PRIORITA

**Soubor:** `.github/workflows/docker.yml` (nový)

**Důvod:** Projekt nemá žádný Docker build → nelze publishovat image

**Kroky:**
1. Vytvořit nový soubor `.github/workflows/docker.yml`
2. Nastavit trigger: `on: push: branches: [main] + tags: ['v*']`
3. Definovat job `build-and-push` s needs: CI jobs
4. Nastavit permissions (contents, packages, id-token, attestations)
5. Přidat kroky:
   - Checkout
   - Docker buildx setup
   - Login do GHCR
   - Metadata extraction
   - Build & push (multi-platform: linux/amd64, linux/arm64)
   - SLSA attestation
   - Trivy scan image
   - SBOM generation

**Konfigurace:**
```yaml
env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

platforms: linux/amd64,linux/arm64
cache-from: type=gha
cache-to: type=gha,mode=max
```

**Validace:**
```bash
# Po commitu na main/tag:
# 1. Zkontrolovat Actions tab
# 2. Ověřit image v Packages: https://github.com/orgs/USER/packages
# 3. Pull + run lokálně: docker pull ghcr.io/ondrejlevy/loxone-mcp:latest
```

---

#### Úkol 1.2: Odstranit duplicitní security job

**Soubor:** `.github/workflows/ci.yml`

**Problém:** Job `security (pip-audit)` je v ci.yml i security.yml

**Kroky:**
1. Otevřít `.github/workflows/ci.yml`
2. Smazat celý job `security:` (řádky cca 68-79)
3. Zachovat pouze v `.github/workflows/security.yml`
4. Zkontrolovat, že `security.yml` má správný trigger

**Před:**
```yaml
jobs:
  lint: ...
  typecheck: ...
  test: ...
  security:    # ← SMAZAT TENTO JOB
    name: Security Audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.14"
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: pip-audit
        run: pip-audit
  sbom: ...
```

**Po:**
```yaml
jobs:
  lint: ...
  typecheck: ...
  test: ...
  sbom: ...  # security job odstraněn
```

---

#### Úkol 1.3: Pin všechny actions na SHA

**Soubory:** Všechny `.github/workflows/*.yml`

**Důvod:** Tagované verze (v4, v5) jsou mutable → bezpečnostní riziko

**Kroky:**
1. Najít všechny použité actions v workflows
2. Pro každou action najít aktuální SHA:
   ```bash
   # Příklad pro actions/checkout@v4:
   # Jít na https://github.com/actions/checkout/releases
   # Zkopírovat SHA nejnovějšího v4.x release
   ```
3. Nahradit reference:
   ```yaml
   # PŘED:
   - uses: actions/checkout@v4
   
   # PO:
   - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
   ```

**Seznam actions k aktualizaci:**

**ci.yml:**
- `actions/checkout@v4` → `@de0fac2e4500dabe0009e67214ff5f5447ce83dd` # v6.0.2
- `actions/setup-python@v5` → `@a309ff8b426b58ec0e2a45f0f869d46889d02405` # v6.2.0
- `actions/upload-artifact@v4` → `@1746f4ab65b179e0ea60a494b83293b640dd5bba` # v4.5.0

**security.yml:**
- `actions/checkout@v4` → `@de0fac2e4500dabe0009e67214ff5f5447ce83dd` # v6.0.2
- `aquasecurity/trivy-action@master` → `@22438a435773de8c97dc0958cc0b823c45b064ac` # master pinned
- `github/codeql-action/upload-sarif@v3` → `@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d` # v3.28.2
- `github/codeql-action/init@v3` → `@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d` # v3.28.2
- `github/codeql-action/analyze@v3` → `@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d` # v3.28.2

**docker.yml (nový):**
- `actions/checkout` → už pinnutý (viz výše)
- `docker/setup-buildx-action@v3` → `@8d2750c68a42422c14e847fe6c8ac0403b4cbd6f` # v3.8.0
- `docker/login-action@v3` → `@c94ce9fb468520275223c153574b00df6fe4bcc9` # v3.4.1
- `docker/metadata-action@v5` → `@c299e40c65443455700f0fdfc63efafe5b349051` # v5.7.1
- `docker/build-push-action@v6` → `@263435318d21b8e681c14492fe198d362a7d2c83` # v6.14.0
- `actions/attest-build-provenance@v3` → `@96278af6caaf10aea03fd8d33a09a777ca52d62f` # v3.2.0
- `anchore/sbom-action@v0` → `@28d71544de8eaf1b958d335707167c5f783590ad` # v0.20.0

**Validace:**
```bash
# Po změnách:
git add .github/workflows/
git commit -m "security: pin all GitHub Actions to SHA hashes"

# Zkontrolovat v GitHub UI:
# Actions → workflow run → zobrazí se konkrétní SHA v logu
```

---

#### Úkol 1.4: Sjednotit Python verzi

**Soubory:** `.github/workflows/ci.yml`, `.github/workflows/security.yml`

**Problém:** ci.yml používá 3.14 (prerelease), security.yml nespecifikuje

**Rozhodnutí:** Použít **Python 3.13** (stabilní, nejnovější GA)

**Kroky:**

**1. Upravit ci.yml:**
```yaml
# Úprava pro všechny joby (lint, typecheck, test, sbom):
- uses: actions/setup-python@<SHA>
  with:
    python-version: "3.13"  # ← změnit z "3.14"
    # ODSTRANIT: allow-prereleases: true
    cache: 'pip'  # ← přidat pro rychlejší CI
```

**2. Upravit security.yml:**
```yaml
# Přidat pro všechny joby, které instalují Python:
jobs:
  pip-audit:  # pokud existuje samostatně
    steps:
      - uses: actions/setup-python@<SHA>
        with:
          python-version: "3.13"  # ← explicitně definovat
          cache: 'pip'

  trivy-container:
    # Nepotřebuje Python setup (pouze Docker)
  
  trivy-fs:
    # Nepotřebuje Python setup
```

**Validace:**
```bash
# Lokálně otestovat s 3.13:
pyenv install 3.13.0  # nebo asdf install python 3.13.0
pyenv local 3.13.0
pip install -e ".[dev]"
pytest && mypy src/ && ruff check src/

# Pokud projde → safe to update CI
```

---

### Projekt: loxone-prometheus-exporter

#### Úkol 1.5: Přidat CodeQL analýzu ⭐ PRIORITA

**Soubor:** `.github/workflows/security.yml` (upravit nebo vytvořit)

**Důvod:** Chybí statická bezpečnostní analýza → riziko zranitelností v kódu

**Kroky:**

**Varianta A: Pokud security.yml neexistuje, vytvořit:**
```yaml
name: Security

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"  # Weekly Monday 06:00 UTC

permissions:
  contents: read
  security-events: write

jobs:
  codeql:
    name: CodeQL Analysis
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      
      - name: Initialize CodeQL
        uses: github/codeql-action/init@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d # v3.28.2
        with:
          languages: python
          queries: security-extended  # Více kontrol než default
      
      - name: Perform CodeQL Analysis
        uses: github/codeql-action/analyze@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d # v3.28.2
        with:
          category: "/language:python"
```

**Varianta B: Pokud security.yml existuje, přidat job:**
- Otevřít existující `security.yml`
- Přidat `codeql:` job na konec souboru
- Zachovat existující permissions

**Validace:**
```bash
# Po merge do main:
# 1. GitHub → Security tab → Code scanning
# 2. Zkontrolovat, že se objevují CodeQL výsledky
# 3. Pokud najde issues → opravit podle doporučení
```

---

#### Úkol 1.6: Přidat Trivy filesystem scan

**Soubor:** `.github/workflows/security.yml` (nebo ci-cd.yml)

**Důvod:** Trivy skenuje pouze Docker image → chybí scan dependencies v source

**Kroky:**

**1. Přidat nový job do security.yml:**
```yaml
jobs:
  # ... existující joby ...
  
  trivy-fs:
    name: Trivy Filesystem Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      
      - name: Run Trivy filesystem scan
        uses: aquasecurity/trivy-action@22438a435773de8c97dc0958cc0b823c45b064ac # master
        with:
          scan-type: fs
          scan-ref: .
          format: sarif
          output: trivy-fs-results.sarif
          severity: CRITICAL,HIGH
      
      - name: Upload Trivy results to Security tab
        uses: github/codeql-action/upload-sarif@48a3b0bac45f2d8791858b300e5bc0b6c82c8b8d # v3.28.2
        if: always()
        with:
          sarif_file: trivy-fs-results.sarif
          category: trivy-filesystem
```

**2. Pokud používáte requirements.txt, ujistit se, že je committed:**
```bash
# Trivy potřebuje vidět dependencies:
ls -la requirements.txt pyproject.toml setup.py
```

**Validace:**
```bash
# Lokálně otestovat:
docker run --rm -v $(pwd):/workspace aquasec/trivy:latest fs /workspace

# Po push do GitHub:
# Security tab → Code scanning → zobrazí Trivy FS výsledky
```

---

#### Úkol 1.7: Přidat schedule trigger pro security scany

**Soubor:** `.github/workflows/ci-cd.yml` (upravit) nebo `security.yml`

**Důvod:** Security scany běží pouze on push → zranitelnosti se objevují kdykoliv

**Kroky:**

**1. Rozhodnout strategii:**
- **Varianta A:** Přidat schedule do existujícího `ci-cd.yml` (jednoduché)
- **Varianta B:** Vytvořit separátní `security.yml` s pouze security jobs (čistší)

**Doporučení:** Varianta B (separace)

**2. Pokud Varianta B, vytvořit security.yml:**
```yaml
name: Security Scans

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"  # Každé pondělí v 6:00 UTC

permissions:
  contents: read
  security-events: write

jobs:
  trivy-container:
    name: Trivy Container Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<SHA>
      - name: Build temporary image
        run: docker build -t loxone-exporter:scan .
      - uses: aquasecurity/trivy-action@<SHA>
        with:
          image-ref: loxone-exporter:scan
          format: sarif
          output: trivy-container.sarif
      - uses: github/codeql-action/upload-sarif@<SHA>
        with:
          sarif_file: trivy-container.sarif

  trivy-fs:
    # ... z předchozího úkolu ...

  codeql:
    # ... z předchozího úkolu ...
```

**3. Pokud Varianta A, upravit ci-cd.yml:**
```yaml
# Jen přidat do sekce 'on:':
on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 6 * * 1"  # ← PŘIDAT

# Pak upravit joby, aby security běžely i na schedule:
jobs:
  test:
    if: github.event_name != 'schedule'  # Skip na schedule
    # ...
  
  build-and-push:
    if: github.event_name != 'schedule' && github.event_name != 'pull_request'
    # ...
  
  trivy-scan:
    if: github.event_name == 'schedule' || github.event_name == 'push'
    # Spustit na schedule + push
```

**Validace:**
```bash
# Nelze otestovat lokálně (cron)
# Po merge:
# 1. Actions tab → zkontrolovat, že schedule trigger je vidět
# 2. Počkat do příštího pondělí
# 3. Nebo triggernout ručně: Actions → workflow → Run workflow
```

---

#### Úkol 1.8: Pin všechny actions na SHA

**Soubor:** `.github/workflows/ci-cd.yml`

**Aktuální stav:**
```yaml
# Příklad současných referencí:
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2 ✅ už pinned
- uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6.2.0 ✅ už pinned
- uses: docker/setup-buildx-action@8d2750c68a42422c14e847fe6c8ac0403b4cbd6f # v3 ✅ už pinned
# ... všechny jsou již pinned v referencovaném projektu
```

**Kroky:**
1. Zkontrolovat `ci-cd.yml` - všechny actions mají SHA? ✅
2. Pokud najdete nějaké `@v<number>`, aktualizovat podobně jako úkol 1.3
3. Pro nově přidané workflows (security.yml) použít SHA z úkolu 1.3

**Stav:** ✅ Projekt už má actions pinned, pouze zkontrolovat nové workflows

---

## 🟡 Fáze 2: Konzistence a optimalizace

### Oba projekty

#### Úkol 2.1: Standardizovat permissions

**Soubory:** Všechny workflows

**Cíl:** Použít principle of least privilege konzistentně

**Minimální permissions pro každý typ jobu:**

```yaml
# CI/Test jobs:
permissions:
  contents: read

# Docker build + push:
permissions:
  contents: read
  packages: write
  id-token: write    # Pro attestation
  attestations: write

# Security scans s SARIF upload:
permissions:
  contents: read
  security-events: write

# CodeQL:
permissions:
  contents: read
  security-events: write
```

**Kroky:**
1. Projít všechny workflows
2. Nastavit `permissions:` na úrovni workflow NEBO job
   - Workflow-level: Platí pro všechny joby (jednodušší)
   - Job-level: Přesnější, ale verbose
3. Doporučení: **Job-level pro různorodé joby, workflow-level pro homogenní**

**Příklad úpravy:**

```yaml
# PŘED (příliš široké permissions na workflow):
name: CI
permissions:
  contents: write
  packages: write
  security-events: write

jobs:
  lint:  # Nepotřebuje write!
    runs-on: ubuntu-latest
    steps: ...

# PO (přesné permissions na job):
name: CI
permissions: {}  # Default: žádné

jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read  # Pouze čtení
    steps: ...
  
  security-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write  # Pouze pro SARIF upload
    steps: ...
```

---

#### Úkol 2.2: Optimalizovat cache strategii

**Soubory:** Všechny workflows s Python nebo Docker

**Cíl:** Rychlejší CI běhy

**Python cache:**
```yaml
# PŘIDAT do setup-python:
- uses: actions/setup-python@<SHA>
  with:
    python-version: "3.13"
    cache: 'pip'  # ← PŘIDAT (cachuje pip dependencies)
```

**Docker cache:**
```yaml
# UŽ POUŽÍVÁ v loxone-prometheus-exporter:
- uses: docker/build-push-action@<SHA>
  with:
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

**Kroky:**
1. Přidat `cache: 'pip'` do všech `setup-python` (pokud chybí)
2. Zkontrolovat Docker cache je nastaven
3. Lokální test: smazat cache, pustit, pustit znovu → 2x by měl být rychlejší

---

#### Úkol 2.3: Unifikovat naming conventions

**Soubory:** Všechny workflows

**Aktuální stav:**
- loxone-mcp: `Lint & Format`, `Type Check`, `Test`, `Security Audit`
- loxone-prometheus-exporter: `Run Tests`, `Build and Push Docker Image`

**Doporučená konvence:**
```yaml
name: <Workflow Purpose>  # CI, Docker Build, Security
jobs:
  <job-id>:
    name: <Human Readable Name>  # Run Tests, Scan Container, etc.
```

**Příklad unifikace:**

```yaml
# LOXONE-MCP (upravit):
name: CI  # Zachovat
jobs:
  lint:
    name: Lint Code  # Bylo: "Lint & Format"
  
  typecheck:
    name: Type Check  # OK (zachovat)
  
  test:
    name: Run Tests  # Bylo: "Test"
  
  sbom:
    name: Generate SBOM  # Bylo: "SBOM Generation"

# LOXONE-PROMETHEUS-EXPORTER (upravit):
name: CI/CD  # Zachovat (nebo rozdělit na CI + Docker workflows)
jobs:
  test:
    name: Run Tests  # OK (zachovat)
  
  build-and-push:
    name: Build Docker Image  # Bylo: "Build and Push Docker Image"
```

**Cíl:** Snadno čitelné, konzistentní napříč projekty

---

#### Úkol 2.4: Dokumentovat workflows

**Soubory:** `README.md` v obou projektech

**Cíl:** Vývojáři vědí, co která pipeline dělá

**Přidat sekci do README.md:**

```markdown
## CI/CD Pipeline

### Workflows

#### CI (`ci.yml`)
Runs on: push to main/develop, pull requests

- **Lint**: Code style check with Ruff
- **Type Check**: Static analysis with Mypy
- **Run Tests**: Unit + integration tests with Pytest
- **Generate SBOM**: Software Bill of Materials

#### Docker Build (`docker.yml`)
Runs on: push to main, version tags

- Multi-platform build (amd64, arm64)
- Push to GitHub Container Registry
- SLSA provenance attestation
- Container vulnerability scan

#### Security (`security.yml`)
Runs on: push, pull requests, weekly schedule

- **pip-audit**: Python dependency vulnerabilities
- **Trivy FS**: Filesystem vulnerability scan
- **Trivy Container**: Docker image scan
- **CodeQL**: Static security analysis

### Badges

[![CI](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/ci.yml)
[![Security](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/security.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/security.yml)
[![Docker](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/docker.yml/badge.svg)](https://github.com/ondrejlevy/loxone-mcp/actions/workflows/docker.yml)

### Running Locally

```bash
# Lint
ruff check src/ tests/

# Type check
mypy src/

# Tests
pytest --cov

# Security audit
pip-audit
```
```

---

## 🟢 Fáze 3: Nice-to-have

#### Úkol 3.1: Matrix testing (optional)

**Pouze pokud potřebujete podporu více verzí Pythonu**

```yaml
jobs:
  test:
    strategy:
      matrix:
        python-version: ['3.11', '3.12', '3.13']
        os: [ubuntu-latest, macos-latest]  # optional
    
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/setup-python@<SHA>
        with:
          python-version: ${{ matrix.python-version }}
```

**Výhody:** Ověřuje kompatibilitu  
**Nevýhody:** Delší CI, více nákladů

---

#### Úkol 3.2: Pre-commit hooks

**Soubor:** `.pre-commit-config.yaml` (nový v obou projektech)

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.12.0
    hooks:
      - id: mypy
        additional_dependencies: [types-PyYAML]
```

**Instalace:**
```bash
pip install pre-commit
pre-commit install
```

**Výhoda:** Catch chyby před commit → rychlejší feedback loop

---

## 📊 Kontrolní checklist

### loxone-mcp
- [ ] Vytvořen `.github/workflows/docker.yml`
- [ ] Docker workflow obsahuje multi-platform build
- [ ] Docker workflow obsahuje SLSA attestation
- [ ] Odstraněn duplicitní `security` job z `ci.yml`
- [ ] Všechny actions pinned na SHA
- [ ] Python verze sjednocena na 3.13
- [ ] Přidán pip cache do setup-python
- [ ] Dokumentace workflows v README
- [ ] Badges v README

### loxone-prometheus-exporter
- [ ] Přidán CodeQL job do `security.yml`
- [ ] Přidán Trivy FS job do `security.yml`
- [ ] Přidán schedule trigger (weekly)
- [ ] Actions pinned (zkontrolovat nové workflows)
- [ ] Python verze 3.13 (nebo explicitní rozhodnutí)
- [ ] Dokumentace workflows v README
- [ ] Badges v README

### Oba projekty
- [ ] Permissions minimalizovány (least privilege)
- [ ] Naming conventions konzistentní
- [ ] Cache strategie optimální
- [ ] README dokumentuje všechny workflows

---

## 🚀 Spuštění změn

### Doporučené pořadí commitů

**loxone-mcp:**
```bash
# 1. Pin actions (safe, non-breaking)
git checkout -b chore/pin-actions
# ... upravit workflows ...
git commit -m "chore: pin all GitHub Actions to SHA hashes"
git push && create PR

# 2. Remove duplicate + sjednotit Python
git checkout -b chore/cleanup-workflows
# ... upravit ci.yml, security.yml ...
git commit -m "chore: remove duplicate security job, unify Python version"
git push && create PR

# 3. Add Docker workflow (hlavní změna)
git checkout -b feat/docker-ci-cd
# ... vytvořit docker.yml ...
git commit -m "feat: add Docker CI/CD workflow with attestation"
git push && create PR

# 4. Update documentation
git checkout -b docs/workflows
# ... upravit README ...
git commit -m "docs: document CI/CD workflows"
git push && create PR
```

**loxone-prometheus-exporter:**
```bash
# 1. Pin actions (pokud potřeba)
git checkout -b chore/security-hardening
# ... pin actions ...
git commit -m "chore: pin actions to SHA (if needed)"

# 2. Add security workflows
git checkout -b feat/enhanced-security
# ... vytvořit/upravit security.yml ...
git commit -m "feat: add CodeQL, Trivy FS, and scheduled scans"
git push && create PR

# 3. Documentation
git checkout -b docs/workflows
# ... README updates ...
git commit -m "docs: document security workflows"
git push && create PR
```

---

## 📈 Úspěšnost - Co očekávat

### Po dokončení - loxone-mcp

**Před:**
- ❌ Žádný Docker build
- ⚠️ Duplicitní security checks
- ⚠️ Security scany pouze on-demand
- ✅ Dobrá security coverage (CodeQL + Trivy)

**Po:**
- ✅ Automatický Docker build + publish
- ✅ Multi-platform support
- ✅ SLSA attestation
- ✅ Týdenní security scany
- ✅ Konzistentní se standardy
- ✅ Pinned actions (supply chain security)

### Po dokončení - loxone-prometheus-exporter

**Před:**
- ✅ Fungující CI/CD
- ❌ Žádný CodeQL
- ❌ Žádný Trivy FS
- ❌ Žádné scheduled scany
- ⚠️ Unpinned actions (částečně pinned)

**Po:**
- ✅ Zachovaný CI/CD flow
- ✅ CodeQL analýza
- ✅ Trivy FS scan
- ✅ Týdenní security scany
- ✅ Plně pinned actions
- ✅ Konzistentní se standardy

---

## 🆘 Troubleshooting

### Problem: Docker build selhává

**Příčina:** Nesprávný Dockerfile path nebo missing dependencies

**Řešení:**
```yaml
# V docker.yml zkontrolovat:
- uses: docker/build-push-action@<SHA>
  with:
    context: .
    file: docker/Dockerfile  # ← správná cesta?
    push: ${{ github.event_name != 'pull_request' }}
```

### Problem: GHCR push permission denied

**Příčina:** Chybí workflow permissions

**Řešení:**
```yaml
# Top-level nebo job-level:
permissions:
  contents: read
  packages: write  # ← MUSÍ být pro GHCR push
```

### Problem: CodeQL nalézá false positives

**Příčina:** Přísná konfigurace

**Řešení:**
```yaml
# Upravit query set:
- uses: github/codeql-action/init@<SHA>
  with:
    languages: python
    queries: security-and-quality  # místo security-extended
```

### Problem: Trivy timeout na velkých images

**Příčina:** Pomalá síť nebo velký image

**Řešení:**
```yaml
- uses: aquasecurity/trivy-action@<SHA>
  with:
    timeout: 15m  # Default je 5m
```

### Problem: Schedule workflows neběží

**Příčina:** GitHub disable inactive workflows po 60 dnech

**Řešení:**
- Jednou za 60 dní otevřít Actions tab
- Nebo ručně trigger workflow
- GitHub automaticky notifikuje před disable

---

## 📅 Timeline

| Týden | Fáze | Effort | Kritické? |
|-------|------|---------|-----------|
| 1 | Fáze 1: loxone-mcp (úkoly 1.1-1.4) | 6-8h | ✅ Ano |
| 1-2 | Fáze 1: loxone-prometheus-exporter (1.5-1.8) | 4-6h | ✅ Ano |
| 2-3 | Fáze 2: Konzistence (2.1-2.4) | 4h | ⚠️ Doporučeno |
| 4 | Fáze 3: Nice-to-have (3.1-3.2) | 2-4h | ⬜ Volitelné |

**Celkem:** ~16-22 hodin práce  
**Kritická část:** ~10-14 hodin

---

## ✅ Závěr

Po dokončení budou **oba projekty mít**:
1. ✅ Kompletní CI/CD pipeline
2. ✅ Multi-layered security (4 nástroje)
3. ✅ Supply chain protection (pinned actions + attestation)
4. ✅ Pravidelné security monitoring
5. ✅ Konzistentní struktura a naming
6. ✅ Dokumentované workflows

**Aktuální priority:**
1. 🔴 **loxone-mcp:** Docker CI/CD (kritické pro deployment)
2. 🔴 **loxone-prometheus-exporter:** CodeQL + Trivy FS (kritické pro security)
3. 🟡 Obě: Pinned actions + cleanup
4. 🟢 Obě: Dokumentace + nice-to-have

**Začněte s úkolem 1.1 (Docker) a 1.5 (CodeQL) - největší dopad!**
