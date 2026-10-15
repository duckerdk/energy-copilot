# Inwentarz odtworzenia projektu — brakujące pliki i informacje

Dokument służy jako lista przekazania projektu kolejnemu programiście/agentowi. Odnotowuje, czego **faktycznie nie ma** w repo, aby nie wymyślać kodu z nazw klas.

## Co już jest na GitHub

- [README](../README.md) i [PROJECT_STATUS](PROJECT_STATUS.md) — cele i status.
- [ENTITIES](ENTITIES.md) + [config/entities.yaml](../config/entities.yaml) — pełny **znany historycznie** rejestr 11 identyfikatorów.
- [TECHNICAL_BASELINE](TECHNICAL_BASELINE.md) — sprzęt, środowisko, diagram przepływu i lista modułów.
- [DATA_PIPELINE](DATA_PIPELINE.md) — dane CSV, 6 źródeł, 270 873 rekordów z historycznego uruchomienia, korekty obliczeń.
- [HA_API](HA_API.md) — historyczny klient REST i opis odczytów/zapisów.
- [CONTROL_LOGIC](CONTROL_LOGIC.md) — wymagania v5.1 i doprecyzowanie v5.1.1.
- [IMPLEMENTATION_HISTORY](IMPLEMENTATION_HISTORY.md) i [REFERENCE_CASES](REFERENCE_CASES.md) — postęp, uruchomienia, błędy.
- `docs/reference/logic_v5.1.txt` i `docs/reference/snapshot_v5.0.txt` — przekazane materiały źródłowe.

## Kod i dane istniejące historycznie, ale nieobecne w repo

| Element | Co wiadomo / skąd pochodzi | Status |
| --- | --- | --- |
| `exporter.py` | eksport danych HA do CSV | nie dostarczono pliku |
| `data_loader.py` | `HADataLoader`, agregacja dzienna, bieżący stan | nie dostarczono pliku |
| `agent_llm.py` | analiza LLM próbki CSV | nie dostarczono pliku |
| `copilot_v2.py` | eksperymentalny krok v2 | nie dostarczono pliku |
| `copilot_v5.py` | wejście do planera i 24h plan | nie dostarczono pliku |
| `agent.py` / `HomeAssistantAPI` | historyczny REST `call_service()` | nie dostarczono pliku |
| `config.yaml` | URL, token, verify_ssl | nie dostarczono, **nie kopiować sekretów do publicznego repo** |
| `ha_history.csv` | 270 873 rekordów / 6 encji według archiwalnego testu | nie dostarczono; najpierw ocenić prywatność danych |
| `logic.txt` używany przez kod | historia promptu; tekst v5.1 zapisany osobno | historycznej kopii z maszyny nie dostarczono |
| `Energy Copilot V5` w dawnym Canvas | snapshot odsyła do kodu | niedostępny jako plik w repo |
| `copilot_v5.2.py` | nazwa pliku znana z historycznego tracebacku; brak `ha_api_client` | nie dostarczono pliku |
| ewentualne pozostałe skrypty `v5.3` | eksperymenty i błędy | nie dostarczono |
| środowisko `.venv`, lista wersji zależności | historycznie używane `pandas`, `requests`, YAML i biblioteka OpenAI | brak dokładnej listy/pinningu |
| testy, pełne logi i historia wywołań HA | brak źródeł | nie dostarczono |

**Nie odtwarzaliśmy kodu na podstawie zgadywania.** W przyszłości najlepiej odzyskać oryginalny katalog `/home/damian/energy-co-pilot` (bez sekretów i danych osobowych), przed pisaniem zamienników.

## Weryfikacje terenowe niezbędne do pierwszego bezpiecznego uruchomienia

- Sprawdzenie obecności **wszystkich 11 historycznych identyfikatorów** i typu usługi notify.
- Zrzut odczytów `GET /api/states/{entity_id}` w środowisku kontrolowanym, bez publikowania tokenów.
- Potwierdzenie mapowania obu sterowań: `grid_charge` i `maximum_battery_grid_charge_current`.
- Ustalenie dokładnej jednostki ceny i struktury przyszłych cen `sensor.energi_data_service`.
- Potwierdzenie mocy kW, próbkowania i historii `sensor.home_energy_consumption`.
- Ustalenie wersji sprzętu, firmware, integracji HA, fizycznego limitu prądowego i warunków powrotu do stanu bezpiecznego.
- Testy niezależnego liczenia energii i porównanie wyników z historycznym planem.

To **lista braków/danych do sprawdzenia**, nie rozszerzenie logiki ani rekomendacja modyfikacji założeń.

## Zasada pracy z tym repo

**Nie oznaczaj historycznej funkcji jako gotowej**, dopóki jej kod nie jest w repo i nie została sprawdzona. Zachowuj osobno: (a) wymogi, (b) historię wykonania, (c) przypadki kontrolne, (d) otwarte kwestie, (e) przyszłe zmiany.
