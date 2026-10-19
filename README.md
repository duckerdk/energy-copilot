# Energy Co-Pilot

**Status (2026-10-19): specyfikacja, bez kodu integracji.** Projekt nowej, lokalnej integracji Home Assistant (custom_components/energy_copilot), docelowo możliwej do instalacji przez HACS. W repo nie ma jeszcze działającego optymalizatora.

## Dokumentacja obowiązująca

- [Cele i reguły biznesowe](requirements/GOALS_AND_REQUIREMENTS.md) — **co** system ma osiągnąć.
- [Instalacja i źródła danych](requirements/SYSTEM_BASELINE.md) — ustalone fakty i ich stopień potwierdzenia.
- [Kontrakt encji HA](requirements/ENTITY_CONTRACT.md) — historyczne identyfikatory, braki i warunki walidacji.
- [Architektura i bezpieczeństwo](requirements/ARCHITECTURE.md) — **jak** budować i testować rozwiązanie.
- [Model optymalizacji](requirements/OPTIMIZATION_MODEL.md) — bilans PV/sieć/dom/bateria, koszty, dynamiczny SOC, zmienny horyzont znanych cen, walidacja prognozy przy curtailment.
- [Scenariusze testowe](requirements/TEST_SCENARIOS.md) — 35 przypadków z danymi i kryteriami akceptacji: bilans, koszty, dynamiczny SOC, ceny, curtailment, bezpieczeństwo i mapowanie encji HA.
- [Blokery wdrożenia](requirements/OPEN_ITEMS.md) — co wymaga sprawdzenia przed rzeczywistym sterowaniem.
- [AGENTS.md](AGENTS.md) — wiążące instrukcje robocze dla Codexa.

## Decyzje podstawowe

- Priorytet: najniższy **końcowy koszt netto** energii (DKK), a nie największa autokonsumpcja.
- Planowanie lokalnie; istniejące encje HA jako wejścia i kanał poleceń. Nie zmieniać ESPHome, Modbus, firmware.
- Ładowanie z sieci może działać automatycznie **dopiero po walidacji toru sterowania**.
- Celowe rozładowanie baterii na eksport wymaga indywidualnej, ważnej zgody użytkownika.
- **Domyślnie tylko odczyt i symulacja.** Brak danych, zatwierdzonego mapowania lub bezpiecznego powrotu = zakaz zapisu.
- Zasada ceny sprzedaży przekazana przez użytkownika: cena spot minus 0,0215 DKK/kWh; pełne warunki rozliczeń nadal wymagają testu na fakturze.

## Historia

Dokumenty prototypu v1–v5 i listy sprzątania starego serwera wycofano z bieżącego drzewa: opisywały inne rozwiązanie i zawierały duplikaty oraz sprzeczne wskazówki. **Pozostają odzyskiwalne z historii Git.** Jedyne istotne historyczne identyfikatory i ostrzeżenia przeniesiono do bieżących wymagań.
