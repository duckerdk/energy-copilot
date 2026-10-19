# Instalacja i dostępność danych

**Źródło:** informacje przekazane przez użytkownika; nie wykonano odczytu ani zapisu w działającym HA. **Potwierdzenie użytkownika ≠ weryfikacja techniczna.**

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

Użytkownik potwierdził osobne pomiary mocy importu, eksportu, ładowania i rozładowania baterii, lecz ich aktualne **entity_id nie są znane**. Fabryczny harmonogram i możliwość wymuszonego rozładowania istnieją wg użytkownika; nie znamy odpowiednich usług/encji, ograniczeń ani potwierdzeń wykonania.

Nie przyjmować bez pomiarów: sprawności AC↔bateria, wydajności PV, temperatury ogniw, limitów BMS, dopuszczalnych prądów, przepływu baterii do sieci, semantyki sterowań czy dokładności prognoz. Dane ze zrzutów ekranu dotyczą chwili wykonania, nie są stałymi instalacji.

Lista znanych nazw i braków: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md). Warunki uruchomienia: [OPEN_ITEMS.md](OPEN_ITEMS.md).
