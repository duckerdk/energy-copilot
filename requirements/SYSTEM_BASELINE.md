# Instalacja i dostępność danych

**Źródło:** dane instalacji przekazane przez użytkownika oraz **odczyt aktualnych encji HA z 19.10.2026** ([HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md)). Nie wykonano żadnego testu zapisów ani fizycznej kalibracji. Samo istnienie encji ≠ potwierdzenie działania sterowania.

| Element | Stan |
| --- | --- |
| Home Assistant | VM na serwerze; dostępne encje falownika |
| Falownik | Deye **SUN-12K-SP04LP3-EU** — model zadeklarowany |
| Łącze falownik–HA | Własny Modbus na ESP32, ESPHome przez Wi-Fi — działa według użytkownika |
| Magazyn | 2 × BSLBATT LiFePO4, 51,2 V, 100 Ah, 5,12 kWh każdy |
| Suma nominalna | **10,24 kWh** — obliczenie 2 × 5,12 kWh |
| Energia między 20–100% SOC | **8,192 kWh nominalnie** — obliczenie, nie energia użyteczna AC |
| Zakres przyjęty | SOC 20–100%, ostatecznie ograniczony przez BMS i falownik |
| Własne przedziały nastaw prądu Co-Pilot | **0–50 A** ładowanie, **0–100 A** rozładowanie, **0–50 A** ładowanie z sieci; limity logiczne użytkownika, nie zakresy fizycznie zweryfikowane |
| Koszt magazynu | **19 000 DKK** według użytkownika |
| Lokalizacja rozliczeń | Dania, obszar DK1 / Nordjylland; N1; Elforbundet/Vindstød |
| Prognoza PV | Forecast.Solar w HA: z dokumentacji wynika, że natywna akcja `forecast_solar.get_forecast` zwraca okresowe `wh_period`/`watts`; **użytkownik potwierdził obecność akcji w Narzędziach deweloperskich → Akcje; zawartość odpowiedzi zostanie sprawdzona przy implementacji**, bez zgadywania danych [PV_FORECAST_CONTRACT.md](PV_FORECAST_CONTRACT.md) |
| Ceny | Energi Data Service: obie encje HA mają `raw_today`/`raw_tomorrow`, `tomorrow_valid` i rekordy `hour`+`price` DKK/kWh (potwierdzone 20.10.2026); [kontrakt](HA_PRICE_SERIES_CONTRACT.md). Co-Pilot pobiera **obie ceny bez zmian**; sam nie oblicza prowizji, podatków ani taryf. Minimalna cena eksportu PV: 0,40 DKK/kWh z `sensor.energi_data_spotpris` [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md) |
| Historia | Recorder / Energy; użytkownik ma historię z kilku lat, rozdzielczość i kompletność **niezweryfikowane** |

W zrzucie potwierdzono m.in. `sensor.sun12k_total_grid_power` (−2470 W przy eksporcie), `sensor.sun12k_battery_output_power` (+19 W), `sensor.pv_sum` (3034 W), `sensor.home_energy_consumption` (583 W) i `sensor.sun12k_battery_capacity` (97%). **Użytkownik potwierdził wzór:** `sensor.home_energy_consumption = sensor.pv_sum + sensor.sun12k_total_grid_power + sensor.sun12k_battery_output_power`. Zgodność bilansu chwilowego **wynika z tego wzoru**; Co-Pilot używa istniejącej encji domu bez potrzeby nowych liczników. Kontrakt testów znaków obu kierunków, AC/DC, liczników i synchronizacji: [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md). Fabryczny harmonogram i możliwość wymuszonego rozładowania istnieją wg użytkownika; nie znamy odpowiednich usług/encji, ograniczeń ani potwierdzeń wykonania.

Nie przyjmować bez pomiarów: sprawności AC↔bateria, wydajności PV, temperatury ogniw, limitów BMS, dopuszczalnych prądów, przepływu baterii do sieci, semantyki sterowań czy dokładności prognoz. Dane ze zrzutów ekranu dotyczą chwili wykonania, nie są stałymi instalacji.

Lista znanych nazw i braków: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md). Warunki uruchomienia: [OPEN_ITEMS.md](OPEN_ITEMS.md).
