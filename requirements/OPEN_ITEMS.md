# Blokery i decyzje do zamknięcia

Dokument zawiera **wyłącznie niepotwierdzone elementy**, nie powtarza ustalonych celów. Codex ma zamykać pozycje dowodem (źródło/odczyt/test), a nie zgadywaniem wartości. Brak punktów krytycznych blokuje **sterowanie**, nie blokuje implementacji monitoringu/dry-run.

## P0 — obowiązkowe przed rzeczywistymi poleceniami

**Ustalone projektowo, bez oczekiwania na dalsze decyzje użytkownika:** kontrakt wejść/wyjść, sposób fizycznej walidacji komend, priorytety fail-safe i tryb monitor/dry-run opisują [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md) i [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md). Punkty poniżej dotyczą **dowodów z aktualnego HA i realnego sprzętu**, nie wyboru algorytmu.

- [ ] **Kontrakt HA — etap 2:** aktualny odczyt 19.10.2026 potwierdził istniejące encje i jednostki PV, domu, sieci, SOC, cen i sterowań ([HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md)). Nadal potrzebne są **atrybuty przyszłych cen i godzinowego PV**, weryfikacja pomiaru w obu kierunkach oraz mapowania AC/DC. Następny wąski odczyt: [HA_TIMESERIES_CAPTURE.md](HA_TIMESERIES_CAPTURE.md).
- [ ] **Mapa zapisów Deye:** zakresy polityki Energy Co-Pilot **ustalone**: `number.sun12k_maximum_battery_charge_current` **0–50 A**, `number.sun12k_maximum_battery_discharge_current` **0–100 A**, `number.sun12k_maximum_battery_grid_charge_current` **0–50 A** — ignorować błędne granice HA ±16 777 220 A. **Przyjęte projektowo:** trzy encje HA mają właściwe funkcje zgodnie z nazwami i [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md); Co-Pilot **nie używa rejestrów Modbus ani bezpośredniego dostępu do falownika**. **Do sprawdzenia fizycznie przed zapisami przez usługi HA:** zachowanie urządzenia przy nastawach, zwłaszcza 0 A, TOU, SOC i bezpieczne zatrzymanie. Szczegóły: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md#limity-prądów-ustalone-przez-użytkownika--obowiązujące-dla-energy-co-pilot).
- [ ] **Backend sterowania w czasie:** wybór architektury do implementacji dry-run rozstrzygnięto na rzecz **current-first**, przy zastanym TOU. Dynamiczne TOU pozostaje opcjonalne do oceny w symulacji; nie jest wymagane do startu monitoringu. Warunki przed fizycznym sterowaniem: potwierdzić, że limity prądu są jedynie maksimami, reguły ładowania z sieci wymagają TOU/Grid Charge, trwałe nastawy są bezpieczne po zaniku HA, a SOC w TOU nie steruje ładowaniem PV. Szczegóły i testy: [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md) oraz [CURRENT_CONTROLLER_MODEL.md](CURRENT_CONTROLLER_MODEL.md) — **reguła przeliczenia mocy na A i decyzji w kwadransach jest już określona**; nie jest wymagany dodatkowy wybór wzoru przez użytkownika.
- [ ] **Separacja źródeł eksportu:** udowodnić, że automatyczny eksport PV nie wywoła eksportu baterii. **Nie** traktować starych encji `battery_controller.*` jako aktywnego kontrolera, źródła danych ani blokady — użytkownik potwierdził, że są to nieaktywne pozostałości. Weryfikować wyłącznie realne, zaobserwowane konflikty z innym działającym sterowaniem.
- [ ] **Fail-safe bez dostępnego HA:** przetestować zachowanie aktywnych nastaw po przerwaniu integracji, Wi-Fi i całego HA; zapewnić niezależny, skuteczny powrót do uzgodnionego trybu fabrycznego lub nie zezwalać na automatykę.
- [ ] **Limity urządzeń:** rzeczywisty SOC minimalny, moc/prąd/temperatura, BMS, ograniczenia importu/eksportu, częstotliwość zapisów i potwierdzenie wykonania.
- [ ] **Test świadomie nadzorowany:** dopiero po punktach powyżej sprawdzić osobno każdy zapis i powrót do nastaw; bez automatycznego wykonywania przez Codexa.

## P1 — wymagane do wiarygodnego planowania i kosztów

- [ ] Sprawdzić godzinową / 15-minutową **strukturę przyszłych cen zakupu i spot**, timestamps, DST i koniec faktycznie opublikowanego okresu. **Zamknięto:** użytkownik potwierdził, że HA zawiera wszystkie opłaty i taryfy w cenie zakupu; Co-Pilot nie nalicza ich drugi raz. Eksport netto liczyć wg przekazanej prowizji Vindstød 0,0215 DKK/kWh.
- [ ] Godzinowy profil PV z Forecast.Solar, jego jakość i horyzont; nie polegać tylko na łącznych prognozach na dziś/jutro. **Weryfikacja prognozy musi odróżniać rzeczywistą produkcję od potencjalnej produkcji w okresach curtailment**: potrzebne są sygnały ograniczania/MPPT lub wiarygodne przesłanki oznaczające przedziały jako nieodpowiednie do kalibracji. Brak pomiaru potencjału nie pozwala obliczać „utraconych kWh” jako różnicy od prognozy.
- [ ] Historia zużycia, importu/eksportu i SOC o wystarczającej rozdzielczości; dane wieloletnie mogą być zagregowane.
- [ ] **Zebrać dane do kalibracji** sprawności torów AC/DC, rzeczywistego kosztu marginalnego degradacji i prognozy zużycia. **Metoda i założenia rozstrzygnięte** w [CALIBRATION_POLICY.md](CALIBRATION_POLICY.md): diagnostyczne sprawności 0,9487/0,9487 są założeniem, nie dowodem; EFC/model ekonomiczny jawnie zależą od danych o trwałości, nie od stałej z sufitu. Zapewnić migawki prognoz do testów `walk-forward` i ocenę reprezentatywności bez curtailment.
- [ ] Sprawdzić praktyczną częstotliwość replanowania i jakość slotów 15-minutowych, **skalibrować wartość kontynuacyjną energii końcowej** i symulowany baseline Deye metodą `walk-forward` ([FORECAST_POLICY.md](FORECAST_POLICY.md), [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md)). **Uzgodniony horyzont: do końca faktycznie opublikowanych cen**, bez arbitralnych 48 godzin; około 13:00 dochodzą ceny kolejnej doby, jeśli źródło je faktycznie udostępni.

Dokument matematyczny: [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md). Scenariusze akceptacyjne: [TEST_SCENARIOS.md](TEST_SCENARIOS.md). Kontrakt wykonawcy: [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md). Przekazanie programiście: [DEVELOPER_HANDOFF.md](DEVELOPER_HANDOFF.md).

## P2 — UX i dystrybucja

- [ ] Zweryfikować uruchomieniowy rejestr decyzji w HA: każdy wybór, w tym `idle`, jego ceny, prognozy, wariant bazowy, wynik DKK i powody muszą być widoczne i możliwe do odtworzenia. Projekt i 10 testów LOG: [DECISION_LOGGING.md](DECISION_LOGGING.md).

- [ ] Zweryfikować implementację zatwierdzania pojedynczych propozycji w natywnym HA; **projektowo ustalone**: przyciski w panelu, identyfikator planu/propozycji, jawny `expires_at`, brak przenoszenia zgody po zmianie planu i brak jej wznowienia po restarcie. Dokładny czas ważności, interakcje z wyłączonym HA oraz kanał powiadomień wymagają testów.
- [ ] Wdrożeniowo zatwierdzić listę konkretnych encji i wygląd dashboardu; **specyfikacja funkcjonalna jest gotowa** w [HA_DASHBOARD.md](HA_DASHBOARD.md) i opiera się na natywnym HA, bez drugiej aplikacji.
- [ ] Po powstaniu działającego pakietu: instrukcja instalacji, HACS, aktualizacji i odzyskiwania po błędzie.

## Decyzje już podjęte — nie otwierać ponownie

Integracja custom_components w HA; wykorzystanie istniejących encji i bez zmian w ESPHome/Modbus; minimalizacja rachunku netto; automatyczne opłacalne ładowanie z sieci **po spełnieniu P0**; każda celowa sprzedaż z baterii wymaga zgody; brak stałego SOC na noc i brak obowiązkowego backupu.
