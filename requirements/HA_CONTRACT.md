# Kontrakt Home Assistant — źródła danych i sterowanie

Wymagania ekonomiczne i uprawnienia: [REQUIREMENTS.md](REQUIREMENTS.md). Fizyczna realizacja: [EXECUTION.md](EXECUTION.md).

## Czujniki
| Rola | Encja | Interpretacja |
|---|---|---|
| Produkcja PV DC | `sensor.pv_sum` | **PV1 + PV2 na wejściach DC falownika**, niezależnie od podziału energii |
| PV1 / PV2 | `sensor.sun12k_pv1_power`, `sensor.sun12k_pv2_power` | Składowe PV; nie dodawać drugi raz do `pv_sum` |
| Sieć | `sensor.sun12k_total_grid_power` | **Dodatnie = import, ujemne = eksport** |
| Bateria | `sensor.sun12k_battery_output_power` | **Dodatnie = rozładowanie, ujemne = ładowanie** |
| Napięcie/prąd baterii | `sensor.sun12k_battery_voltage`, `sensor.sun12k_battery_output_current` | Weryfikować relację P≈V·I i stronę DC z danymi HA |
| SOC | `sensor.sun12k_battery_capacity` | %; twarda dolna granica polityki w REQUIREMENTS |
| Zużycie domu | `sensor.home_energy_consumption` | Pochodna `pv_sum + total_grid_power + battery_output_power` |
| Alternatywny odczyt sieci | `sensor.sun12k_out_of_grid_total_power_2` | Nie dodawać do `total_grid_power` |
| Energia dzienna | `sensor.sun12k_daily_production`, `sensor.sun12k_today_charge_of_the_battery`, `sensor.sun12k_today_discharge_of_the_battery` | Kumulowane kWh, nie odrębne źródła mocy |

Normalizacja mocy: `grid_import=max(0,P_grid)`, `grid_export=max(0,-P_grid)`, `battery_discharge=max(0,P_bat)`, `battery_charge=max(0,-P_bat)`. Wszystkie wartości wejściowe początkowo [W], następnie konwersja na kW. Kierunki potwierdził użytkownik; nie zadawać mu znów tych pytań. `sensor.pv_sum` pokazuje **moc faktycznie przyjętą na wejściach falownika**, a nie potencjał produkcji ograniczonej (curtailment). Nie doliczać PV→bateria jako dodatkowej produkcji.

**Dom jest szablonem, nie niezależnym licznikiem.** Używa `float(0)`, co maskuje `unavailable` i tworzy możliwe fałszywe odczyty także w historii. Dla każdego slotu uczenia, backtestu i decyzji sprawdź dostępność i aktualność wszystkich źródłowych PV/grid/battery, ich synchronizację i jednostki. Oznacz `invalid_input`, `historical_quality_unverifiable` i `snapshot_not_synchronous`, zamiast zakładać zero. Zerowa reszta z równania szablonu nie dowodzi fizycznej sprawności. Strony AC/DC i straty wymaga model [OPTIMIZATION.md](OPTIMIZATION.md).

## Ceny
- `sensor.energi_data_service`: końcowa cena zakupu; `sensor.energi_data_spotpris`: cena sprzedaży. Ceny z HA są danymi końcowymi; **bez dodawania lub odejmowania opłat**.
- Obie encje udostępniają `attributes.raw_today`, `raw_tomorrow`, `tomorrow_valid` oraz rekordy `hour` i `price`. Odczytaj tylko rzeczywiście opublikowane dane, wspólne ważne przedziały kupna i sprzedaży.
- Parsuj godzinę do UTC, zachowaj strefę Europe/Copenhagen i zmiany DST (23/25 godzin), wykryj puste, duplikowane, przeterminowane i rozbieżne sloty. **Nie dopisuj cen nieopublikowanych**.
- Surowe ceny godzinowe mogą być zaokrąglone do 3 miejsc, a `current_price` dokładniejsze. Gdy np. `raw.price=0.400` i `current_price=0.3996` dają sprzeczne decyzje co do eksportu PV, oznacz `PRICE_THRESHOLD_AMBIGUOUS`, bez polecenia ON. Nie modyfikuj progu cenowego „histerezą”.

## Prognozy
- Forecast.Solar w HA: użytkownik potwierdził widoczność `forecast_solar.get_forecast`. Przy M2 sprawdź rzeczywisty `config_entry`, odpowiedź, `wh_period`/jednostki, daty, UTC i pokrycie. Nie rekonstruuj fikcyjnych przedziałów z samej sumy dziennej.
- Forecast PV i historia: przechowuj wersje prognoz oraz ich czas **sprzed** prognozowanego okresu. Pełna bateria i Solar Sell OFF mogą oznaczać curtailment; nie ucz błędu Forecast.Solar na takich przedziałach bez potwierdzenia, że produkcja była nieograniczona.
- Prognoza zapotrzebowania: Recorder z `home_energy_consumption`, profil na 15 min z porą dnia/tygodnia/sezonem i kontrolą źródeł historycznych. Używaj tylko danych znanych w chwili decyzji.
- Sprawności PV→bateria, grid→bateria, bateria→AC, PV→AC są osobne. Parametry `0.9487` i `0.97` to historyczne wartości konfiguracyjne, **nie zmierzone wyniki**. Kalibrować z obserwowalnych okresów, raportując niepewność.

## Encje wykonawcze
| Akcja | Encja |
|---|---|
| Limit prądu ładowania 0–50 A | `number.sun12k_maximum_battery_charge_current` |
| Limit rozładowania 0–100 A | `number.sun12k_maximum_battery_discharge_current` |
| Limit ładowania z sieci 0–50 A | `number.sun12k_maximum_battery_grid_charge_current` |
| Global Grid Charge | `switch.sun12k_grid_charge` |
| Eksport nadwyżki PV | `switch.sun12k_solar_sell` |
| TOU ON/OFF | `switch.sun12k_time_of_use` |
| TOU 1…6: start, power, capacity | `number.sun12k_time_point_N_start`, `number.sun12k_time_point_N_power`, `number.sun12k_time_point_N_capacity` |
| TOU 1…6: Grid Charge | `switch.sun12k_time_point_N_charge_enable` |

Użytkownik potwierdził poprawne działanie nastaw 0 A i pozostałych regulatorów. W oprogramowaniu nadal walidować zakres/odczyt; HA potrafi zgłaszać absurdalne min/max ±16 777 220 A. Nie stosować ich. Limity są maksimum, **nie gwarantowaną mocą**. Nie używać nieaktywnych pozostałości `battery_controller.*`. Nie zmieniać YAML/ESPHome/Modbus. Testy: [VALIDATION.md](VALIDATION.md).
