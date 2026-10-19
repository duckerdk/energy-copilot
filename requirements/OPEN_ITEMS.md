# Blokery i decyzje do zamknięcia

Dokument zawiera **wyłącznie niepotwierdzone elementy**, nie powtarza ustalonych celów. Codex ma zamykać pozycje dowodem (źródło/odczyt/test), a nie zgadywaniem wartości. Brak punktów krytycznych blokuje **sterowanie**, nie blokuje implementacji monitoringu/dry-run.

## P0 — obowiązkowe przed rzeczywistymi poleceniami

**Ustalone projektowo, bez oczekiwania na dalsze decyzje użytkownika:** kontrakt wejść/wyjść, sposób fizycznej walidacji komend, priorytety fail-safe i tryb monitor/dry-run opisują [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md) i [EXECUTION_CONTRACT.md](EXECUTION_CONTRACT.md). Punkty poniżej dotyczą **dowodów z aktualnego HA i realnego sprzętu**, nie wyboru algorytmu.

- [ ] **Odczyt kontraktu HA:** zweryfikować aktualność, jednostki, atrybuty prognoz i przypisanie fizycznych torów. Znamy 11 nazw z prototypu oraz 8 dodatkowych z logu HA (historyczne, bez potwierdzenia obecnej dostępności). Jednorazowy odczyt: [HA_READONLY_CAPTURE.md](HA_READONLY_CAPTURE.md). Rejestr: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md).
- [ ] **Mapa zapisów Deye:** udowodnić fizyczny skutek każdej akcji ładowania z sieci/PV, eksportu, docelowego SOC, wymuszenia rozładowania i harmonogramu. Rozwiązać konflikt znaczenia number.sun12k_maximum_battery_grid_charge_current.
- [ ] **Separacja źródeł eksportu:** udowodnić, że automatyczny eksport PV nie może niezamierzenie wywołać eksportu z baterii.
- [ ] **Fail-safe bez dostępnego HA:** przetestować zachowanie aktywnych nastaw po przerwaniu integracji, Wi-Fi i całego HA; zapewnić niezależny, skuteczny powrót do uzgodnionego trybu fabrycznego lub nie zezwalać na automatykę.
- [ ] **Limity urządzeń:** rzeczywisty SOC minimalny, moc/prąd/temperatura, BMS, ograniczenia importu/eksportu, częstotliwość zapisów i potwierdzenie wykonania.
- [ ] **Test świadomie nadzorowany:** dopiero po punktach powyżej sprawdzić osobno każdy zapis i powrót do nastaw; bez automatycznego wykonywania przez Codexa.

## P1 — wymagane do wiarygodnego planowania i kosztów

- [ ] Weryfikacja godzinowej / 15-minutowej serii **cen zakupu z opłatami** i **spot**, dat, DST oraz kompletności taryf; w tym potwierdzenie na fakturze rozliczenia sprzedaży Vindstød (0,0215 DKK/kWh jako znana prowizja).
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
