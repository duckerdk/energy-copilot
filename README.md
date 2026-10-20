# Energy Co-Pilot

**Status: specyfikacja, bez kodu integracji i bez wykonanych testów implementacji.** Docelowo lokalna integracja Home Assistant `custom_components/energy_copilot` (opcjonalnie HACS). Niniejsze repo **nie steruje falownikiem**.

## Cel i granice

Minimalizować koszt netto energii w DKK przy uwzględnieniu strat i kosztu dodatkowych cykli baterii. Oddzielać koszt rachunku, koszt degradacji, plan ekonomiczny, wykonalność w Deye i fizyczny rezultat.

- Jedyny interfejs danych i ewentualnego sterowania: istniejące encje oraz natywne usługi Home Assistant. Bez bezpośredniego Modbus, ESPHome, firmware lub dodatkowego serwera.
- Zakup: `sensor.energi_data_service`; sprzedaż: `sensor.energi_data_spotpris`. Używać kwot HA **bez korekt podatków, taryf ani prowizji**.
- Autonomiczne zezwolenie na eksport **PV**, po dopuszczeniu trybu live: `switch.sun12k_solar_sell` od **0,40 DKK/kWh**. To nie jest zgoda na eksport baterii; brak potwierdzonej separacji blokuje zapis.
- Celowe oddanie energii **z baterii** do sieci wymaga osobnej, ważnej zgody na konkretną propozycję.
- Tryb początkowy: **monitor/dry-run**, bez zapisów. Nastawy Deye pozostają po zaniku HA, dlatego test niezależnego zabezpieczenia jest warunkiem automatyki.

## Dokumenty — czytaj selektywnie

| Zakres | Źródło normatywne |
| --- | --- |
| Cel i instalacja | [GOALS_AND_REQUIREMENTS](requirements/GOALS_AND_REQUIREMENTS.md), [SYSTEM_BASELINE](requirements/SYSTEM_BASELINE.md) |
| Wejścia i jakość danych | [ENTITY_CONTRACT](requirements/ENTITY_CONTRACT.md), [MEASUREMENT_CONTRACT](requirements/MEASUREMENT_CONTRACT.md), [HA_PRICE_SERIES_CONTRACT](requirements/HA_PRICE_SERIES_CONTRACT.md), [PV_FORECAST_CONTRACT](requirements/PV_FORECAST_CONTRACT.md), [LOAD_FORECAST_CONTRACT](requirements/LOAD_FORECAST_CONTRACT.md) |
| Matematyka i niepewność | [OPTIMIZATION_MODEL](requirements/OPTIMIZATION_MODEL.md), [FORECAST_POLICY](requirements/FORECAST_POLICY.md), [CALIBRATION_POLICY](requirements/CALIBRATION_POLICY.md) |
| Sterowanie i bezpieczeństwo | [ARCHITECTURE](requirements/ARCHITECTURE.md), [CONTROL_STRATEGY](requirements/CONTROL_STRATEGY.md), [CURRENT_CONTROLLER_MODEL](requirements/CURRENT_CONTROLLER_MODEL.md), [EXECUTION_CONTRACT](requirements/EXECUTION_CONTRACT.md), [PV_EXPORT_POLICY](requirements/PV_EXPORT_POLICY.md) |
| Prezentacja i walidacja | [DECISION_LOGGING](requirements/DECISION_LOGGING.md), [HA_DASHBOARD](requirements/HA_DASHBOARD.md), [TEST_SCENARIOS](requirements/TEST_SCENARIOS.md), [BACKTEST_VALIDATION](requirements/BACKTEST_VALIDATION.md) |
| Dowody i nierozwiązane kwestie | [HA_ENTITY_SNAPSHOT_2026-10-19](requirements/HA_ENTITY_SNAPSHOT_2026-10-19.md) (historyczny odczyt), [OPEN_ITEMS](requirements/OPEN_ITEMS.md) |

**Wskazówki dla Codexa:** [AGENTS.md](AGENTS.md). Dokumenty z `requirements/` zawierają **przypadki testowe do napisania**, a nie wyniki testów. Ustalonym nazwom encji nie wolno przypisywać fizycznej funkcji bez sprawdzenia.

## Kolejność wdrożenia

1. **M1 — fundament:** manifest, config/options flow, tłumaczenia, setup/unload i testy; zero wywołań sterujących.
2. **M2 — wejścia:** mapowanie, parser cen, prognozy PV, historia zużycia, jakość czasu/znaków/jednostek.
3. **M3 — plan:** model fizyczny, ekonomia, dry-run, porównanie alternatyw i rejestr każdej decyzji.
4. **M4 — HA UX:** encje, panel, widoczne przyczyny, zgody i historia decyzji.
5. **M5 — walidacja:** deterministyczne testy i backtest walk-forward bez przyszłych danych, z kontrolą curtailment.
6. **M6 — opcjonalne polecenia:** wyłącznie po zamknięciu właściwych P0 z [OPEN_ITEMS](requirements/OPEN_ITEMS.md), fizycznych testach i świadomym włączeniu przez użytkownika.

**Odbiór każdej iteracji:** podać zmienione pliki, testy naprawdę uruchomione, testy zablokowane, założenia i aktualne P0/P1. Nie podawać wyników symulacji jako oszczędności osiągniętych na instalacji.
