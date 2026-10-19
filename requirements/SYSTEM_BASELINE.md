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
| Koszt magazynu | **19 000 DKK** według użytkownika |
| Lokalizacja rozliczeń | Dania, obszar DK1 / Nordjylland; N1; Elforbundet/Vindstød |
| Prognoza PV | Forecast.Solar w HA; godzinowa seria **niezweryfikowana** |
| Ceny | Energi Data Service i istniejące encje HA; atrybuty przyszłych cen **niezweryfikowane** |
| Historia | Recorder / Energy; użytkownik ma historię z kilku lat, rozdzielczość i kompletność **niezweryfikowane** |

W zrzucie potwierdzono m.in. `sensor.sun12k_total_grid_power` (−2470 W przy eksporcie), `sensor.sun12k_battery_output_power` (+19 W), `sensor.pv_sum` (3034 W), `sensor.home_energy_consumption` (583 W) i `sensor.sun12k_battery_capacity` (97%). Bilans chwilowy zgadza się arytmetycznie, ale kierunki znaków i punkty pomiarowe przy innych trybach **wymagają testu**. Fabryczny harmonogram i możliwość wymuszonego rozładowania istnieją wg użytkownika; nie znamy odpowiednich usług/encji, ograniczeń ani potwierdzeń wykonania.

Nie przyjmować bez pomiarów: sprawności AC↔bateria, wydajności PV, temperatury ogniw, limitów BMS, dopuszczalnych prądów, przepływu baterii do sieci, semantyki sterowań czy dokładności prognoz. Dane ze zrzutów ekranu dotyczą chwili wykonania, nie są stałymi instalacji.

Lista znanych nazw i braków: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md). Warunki uruchomienia: [OPEN_ITEMS.md](OPEN_ITEMS.md).
