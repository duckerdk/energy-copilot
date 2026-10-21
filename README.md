# Energy Co-Pilot

Natywna integracja Home Assistant `custom_components/energy_copilot`. **Aktualne wydanie: [v0.1.10](https://github.com/duckerdk/energy-copilot/releases/tag/v0.1.10).** Obecny zakres: **M1/M2** (pomiary, ceny, prognozy, Recorder, diagnostyka) i eksperymentalny **M3 `dry_run`** (teoretyczne porównanie scenariuszy ładowania/rozładowania). Integracja jest **wyłącznie do odczytu**, bez sterowania falownikiem, bez potwierdzonego planu sześciu TOU i bez wiarygodnej deklaracji rzeczywistych oszczędności.

Celem docelowego rozwiązania jest minimalizacja całkowitego kosztu energii w horyzoncie opublikowanych cen, z uwzględnieniem SOC, sprawności i degradacji baterii. Zatwierdzone reguły i uprawnienia opisuje wyłącznie [REQUIREMENTS.md](requirements/REQUIREMENTS.md).

## Instalacja i aktualizacja

Wymagany Home Assistant **2026.10 lub nowszy** (testy automatyczne: Core 2026.10.2, Python 3.14).

1. Dodaj `https://github.com/duckerdk/energy-copilot` jako własne repozytorium typu **Integration** w HACS.
2. Zainstaluj opublikowane wydanie, zrestartuj Home Assistant i dodaj **Energy Co-Pilot** w **Ustawienia → Urządzenia i usługi**.
3. Przy aktualizacji sprawdź w diagnostyce `installed_version`, `installed_build.tag` i `installed_build.integrity`. Pakiet oficjalnego wydania powinien wskazywać `payload_matches_build_info`.

Alternatywą jest ręczne skopiowanie katalogu `custom_components/energy_copilot` do instalacji HA; takie kopiowanie nie zapewnia metadanych `BUILD_INFO.json` z wydania. Nie ma potrzeby zmiany ESPHome, Modbus ani ustawień falownika.

## Test M3 w Home Assistant (bez zapisu nastaw)

1. Po aktualizacji do wydania obsługującego M3 wejdź w **Ustawienia → Urządzenia i usługi → Energy Co-Pilot → Konfiguruj** i wybierz **dry_run**. Tryb **monitor** pozostawia M3 nieaktywny.
2. Sprawdź `sensor.energy_co_pilot_planning_status`: `monitor` (wyłączony), `blocked` (brak danych — szczegóły w atrybucie `reason`), `preview` (obliczenia tylko na pokrytym horyzoncie).
3. `sensor.energy_co_pilot_modeled_saving` pokazuje wyłącznie hipotetyczną różnicę DKK między scenariuszem bez cykli baterii i najlepiej ocenionym **ograniczonym** scenariuszem pojedynczego cyklu z sieci; nie jest to oszczędność potwierdzona, wynik globalnego solvera ani realna konfiguracja TOU. Przy `blocked` jego wartość jest `unknown`.
4. Pobierz standardową diagnostykę integracji: `planning_preview` zawiera kod blokady, zakres czasu, liczbę kwadransów, kompletność i podsumowanie wariantów — bez szczegółowej prywatnej historii domu.

**Rygory i ograniczenia testu v0.1.9:** kompletne kwadranse Recorder nadal są wymagane; brakująca prognoza PV (również nocna) nie jest zastępowana zerem. W `dry_run` dłuższe lub nieregularne przedziały energii Forecast.Solar przeliczane są na kwadranse **jawnym, niezweryfikowanym modelem stałej mocy w ramach oryginalnego okresu**: całkowite kWh okresu pozostaje zachowane, a części już minionej nie liczy się ponownie jako energii przyszłej. Nie jest to zweryfikowany profil 15-minutowy ani prognoza fizyczna. Atrybuty `pv_temporal_model` i `pv_temporal_modeled_quarters` pokazują zakres użycia modelu. Luka lub nałożenie się okresów nadal blokuje; brak kompletnej historii zużycia może zakończyć horyzont jako `partial`. Możliwe jest krótsze, jawnie oznaczone `partial` preview. Historia zużycia z poprzednich 24 h UTC jest tylko niezweryfikowanym wzorcem. W v0.1.10 wyłącznie prognoza w `dry_run` może modelować **krótkie luki do 3 kolejnych kwadransów** na podstawie dwóch sąsiednich, w pełni poprawnych kwadransów poprzedniej doby; wykorzystuje interpolację liniową, oznacza wynik `load_model=previous_24h_utc_linear_bracketed_gap_model_unverified` i `load_modeled_quarters`. Dane Recorder, ich jakość i luki pozostają bez zmian. Brak punktów brzegowych lub dłuższa awaria nadal blokują albo skracają podgląd; łączny modelowany koszt nie jest wartością potwierdzoną. Model stosuje prowizoryczne, niekalibrowane wartości: sprawność 0,95 każdej ścieżki, mnożnik PV Forecast.Solar→DC = 1,0, nominalna pojemność baterii 10,24 kWh oraz napięcie bieżące (lub nominalne 51,2 V, gdy brak opcjonalnego czujnika). Warianty mają końcowy SOC równy początkowemu, więc nie zakłada się arbitralnej wartości końcowej baterii. Nie interpretować liczb jako rekomendacji wykonawczej; sześć TOU, kalibracja DC/AC i rzeczywisty Deye baseline pozostają do zrobienia. M3 **nie wykonuje żadnych usług zapisu HA** i nie zmienia oceny `Input quality`.

## Źródła i zasady bieżących danych

| Rola | Encja |
| --- | --- |
| Produkcja PV — **jedyna** | `sensor.pv_sum` |
| Sieć: dodatnie = import, ujemne = eksport | `sensor.sun12k_total_grid_power` |
| Bateria: dodatnie = rozładowanie, ujemne = ładowanie | `sensor.sun12k_battery_output_power` |
| Zużycie domu, pochodna PV + sieć + bateria | `sensor.home_energy_consumption` |
| SOC | `sensor.sun12k_battery_capacity` |
| Ceny zakupu / sprzedaży | `sensor.energi_data_service` / `sensor.energi_data_spotpris` |

PV1/PV2 nie są źródłami danych integracji. Poprawne, dostępne stany wszystkich pomiarów — w tym dodatnie PV, `0 W`, SOC, napięcie, prąd i liczniki dzienne — pozostają ważne nawet bez wielogodzinnych aktualizacji. Sam wiek `last_reported`/`last_updated` nie jest dowodem awarii ani heartbeat sprzętu. Jawne `unknown`, `unavailable`, błędne jednostki, wartości i nieprawidłowe czasy przyszłe nadal są odrzucane. Asynchroniczne raportowanie czujników nie jest samo w sobie błędem wejścia. Rzeczywiste awarie oraz powroty źródeł po awarii nadal są kontrolowane.

Ujemne, ale poprawne i zweryfikowane kontekstowo odczyty `home` są na potrzeby obliczeń normalizowane do `max(0, home)`, również w historii. Nie zmienia to encji HA ani surowych danych. Braków, luk Recorder i niewiarygodnych szablonów po awarii **nie wolno** zastępować zerami.

Dokładne mapowanie, ograniczenia i potwierdzone formaty HA: [HA_CONTRACT.md](requirements/HA_CONTRACT.md).

## Prognoza, historia i diagnostyka

- **Forecast.Solar**: natywna usługa HA `forecast_solar.get_forecast`; `wh_period[t]` opisuje energię przedziału **kończącego się** w `t`. Brak opublikowanej prognozy, także nocą i o zmierzchu, nie jest uzupełniany domniemanym zerem. Niepełny horyzont jest pokazywany osobno jako `forecast_state=incomplete`, bez automatycznego pogarszania `Input quality`.
- **Archiwum prognoz**: zachowuje oryginalne W/Wh i czas odczytu do odtworzenia prognozy znanej w chwili decyzji. Domyślna retencja to 90 dni i 10 000 wersji, z limitem 32 MiB; limity można konfigurować w Opcjach. `forecast_history.as_of(...)` zwraca archiwalną obserwację, a `decision_periods_as_of(...)` tylko pełne przyszłe okresy dostępne w chwili decyzji. Nieodtwarzalne stare wersje nie są przedstawiane jako prawidłowe.
- **Recorder**: bieżąca diagnostyka wykorzystuje ostatnie 24 h; `history_reader.async_iter_slots(start, end)` umożliwia odczyt na żądanie w porcjach do 24 h (maks. 366 dni). Kwadrans bez pełnych, wiarygodnych danych ma `home_kwh=None`. Zachowana energia częściowa nie jest ekstrapolowana. Sama historia stanów nie dowodzi ciągłego raportowania sprzętu.
- **Prywatność**: standardowy eksport diagnostyki zawiera agregaty jakości i korekt, nie szereg prywatnych próbek mocy domu ani szczegółowe zdarzenia audytu.

Sensor **Input quality** ocenia wymagane **bieżące** dane: `valid` (brak obecnych problemów blokujących i niepewności), `uncertain` (akceptowane wejścia z istotną niepewnością), `degraded` (nieważne wymagane wejście). Kwestie historyczne i Forecast.Solar są widoczne oddzielnie; `valid` **nie** potwierdza poprawności fizycznego bilansu AC/DC ani gotowości planera. W trybie `monitor` status planowania pozostaje `not_evaluated_m2`; w `dry_run` diagnostyka rozróżnia `m3_preview_blocked` i `experimental_m3_preview_only`. Żaden z tych stanów nie oznacza możliwości sterowania falownikiem.

## Dokumentacja projektu

| Plik | Zakres |
| --- | --- |
| [REQUIREMENTS.md](requirements/REQUIREMENTS.md) | Jedyne źródło decyzji użytkownika, cel ekonomiczny i uprawnienia |
| [HA_CONTRACT.md](requirements/HA_CONTRACT.md) | Encje HA, znaki, jednostki, kontrakt danych |
| [OPTIMIZATION.md](requirements/OPTIMIZATION.md) | Model przepływów, prognoz i minimalizacji kosztu |
| [EXECUTION.md](requirements/EXECUTION.md) | Wykonanie, TOU, STOP, bezpieczeństwo i zgody |
| [VALIDATION.md](requirements/VALIDATION.md) | Wymagane regresje, odbiór, backtest |
| [OPEN_ITEMS.md](requirements/OPEN_ITEMS.md) | Wyłącznie nadal otwarte kwestie i wymagane potwierdzenia |
| [AGENTS.md](AGENTS.md) | Zasady pracy Codexa w tym repozytorium |

Nie dodawaj równoległych specyfikacji, archiwum ani plików zawierających prywatne dane HA. Historia zmian i poprzednie wydania pozostają w Git.

## Testy i wydania

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests scripts/build_release.py
.venv/bin/ruff format --check custom_components tests scripts/build_release.py
.venv/bin/pytest --cov=custom_components.energy_copilot --cov-report=term-missing
.venv/bin/python scripts/check_docs.py
```

GitHub Actions wykonuje te same kontrole. Wydania HACS wykorzystują **niezmienny tag** `vX.Y.Z`, odpowiadającą wersję manifestu i pakiet `energy_copilot.zip` z `BUILD_INFO.json` oraz `SHA256SUMS`. Utworzenie commitu na `main` **nie jest** publikacją wydania. Szczegółowe zasady odbioru, testów fizycznych i przejścia do M6: [VALIDATION.md](requirements/VALIDATION.md) oraz [EXECUTION.md](requirements/EXECUTION.md).
