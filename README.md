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

Historia jest rekonstruowana od ostatniego rzeczywistego rekordu każdego źródła przez kolejne zmiany stanów. `last_updated` w Recorder oznacza zmianę, nie heartbeat: stałe nocne PV=0 i niezależne czasy zmian źródeł nie podlegają progom świeżości 5 min ani synchronizacji 10 s stosowanym do pomiarów bieżących. Reader zachowuje prawdziwy czas rekordu granicznego zamiast syntetycznego początku zapytania. Przerwy między procesami Recorder, niepewne zakończenia, źródła wykluczone, brak jednostek oraz jawne `unknown/unavailable` nadal odrzucają dotknięty kwadrans. `home` pozostaje zapisanym stanem szablonu; liczba w szablonie nie zastępuje brakującego PV/sieci/baterii.

Aktywnie wyłączony Recorder jest błędem `recorder_disabled`. Historyczna sesja procesu nie dowodzi, że zapis nigdy nie był pauzowany: HA nie zachowuje pełnego rejestru `recorder.disable` ani zmian filtrów. Diagnostyka ujawnia `device_freshness_verified=false`, `recording_pause_history_verified=false`, `historical_filter_changes_verified=false` i problem `recorder_pause_history_unverifiable`. Liczba odtworzonych kwadransów nie jest dowodem ciągłego raportowania urządzeń. To odczyt M2, bez modelu, uczenia, backtestu lub sterowania M3–M6.

Prognoza zachowuje oryginalne Wh także dla rozpoczętego przedziału; nie usuwa całej bieżącej godziny wskutek pobrania kilka sekund po jej początku. Nie przelicza całkowitej energii tego przedziału proporcjonalnie do pozostałych minut. Czas pobrania i `forecast_observed_after_period_start` ujawniają, od kiedy dane były dostępne. Diagnostyka pokrycia rozdziela brak przed opublikowanym horyzontem, lukę wewnętrzną i brak po jego końcu, z dokładnymi granicami UTC. Brak po 16:06:30 w zgłoszonym raporcie nie jest potwierdzoną zerową produkcją do 22:00: bez danych usługi nie wypełniamy nocy zerami. Nieznana granica końcowego niezerowego okresu też pozostaje błędem. Testy obejmują UTC/DST i nie podmieniają rzeczywistych danych użytkownika symulacją.

## Testy deweloperskie

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests scripts/build_release.py
.venv/bin/ruff format --check custom_components tests scripts/build_release.py
.venv/bin/pytest --cov=custom_components.energy_copilot --cov-report=term-missing
.venv/bin/python scripts/check_docs.py
```

Testy blokują sieć IP; dopuszczają lokalne gniazda Unix potrzebne pętli asyncio. Obejmują natywny cykl życia HA, rzeczywisty Recorder SQLite w pamięci, implementację usługi Forecast.Solar z kontrolowanym estymatem oraz regresje danych/cen/UTC/DST. Nie komunikują się z falownikiem ani prywatną instancją HA. CI wykonuje te same kontrole. Gotowość do dodania jako repozytorium niestandardowe HACS nie oznacza zgłoszenia do domyślnego katalogu HACS.

## Wydania i identyfikacja zainstalowanego kodu

Opublikowane wydanie to [**0.1.1**](https://github.com/duckerdk/energy-copilot/releases/tag/v0.1.1), tag `v0.1.1`, commit `dea78abe236683f2ce46085b6f207671fd10ebf8`. Każde wydanie ma nowy numer SemVer w manifeście, niezmienny tag `vX.Y.Z` i odpowiadający GitHub Release. Sam commit lub merge do `main` nie jest wydaniem; istniejącego tagu/Release nie przesuwamy i nie nadpisujemy. `.github/workflows/release.yml` po wypchnięciu tagu uruchamia cały zestaw testów, Ruff, formatowanie, kontrolę dokumentacji i zgodności tag–manifest–commit, następnie publikuje zasoby Release. Wydanie jest dostępne dopiero po pomyślnym zakończeniu publikacji, nie po samym utworzeniu tagu.

`scripts/build_release.py --tag vX.Y.Z --commit PEŁNY_SHA --output /tmp/energy-copilot-release` buduje powtarzalne `energy_copilot.zip`, `BUILD_INFO.json` i `SHA256SUMS` wyłącznie z obiektów Git oznaczonego commitu. Nie dołącza prywatnych ani nieśledzonych plików. ZIP zawiera pliki integracji w głównym katalogu, zgodnie z `zip_release`/`filename` w HACS. `BUILD_INFO.json` wewnątrz paczki identyfikuje wersję, tag, pełny commit i sumy plików; kod nie wyznacza zainstalowanej rewizji z HEAD lokalnego repozytorium.

Aby zaktualizować: odśwież repozytorium w HACS, wybierz opublikowaną wersję Release, pobierz ją i zrestartuj HA. Następnie pobierz diagnostykę Energy Co-Pilot: `integration_manifest.version` i `installed_version` mają wskazywać `0.1.1`, a `installed_build` — tag, commit i `integrity=payload_matches_build_info`. Wersja jest także atrybutem sensora diagnostycznego i wersją oprogramowania urządzenia HA. Brak metadanych przy ręcznym kopiowaniu oznacza `metadata_unavailable`; lokalne zmiany w plikach oznaczają `payload_modified` i nie są przedstawiane jako dokładna rewizja wydania. Starsza instalacja `0.1.0` nie pozwala odtworzyć konkretnego commitu wyłącznie z numeru wersji.
