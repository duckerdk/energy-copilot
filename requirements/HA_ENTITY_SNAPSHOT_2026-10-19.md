# Aktualny odczyt encji HA — 19.10.2026

**Źródło:** plik `wynik.txt` przekazany przez użytkownika, rezultat odczytowego szablonu HA; wartości i `last_updated` pochodzą z jednego zrzutu około **13:24 UTC (15:24 CEST)** 19.10.2026. **Status: zaobserwowane encje i wartości, a nie test aktywnych zapisów lub dowód dostępności historycznych profili.** Nie przechowywać kopii surowego zrzutu z niezwiązanymi urządzeniami w repozytorium.

## 1. Mapowanie bieżących odczytów

| Rola planera | Faktycznie obecny `entity_id` | Stan w zrzucie | Jednostka | Pewność |
| --- | --- | ---: | --- | --- |
| PV rzeczywiste | `sensor.pv_sum` | 3034 | W → **3,034 kW** | Nazwa i jednostka potwierdzone; punkt DC/AC i curtailment nieustalone |
| PV MPPT1 | `sensor.sun12k_pv1_power` | 2387 | W | Zaobserwowane |
| PV MPPT2 | `sensor.sun12k_pv2_power` | 647 | W | Zaobserwowane |
| Dom | `sensor.home_energy_consumption` | 583 | W → **0,583 kW** | Zaobserwowane; definicja względem wyjścia LOAD do wyjaśnienia |
| Alternatywny LOAD | `sensor.sun12k_load_totalpower` | 532 | W | Inna wartość niż dom; nie utożsamiać bez sprawdzenia topologii |
| Sieć — net (import/eksport ze znakiem) | `sensor.sun12k_total_grid_power` | −2470 | W → **−2,470 kW** | **Kandydat:** wartość ujemna odpowiada eksportowi w tym zrzucie; drugi znak/import do sprawdzenia |
| Alternatywna moc sieci | `sensor.sun12k_out_of_grid_total_power_2` | −2483 | W | Podobny odczyt co `total_grid_power`; nie sumować dwóch kanałów |
| Bateria moc DC? | `sensor.sun12k_battery_output_power` | +19 | W → **0,019 kW** | **Kandydat:** dodatnia moc baterii pomaga zamknąć bilans przy eksporcie; kierunek znaków i strona DC do sprawdzenia |
| SOC | `sensor.sun12k_battery_capacity` | 97 | % | ID i jednostka potwierdzone; `last_updated` starszy niż inne pomiary, nie dowodzi jednak braku nowych raportów |
| Bateria napięcie | `sensor.sun12k_battery_voltage` | 56,69 | V | Kandydat do walidacji pomiaru `P≈U×I` |
| Bateria prąd | `sensor.sun12k_battery_output_current` | 0,35 | A | Kandydat; zgodność z mocą ~19,84 W, strona i znak wymagają sprawdzenia |
| Temperatura baterii | `sensor.sun12k_battery_temperature` | 21,9 | °C | Pomiar zaobserwowany, nie zastępuje temperatury każdej baterii |
| Wytwarzanie PV dziś | `sensor.sun12k_daily_production` | 23,5 | kWh | Dzienny licznik; sprawdzić reset oraz stronę AC/DC |
| Energia importowana dziś | `sensor.sun12k_daily_energy_bought` | 4,3 | kWh | Dzienny licznik, aktualność/odświeżanie do sprawdzenia |
| Energia eksportowana dziś | `sensor.sun12k_daily_energy_sold` | 4,3 | kWh | Dzienny licznik |
| Energia ładowania magazynu dziś | `sensor.sun12k_today_charge_of_the_battery` | 8,6 | kWh | Dzienny licznik; nieznana strona bilansu |
| Energia rozładowania magazynu dziś | `sensor.sun12k_today_discharge_of_the_battery` | 1,2 | kWh | Dzienny licznik; nieznana strona bilansu |
| Cena spot aktualna | `sensor.energi_data_spotpris` | 1,75508376559425 | DKK/kWh | Pomiar bieżącej ceny; brak atrybutów przyszłych slotów |
| Cena zakupu końcowa | `sensor.energi_data_service` | 2,23828751559425 | DKK/kWh | Użytkownik potwierdził, że cena HA zawiera **wszystkie opłaty i taryfy**; różnica do spot wynika z nich i innych składników, bez podwójnego naliczania |
| Prognoza PV dziś | `sensor.energy_production_today` | 15,865 | kWh | Dobowa suma, nie godzinowe sloty |
| Prognoza PV pozostała dziś | `sensor.energy_production_today_remaining` | 4,431 | kWh | Nie zastępuje informacji o wszystkich przyszłych slotach |
| Prognoza PV jutro | `sensor.energy_production_tomorrow` | 7,536 | kWh | Dobowa suma; potrzebne dane intraday |
| Forecast następne 24h — alternatywny | `sensor.pv_forecast_next_24h` | 51,72 | **brak jednostki** | Nie mapować automatycznie jako 51,72 kWh ani jako pomiar potencjału PV |
| Forecast kontrolera (alternatywny) | `sensor.battery_controller_pv_forecast` | 4,197 | kW | Wyjście **innej** integracji, nie bezpośrednie źródło niezależnej prognozy |
| Prognoza domu kontrolera | `sensor.battery_controller_consumption_forecast` | 2,1 | kW | Wyjście innej integracji, nie historyczny pomiar rzeczywistego poboru |

## 2. Kontrola spójności jednego odczytu

- Dwa pomiary PV: **2387 W + 647 W = 3034 W** — dokładnie tyle co `sensor.pv_sum`. Dobre potwierdzenie agregacji odczytów obu MPPT w chwili zrzutu.
- Równanie przykładowego bilansu **3034 W PV + 19 W baterii = 583 W domu + 2470 W eksportu = 3053 W** zamyka się **numerycznie**. **Uwaga metodologiczna:** trzeba sprawdzić, czy `home_energy_consumption` nie jest *wyliczony* z pozostałych sensorów; wówczas równanie byłoby tautologią. Nie dowodzi niezależności pomiarów, poprawności torów AC/DC ani znaków podczas importu i ładowania. Kontrakt: [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md).
- Odczyty pochodzą z różnych chwil (PV/dom około 13:24:14 UTC, eksport około 13:24:11 UTC, bateria około 13:24:09 UTC). W kontrolerze należy wymagać synchronizacji/tolerancji czasu, nie wymuszać idealnego bilansu z asynchronicznych próbek.
- Prognoza PV „dziś” = 15,865 kWh, a zarejestrowana produkcja = 23,5 kWh. **Odchylenie jest naturalną możliwością prognozowania, nie automatycznym błędem systemu**. Do oceny jakości potrzeba odpowiadających sobie czasów/profili, migawek prognoz i informacji o curtailment, nie wymagać 100% zgodności.
- `last_updated` to czas zmiany stanu/atrybutów HA, **nie musi być** czasem ostatniej telemetrii z urządzenia. Starsza data SOC lub sterowania nie dowodzi samodzielnie, że czujnik przestał działać; potrzebny `last_reported` lub równoważny sygnał nowej próbki, jeśli dostępny.
- Pożądany przychód ze sprzedaży dla aktualnego spot wynosi **1,75508376559425 − 0,0215 = 1,73358376559425 DKK/kWh**, przy założonej przez użytkownika prowizji. **Nie** używać `sensor.energi_data_service` jako ceny sprzedaży.

## 3. Bieżące encje sterowania — potwierdzono ISTNIENIE, nie funkcję fizyczną

| Kandydat | Zrzut | Co pozostaje niewiadome |
| --- | --- | --- |
| `switch.sun12k_solar_sell` | on | Czy wyłącza wyłącznie eksport PV, czy obejmuje również baterię; wpływ na curtailment |
| `switch.sun12k_grid_charge` | on | Priorytety ładowania, interakcja z harmonogramem |
| `switch.sun12k_time_of_use` | on | Skutki i zakres sześciu okien |
| `switch.sun12k_time_point_[1..6]_charge_enable` | wszystkie off | Czy pozostałe pola czasu/mocy/celu SOC nadal działają dla rozładowania |
| `number.sun12k_maximum_battery_charge_current` | 50 A | Co faktycznie limituje, priorytety i BMS |
| `number.sun12k_maximum_battery_discharge_current` | 100 A | Co faktycznie limituje, priorytety i BMS |
| `number.sun12k_maximum_battery_grid_charge_current` | 50 A | Konkretny skutek na PV i sieć nadal niewykazany |
| `number.sun12k_time_point_[1..6]_start` | 2330, 0, 500, 1200, 1500, 2300 | Jednostka i format pól czasu do potwierdzenia (prawdopodobny HHMM, bez dowodu) |
| `number.sun12k_time_point_[1..6]_power` | 4000, 4000, 4002, 4500, 4000, 4000 W | Moc związana z TOU, nie potwierdzona możliwość precyzyjnego sterowania realną mocą baterii |
| `number.sun12k_time_point_[1..6]_capacity` | 20% (wszystkie) | Jak falownik interpretuje cele/granice SOC w tych przedziałach |

**Wada metadanych HA i rozstrzygnięcie użytkownika z 20.10.2026:** trzy regulatory prądu podają w HA **min = −16 777 220 A / max = +16 777 220 A**. Energy Co-Pilot nie korzysta z tych granic. Ustalono własne domknięte zakresy **0–50 A** (`maximum_battery_charge_current`), **0–100 A** (`maximum_battery_discharge_current`) i **0–50 A** (`maximum_battery_grid_charge_current`). To limity logiczne, nie dowód możliwości sprzętu; przed zapisami nadal weryfikujemy fizyczną reakcję, w szczególności znaczenie 0 A. Dokładne wymagania: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md#limity-prądów-ustalone-przez-użytkownika--obowiązujące-dla-energy-co-pilot).

## 4. Pozostałości po Battery Controller — ignorować

W odczycie z 19.10.2026 występowały encje `switch.battery_controller_optimization_enabled`, `select.battery_controller_control_mode` i inne z prefiksem `battery_controller`. **Użytkownik wyjaśnił 20.10.2026, że są to nieaktywne pozostałości po starej integracji.** Nie traktować ich jako działającego kontrolera, blokera, źródła danych ani narzędzia sterowania. Energy Co-Pilot używa zweryfikowanych encji `sun12k_*` i innych wskazanych źródeł HA, a nie wyników starego Battery Controller. Konflikt dotyczy wyłącznie **rzeczywiście aktywnego** zewnętrznego wykonawcy, jeśli taki zostanie zaobserwowany.

## 5. Co TEN odczyt rozstrzyga, a czego nie

**Ustalone:** istnienie wielu potrzebnych encji, ich jednostki, obecne stany i dwie wewnętrzne kontrole bilansu (MPPT→PV i PV+bateria→dom+eksport). Znamy bieżące wartości spot, kandydata ceny zakupu, baterii, PV, domu i mocy eksportu.

**Uzupełnienie 20.10.2026: format przyszłych cen zakupu i spot został później potwierdzony w [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md). Poniższy opis dotyczył stanu wiedzy **wyłącznie w chwili odczytu `wynik.txt`**.

**Nadal nieustalone na podstawie `wynik.txt`:** struktura i kompletność **przyszłych cen kupna/spot** (szablon nie eksportował atrybutów); godzinowe sloty Forecast.Solar; wiarygodność punktów pomiaru DC/AC przy ładowaniu i rozładowaniu; realne limity BMS; ewentualne rzeczywiście aktywne obce sterowanie zapisami; osobne i mierzalne polecenie eksportu **z baterii**; przywrócenie trybu po utracie HA.

**Wniosek bezpieczeństwa:** **nie** włączać sprzętowego executora na podstawie tego zrzutu. Następnym źródłem dowodowym są wyłącznie atrybuty konkretnie zidentyfikowanych źródeł cen i prognoz. Testy akcji wymagają osobnego, świadomie nadzorowanego kroku.
