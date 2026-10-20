# Otwarte kwestie i blokady

**Stan: 20.10.2026.** To lista **niezamkniętych dowodów**, a nie powtórzenie decyzji projektowych. Brak P0 blokuje wyłącznie przypisaną funkcję sterującą; **nie** blokuje etapów M1–M5 (`monitor/dry_run`). Zamykać punkt wyłącznie na podstawie odczytu, testu lub dokumentu z datą i przypisaną zdolnością.

## P0 — przed pierwszym realnym zapisem

- [ ] **Topologia i jakość pomiarów (znaki potwierdzone):** 20.10.2026 użytkownik potwierdził: sieć + import / - eksport; bateria + rozładowanie / - ładowanie. Potwierdzone przez użytkownika: `sensor.pv_sum` to suma mocy na wejściach DC PV falownika, niezależna od późniejszego podziału energii przez falownik; nie jest to dostępny potencjał produkcji przy ograniczeniu PV. Otwarte do automatycznej weryfikacji przez Codexa (bez kolejnych pytań o umiejscowienie sensorów): czy `battery_output_power` odpowiada mocy DC `battery_voltage * battery_output_current`, punkty pomiaru pozostałych mocy AC, synchronizacja i jakość próbek. W migawce 19.10 wartości 56,69 V * 0,35 A = 19,84 W wobec 19 W mocy baterii wskazują na pomiar DC, lecz nie dowodzą kalibracji, kierunku obliczania mocy we wszystkich stanach ani sprawności torów. [MEASUREMENT_CONTRACT](MEASUREMENT_CONTRACT.md).
- [ ] **Sterowania prądem / 0 A — użytkownik potwierdził działanie:** 20.10.2026 użytkownik potwierdził, że Deye przyjmuje zadane nastawy i realizuje ich fizyczny skutek. **Nie pytać ponownie o zasadę działania ani każdą wartość.** Implementacja ma sprawdzić stan i odpowiedź API, faktyczny krok jednostki, konflikty TOU/Grid Charge/SOC/BMS i procedurę bezpiecznego powrotu, gdy będzie gotowa. Granice 0–50/0–100/0–50 A to polityka Co-Pilot; błędne min/max HA nie upoważniają do przekroczenia limitów. [ENTITY_CONTRACT](ENTITY_CONTRACT.md), [CURRENT_CONTROLLER_MODEL](CURRENT_CONTROLLER_MODEL.md).
- [ ] **Zezwolenie na eksport PV:** użytkownik potwierdził 20.10.2026, że w **obecnej konfiguracji** `switch.sun12k_solar_sell` dotyczy wyłącznie nadwyżki PV, a sprzedaż energii z baterii jest wyłączona. Przed live nadal sprawdzić niezależnie rzeczywisty eksport przy ON/OFF oraz czy późniejsze zmiany TOU/pozostałych nastaw nie znoszą tej separacji. [PV_EXPORT_POLICY](PV_EXPORT_POLICY.md).
- [ ] **Bezpieczeństwo po utracie HA — ryzyko ekonomiczne zaakceptowane:** 20.10.2026 użytkownik zaakceptował pozostawanie ostatnich nastaw Deye po awarii HA, nawet jeśli nie są optymalne cenowo. Implementacja ma wykrywać/raportować awarię po powrocie, odczytać nastawy i przeliczyć plan; trzeba jednak zachować ochronę fizyczną BMS/falownika i respektować 20% min SOC oraz ograniczenia zgód (szczególnie eksportu baterii). Nie żądać od użytkownika kolejnego potwierdzenia samego utrzymania nastaw. [EXECUTION_CONTRACT](EXECUTION_CONTRACT.md). [EXECUTION_CONTRACT](EXECUTION_CONTRACT.md).
- [ ] **Limity sprzętowe:** potwierdzić ograniczenia napięć, temperatur, BMS, SOC, mocy AC/DC, importu/eksportu, interwału zapisów i reakcje na niepowodzenia.
- [ ] **Test nadzorowany:** osobno zatwierdzony przez użytkownika test każdej proponowanej akcji HA, z wyjściowymi nastawami, niezależnym pomiarem skutku, sposobem anulowania i planem przywrócenia. **Codex nie wykonuje go samodzielnie.**
- [ ] **Eksport z baterii (odrębna zdolność):** sterowanie źródłem, niezależny pomiar limitu kWh, zakończenie po utracie HA i zgoda na każdą propozycję; bez tego funkcja pozostaje wyłączona.

## P1 — przed wiarygodnym planem i deklaracją korzyści

- [ ] **Cena blisko progu 0,40:** sprawdzić rozbieżność między zaokrąglonym `raw_*.price` i dokładniejszym `current_price`; przy sprzecznych decyzjach progowych nie włączać eksportu, zgłosić `PRICE_THRESHOLD_AMBIGUOUS`. Ustalić/testować źródło dokładności i moment przejścia ceny (również przy restartach). [HA_PRICE_SERIES_CONTRACT](HA_PRICE_SERIES_CONTRACT.md).
- [ ] **Forecast.Solar:** użytkownik potwierdził obecność akcji w UI, lecz nie jej odpowiedzi. W M2 zweryfikować wybrany `config_entry`, strukturę `wh_period`, UTC i pokrycie. Dalsza kalibracja tylko na przedziałach bez curtailment. [PV_FORECAST_CONTRACT](PV_FORECAST_CONTRACT.md).
- [ ] **Historia Recorder:** sprawdzić retencję, rozdzielczość i jakość źródłowych trzech serii składających się na `home_energy_consumption` **w każdym historycznym slocie**, nie tylko stan obecny; zamiana `unavailable` na zero może zatruć model. [LOAD_FORECAST_CONTRACT](LOAD_FORECAST_CONTRACT.md), [MEASUREMENT_CONTRACT](MEASUREMENT_CONTRACT.md).
- [ ] **Dane do ekonomii — stawka degradacji zamknięta:** użytkownik ustalił stałe **0,40 DKK/kWh rozładowania baterii DC**, liczone jednokrotnie i uwzględniane również przy decyzjach o zakupie energii na ładowanie. Minimum SOC = **20% twardo**. Do pomiarów / walidacji implementacyjnej pozostają sprawności AC/DC, użyteczna pojemność, rzeczywiste ograniczenia BMS i jakość prognoz; 0,9487 to ilustracja, nie pomiar. [CALIBRATION_POLICY](CALIBRATION_POLICY.md).
- [ ] **MPC i uczciwy benchmark:** porównać optymalizację z autonomicznym grid charge i dynamicznym TOU z realnym baseline, wartość SOC po końcu opublikowanych cen, migawki prognoz sprzed chwili decyzji, porównanie `walk-forward` z realnym stanem bazowym. Nie raportować hipotetycznego zysku jako oszczędności. [BACKTEST_VALIDATION](BACKTEST_VALIDATION.md).

## P2 — przed dystrybucją

- [ ] Potwierdzić trwały i przeszukiwalny rejestr **każdej decyzji** w HA oraz bezpieczną retencję, bez zalewania logów. [DECISION_LOGGING](DECISION_LOGGING.md).
- [ ] Sprawdzić UX zgody/odwołania pojedynczej propozycji i dashboard na działającym HA. [HA_DASHBOARD](HA_DASHBOARD.md).
- [ ] Po napisaniu kodu: instrukcja instalacji, testy kompatybilności wybranej wersji HA i ewentualnie HACS.

## Decyzje zamknięte (nie są blokadami)

Integracja natywna HA, bez Modbus/ESPHome; zakup i sprzedaż dokładnie z dwóch encji HA; cena progowa eksportu PV 0,40 DKK/kWh; brak eksportu baterii bez zgody; **użytkownik zatwierdził autonomiczne ładowanie z sieci i zmianę sześciu TOU**; ręczne zmiany w trakcie automatyki mogą być nadpisane przy następnym planie (STOP ma pierwszeństwo); eksport baterii tylko po indywidualnej zgodzie; **jedyny cel: minimalizacja łącznego kosztu w dostępnym horyzoncie**; początek `monitor/dry_run`; brak dodatkowej rezerwy SOC na blackout ponad **twarde minimum 20%**; stała degradacja **0,40 DKK/kWh rozładowania DC**, uwzględniana przy decyzjach zakupowych; akceptacja ostatnich nastaw po awarii HA. Pozostałe szczegóły w dokumentach normatywnych, nie powielać tutaj.


## Uprawnienia projektowe potwierdzone 20.10.2026 (nie pytać ponownie)

- Automatyczne ładowanie z sieci bez potwierdzania każdego cyklu, wyłącznie gdy opłacalne po cenie zakupu, stratach i degradacji.
- Autonomiczne zmiany **wszystkich sześciu TOU** są dopuszczone, o ile plan jest poprawny i bezpiecznie wykonywalny; wcześniejszy zakaz automatyki TOU dotyczył etapu implementacyjnego, nie uprawnień użytkownika.
- Co-Pilot jest nadrzędnym sterownikiem w trybie automatycznym: ręczna zmiana zwykłej nastawy może zostać nadpisana przy kolejnym planie. STOP/wyłączenie automatyki i limity bezpieczeństwa mają pierwszeństwo.
- Eksport baterii zachować jako opcjonalną funkcję z **osobnym zatwierdzeniem każdej operacji**; brak zgody = brak eksportu baterii.
- Cel nadrzędny: **minimalizacja całkowitego kosztu energii w całym dostępnym horyzoncie**, nie priorytet autokonsumpcji. Uwzględniać ceny, sprzedaż PV, degradację, sprawność, SOC i wartość końcową baterii; priorytet autokonsumpcji nie może zastąpić funkcji celu.
