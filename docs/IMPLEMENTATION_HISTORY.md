# Historia implementacji, uruchomień i błędów

**Okres:** 14.06.2025. To jest **odtworzenie z dokumentów i wcześniejszych rozmów**, a nie historia commitów (nowe repo założono w 2026). Raportowane wyniki oznaczono jako wyniki pojedynczych uruchomień, nie walidację produkcyjną.

## 1. Etapy i rzeczywiste artefakty

| Etap | Istniejące historycznie komponenty | Osiągnięty wynik / ograniczenie |
| --- | --- | --- |
| v1.0 / eksport | `exporter.py`, `data_loader.py`, `ha_history.csv`, `.venv`, `pandas` | relacjonowano działający eksport HA i odczyt **270 873 rekordów, 6 encji**, znaczniki UTC |
| v2.0 / LLM | `agent_llm.py`; eksperymenty `copilot_v2.py` | GPT-4o otrzymywał próbkę ok. **100 rekordów**; wyniki statystyk różniły się między uruchomieniami |
| v5.0 / plan dobowy | `HADataLoader`, `EnergyPolicyAgent`, `copilot_v5.py`, `logic.txt` | wg snapshotu prototyp generował plan na **24 h** z historią, aktualnym stanem i 30-dniowymi agregatami |
| v5.1 | [logic_v5.1.txt](reference/logic_v5.1.txt) | zapis szczegółowych założeń SOC / PV / sprzedaż / zakup |
| v5.1.1 / korekta | rozdzielenie `switch.sun12k_grid_charge` i `number.sun12k_maximum_battery_grid_charge_current` | ustalenie użytkownika; test wyjścia planu LLM opisany poniżej |
| „v5.2” / eksperyment | planowanie tanich godzin z `sensor.energi_data_service` | uruchomienie pliku `copilot_v5.2.py` blokował brak `ha_api_client` |
| „v5.3” / eksperyment | szacowanie nocnego poboru z historii | błędne liczby energii/SOC, brak potwierdzonej poprawy |
| v5.4 | pamięć długoterminowa | plan ze snapshotu; brak dowodu wykonania |

**Uwaga o nazewnictwie:** v5.2 i v5.3 w snapshot v5.0 oznaczały *planowane etapy*, a później etykietowano nimi także niezakończone eksperymentalne wersje kodu. Nie są one potwierdzonymi stabilnymi wydaniami.

## 2. Wczesny test warstwy danych

W rozmowie przy snapshocie v1 zrelacjonowano wartości statystyczne dla jednego testowego fragmentu danych:

| Miara | Wynik ze zgłoszenia |
| --- | ---: |
| min | -0.04747252125 |
| max | 1.38425766384675 |
| średnia | 0.48622474251546033 |
| suma | 64.18166601204076 |
| liczba wartości | 132 |

**Brak dostępnego wycinka CSV, filtra encji i kodu obliczającego** — nie przypisujemy tych liczb arbitralnie do energii w kWh ani do całego zbioru. Wartości zachowano jako historyczny punkt kontrolny wymagający odtworzenia na źródłowych danych.

## 3. Potwierdzony raport z uruchomienia planera v5.0 / v5.1.1

Użytkownik przedstawił wynik uruchomienia `python3 copilot_v5.py`, w którym model **zaproponował**:

| Wejście / wynik planera | Wartość ze zgłoszenia |
| --- | --- |
| Aktualny SOC | **99%** |
| Interpretowana ilość energii | **7,92 / 8 kWh** |
| Nocne zużycie przyjęte do planu | **5 kWh** |
| Bufor | **10%** (w tym przykładzie 0,8 kWh) |
| Wyliczone `required_soc` | **72,5%** |
| Cena spot | **0,979 DKK/kWh** |
| Próg sprzedaży | **0,4 DKK/kWh** |
| Prognoza PV na dziś | **41,823 kWh** |
| Prognoza PV na jutro | **21,218 kWh** |
| Plan: `switch.sun12k_solar_sell` | **ON** |
| Plan: `switch.sun12k_grid_charge` | **OFF** |
| Plan: `number.sun12k_maximum_battery_grid_charge_current` | **1 A** |

**Klasyfikacja:** wynik aplikacji/LLM przedstawiający **plan**, nie potwierdzenie wykonania działań. Nie ma dowodu zmiany stanów urządzenia ani logu potwierdzającego eksport/ładowanie. Zachowujemy te liczby jako **historyczny przykład wejścia/wyjścia**, nie aktualny odczyt HA i nie zweryfikowany test algorytmu.

Ten przykład jest też zapisany w [przypadkach referencyjnych](REFERENCE_CASES.md), by możliwe było późniejsze odtworzenie zachowania.

## 4. Błędy integracji i wyliczeń

### Komunikacja HA: brak modułu w v5.2

```text
ModuleNotFoundError: No module named 'ha_api_client'
```

- Wcześniej działał prostszy klient `HomeAssistantAPI` używający YAML, `requests.Session`, Bearer i `call_service()`.
- Zaobserwowano test `light.turn_on` na `light.gang_led_swiatlo`.
- Nie ma dowodu zakończenia portowania do oddzielnego `ha_api_client.py` i dodania pełnego odczytu stanu.

### Estymacja nocnego poboru w v5.3

Zgłoszone w próbach nieprawidłowe wyniki:
- `estimated_night_consumption` około **154 305,42 kWh**;
- `required_soc` około **1 928 817,75%**;
- w innej iteracji pojawiło się **308610.85 Wh**.

Diagnoza z rozmowy: wykorzystano niewłaściwe dane (cenę zamiast poboru), a także błędne przeliczenie mocy kW na energię kWh. Przy stałych 5-minutowych próbkach obowiązuje `Σ(P_kW × 5/60 h)`, nie `Σ(P_kW)`. Nie pokazano poprawnego, zweryfikowanego ponownego wyniku.

### Strefy czasowe / JSON

Wcześniej występowały błędy:
- porównania dat `offset-aware` z `offset-naive`;
- serializacji obiektów `datetime.date` do JSON.

Snapshot v5.0 deklarował rozwiązanie tych problemów w tamtym prototypie, ale kod i testy regresji nie są obecnie dostępne.

### Powtarzalność obliczeń

Eksperymenty `agent_llm.py` i `copilot_v2.py` pokazywały niespójne wyniki liczbowe GPT przy tych samych/przybliżonych danych. Nie zapisano zweryfikowanego algorytmu pozwalającego porównać wyjście z deterministyczną kalkulacją.

## 5. Ostateczny stan wiedzy

Historycznie uzyskano: eksport CSV, loader/agregacje, prosty test usługi HA, szkielet planera AI i **co najmniej jedno konkretne wyjście planera 24 h**. Nie mamy jednak oryginalnych kodów, oryginalnych logów ani danych do odtworzenia testu.

**Nie zostało potwierdzone**: wykonywanie komend na falowniku, odczyt i zapis wszystkich 11 identyfikatorów, wiarygodne prognozy i profil nocy, pętla harmonogramu, pamięć długoterminowa, testy regresyjne, wdrożenie i monitoring.
