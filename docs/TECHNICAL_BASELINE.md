# Baza techniczna — stan odtworzony z prac Energy Co-Pilot

Data referencyjna prac: **14.06.2025**. Dokument jest inwentarzem faktów i historycznych deklaracji, a nie instrukcją uruchamiania gotowego systemu.

## Sprzęt i środowisko

| Element | Stan wiedzy |
| --- | --- |
| System | Home Assistant jako źródło danych i warstwa sterowania |
| Falownik | Encje z prefiksem `sun12k`; **dokładnego modelu producenta i firmware nie udokumentowano** |
| Źródła energii | PV, magazyn, zakup i eksport do sieci |
| Magazyn | 8 kWh **użytkowej** pojemności wg logiki v5.1; założony zakres pracy 20–100% SOC |
| Energia wymagana w nocy | minimum 5 kWh, wartość preferowana 8 kWh wg specyfikacji |
| Bufor | 10 punktów % wg wzoru v5.1 |
| Próg eksportu | bieżąca cena spot ≥ 0,4 DKK/kWh |
| Wysyłanie alertów | `notify.mobile_app_pixel_7dk` (plan) |
| Maszyna developerska (historycznie) | Linux; katalog `/home/damian/energy-co-pilot` / `~/energy-co-pilot` |
| Python | Środowisko `.venv`, biblioteka `pandas`; `requests` dla REST HA; YAML konfiguracji |
| LLM | Snapshot v5.0: „GPT-4o ADA” z wejściami JSON; brak konfiguracji potwierdzonej obecnie |
| Repozytorium źródłowe (nowe) | `duckerdk/energy-copilot`; brak przeniesionego kodu z dawnej maszyny |

Nie posiadamy: liczby modułów PV, mocy falownika, konfiguracji faz, modelu baterii, mocy ładowania, adresu HA, wersji HA/integracji, rzeczywistej taryfy, strat energetycznych ani mapowania rejestrów sprzętu. **Nie wolno ich uzupełniać przypuszczeniami.**

## Historyczny katalog projektu

W rozmowach wymieniano następujące pliki/moduły (nie wszystkie były dostępne jednocześnie i nie ma ich źródeł w nowym repo):

| Ścieżka względna | Historyczna rola / ustalenie | Potwierdzenie |
| --- | --- | --- |
| `exporter.py` | eksport danych HA do CSV | zrelacjonowany jako działający we wczesnym snapshocie |
| `ha_history.csv` | szeregi czasowe, nagłówek `timestamp,entity_id,value` | historyczne uruchomienie: 270 873 wierszy / 6 encji |
| `data_loader.py` | wczytywanie CSV i agregacja danych | prototyp uruchamiany w rozmowie |
| `agent_llm.py` | eksperymenty z LLM i interpretacją historii | pojawiały się niespójne liczby |
| `copilot_v2.py` | iteracja analizy energetycznej | historyczne uruchomienie, nieustalone wyniki |
| `copilot_v5.py` | ładowanie CSV + bieżących danych, agregaty i 24h plan AI | snapshot v5.0 relacjonował uruchomienie |
| `agent.py` | historyczny klient `HomeAssistantAPI` | wcześniejszy interfejs REST |
| `config.yaml` | `home_assistant.url`, `home_assistant.token`, `home_assistant.verify_ssl` | plik historycznie używany, sekretów brak |
| `logic.txt` | tekst logiki dla agenta | dostarczona osobno logika v5.1 |
| `ha_api_client.py` | nazwa importu z nieudanej wersji v5.2 | brak modułu; `ModuleNotFoundError` |
| `copilot_v5.2` / `v5.3` | eksperymentalne wydania | nie ma potwierdzonego pakietu do odtworzenia |

Nie znamy pełnych dokładnych nazw wszystkich eksperymentalnych plików, kodu oraz API klas. W szczególności snapshot odsyłał do „Energy Copilot V5” w historycznym Canvas — **oryginału nie ma tutaj**.

## Warstwy opracowanego prototypu

```text
                     Home Assistant
          czujniki + przełączniki falownika
                        │
         ┌──────────────┴──────────────┐
         │                             │
  exporter.py → ha_history.csv     HomeAssistantAPI
         │                         config.yaml + REST
         │                             │
         └──────────────┬──────────────┘
                        ▼
             HADataLoader / pandas
          current_data + daily_aggregates
                        │
                        ▼
              EnergyPolicyAgent
            dane JSON + tekst logiki
                        │
                        ▼
                  LLM (GPT-4o)
                        │
                        ▼
                 plan na 24 h
                        │
                [brak potwierdzonego
                 wykonawcy akcji HA]
```

Diagram przedstawia zamierzony przepływ oraz **historyczne prototypy**, nie certyfikowaną architekturę produkcyjną.

## Znane elementy API Pythona

- `HADataLoader` — ładowanie eksportu CSV oraz udostępnienie `get_daily_aggregates()` i `get_current_data()`.
- `EnergyPolicyAgent` — przygotowanie wejścia modelu, zawierającego `current_data` i `daily_aggregates`, i generowanie proponowanego planu 24 h.
- `HomeAssistantAPI` — klient REST z sesją `requests.Session`, autoryzacją Bearer i metodą `call_service()`; wersja wykorzystywana w próbie v5.2 **nie udostępniała kompletnej metody odczytu stanu**.
- Używany historycznie eksperymentalny test `call_service`: `light.turn_on` dla `light.gang_led_swiatlo`; był to **test API**, nie element sterowania energią.

## Historyczne uruchomienie

Przy istniejących plikach na dawnej maszynie stosowano:

```bash
cd /home/damian/energy-co-pilot
source .venv/bin/activate
python3 copilot_v5.py
```

Polecenie jest **archiwalną referencją**. Nowe repo nie zawiera `copilot_v5.py`, `.venv`, `ha_history.csv` ani sekretów, więc **nie można go obecnie uruchomić**.

## Odnośniki

- [Rejestr encji i komend](ENTITIES.md)
- [Kontrakt danych i historia przetwarzania](DATA_PIPELINE.md)
- [REST API i konfiguracja](HA_API.md)
- [Logika v5.1 oraz korekta v5.1.1](CONTROL_LOGIC.md)
- [Stan kodu i eksperymentów](IMPLEMENTATION_HISTORY.md)
