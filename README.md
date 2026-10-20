# Energy Co-Pilot

**Status (2026-10-19): specyfikacja, bez kodu integracji.** Projekt nowej, lokalnej integracji Home Assistant (custom_components/energy_copilot), docelowo możliwej do instalacji przez HACS. W repo nie ma jeszcze działającego optymalizatora.

## Dokumentacja obowiązująca

- [Cele i reguły biznesowe](requirements/GOALS_AND_REQUIREMENTS.md) — **co** system ma osiągnąć.
- [Instalacja i źródła danych](requirements/SYSTEM_BASELINE.md) — ustalone fakty i ich stopień potwierdzenia.
- [Kontrakt encji HA](requirements/ENTITY_CONTRACT.md) — historyczne identyfikatory, braki i warunki walidacji.
- [Architektura i bezpieczeństwo](requirements/ARCHITECTURE.md) — **jak** budować i testować rozwiązanie.
- [Model optymalizacji](requirements/OPTIMIZATION_MODEL.md) — bilans PV/sieć/dom/bateria, koszty, dynamiczny SOC, zmienny horyzont znanych cen, walidacja prognozy przy curtailment.
- [Scenariusze testowe](requirements/TEST_SCENARIOS.md) — 40 przypadków z danymi i kryteriami akceptacji: bilans, koszty, dynamiczny SOC, ceny, curtailment, bezpieczeństwo i mapowanie encji HA.
- [Strategia sterowania prąd/TOU](requirements/CONTROL_STRATEGY.md) — preferowany current-first, trwałość nastaw, ograniczenia sześciu okien TOU i 16 testów porównania.
- [Algorytm regulatora prądu](requirements/CURRENT_CONTROLLER_MODEL.md) — dokładne przeliczenia A↔kW, sterowanie 15-minutowe, ograniczenia TOU/SOC, 20 testów CUR.
- [Wykonawca HA](requirements/EXECUTION_CONTRACT.md) — kontrakt poleceń, weryfikacja skutków, zgody, stany i awarie; 12 dodatkowych testów EXE.
- [Panel Home Assistant](requirements/HA_DASHBOARD.md) — widok pomiarów, planu, kosztów, SOC, zgód i diagnostyki; 10 testów UI.
- [Rejestr decyzji](requirements/DECISION_LOGGING.md) — wymagane od pierwszego rozruchu ceny, prognozy, koszty, porównanie alternatyw i historia w HA.
- [Niepewność i wartość końcowa SOC](requirements/FORECAST_POLICY.md) — scenariusze prognoz, statystyka błędów i brak fikcyjnych przyszłych cen.
- [Kalibracja i degradacja](requirements/CALIBRATION_POLICY.md) — jawne założenia sprawności, metoda pomiarów i marginalny koszt cyklu; brak udawania pomiarów.
- [Jednorazowy odczyt HA](requirements/HA_READONLY_CAPTURE.md) — wyłącznie odczytowy raport bieżących encji i jednostek, nie test sterowania.
- [Wynik odczytu HA z 19.10.2026](requirements/HA_ENTITY_SNAPSHOT_2026-10-19.md) — potwierdzone obecne ID, bilans PV/bateria/dom/sieć, kandydaci sterowań i ryzyka.
- [Potwierdzony kontrakt cen HA](requirements/HA_PRICE_SERIES_CONTRACT.md) — `raw_today/raw_tomorrow`, `tomorrow_valid`, DST, taryfy, parser i 18 testów PRICE.
- [Kontrakt godzinowej prognozy PV](requirements/PV_FORECAST_CONTRACT.md) — natywna akcja HA `forecast_solar.get_forecast`, odpowiedź `wh_period`/`watts`, normalizacja i 18 testów PVF.
- [Prognoza zużycia domu](requirements/LOAD_FORECAST_CONTRACT.md) — profil poboru z historii Recorder, punkt pomiarowy, DST i 16 testów LOAD.
- [Kontrakt pomiarów i bilansu](requirements/MEASUREMENT_CONTRACT.md) — rzeczywiste encje PV/sieć/bateria/dom, znaki i źródła pochodne, integracja kWh, 20 testów MTR.
- [Archiwalny szablon diagnostyki HA](requirements/HA_TIMESERIES_CAPTURE.md) — opcjonalny; **nie** jest wymagany do pobrania cen ani prognoz.
- [Walidacja historyczna](requirements/BACKTEST_VALIDATION.md) — test walk-forward bez wiedzy o przyszłości oraz uczciwa metoda liczenia korzyści.
- [Przekazanie programiście](requirements/DEVELOPER_HANDOFF.md) — kolejność dokumentów, etapy M1–M6 i warunki odbioru.
- [Blokery wdrożenia](requirements/OPEN_ITEMS.md) — co wymaga sprawdzenia przed rzeczywistym sterowaniem.
- [AGENTS.md](AGENTS.md) — wiążące instrukcje robocze dla Codexa.

## Decyzje podstawowe

- Priorytet: najniższy **końcowy koszt netto** energii (DKK), a nie największa autokonsumpcja.
- Planowanie lokalnie; istniejące encje HA jako wejścia i kanał poleceń. Nie zmieniać ESPHome, Modbus, firmware.
- Ładowanie z sieci może działać automatycznie **dopiero po walidacji toru sterowania**.
- Celowe rozładowanie baterii na eksport wymaga indywidualnej, ważnej zgody użytkownika.
- **Domyślnie tylko odczyt i symulacja.** Brak danych, zatwierdzonego mapowania lub bezpiecznego powrotu = zakaz zapisu.
- **Własne granice prądu regulatorów Deye (polityka Co-Pilot): 0–50 A ładowanie, 0–100 A rozładowanie, 0–50 A grid charge**; nie korzystać z błędnych granic encji HA. Wartość 0 A nie oznacza potwierdzonego fizycznego wyłączenia.
- Zasada ceny sprzedaży przekazana przez użytkownika: cena spot minus 0,0215 DKK/kWh; pełne warunki rozliczeń nadal wymagają testu na fakturze.

## Historia

Dokumenty prototypu v1–v5 i listy sprzątania starego serwera wycofano z bieżącego drzewa: opisywały inne rozwiązanie i zawierały duplikaty oraz sprzeczne wskazówki. **Pozostają odzyskiwalne z historii Git.** Jedyne istotne historyczne identyfikatory i ostrzeżenia przeniesiono do bieżących wymagań.
