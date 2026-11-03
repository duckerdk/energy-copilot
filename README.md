# Energy Co-Pilot

Integracja Home Assistant do ekonomicznego sterowania magazynem energii i falownikiem Deye przez istniejące encje i usługi HA. Planer optymalizuje koszt zakupu energii, przychody ze sprzedaży PV, zużycie baterii i ryzyko prognoz. Plan powstaje co 15 minut na podstawie **opublikowanych cen i dostępnych prognoz**, bez zgadywania brakujących danych.

**Aktualna wersja:** [manifest.json](custom_components/energy_copilot/manifest.json) · **Instalacja HACS:** [GitHub Releases](https://github.com/duckerdk/energy-copilot/releases) · **Wymagany Home Assistant:** 2026.10 lub nowszy.

## Instalacja

1. W HACS dodaj `https://github.com/duckerdk/energy-copilot` jako repozytorium typu **Integration**.
2. Zainstaluj najnowszy opublikowany Release, uruchom ponownie Home Assistant i dodaj Energy Co-Pilot w **Ustawienia → Urządzenia i usługi**.
3. W **Energy Co-Pilot → Konfiguruj** wybierz `dry_run` (symulacja) albo świadomie aktywuj `automatic` (sterowanie). **Automatic control ARM / STOP** pozwala zatrzymać zapisy.
4. Po aktualizacji sprawdź w pobranej diagnostyce `installed_version`, `installed_build.tag` i `installed_build.integrity`. Dla oficjalnej paczki oczekiwane jest `payload_matches_build_info`.

Do cofnięcia aktualizacji wybierz wcześniejszą dostępną wersję w HACS, uruchom ponownie HA i zweryfikuj tag. Polityka retencji zakłada **bieżące wydanie i pięć poprzednich**; starsze wydania są przeznaczone do usunięcia po sprawdzeniu punktów rollbacku. Ręczne kopiowanie folderu integracji nie zapewnia metadanych pochodzenia paczki.

## Jak działa

- **`monitor`:** tylko odczyt; **`dry_run`:** planowanie bez poleceń do falownika; **`automatic`:** sterowanie po aktywacji.
- **SOC 20–100%**, rozdzielczość nastaw TOU 1%. W okresach wysokich cen dostępna jest cała energetycznie dopuszczalna moc rozładowania, bez sztucznego dawkowania.
- Wykonawca może zmieniać **sześć slotów TOU**, Grid Charge i Solar Sell. **Eksport baterii pozostaje zabroniony**, a `Load First` nie jest zmieniane. Eksport nadwyżki PV może być włączony od ceny sprzedaży **0,40 DKK/kWh**.
- Integracja **nie odczytuje ani nie zapisuje maksymalnego prądu rozładowania**. Prądy ładowania mogą być regulowane tylko dla **przesunięcia lub rozciągnięcia ładowania w czasie**; planowany SOC ani prognoza mocy nie służą do dławienia PV.
- Model zużycia domu używa **45 dni** historii (z większą wagą ostatnich 7/14 dni). Planer rozpatruje pełny wspólny horyzont, niepewność PV i zużycia oraz wartość energii pozostałej po horyzoncie.
- Nastawy potwierdzane są odczytem encji HA; niepewne zapisy podlegają procedurze odzyskiwania na podstawie nowego planu. **Stan encji HA nie potwierdza fizycznego przepływu energii.**

Zatwierdzone zasady i bezpieczeństwo opisują [REQUIREMENTS](requirements/REQUIREMENTS.md), [OPTIMIZATION](requirements/OPTIMIZATION.md) i [EXECUTION](requirements/EXECUTION.md).

## Źródła danych

| Rola | Encja |
| --- | --- |
| PV (jedyne źródło) | `sensor.pv_sum` |
| Sieć (+ import, − eksport) | `sensor.sun12k_total_grid_power` |
| Bateria (+ rozładowanie, − ładowanie) | `sensor.sun12k_battery_output_power` |
| Zużycie domu (bilans pochodny) | `sensor.home_energy_consumption` |
| SOC | `sensor.sun12k_battery_capacity` |
| Ceny zakupu / sprzedaży DKK/kWh | `sensor.energi_data_service` / `sensor.energi_data_spotpris` |

Nieprawidłowych lub brakujących danych nie należy zamieniać na zera. `sensor.pv_sum` zastępuje sumowanie PV1/PV2. Pełny kontrakt: [HA_CONTRACT](requirements/HA_CONTRACT.md).

## Planner Lab i Replay HA

**[Otwórz Planner Lab](https://duckerdk.github.io/energy-copilot/planner-lab/)** — symulacja w przeglądarce przez GitHub Pages, bez instalacji Home Assistant lub Pythona. Można zmieniać ceny, PV, zużycie, SOC, ograniczenia i sprawności, importować JSON/CSV lub pliki TXT cen i Forecast.Solar oraz eksportować wyniki.

**Ważne:** zwykły scenariusz godzinowy wykorzystuje historyczną migawkę taryf N1 z 20.10.2026 i przykładowy profil domu z 19–20.10.2026. Taryfy **nie aktualizują się automatycznie**. W tym trybie importowane ceny z HA traktowane są jako spot.

### Odtworzenie dokładnych danych HA

1. Ustaw `dry_run` i sprawdź status `preview`. W HA wybierz **Energy Co-Pilot → Pobierz diagnostykę**.
2. W Planner Lab otwórz **Replay HA → Wczytaj diagnostykę HA (.json)**. Plik musi zawierać `data.planner_replay`.
3. **Porównaj HA i Lab** kontroluje zgodność oryginalnego wyniku; **Oblicz plan na danych HA** uruchamia optymalizację na zaimportowanych kwadransach.
4. Edytuj ceny zakupu/sprzedaży, prognozy, SOC i parametry baterii, ponownie oblicz plan albo przywróć oryginalne dane. Różnice można wyeksportować.

Replay korzysta z oryginalnych **15-minutowych wejść**, bez ponownego doliczania taryf lub generowania prognoz. Dane są przetwarzane lokalnie w przeglądarce. Diagnostyka może zawierać prywatne informacje o instalacji — nie udostępniaj jej publicznie. Lab nie wysyła poleceń do falownika i nie dowodzi fizycznej wykonalności projekcji na sześć TOU.

## Status, aktywność i diagnostyka

- **`sensor.energy_co_pilot_planning_status`:** `monitor` — brak planowania, `blocked` — brak wymaganych danych, `preview` — plan dostępny dla pełnego lub częściowego horyzontu.
- **Aktywność HA (Logbook):** chronologiczne decyzje, wykonane zapisy, blokady i odzyskiwanie sterowania; **Logi systemowe → Core:** ostrzeżenia i błędy oraz komunikaty INFO (zależnie od poziomu logowania).
- **Pobierz diagnostykę:** szczegółowy dziennik, wejścia optymalizatora i dane do Replay HA.
- **`sensor.energy_co_pilot_modeled_saving`:** oszczędność *modelowana* względem scenariusza bez cykli magazynu — **nie** potwierdzona oszczędność względem rzeczywistej pracy Deye.

## Dokumentacja projektu

| Dokument | Zakres |
| --- | --- |
| [REQUIREMENTS](requirements/REQUIREMENTS.md) | Wiążące decyzje użytkownika i polityka sterowania |
| [HA_CONTRACT](requirements/HA_CONTRACT.md) | Encje, ceny, jednostki i jakość danych |
| [OPTIMIZATION](requirements/OPTIMIZATION.md) | Model energii, ryzyka i kosztu |
| [EXECUTION](requirements/EXECUTION.md) | TOU, zapisy, recovery i bezpieczeństwo |
| [VALIDATION](requirements/VALIDATION.md) | Regresje i kryteria odbioru |
| [OPEN_ITEMS](requirements/OPEN_ITEMS.md) | Aktualne sprawy niepotwierdzone na realnym HA |
| [AGENTS](AGENTS.md) | Instrukcje pracy dla Codexa |

## Testy i publikacja

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/ruff check custom_components tests scripts/build_release.py
.venv/bin/ruff format --check custom_components tests scripts/build_release.py
.venv/bin/pytest --cov=custom_components.energy_copilot --cov-report=term-missing
.venv/bin/python scripts/check_docs.py
```

Wydania HACS buduje [publish-version-on-main.yml](.github/workflows/publish-version-on-main.yml) z niezmiennego taga. **Merge i zielone CI nie oznaczają opublikowanego wydania.** Weryfikuj Release oraz aktywa `energy_copilot.zip`, `BUILD_INFO.json` i `SHA256SUMS`. Zmiany dokumentacji nie wymagają nowej wersji integracji.