# Analýza MCP serveru – Top 50 AI Use-Cases pro Loxone Smart Home

**Datum**: 2026-02-10  
**Verze**: 1.0

---

## 1. Analýza aktuálně implementovaných Tools & Resources

### 1.1 Implementované MCP Tools (14)

| # | Tool | Typ | Popis |
|---|------|------|-------|
| 1 | `get_component_state` | READ | Stav konkrétní komponenty dle UUID |
| 2 | `control_component` | WRITE | Ovládání komponenty (On/Off/Pulse/FullUp…) |
| 3 | `get_room_components` | READ | Všechny komponenty v místnosti dle UUID |
| 4 | `get_components_by_type` | READ | Komponenty dle typu (LightController, Jalousie…) |
| 5 | `list_rooms` | READ | Výpis všech místností s počty komponent |
| 6 | `get_room_by_name` | READ | Vyhledání místnosti dle názvu (case-insensitive, partial match) |
| 7 | `get_lights_status` | READ | Stav světel (celý dům nebo filtr dle místnosti) |
| 8 | `control_room_lights` | WRITE | Zapnout/Vypnout všechna světla v místnosti |
| 9 | `get_temperatures` | READ | Teploty z IRoomControllerV2 + teplotních senzorů |
| 10 | `get_presence_status` | READ | Stav přítomnosti/pohybu dle místnosti |
| 11 | `get_window_door_status` | READ | Stav oken/dveří (otevřeno/zavřeno) |
| 12 | `get_alarm_status` | READ | Stav zabezpečovacího systému |
| 13 | `control_alarm` | WRITE | Aktivace/deaktivace alarmu |
| 14 | `get_energy_status` | READ | Spotřeba/výroba energie, stav baterie |

### 1.2 Implementované MCP Resources (4)

| # | URI | Popis |
|---|-----|-------|
| 1 | `loxone://structure` | Kompletní struktura Loxone miniserveru |
| 2 | `loxone://components` | Všechny komponenty s obohacenými daty |
| 3 | `loxone://rooms` | Místnosti s počty komponent |
| 4 | `loxone://categories` | Kategorie s počty komponent |

### 1.3 Podporované typy komponent a akce

| Typ komponenty | Podporované akce |
|----------------|-----------------|
| LightController | On, Off |
| LightControllerV2 | On, Off |
| Switch | On, Off, Pulse |
| EIBDimmer | On, Off |
| Dimmer | On, Off |
| Jalousie | FullUp, FullDown, Up, Down, Stop, Shade |
| IRoomControllerV2 | setManualTemperature, setComfortTemperature, setMode |
| Alarm | On, Off, delayedon, quit |
| SmokeAlarm | mute, quit |
| Gate | Open, Close, Stop |

### 1.4 Identifikované mezery v aktuální implementaci

- **Žádná podpora stínění/žaluzií** na úrovni vyšších nástrojů (pouze přes `control_component`)
- **Žádný tool pro nastavení teploty** přímo dle místnosti (nutno znát UUID)
- **Žádná podpora Mood/scén** u Lighting Controlleru
- **Žádná podpora audio** (Loxone Music Server)
- **Žádný tool pro hromadné operace** (multi-room, celý dům)
- **Žádná podpora interkomu/doorbellu**
- **Žádná podpora Pool / Sauna / Irrigation**
- **Žádná podpora smart timers / schedules**
- **Chybí logické dotazy** ("Jsou všechna světla zhasnutá?", "Je dům zabezpečen?")
- **Chybí historické dotazy** na stav komponent

---

## 2. Loxone – Dostupné bloky a jejich možnosti

Na základě Loxone dokumentace (87 function blocks) jsou pro AI kontrolu relevantní zejména:

### 2.1 Osvětlení
- **Lighting Controller / LightControllerV2** – až 18 světelných okruhů, 89 nálad (Moods), dimming, RGB, Tunable White, Daylight Control, prezence/pohyb automatika, simulace přítomnosti
- **Dimmer / EIBDimmer** – stmívání 0-100%
- **Switch** – zapnout/vypnout/pulz

### 2.2 Stínění
- **Automatic Shading (Jalousie)** – žaluzie, rolety, závěsy, markýzy; automatické stínění dle polohy slunce; pozice 0-100%, nastavení lamel; ochrana proti větru

### 2.3 Klimatizace & Vytápění
- **Intelligent Room Controller (IRoomControllerV2)** – Comfort/Eco/Building protection mody; cílová teplota; automatické vytápění/chlazení; PWM výstupy; integrace s AC jednotkami  
- **AC Unit Controller** – ovládání klimatizací
- **Heating/Cooling Controller** – centrální řízení zdrojů

### 2.4 Zabezpečení
- **Alarm** – aktivace/deaktivace, zpožděná aktivace, úrovně poplachu
- **SmokeAlarm** – kouřový alarm, ztlumení
- **Alarm Chain** – 10-úrovňový řetěz alarmů s escalací
- **AAL Smart Alarm** – osobní nouzový alarm

### 2.5 Přístup
- **Gate** – otevření/zavření/stop brány/garáže
- **Intercom** – zvonkový systém, dveřní komunikace

### 2.6 Audio
- **Music Server / Audio Zone** – přehrávání, hlasitost, zdroj, zóny

### 2.7 Energie
- **EnergyMonitor / Meter** – spotřeba, výroba, stav baterie
- **InfoOnlyAnalog** – obecné analogové senzory

### 2.8 Senzory
- **PresenceDetector / MotionSensor** – detekce přítomnosti/pohybu
- **InfoOnlyDigital** – kontakty oken/dveří, binární senzory
- **InfoOnlyAnalog** – teplota, vlhkost, CO2, osvětlení

### 2.9 Ostatní
- **Pool Controller** – řízení bazénu
- **Sauna Controller** – řízení sauny
- **Irrigation** – zavlažování
- **Tracker** – GPS tracking
- **Timer / Schedule** – časové plány

---

## 3. Top 50 AI Use-Cases pro Loxone Smart Home

### Kategorie: 🔆 Osvětlení (1–10)

| # | Use-Case | Popis |
|---|----------|-------|
| 1 | **"Rozsviť v obýváku"** | Zapnout světla v konkrétní místnosti dle názvu |
| 2 | **"Zhasni v celém domě"** | Vypnout všechna světla ve všech místnostech |
| 3 | **"Nastav světlo v ložnici na 30%"** | Stmívání konkrétního světla na danou úroveň |
| 4 | **"Aktivuj filmovou náladu v obýváku"** | Přepnutí na konkrétní Mood dle názvu/ID |
| 5 | **"Jaká světla svítí?"** | Dotaz na celkový přehled rozsvícených světel |
| 6 | **"Simuluj přítomnost, jedu na dovolenou"** | Aktivace simulace přítomnosti |
| 7 | **"Nastav teplou barvu světla na večer"** | Ovládání barevné teploty (Tunable White) |
| 8 | **"Rozsvíťte na chodbě na 5 minut"** | Časově omezené zapnutí světla |
| 9 | **"Zapni noční režim osvětlení"** | Přepnutí na specifický Mood (noční) |
| 10 | **"Které místnosti mají rozsvíceno?"** | Přehledový dotaz stavu světel po místnostech |

### Kategorie: 🪟 Stínění & Žaluzie (11–17)

| # | Use-Case | Popis |
|---|----------|-------|
| 11 | **"Stáhni žaluzie v obýváku"** | Zavření žaluzií v konkrétní místnosti |
| 12 | **"Vytáhni všechny rolety"** | Otevření všech rolet v domě |
| 13 | **"Nastav žaluzie na 50%"** | Nastavení žaluzií na konkrétní pozici |
| 14 | **"Přestav lamely vodorovně"** | Nastavení úhlu lamel |
| 15 | **"Stav žaluzií v celém domě?"** | Dotaz na pozice všech stínících prvků |
| 16 | **"Aktivuj automatické stínění"** | Zapnutí sun position automatic |
| 17 | **"Stáhni žaluzie na jižní straně"** | Stínění dle orientace oken |

### Kategorie: 🌡️ Klima & Vytápění (18–27)

| # | Use-Case | Popis |
|---|----------|-------|
| 18 | **"Jaká je teplota v ložnici?"** | Dotaz na aktuální teplotu |
| 19 | **"Nastav teplotu v obýváku na 22°C"** | Změna cílové teploty dle místnosti |
| 20 | **"Přepni celý dům do režimu Eco"** | Změna HVAC módu všech IRC |
| 21 | **"Přepni ložnici do komfortního režimu"** | Změna módu konkrétního IRC |
| 22 | **"Který pokoj je nejteplejší/nejchladnější?"** | Analytický dotaz na teploty |
| 23 | **"Zapni klimatizaci v pracovně"** | Ovládání AC jednotky |
| 24 | **"Nastav noční teploty pro spaní"** | Building protection / snížené teploty |
| 25 | **"Jaký je aktuální režim vytápění?"** | Dotaz na HVAC mód per room |
| 26 | **"Jsou otevřená okna a topí se?"** | Kontrola konfliktu topení/okna |
| 27 | **"Jaká je venkovní teplota?"** | Dotaz na outdoor temperature sensor |

### Kategorie: 🔒 Zabezpečení & Přístup (28–35)

| # | Use-Case | Popis |
|---|----------|-------|
| 28 | **"Zabezpeč dům, odcházím"** | Aktivace alarmu + odchozí scéna |
| 29 | **"Je dům zabezpečen?"** | Dotaz na stav alarmu |
| 30 | **"Deaktivuj alarm"** | Vypnutí alarmu |
| 31 | **"Otevři garáž"** | Ovládání brány/garáže |
| 32 | **"Jsou všechna okna zavřená?"** | Kontrola okenních/dveřních kontaktů |
| 33 | **"Která okna/dveře jsou otevřená?"** | Detailní výpis otevřených prvků |
| 34 | **"Kdo zvoní u dveří?"** | Informace z interkomu/doorbellu |
| 35 | **"Odemkni vstupní dveře"** | Ovládání zámku/dveřního interkomu |

### Kategorie: 👤 Přítomnost & Pohyb (36–39)

| # | Use-Case | Popis |
|---|----------|-------|
| 36 | **"Je někdo doma?"** | Kontrola přítomnosti v celém domě |
| 37 | **"Ve kterých místnostech je pohyb?"** | Přehled aktivních PIR senzorů |
| 38 | **"Jak dlouho je obývák prázdný?"** | Historický dotaz na přítomnost |
| 39 | **"Upozorni mě, když někdo vstoupí do garáže"** | Nastavení notifikace na pohyb |

### Kategorie: ⚡ Energie (40–43)

| # | Use-Case | Popis |
|---|----------|-------|
| 40 | **"Jaká je aktuální spotřeba?"** | Přehled spotřeby z gridu |
| 41 | **"Kolik vyrábí fotovoltaika?"** | Dotaz na solární výrobu |
| 42 | **"Jaký je stav baterie?"** | Stav domácí baterie |
| 43 | **"Jaký je energetický přehled dne?"** | Sumarizace spotřeby/výroby za den |

### Kategorie: 🎵 Audio & Média (44–46)

| # | Use-Case | Popis |
|---|----------|-------|
| 44 | **"Pusť hudbu v obýváku"** | Spuštění přehrávání v audio zóně |
| 45 | **"Ztlum hudbu na 30%"** | Nastavení hlasitosti |
| 46 | **"Zastav hudbu v celém domě"** | Stop všech audio zón |

### Kategorie: 🏠 Scény & Automatizace (47–50)

| # | Use-Case | Popis |
|---|----------|-------|
| 47 | **"Aktivuj scénu Dobrou noc"** | Zhasnutí, zamknutí, stažení žaluzií, snížení teplot |
| 48 | **"Přepni do režimu Dovolená"** | Building protection, simulace přítomnosti, zavření žaluzií |
| 49 | **"Ranní rutina"** | Vytažení rolet, rozsvícení, nastavení komfortní teploty |
| 50 | **"Přehled stavu celého domu"** | Komplexní dashboard – světla, teploty, zabezpečení, energie |

---

## 4. Analýza proveditelnosti se současnou implementací

### ✅ Plně proveditelné (18 use-cases)

| # | Use-Case | Pokrytí |
|---|----------|---------|
| 1 | Rozsviť v obýváku | `control_room_lights` (On) |
| 5 | Jaká světla svítí? | `get_lights_status` |
| 10 | Které místnosti mají rozsvíceno? | `get_lights_status` (bez room_name) |
| 18 | Jaká je teplota v ložnici? | `get_temperatures` (room_name) |
| 25 | Jaký je aktuální režim vytápění? | `get_temperatures` → mode field |
| 29 | Je dům zabezpečen? | `get_alarm_status` |
| 30 | Deaktivuj alarm | `control_alarm` (Off) |
| 32 | Jsou všechna okna zavřená? | `get_window_door_status` → allClosed |
| 33 | Která okna/dveře jsou otevřená? | `get_window_door_status` → openItems |
| 36 | Je někdo doma? | `get_presence_status` → presenceDetected |
| 37 | Ve kterých místnostech je pohyb? | `get_presence_status` → roomsWithPresence |
| 40 | Jaká je aktuální spotřeba? | `get_energy_status` → gridConsumption |
| 41 | Kolik vyrábí fotovoltaika? | `get_energy_status` → solarProduction |
| 42 | Jaký je stav baterie? | `get_energy_status` → batteryLevel |
| 12 | Vytáhni všechny rolety | `get_components_by_type` + `control_component` × N |
| 28 | Zabezpeč dům, odcházím | `control_alarm` (On) |
| 31 | Otevři garáž | `control_component` (Gate, Open) |
| 15 | Stav žaluzií v celém domě? | `get_components_by_type` (Jalousie) |

### ⚠️ Částečně proveditelné – vyžadují multi-step orchestraci AI (14 use-cases)

| # | Use-Case | Limitace | Jak to funguje |
|---|----------|----------|----------------|
| 2 | Zhasni v celém domě | Nutno volat `control_room_lights(Off)` per room | AI musí iterovat přes `list_rooms` |
| 3 | Nastav světlo na 30% | Dimming existuje přes `control_component` s params.value | AI musí najít UUID přes `get_room_by_name` |
| 11 | Stáhni žaluzie v obýváku | Přes `control_component` per Jalousie | AI musí najít Jalousie v místnosti |
| 13 | Nastav žaluzie na 50% | `control_component` s action "Shade" a params | AI musí interpretovat % na pozici |
| 19 | Nastav teplotu na 22°C | `control_component` IRC s `setManualTemperature` + value | AI musí najít IRC v místnosti |
| 20 | Přepni celý dům do Eco | `control_component` IRC `setMode` per room | Multi-step per IRC |
| 21 | Přepni ložnici do komfortu | `control_component` IRC `setComfortTemperature` | AI musí najít IRC |
| 22 | Nejteplejší pokoj? | `get_temperatures` + AI analýza výsledků | AI interpretuje data |
| 26 | Otevřená okna a topí se? | Kombinace `get_window_door_status` + `get_temperatures` | AI koreluje data |
| 27 | Venkovní teplota? | `get_temperatures` hledá "outdoor" senzor | Závisí na pojmenování senzoru |
| 47 | Scéna Dobrou noc | Kombinace više tools v sekvenci | AI orchestruje 4-5 tool calls |
| 48 | Režim Dovolená | Multi-tool sekvence | AI orchestruje mnoho toolů |
| 49 | Ranní rutina | Multi-tool sekvence | AI orchestruje mnoho toolů |
| 50 | Přehled celého domu | Kombinace všech read tools | AI agreguje data |

### ❌ Nelze provést – chybí podpora (18 use-cases)

| # | Use-Case | Chybějící funkcionalita |
|---|----------|------------------------|
| 4 | Filmová nálada | **Chybí: `set_lighting_mood`** – Lighting Controller nemá tool pro přepínání Moods |
| 6 | Simulace přítomnosti | **Chybí: `enable_presence_simulation`** – Lighting Controller property |
| 7 | Teplá barva světla | **Chybí: `set_color_temperature`** – RGB/Tunable White řízení |
| 8 | Rozsvíť na 5 minut | **Chybí: timer/delayed actions** |
| 9 | Noční režim osvětlení | **Chybí: `set_lighting_mood`** |
| 14 | Lamely vodorovně | **Chybí: `set_slat_position`** – explicitní ovládání lamel |
| 16 | Aktivuj auto stínění | **Chybí: `enable_sun_position_automatic`** |
| 17 | Žaluzie na jižní straně | **Chybí: filtr dle orientace/kompasu** |
| 23 | Zapni klimatizaci | **Chybí: podpora AC Unit Controller** |
| 24 | Noční teploty | **Chybí: bulk temperature/mode nastavení** |
| 34 | Kdo zvoní? | **Chybí: Intercom integration** |
| 35 | Odemkni dveře | **Chybí: Door lock / Intercom control** |
| 38 | Jak dlouho je prázdný? | **Chybí: historická data** |
| 39 | Upozorni na pohyb | **Chybí: conditional notifications / watchers** |
| 43 | Energetický přehled dne | **Chybí: historický energy reporting** |
| 44 | Pusť hudbu | **Chybí: Audio/Music Server tools** |
| 45 | Ztlum hudbu | **Chybí: Audio volume control** |
| 46 | Zastav hudbu | **Chybí: Audio stop/pause** |

---

## 5. Navrhovaná rozšíření MCP serveru

### 5.1 Priorita 1 – Vysoká hodnota, nízká složitost

#### Tool: `control_room_blinds`
```
Ovládání žaluzií/rolet v místnosti dle názvu.
Input: {room_name: str, action: "FullUp"|"FullDown"|"Stop"|"Shade", position?: int}
Pokrytí: UC #11, #12, #13
```

#### Tool: `set_room_temperature`
```
Nastavení cílové teploty dle názvu místnosti.
Input: {room_name: str, temperature: float, mode?: "comfort"|"eco"|"manual"}
Pokrytí: UC #19, #21, #24
```

#### Tool: `set_hvac_mode`
```
Nastavení HVAC módu pro místnost nebo celý dům.
Input: {room_name?: str, mode: "auto"|"comfort"|"eco"|"building_protection"|"off"}
Pokrytí: UC #20, #24
```

#### Tool: `get_blinds_status`
```
Dotaz na stav stínění (pozice žaluzií, lamel) per room nebo celý dům.
Input: {room_name?: str}
Pokrytí: UC #15 (vylepšený), #17
```

#### Tool: `control_all_lights`
```
Zapnout/Vypnout světla v celém domě jedním voláním.
Input: {action: "On"|"Off"}
Pokrytí: UC #2
```

#### Tool: `get_home_summary`
```
Komplexní přehled stavu domu – světla, teploty, zabezpečení, energie, okna.
Input: {}
Pokrytí: UC #50
```

### 5.2 Priorita 2 – Střední hodnota

#### Tool: `set_lighting_mood`
```
Přepnutí Lighting Controlleru na konkrétní Mood (dle ID nebo názvu).
Input: {room_name: str, mood_id?: int, mood_name?: str}
Pokrytí: UC #4, #9
```

#### Tool: `dim_light`
```
Stmívání konkrétního světla nebo místnosti na danou úroveň.
Input: {room_name?: str, component_uuid?: str, brightness: int (0-100)}
Pokrytí: UC #3
```

#### Tool: `set_slat_position`
```
Nastavení pozice lamel žaluzií.
Input: {room_name?: str, component_uuid?: str, position: int (0-100)}
Pokrytí: UC #14
```

#### Tool: `execute_scene`
```
Spuštění předdefinované scény (sekvence akcí).
Input: {scene_name: "goodnight"|"morning"|"away"|"home"|custom}
Pokrytí: UC #47, #48, #49
Implementace: Server-side orchestrace více control příkazů.
```

#### Rozšířit `COMPONENT_ACTIONS` o:
```python
"Jalousie": [..., "setPosition"],  # Přidat setPosition
"AutomaticShading": ["Sps", "DisSp", "Co", "Cc", "Pos", "Slat"],
"ACUnitController": ["On", "Off", "setMode", "setTemperature", "setFanSpeed"],
"AudioZone": ["Play", "Pause", "Stop", "VolumeUp", "VolumeDown", "SetVolume"],
```

### 5.3 Priorita 3 – Budoucí rozšíření

#### Tool: `control_audio`
```
Ovládání Loxone Music Serveru / audio zón.
Input: {zone_name: str, action: "play"|"pause"|"stop"|"volume", value?: int, source?: str}
Pokrytí: UC #44, #45, #46
```

#### Tool: `control_intercom`
```
Interakce s interkomem (answer, open door, reject).
Input: {action: "answer"|"open"|"reject"}
Pokrytí: UC #34, #35
```

#### Tool: `enable_presence_simulation`
```
Aktivace/deaktivace simulace přítomnosti na Lighting Controllerech.
Input: {enabled: bool, rooms?: [str]}
Pokrytí: UC #6
```

#### Tool: `get_history` (vyžaduje API rozšíření)
```
Dotaz na historický stav komponenty.
Input: {component_uuid: str, from: datetime, to: datetime}
Pokrytí: UC #38, #43
Poznámka: Loxone API standardně neposkytuje historii – vyžaduje statistiky.
```

#### Tool: `subscribe_notification`
```
Nastavení podmíněné notifikace (watch).
Input: {component_uuid: str, condition: "on_change"|"threshold", threshold?: float}
Pokrytí: UC #39
```

---

## 6. Souhrnná matice

| Kategorie | Celkem UC | ✅ Plně | ⚠️ Částečně | ❌ Nelze |
|-----------|-----------|---------|-------------|---------|
| Osvětlení | 10 | 3 | 2 | 5 |
| Stínění | 7 | 2 | 2 | 3 |
| Klima | 10 | 2 | 5 | 3 |
| Zabezpečení | 8 | 5 | 0 | 3 |
| Přítomnost | 4 | 2 | 0 | 2 |
| Energie | 4 | 3 | 0 | 1 |
| Audio | 3 | 0 | 0 | 3 |
| Scény | 4 | 0 | 3 | 1 |
| **CELKEM** | **50** | **17 (34%)** | **12 (24%)** | **18 (36%)** |
| **+ Částečné** | | **29 (58%)** | | |

### Doporučení implementačních vln

**Vlna 1** (6 nových tools → pokrytí 40/50 = 80%):
- `control_room_blinds`, `set_room_temperature`, `set_hvac_mode`, `get_blinds_status`, `control_all_lights`, `get_home_summary`

**Vlna 2** (4 nové tools → pokrytí 46/50 = 92%):
- `set_lighting_mood`, `dim_light`, `set_slat_position`, `execute_scene`

**Vlna 3** (5 nových tools → pokrytí 50/50 = 100%):
- `control_audio`, `control_intercom`, `enable_presence_simulation`, `get_history`, `subscribe_notification`
