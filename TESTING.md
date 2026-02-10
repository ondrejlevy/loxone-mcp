# Testování projektu lokálně

Tento dokument popisuje, jak spouštět všechny testy stejně jako v CI/CD pipeline před pushem do repozitáře.

## Požadavky

### Instalace pyenv (macOS)

```bash
# Instalace pyenv přes Homebrew
brew install pyenv

# Přidání pyenv do shellu (přidejte do ~/.zshrc nebo ~/.bash_profile)
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc

# Restartujte shell nebo spusťte
source ~/.zshrc
```

### Instalace a nastavení Python 3.14

```bash
# Instalace Python 3.14
pyenv install 3.14

# Nastavení Python 3.14 jako lokální verzi pro tento projekt
cd /path/to/loxone-mcp
pyenv local 3.14

# Ověření verze
python --version  # mělo by vypsat Python 3.14.x
```

## Nastavení vývojového prostředí

```bash
# Vytvoření virtuálního prostředí
python -m venv .venv

# Aktivace virtuálního prostředí
source .venv/bin/activate

# Instalace projektu s dev závislostmi
pip install --upgrade pip
pip install -e ".[dev]"
pip install pip-audit
```

## Spuštění testů (jako v CI/CD)

### 1. pip-audit (Kontrola zranitelností v závislostech)

```bash
pip-audit --desc --skip-editable
```

### 2. Ruff (Linter)

```bash
ruff check src/ tests/
```

Pro automatickou opravu některých chyb:

```bash
ruff check src/ tests/ --fix
```

### 3. mypy (Type checker)

```bash
mypy src/
```

### 4. pytest (Jednotkové a integrační testy)

```bash
pytest src/tests/ -v --cov=loxone_mcp --cov-report=xml --cov-report=term
```

Nebo jen unit testy:

```bash
pytest src/tests/unit/ -v
```

Nebo contract testy:

```bash
pytest src/tests/contract/ -v
```

### 5. Kompletní CI pipeline lokálně

Spusťte všechny testy najednou:

```bash
# Celá test suite
pip-audit --desc --skip-editable && \
ruff check src/ && \
mypy src/ && \
pytest src/tests/ -v --cov=loxone_mcp --cov-report=xml --cov-report=term
```

## Struktura testů

Testy jsou organizovány do následujících kategorií:

- `src/tests/unit/` - Jednotkové testy (rychlé, izolované)
- `src/tests/integration/` - Integrační testy (mohou vyžadovat síť)
- `src/tests/contract/` - Testy MCP protokolových kontraktů
- `src/tests/fixtures/` - Testovací fixtures a mock data

## Spuštění jednotlivých kategorií testů

```bash
# Jen unit testy
pytest src/tests/unit/ -m unit -v

# Jen integrační testy
pytest src/tests/integration/ -m integration -v

# Jen contract testy
pytest src/tests/contract/ -m contract -v

# Všechny testy kromě pomalých
pytest src/tests/ -v -m "not slow"
```

Pokud všechny testy projdou, můžete bezpečně pushovat do remote repository.

## Doporučený workflow před commitem

```bash
# 1. Formátování kódu
ruff check src/ --fix

# 2. Spuštění všech testů
pip-audit --desc --skip-editable && \
ruff check src/ && \
mypy src/ && \
pytest src/tests/ -v

# 3. Pokud vše projde, commit a push
git add .
git commit -m "Your commit message"
git push
```

## Debugování

### Kontrola Python verze v projektu

```bash
python --version
which python
pyenv version
```

### Reinstalace závislostí

```bash
# Smazání virtuálního prostředí
rm -rf .venv

# Vytvoření nového a instalace
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"
pip install pip-audit
```

### Spuštění jednotlivých testů

```bash
# Konkrétní test soubor
pytest src/tests/unit/test_config.py -v

# Konkrétní test funkce
pytest src/tests/unit/test_config.py::test_config_validation -v

# S výpisem print() příkazů
pytest src/tests/unit/test_config.py -v -s
```

## Timeouts v testech

Některé testy (např. v `src/tests/integration/`) mohou běžet déle. Pokud chcete nastavit timeout:

```bash
pytest src/tests/ -v --timeout=30
```

## Pre-commit Hook (volitelné)

Pro automatické spouštění testů před každým commitem:

```bash
# Vytvořte soubor .git/hooks/pre-commit
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
set -e

echo "Running pre-commit checks..."

# Ruff
echo "1/3 Running ruff..."
ruff check src/

# mypy
echo "2/3 Running mypy..."
.venv/bin/mypy src/

# pytest
echo "3/3 Running tests..."
.venv/bin/pytest src/tests/unit/ -v --tb=short

echo "✅ All checks passed!"
EOF

# Udělejte ho spustitelným
chmod +x .git/hooks/pre-commit
```

## Užitečné příkazy

```bash
# Zobrazení pokrytí kódu v HTML
pytest src/tests/ --cov=loxone_mcp --cov-report=html
open htmlcov/index.html

# Spuštění testů s detailním výpisem
pytest src/tests/ -vv --tb=long

# Spuštění testů parallel (rychlejší)
pip install pytest-xdist
pytest src/tests/ -n auto
```
