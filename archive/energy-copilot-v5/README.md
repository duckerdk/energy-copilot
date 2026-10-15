# Energy Co-Pilot — Home Assistant / PV / magazyn / sieć

Dokumentacja techniczna historycznego prototypu zarządzania energią **Energy Co-Pilot**. Założenia i testy powstawały głównie **14.06.2025**; niniejsze repozytorium uporządkowano **15.10.2026**.

**Status: DOCUMENTED / NOT DEPLOYABLE.** Odtworzono wymagania, rejestr encji, znaną konfigurację interfejsów, architekturę, wejścia i wyjścia oraz historię uruchomień. **Oryginalne pliki Python, `ha_history.csv` i konfiguracyjne nie są dostępne w repozytorium.** Zawarte tu opisy nie dowodzą automatycznej pracy instalacji.

## Punkt wejścia dla programisty lub kolejnego agenta

| Obszar | Dokument / zasób | Znaczenie |
| --- | --- | --- |
| **Encje HA (wszystkie znane)** | [docs/ENTITIES.md](docs/ENTITIES.md) | **11 identyfikatorów** (7 sensorów, 2 switch, 1 number, 1 usługa notify), jednostki, funkcje i konflikty |
| **Rejestr do odczytu maszynowego** | [config/entities.yaml](config/entities.yaml) | Klucze logiczne → dokładne historyczne `entity_id` / `service_id` |
| **Technika i architektura** | [docs/TECHNICAL_BASELINE.md](docs/TECHNICAL_BASELINE.md) | System, magazyn, parametry, środowisko Linux/Python, diagram i lista modułów |
| **Integracja HA** | [docs/HA_API.md](docs/HA_API.md) | REST, struktura `config.yaml`, autoryzacja, test klienta, formaty komend |
| **Dane / CSV / obliczenia** | [docs/DATA_PIPELINE.md](docs/DATA_PIPELINE.md) | `timestamp,entity_id,value`, 270 873 rekordów z archiwalnego testu, 6 serii, kW → kWh |
| **Logika sterowania** | [docs/CONTROL_LOGIC.md](docs/CONTROL_LOGIC.md) | Wymagania v5.1 i **obowiązkowe rozdzielenie funkcji v5.1.1** |
| **Przebieg implementacji** | [docs/IMPLEMENTATION_HISTORY.md](docs/IMPLEMENTATION_HISTORY.md) | v1 / v2 / v5.0–v5.3, wyniki uruchomień i błędy |
| **Wyniki odniesienia** | [docs/REFERENCE_CASES.md](docs/REFERENCE_CASES.md) | Przypadki liczbowe i historyczny plan (nie zatwierdzone testy automatyczne) |
| **Stan i historia** | [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | Potwierdzone vs deklarowane vs brak |
| **Brakujący kod i odtworzenie** | [docs/RECOVERY_INVENTORY.md](docs/RECOVERY_INVENTORY.md) | Dokładnie które historyczne pliki i pomiary trzeba odzyskać |

Oryginalne materiały bez zmiany założeń: [logic v5.1](docs/reference/logic_v5.1.txt) i [snapshot v5.0](docs/reference/snapshot_v5.0.txt).

## Najważniejsze parametry historyczne

| Parametr | Wartość z logiki v5.1 |
| --- | --- |
| Pojemność użytkowa | **8 kWh** |
| Zakładany SOC | **20–100%** |
| Nocne zużycie | **5 kWh** minimum / **8 kWh** preferowane |
| Bufor wymaganej rezerwy | **10 punktów procentowych** w źródłowym wzorze |
| Minimalna cena sprzedaży spot | **0,4 DKK/kWh** |
| Dobowy plan | horyzont **24 h**, uruchamianie wg specyfikacji np. **00:10** |

## Krytyczna korekta techniczna (v5.1.1)

- `switch.sun12k_grid_charge` → **włącz/wyłącz ładowanie z sieci**.
- `number.sun12k_maximum_battery_grid_charge_current` → według późniejszego ustalenia użytkownika **ograniczanie ładowania z PV**, przy czym historycznie użyto `1 A`. **Tego znaczenia nie sprawdzono na żywej instalacji; nazwa encji i tekst v5.1 są z nim sprzeczne.**
- `switch.sun12k_solar_sell` → zezwolenie na sprzedaż/eksport.

**Nie zastępować `grid_charge=off` nastawą `1 A`.** Nie sterować rzeczywistym falownikiem bez sprawdzenia działania tej encji, zakresu i stanów awaryjnych.

## Historycznie uzyskane wyniki

- Opracowywano `exporter.py`, `data_loader.py` / `HADataLoader`, `agent_llm.py`, `copilot_v2.py`, `copilot_v5.py` i `EnergyPolicyAgent`.
- Snapshot v5.0 deklarował działającą ścieżkę CSV + bieżące HA + 30-dniowe agregaty → LLM → plan 24 h.
- Konkretny zrelacjonowany plan: SOC **99%**, cena **0,979 DKK/kWh**, prognoza PV **41,823 / 21,218 kWh**, wymagany SOC **72,5%**, zalecenia sprzedaż **ON**, ładowanie z sieci **OFF**, limit **1 A**. **To wynik modelu/aplikacji, a nie potwierdzenie wykonania.**
- W późniejszych eksperymentach wystąpiły błędy: brak `ha_api_client`, nierealistyczna estymacja nocnego zużycia i problemy przeliczania kW na kWh.

## Stan repo do dalszej pracy

To **baza wiedzy inżynierskiej i kontrakt interfejsów**, a **nie ukończony pakiet wdrożeniowy**. Nie wprowadzono zmian w logice/założeniach ani kodu wykonawcy poleceń do urządzeń. W [inwentarzu](docs/RECOVERY_INVENTORY.md) opisano brakujące źródła oryginalnego kodu, dane i kwestie do potwierdzenia.

W repo **nie umieszczamy** sekretów HA, rzeczywistych tokenów ani surowych prywatnych danych historycznych bez świadomej decyzji.
