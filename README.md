# Energy Co-Pilot

**Status:** M1/M2 — natywna integracja Home Assistant `custom_components/energy_copilot`, wyłącznie do odczytu. Konfiguracja i options flow, setup/reload/unload, walidacja pomiarów i cen, odczyt Forecast.Solar/Recorder oraz diagnostyka mają testy automatyczne. M3–M6 pozostają do implementacji; przypadki w VALIDATION są wymaganiami, nie raportem wykonania. Integracja nie rejestruje usług ani encji sterujących falownikiem.

**Cel:** minimalizować całkowity koszt energii na całym dostępnym horyzoncie opublikowanych cen. Źródłem wszystkich zatwierdzonych decyzji jest [REQUIREMENTS.md](requirements/REQUIREMENTS.md). Nie rekonstruować decyzji użytkownika ze starych komentarzy ani z `OPEN_ITEMS`.

## Dokumenty — jedna rola na plik

| Plik | Jedyna odpowiedzialność |
| --- | --- |
| [REQUIREMENTS](requirements/REQUIREMENTS.md) | Cel, instalacja, polityka cen/SOC/degradacji, uprawnienia użytkownika |
| [HA_CONTRACT](requirements/HA_CONTRACT.md) | Encje, znaki, jednostki, dostępność, ceny, dane PV/Recorder |
| [OPTIMIZATION](requirements/OPTIMIZATION.md) | Bilans, funkcja celu, prognozowanie, wykonalny plan |
| [EXECUTION](requirements/EXECUTION.md) | HA executor, bezpieczeństwo, TOU, zgody i awarie |
| [VALIDATION](requirements/VALIDATION.md) | Testy do napisania, benchmark, log i dashboard |
| [OPEN_ITEMS](requirements/OPEN_ITEMS.md) | **Wyłącznie niewyjaśnione dowody techniczne**, z właścicielem i etapem |

Dodatkowo [AGENTS.md](AGENTS.md) zawiera instrukcje wykonawcze dla Codexa. Nie tworzyć nowych plików specyfikacji bez rzeczywistej nowej odpowiedzialności; poprawiać właściwy istniejący plik. Brak archiwum — historia jest dostępna przez Git.

## Implementacja

1. M1: manifest, config/options flow, typed runtime data, setup/unload, testy — zero zapisów.
2. M2: mapowanie encji, walidacja cen/UTC/DST/Recorder/Forecast.Solar.
3. M3: planner minimalnego kosztu, realistyczne możliwości Deye, `dry_run`, rejestr decyzji.
4. M4: HA encje, dashboard, zgody eksportu baterii, STOP.
5. M5: testy, walk-forward, walidacja alternatyw i jakości danych.
6. M6: **dopiero po świadomym włączeniu live i testach** — autonomiczne prądy, Grid Charge, sześć TOU, Solar Sell PV; eksport baterii tylko przy indywidualnej zgodzie.

Odbiór iteracji: kod i pliki, testy naprawdę wykonane, testy nieprzeprowadzone, istotne ryzyka i aktualne [OPEN_ITEMS](requirements/OPEN_ITEMS.md). Bez udawania, że symulacja jest oszczędnością z urządzenia.

## Instalacja M1/M2

Wymagany Home Assistant **2026.10 lub nowszy** (testy: Core 2026.10.2, Python 3.14). W HACS dodaj to repozytorium jako niestandardową integrację albo skopiuj katalog `custom_components/energy_copilot` do katalogu `custom_components` swojej instancji HA. Zrestartuj HA i dodaj **Energy Co-Pilot** w Ustawienia → Urządzenia i usługi. Nie zmieniaj konfiguracji ESPHome ani falownika.

Formularz wymaga tylko źródeł PV, sieci, baterii, SOC, domu i obu cen. PV1/PV2, napięcie/prąd, alternatywny licznik sieci, liczniki dzienne i odczyt Solar Sell są opcjonalne; ich brak nie blokuje konfiguracji, lecz jest widoczny w diagnostyce. Wszystkie mapowania można podać ręcznie. Usunięcie opcjonalnego mapowania w Opcjach wyłącza jego odczyt również po przeładowaniu. Opcjonalnie można wskazać config entry Forecast.Solar. `monitor` i `dry_run` nadal wyłącznie odczytują dane — planner nie jest jeszcze zaimplementowany.

Sensor **Input quality** i pobierana diagnostyka pokazują brakujące, niepoprawne i nieweryfikowalne dane oraz faktyczne pokrycie historii. Prognoza korzysta wyłącznie z natywnego `forecast_solar.get_forecast` w rozdzielczości `raw`, bez bezpośredniego API dostawcy. W Opcjach można ustawić retencję prognoz od 1 do 366 dni (domyślnie 90) i limit od 1 do 50 000 wersji (domyślnie 10 000). Dodatkowy limit jednego magazynu wynosi 32 MiB; wcześniejszy z limitów usuwa najstarsze obserwacje i nieużywane dane. Liczenie rozmiaru i walidacja magazynu odbywają się poza pętlą HA. Usunięcie integracji usuwa jej magazyn `.storage`.

Magazyn zachowuje oryginalne mapy W/Wh i klucze czasu z odpowiedzi oraz czas pierwszego udanego odczytu. HA nie podaje w tej usłudze czasu wygenerowania prognozy przez dostawcę. Identyczne kolejne odpowiedzi nie tworzą wersji ani kolejnych zapisów. Powrót do wcześniejszych wartości po innej prognozie tworzy nową obserwację, współdzieląc oryginalny zestaw danych. `coordinator.forecast_history.as_of(decision_at, source_entry=...)` wybiera ostatnią zachowaną obserwację dostępną w chwili decyzji; `original_at(...)` zwraca kopię jej pierwotnych wartości. Późniejsze aktualizacje nie zastępują wcześniejszych prognoz. Odtwarzanie jest ograniczone retencją; duże odczyty na potrzeby przyszłych testów należy wykonywać poza pętlą HA. Stary magazyn jest migrowany z zachowaniem znanych okresów i czasu, ale utraconych wcześniej surowych odpowiedzi nie można odzyskać. Diagnostyka rozróżnia takie wersje. Błędny lub nieznany magazyn nie jest nadpisywany.

Bieżące odczyty Recorder nadal obejmują jedynie ostatnie 24 h, odświeżane co 15 min. Dłuższe zakresy udostępnia na żądanie `coordinator.history_reader.async_iter_slots(start, end)` — maksymalnie 366 dni, w kolejnych porcjach do 24 h. Iterator jest leniwy: bez wywołania nie wykonuje zapytań, a przerwanie nie uruchamia kolejnych porcji. Wymaga dat ze strefą, pełnych kwadransów i końca niepóźniejszego niż aktualna chwila. Konsument powinien zamknąć iterator po wcześniejszym zakończeniu (np. `contextlib.aclosing`). Odczyty korzystają z executora Recorder i wspólnej blokady; unload blokuje dalsze porcje. Integracja nie kopiuje historii do osobnej bazy i nie zwiększa retencji Recorder. Diagnostyka rozdziela ustawioną retencję od zaobserwowanego pokrycia i raportuje ostatni odczyt bieżący oraz zakres zażądany osobno.

Każdy historyczny kwadrans jest weryfikowany przez PV/sieć/bateria/dom, jednostki, synchronizację i świeżość. Brakujące/usunięte dane nie stają się zerowym zużyciem. Recorder przechowuje zmiany stanów, więc nie dowodzi ciągłej dostępności niezmiennego czujnika: przedłużenie próbki ponad 5 min jest nieweryfikowalne. To przygotowanie odczytu danych M2, bez implementacji modelu, uczenia lub backtestu M3–M5. Nie potwierdzono jeszcze działania na fizycznej instalacji użytkownika ani sprawności AC/DC.

## Testy deweloperskie

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests
.venv/bin/ruff format --check custom_components tests
.venv/bin/pytest --cov=custom_components.energy_copilot --cov-report=term-missing
.venv/bin/python scripts/check_docs.py
```

Testy blokują sieć IP; dopuszczają lokalne gniazda Unix potrzebne pętli asyncio. Obejmują natywny cykl życia HA, rzeczywisty Recorder SQLite w pamięci, implementację usługi Forecast.Solar z kontrolowanym estymatem oraz regresje danych/cen/UTC/DST. Nie komunikują się z falownikiem ani prywatną instancją HA. CI wykonuje te same kontrole. Gotowość do dodania jako repozytorium niestandardowe HACS nie oznacza zgłoszenia do domyślnego katalogu HACS.
