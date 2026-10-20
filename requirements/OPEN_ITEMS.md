# Otwarte kwestie i blokady

**Stan: 20.10.2026.** To lista **niezamkniętych dowodów**, a nie powtórzenie decyzji projektowych. Brak P0 blokuje wyłącznie przypisaną funkcję sterującą; **nie** blokuje etapów M1–M5 (`monitor/dry_run`). Zamykać punkt wyłącznie na podstawie odczytu, testu lub dokumentu z datą i przypisaną zdolnością.

## P0 — przed pierwszym realnym zapisem

- [ ] **Topologia i jakość pomiarów (znaki potwierdzone):** 20.10.2026 użytkownik potwierdził: sieć + import / - eksport; bateria + rozładowanie / - ładowanie. Potwierdzone przez użytkownika: `sensor.pv_sum` to suma mocy na wejściach DC PV falownika, niezależna od późniejszego podziału energii przez falownik; nie jest to dostępny potencjał produkcji przy ograniczeniu PV. Otwarte: punkt pomiaru mocy baterii i przepływów AC, synchronizacja oraz jakość próbek. [MEASUREMENT_CONTRACT](MEASUREMENT_CONTRACT.md).
- [ ] **Sterowania prądem / 0 A:** potwierdzić fizyczne działanie trzech regulatorów, ich krok i zakres na urządzeniu, priorytety TOU/Grid Charge/SOC/BMS oraz bezpieczną procedurę wyjścia. Granice 0–50/0–100/0–50 A to tylko polityka Co-Pilot; błędne min/max encji HA nie upoważniają do zapisu. [ENTITY_CONTRACT](ENTITY_CONTRACT.md), [CURRENT_CONTROLLER_MODEL](CURRENT_CONTROLLER_MODEL.md).
- [ ] **Zezwolenie na eksport PV:** wykazać, że ON `switch.sun12k_solar_sell` nie może spowodować niezamierzonego eksportu energii z baterii, a OFF działa zgodnie z oczekiwaniem. Bez niezawodnej separacji nie automatyzować tej akcji. [PV_EXPORT_POLICY](PV_EXPORT_POLICY.md).
- [ ] **Bezpieczeństwo po utracie HA:** rzeczywiście przetestować stan przy zaniku integracji, HA i łączności; dla operacji wymagających zakończenia o danej godzinie potwierdzić **niezależny** mechanizm wyłączenia/ograniczenia. Ostatnie nastawy Deye pozostają zapisane. [EXECUTION_CONTRACT](EXECUTION_CONTRACT.md).
- [ ] **Limity sprzętowe:** potwierdzić ograniczenia napięć, temperatur, BMS, SOC, mocy AC/DC, importu/eksportu, interwału zapisów i reakcje na niepowodzenia.
- [ ] **Test nadzorowany:** osobno zatwierdzony przez użytkownika test każdej proponowanej akcji HA, z wyjściowymi nastawami, niezależnym pomiarem skutku, sposobem anulowania i planem przywrócenia. **Codex nie wykonuje go samodzielnie.**
- [ ] **Eksport z baterii (odrębna zdolność):** sterowanie źródłem, niezależny pomiar limitu kWh, zakończenie po utracie HA i zgoda na każdą propozycję; bez tego funkcja pozostaje wyłączona.

## P1 — przed wiarygodnym planem i deklaracją korzyści

- [ ] **Cena blisko progu 0,40:** sprawdzić rozbieżność między zaokrąglonym `raw_*.price` i dokładniejszym `current_price`; przy sprzecznych decyzjach progowych nie włączać eksportu, zgłosić `PRICE_THRESHOLD_AMBIGUOUS`. Ustalić/testować źródło dokładności i moment przejścia ceny (również przy restartach). [HA_PRICE_SERIES_CONTRACT](HA_PRICE_SERIES_CONTRACT.md).
- [ ] **Forecast.Solar:** użytkownik potwierdził obecność akcji w UI, lecz nie jej odpowiedzi. W M2 zweryfikować wybrany `config_entry`, strukturę `wh_period`, UTC i pokrycie. Dalsza kalibracja tylko na przedziałach bez curtailment. [PV_FORECAST_CONTRACT](PV_FORECAST_CONTRACT.md).
- [ ] **Historia Recorder:** sprawdzić retencję, rozdzielczość i jakość źródłowych trzech serii składających się na `home_energy_consumption` **w każdym historycznym slocie**, nie tylko stan obecny; zamiana `unavailable` na zero może zatruć model. [LOAD_FORECAST_CONTRACT](LOAD_FORECAST_CONTRACT.md), [MEASUREMENT_CONTRACT](MEASUREMENT_CONTRACT.md).
- [ ] **Dane do ekonomii:** sprawność AC/DC i jej zależność od mocy, rzeczywisty koszt marginalny degradacji, dostępny SOC i ograniczenia BMS. Parametry 0,9487 to ilustracja, nie pomiar. [CALIBRATION_POLICY](CALIBRATION_POLICY.md).
- [ ] **MPC i uczciwy benchmark:** modelowalny zbiór działań current-first z istniejącym TOU, wartość SOC po końcu opublikowanych cen, migawki prognoz sprzed chwili decyzji, porównanie `walk-forward` z realnym stanem bazowym. Nie raportować hipotetycznego zysku jako oszczędności. [BACKTEST_VALIDATION](BACKTEST_VALIDATION.md).

## P2 — przed dystrybucją

- [ ] Potwierdzić trwały i przeszukiwalny rejestr **każdej decyzji** w HA oraz bezpieczną retencję, bez zalewania logów. [DECISION_LOGGING](DECISION_LOGGING.md).
- [ ] Sprawdzić UX zgody/odwołania pojedynczej propozycji i dashboard na działającym HA. [HA_DASHBOARD](HA_DASHBOARD.md).
- [ ] Po napisaniu kodu: instrukcja instalacji, testy kompatybilności wybranej wersji HA i ewentualnie HACS.

## Decyzje zamknięte (nie są blokadami)

Integracja natywna HA, bez Modbus/ESPHome; zakup i sprzedaż dokładnie z dwóch encji HA; cena progowa eksportu PV 0,40 DKK/kWh; brak eksportu baterii bez zgody; podstawowy backend current-first; początek `monitor/dry_run`; brak obowiązkowej rezerwy SOC na blackout. Pozostałe szczegóły w dokumentach normatywnych, nie powielać tutaj.
