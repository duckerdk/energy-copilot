# Energy Co-Pilot

Natywna integracja Home Assistant `custom_components/energy_copilot`. Aktualną wersję określa [manifest.json](custom_components/energy_copilot/manifest.json), a wersje dostępne w HACS — [GitHub Releases](https://github.com/duckerdk/energy-copilot/releases). Planer pracuje na opublikowanych cenach i prognozach, a zapis nastaw odbywa się tylko w trybie `automatic`. `monitor` i `dry_run` nie wysyłają poleceń. Prognoza domu korzysta z **ostatnich 45 dni** z większą wagą ostatnich 7/14 dni. Polityka **2.0.0** porównuje pełne plany: zakup teraz, poczekanie na PV, doładowanie przed szczytem oraz wspólny scenariusz niedoszacowania zużycia i nadwyżki PV. Dodatkowy bufor na błąd zużycia może wynosić **0–15 punktów procentowych SOC** i nie jest sztywnym celem. Atrybut `robust_policy` sensora `sensor.energy_co_pilot_planning_status` i diagnostyka podają porównanie wariantów, ryzyka i powody wyboru; `load_risk_policy` służy tylko zachowaniu zgodności ze starszymi odbiorcami danych. Zasady sterowania i bezpieczeństwa: [REQUIREMENTS](requirements/REQUIREMENTS.md) oraz [EXECUTION](requirements/EXECUTION.md). **Regulacja prądów ładowania jest dozwolona wyłącznie po to, aby przesunąć ładowanie w czasie albo rozciągnąć je na dłuższy okres; nigdy w celu dopasowania do prognozowanej mocy czy SOC.** Integracja w ogóle nie odczytuje ani nie zapisuje nastawy maksymalnego prądu rozładowania.

Zatwierdzone reguły, cele i uprawnienia: [REQUIREMENTS.md](requirements/REQUIREMENTS.md). Jedynym źródłem produkcji w integracji jest `sensor.pv_sum`; nie stosuje się PV1/PV2.

## Planner Lab — tylko GitHub Pages

**[Otwórz Planner Lab](https://duckerdk.github.io/energy-copilot/planner-lab/)**. Uruchamia się w przeglądarce (Pyodide i Web Worker), bez lokalnego serwera, instalacji Pythona ani Home Assistant. Dane scenariusza nie są wysyłane do serwera aplikacyjnego. Repozytorium publikuje stronę przez [planner-lab-pages.yml](.github/workflows/planner-lab-pages.yml); wymagana konfiguracja Pages: **Settings → Pages → Build and deployment → GitHub Actions**.

W tabeli można zmienić godzinowe ceny spot, prognozę PV, pobór domu, SOC, pojemność, napięcie, ograniczenia prądowe i sprawność na 24–72 h. Obliczenia wykorzystują **ciągły solver scenariuszy z `engine.py` i oryginalny fizyczny walidator z `planner.py`**. Ceny zakupu: spot + migawka taryf N1 z 20.10.2026 (nie aktualizuje się automatycznie); sprzedaż: spot. Przykładowe dobowe zużycie bazuje na godzinowej historii HA 19–20.10.2026 i powtarza się w scenariuszach dłuższych. Możliwy import/eksport scenariuszy JSON/CSV oraz eksport wyników kwartalnych. **Import plików HA:** w Planner Lab użyj „Import cen HA (.txt)” dla eksportu `raw_today/raw_tomorrow` oraz „Import Forecast.Solar (.txt)” dla `watts`/`wh_period`. Ceny z pliku są interpretowane jako **spot** (zakup wyliczany oddzielnie z historycznych taryf N1). PV przeliczane jest z **Wh okresu zakończonego w podanym czasie** na godzinową średnią kW z zachowaniem energii, także przy niepełnych godzinach wschodu i zachodu. Zera przed wschodem/po zachodzie w obrębie doby są przyjmowane tylko przy potwierdzonych zerowych W na obu krańcach. Daty i DST są dopasowywane po UTC, po imporcie dwóch plików wykorzystywany jest ich **wspólny** horyzont. Zużycie domu pozostaje edytowalne (domyślnie archiwalny profil przykładowy). Pliki nie opuszczają przeglądarki. Strona nie steruje falownikiem ani nie udowadnia fizycznej wykonalności sześciu TOU.

## Replay HA — odtworzenie obliczeń w przeglądarce

1. W aktualnej wersji Energy Co-Pilot ustaw `dry_run` i upewnij się, że status planowania to `preview`.
2. W HA otwórz **Ustawienia → Urządzenia i usługi → Energy Co-Pilot → Pobierz diagnostykę**. Nowa diagnostyka JSON zawiera `data.planner_replay` — dokładnie te wartości, które zostały podane do optymalizatora w jednym przebiegu: parametry baterii, początkowy SOC, wszystkie kwadranse PV/dom, **rzeczywiste ceny zakupu i sprzedaży**, zezwolenie na eksport PV, użyta wycena końcowego SOC oraz pełne wynikowe przepływy.
3. Wejdź w [Planner Lab](https://duckerdk.github.io/energy-copilot/planner-lab/), sekcja **Replay HA**, kliknij **Wczytaj diagnostykę HA (.json)**, wybierz nowy plik i kliknij **Porównaj HA i Lab**.
4. **Po imporcie dane HA automatycznie stają się edytowalnym scenariuszem 15-minutowym**, a Lab oblicza nowy plan bez ręcznego wprowadzania cen, PV czy zużycia. Możesz zmieniać kwadranse, osobno ceny zakupu i sprzedaży, SOC, napięcie, prądy, sprawności i wycenę końcową. **Oblicz plan na danych HA** uruchamia ponownie ten sam produkcyjny solver, a wykresy i podsumowanie przedstawiają wynik na danych HA lub zmodyfikowanym scenariuszu. `Przywróć oryginalne dane HA` resetuje zmiany; `Zapisz zmieniony scenariusz JSON` umożliwia późniejszy import.
5. Osobny przycisk **Porównaj HA i Lab** nadal kontroluje numeryczną zgodność oryginalnego przebiegu; wynik i różnice kwadransowe można pobrać jako CSV. **Wróć do scenariusza godzinowego** przywraca dotychczasowy, przykładowy tryb. Nie mieszać obu trybów: import HA używa oryginalnych cen i energii co 15 minut, a scenariusz godzinowy nadal korzysta z taryf N1 i profilu historycznego.

W trybie Replay HA **nie** dodaje się taryf N1 ani nie wyznacza ponownie prognoz: replay używa oryginalnych, już przygotowanych wejść kwadransowych. Nie wymaga pełnej godziny startu i zachowuje dokładne wartości SOC, napięcia, wydajności i wartości końcowej. Porównuje przebiegi **tej samej** polityki 2.0.0 (`robust_strategy.py` i `continuous_optimizer.py`), dołączonej do GitHub Pages wraz z `replay.py`, `planner.py` i `horizon_optimizer.py`. Tryb zwykłego Scenariusza pozostaje niezależny.

**Prywatność:** plik diagnostyki zawiera prognozowane zużycie domu z rozdzielczością 15 minut. Lab odczytuje go **lokalnie w przeglądarce**; nie zapisuje go do repo, serwera ani stanu sensora. Pełna diagnostyka HA może zawierać dodatkowe informacje systemowe: udostępniaj ją ostrożnie. Stare diagnostyki z v1.13.0 nie posiadają wymaganej migawki, więc nie można ich odtworzyć w ten sposób. Replay ma cel wyłącznie kontrolny i **nie wykonuje komend falownika**.

## Gdzie są logi Energy Co-Pilot

- **Aktywność:** czytelna, chronologiczna historia decyzji planera, wysłanych nastaw, blokad, wznowień i ARM/STOP. Każdy wpis nosi nazwę **Energy Co-Pilot**. Używa natywnego zdarzenia HA `logbook_entry` z domeną `energy_copilot` i identyfikatorem encji `Decision journal` z rejestru encji, dzięki czemu wpisy można przeglądać po wybraniu urządzenia Energy Co-Pilot. Retencją zarządza Recorder. Sensor `Decision journal` pozostaje punktem dostępu do archiwum ze stałym stanem `ready` lub `unavailable`. Zmiany stanów planera i jakości danych są publikowane osobno z konkretną przyczyną, a nie jako pozbawione kontekstu zmiany stanu sensora.
- **Logi systemowe → Core:** czytelne komunikaty `Energy Co-Pilot`. Ostrzeżenia o blokadach i błędy są na poziomie WARNING/ERROR; zwykłe decyzje na INFO i są dostępne w widoku surowych logów, jeśli poziom logowania HA dopuszcza INFO. Widok skrócony Logów systemowych pokazuje przede wszystkim ostrzeżenia i błędy.
- **Pobierz diagnostykę:** techniczne archiwum `data.decision_journal.events` przechowywane do 30 dni/6000 wpisów, niezależne od retencji Recorder. Przeznaczone do dokładnej analizy, nie do codziennej lektury.

Wpis wykonania rozróżnia potwierdzone zmiany nastaw (przed → po, encja) i brak nowych poleceń przy już poprawnych nastawach. Błąd zapisu wskazuje niepotwierdzone polecenie i wcześniej potwierdzone zmiany. Nie dopisujemy komentarzy o przepływie energii do każdego wpisu. Pierwszy plan kwadransa podaje wybrane działanie i krótkie uzasadnienie kosztowe. Dla ładowania PV, ładowania z sieci i rozładowania uruchamiana jest osobna, nieingerująca w sterowanie optymalizacja tego samego horyzontu z zakazem wybranej akcji w pierwszym kwadransie. Różnica kosztu obu pełnych wariantów jest raportowana z dokładnością 0,001 DKK; przy braku różnicy dziennik tego nie ukrywa. Korekta tego samego kwadransa jest wpisem `Korekta planu` z różnicami względem poprzedniego planu. Odczyty SOC, ceny i prognozy nie są kopiowane do uzasadnienia. Planer loguje zmianę statusu i przyczynę; wykonawca loguje skutki w falowniku. **Brak kontrfaktycznego porównania** musi zostać nazwany wprost — nie wolno zastępować go hasłem, że optymalizator minimalizuje koszt.

## Instalacja i aktualizacja HACS

Wymagany Home Assistant **2026.10 lub nowszy** (testowany Core 2026.10.2, Python 3.14).

1. Dodaj repozytorium `https://github.com/duckerdk/energy-copilot` do HACS jako **Integration**.
2. Zainstaluj najnowszy opublikowany GitHub Release, uruchom ponownie HA i dodaj integrację w **Ustawienia → Urządzenia i usługi**.
3. Po aktualizacji sprawdź `installed_version` oraz `installed_build.tag` i `installed_build.integrity` w diagnostyce. Oficjalne wydanie ma `payload_matches_build_info`.

Alternatywne ręczne kopiowanie `custom_components/energy_copilot` nie zapewnia `BUILD_INFO.json` ani gwarantowanego pochodzenia wydania. Nie trzeba zmieniać ESPHome, Modbus lub ustawień falownika.

**Rollback 2.0.3 → 2.0.2:** wybierz w HACS wydanie `2.0.2` i uruchom ponownie Home Assistant; opublikowany tag i paczka `v2.0.2` pozostają niezmienione.

**Rollback 2.0.2 → 2.0.1:** HACS pozwala wybrać wcześniejsze wydanie. Po instalacji uruchom ponownie HA. Wydanie 2.0.1 pozostaje nienaruszone.

**Rollback 2.0.1 → 2.0.0 lub 1.16.19:** obie starsze wersje zachowują własne, niezmienione tagi i paczki. W HACS wybierz poprzednią wersję, uruchom ponownie HA i sprawdź `installed_build.tag` w diagnostyce.

**Rollback 2.0.0 → 1.16.19:** wersja `v1.16.19` pozostaje osobnym, niezmienionym [GitHub Release](https://github.com/duckerdk/energy-copilot/releases/tag/v1.16.19), z własną paczką i sumami kontrolnymi. W HACS otwórz integrację Energy Co-Pilot, wybierz ponowne pobranie i wersję `1.16.19`, uruchom ponownie HA i zweryfikuj tag oraz sumę w diagnostyce. Nie przesuwać ani nie nadpisywać istniejących tagów.

## Planowanie w HA

**2.0.3 — poprawiona selekcja godzin zakupu:** próg opłacalności rozpoczęcia nowej kampanii ładowania (0,10 DKK; kontynuacja 0,05 DKK) **nie służy już do przenoszenia takiego samego zakupu na droższe kwadranse**. Filtr usuwa jedynie naprawdę zbędne ładowanie; jeśli ponowne rozwiązanie pełnego horyzontu zastępuje je zakupem w innych godzinach, oryginalne tańsze okno zostaje zachowane. Diagnostyka podaje `charge_relocations_preserved` oraz osobno `minor_charges_rejected`. Wymaga weryfikacji na żywym HA, a plan nie jest dowodem faktycznego przepływu.

**2.0.2 — automatyczne odzyskiwanie sterowania:** zapisy są sprawdzane w jednej encji HA co 2 s, maksymalnie przez 30 s. Po niepewnym zapisie ARM pozostaje aktywny, a wykonawca porównuje aktualne nastawy z **nowym** planem po opóźnieniu 30–300 s. Ręczny STOP ma pierwszeństwo. Drobne różnice SOC nie generują serii zapisów. Aktywność HA pokazuje krótkie polskie komunikaty z cenami, np. „Ładuję baterię po 2,11 na droższy okres (3,89)”. Pełne szczegóły zostają w diagnostyce. Potwierdzenie encji HA nie zastępuje niezależnej weryfikacji pracy falownika.


**2.0.1 — korekta bieżącego SOC i rozładowania:** Home Assistant przelicza plan od ostatniego odczytu SOC, także dla **pozostałej części aktualnego kwadransa**. Najbliższe przedziały uwzględniają zanikającą korektę prognoz z pomiarów W PV i domu; po zmianie decyzji `battery_discharge` wykonawca ustawia aktywny próg TOU **20%**, nie prognozowany SOC na koniec kwadransa. Wycenianie niepewnego dodatkowego poboru nie karze nominalnego zużycia baterii — liczy koszt rzeczywiście brakującej energii według godzin jej importu. Nie jest to gwarancja fizycznej realizacji przepływów, a działanie na realnym Deye wymaga weryfikacji.


W **Energy Co-Pilot → Konfiguruj** ustaw `dry_run` dla symulacji, a `automatic` dla jawnie aktywowanego sterowania (domyślnie ARM po starcie; **Automatic control ARM / STOP** pozwala ręcznie zatrzymać zapis). Status `sensor.energy_co_pilot_planning_status` oznacza: `monitor` — brak planu, `blocked` — brak istotnych danych, `preview` — wygenerowany plan dla dostępnego horyzontu (`complete` albo `partial`). `sensor.energy_co_pilot_modeled_saving` jest **modelowaną** różnicą kosztu względem wariantu bez cykli magazynu, a **nie** realną oszczędnością wobec aktualnego Deye.

Od v1.13.0 optymalizator rozpatruje **cały wspólny horyzont opublikowanych cen i dostępnych prognoz**, z krokiem czasu 15 min, ale **ciągłą energią baterii** (bez dawnej siatki 0,10 kWh). Zachowuje SOC 20–100%, limity prądów ładowania do 50 A (bez odczytu nastawy prądu rozładowania), koszt degradacji 0,40 DKK/kWh DC, zakaz eksportu baterii i niezależną walidację przepływów. Koniec planu uwzględnia modelowaną wartość pozostawionej energii; nie stosuje sztywnego docelowego SOC. Wycena okresu po końcu znanych cen jest niepewnym wskaźnikiem opartym **wyłącznie na opublikowanych cenach i prognozie zużycia**, nie wymyślonymi cenami jutra.

**Potwierdzona konfiguracja falownika:** `Load First`, eksport baterii OFF; nie zmieniać. Użytkownik potwierdził, że Deye realizuje zadane prądy ładowania. Planer przewiduje prąd ładowania i stan `Solar Sell`: od **0,40 DKK/kWh ceny sprzedaży** włącznie ON, poniżej OFF. Po włączeniu eksportu falownik sam rozdziela nadwyżkę PV; optymalizator nie nadaje osobnej nastawy mocy eksportu. W trybie `dry_run` żadnej z tych nastaw nie wysyła.

Atrybut `hourly_plan` podaje: `start`, `buy_price_dkk_kwh`, `sell_price_dkk_kwh`, `solar_sell_planned_on`, `home_kwh`, `pv_dc_kwh`, `grid_charge_kwh`, `pv_charge_dc_kwh`, `battery_discharge_dc_kwh`, `charge_current_setpoint_a`, `grid_import_kwh`, `grid_export_kwh`, `purchase_cost_dkk`, `sales_revenue_dkk`, `pv_curtailed_dc_kwh` i `soc_end_pct`. Sumy zakupu i przychodu ze sprzedaży są raportowane **oddzielnie** od degradacji i teoretycznej korzyści.

## Źródła danych i jakość

| Rola | Encja |
| --- | --- |
| Moc PV (jedyna) | `sensor.pv_sum` |
| Sieć (+ import / − eksport) | `sensor.sun12k_total_grid_power` |
| Bateria (+ rozładowanie / − ładowanie) | `sensor.sun12k_battery_output_power` |
| Zużycie domu (pochodne PV + sieć + bateria) | `sensor.home_energy_consumption` |
| SOC | `sensor.sun12k_battery_capacity` |
| Zakup / sprzedaż DKK/kWh | `sensor.energi_data_service` / `sensor.energi_data_spotpris` |

Liczbową ujemną moc domu normalizuje się wewnętrznie do 0 W; `unknown`, `unavailable` oraz luki Recorder **nie są** zerowane. Sam wiek `last_reported` nie oznacza awarii niezmiennej wartości. Pełny kontrakt pomiarów: [HA_CONTRACT.md](requirements/HA_CONTRACT.md).

**Forecast.Solar:** `wh_period[t]` opisuje energię okresu kończącego się w `t`. Brakujące przedziały nocne mogą być uzupełnione zerem **jedynie** przy potwierdzonym 0 W o astronomicznym wschodzie/zachodzie słońca. Braki dzienne pozostają jawne. Oryginalne prognozy W/Wh są archiwizowane bez zmian; model równomiernej mocy wewnątrz opublikowanego okresu jest oznaczony `uniform_power_unverified`.

**Zużycie domu:** model 7-dniowy czyta godzinowe statystyki HA z ostatnich 45 dni, uwzględnia dni tygodnia, dni robocze/wolne, duńskie święta i DST. Obejmuje 672 kwadranse; energia godzinowa jest dzielona po równo na kwadranse. Wariant oparty o pochodny bilans domu **nie jest niezależnym pomiarem AC**. Raport jakości pokazuje 7-dniowy holdout historyczny oraz narastające błędy prognozy PV i domu porównywane z odczytami po zamrożeniu prognoz; nie są dowodem fizycznej kalibracji.

**Recorder i archiwum:** domyślna diagnostyka pokazuje agregaty jakości, nie prywatne szeregi zużycia. Archiwum surowych prognoz ma domyślną retencję 90 dni i 10 000 wersji (ograniczenie 32 MiB). Zapisy cen dostępne są tylko w okresie ich rzeczywistej publikacji.

### Wykres 7 dni w Home Assistant

Zainstaluj osobno przez HACS (Frontend) [ApexCharts Card](https://github.com/RomRider/apexcharts-card). Dodaj ręczną kartę dashboardu i wklej YAML, zmieniając `entity` na faktyczny identyfikator:

```yaml
type: custom:apexcharts-card
graph_span: 7d
span:
  start: hour
header:
  show: true
  title: Prognoza zużycia na 7 dni
series:
  - entity: sensor.energy_co_pilot_7_day_home_energy_forecast
    name: Zużycie (kWh/h)
    type: column
    data_generator: |
      return (entity.attributes.hourly || []).map(p => [
        new Date(p.start).getTime(), p.kwh
      ]);
```

Karta ApexCharts nie jest częścią samej integracji Energy Co-Pilot. Prognoza 7 dni nie oznacza, że dostępne są ceny energii i PV na 7 dni — podgląd optymalizacji nadal działa tylko w horyzoncie rzeczywiście opublikowanych danych. Test historyczny walk-forward i potwierdzenie kalibracji źródeł pozostają wymagane.

## Dokumentacja projektu

| Plik | Cel |
| --- | --- |
| [REQUIREMENTS](requirements/REQUIREMENTS.md) | Decyzje użytkownika, ograniczenia, zakres autonomii |
| [HA_CONTRACT](requirements/HA_CONTRACT.md) | Encje HA, wartości, jednostki, Forecast.Solar |
| [OPTIMIZATION](requirements/OPTIMIZATION.md) | Model przepływów i cel kosztowy |
| [EXECUTION](requirements/EXECUTION.md) | Wykonanie TOU, STOP i bezpieczeństwo |
| [VALIDATION](requirements/VALIDATION.md) | Testy automatyczne i kryteria odbioru |
| [OPEN_ITEMS](requirements/OPEN_ITEMS.md) | Wyłącznie aktualne zadania do wykonania |
| [AGENTS](AGENTS.md) | Zasady pracy Codexa |

## Testy i wydania

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests scripts/build_release.py
.venv/bin/ruff format --check custom_components tests scripts/build_release.py
.venv/bin/pytest --cov=custom_components.energy_copilot --cov-report=term-missing
.venv/bin/python scripts/check_docs.py
```

**Jedyny workflow publikujący:** [publish-version-on-main.yml](.github/workflows/publish-version-on-main.yml). Uruchamia się po zmianie `manifest.json` na `main`; dla istniejącego taga bez wydania można go uruchomić ręcznie (`workflow_dispatch`). Zawsze wykonuje testy, buduje pakiet z niezmiennego taga i weryfikuje publiczne wydanie oraz aktywa `energy_copilot.zip`, `BUILD_INFO.json`, `SHA256SUMS`. **Merge i zielone CI nie oznaczają wydania.** Wersja musi być nowa; nie wolno przesuwać istniejącego taga. Dokumentacja sama nie podnosi wersji. Procedura i kryterium GOTOWE: [AGENTS.md](AGENTS.md).

## Status i pochodzenie wydań

Aktualny numer wersji sprawdzaj w manifeście, a opublikowane paczki i historię zmian w [GitHub Releases](https://github.com/duckerdk/energy-copilot/releases). Po instalacji w HA porównaj `installed_version`, `installed_build.tag` i `installed_build.integrity` w diagnostyce. Dziennik zmian utrzymują tagi i wydania — README opisuje **aktualny kontrakt**, nie chronologię dawnych napraw.
