# Energy Co-Pilot

Natywna integracja Home Assistant `custom_components/energy_copilot`. **Aktualna wydana wersja: [v1.13.0](https://github.com/duckerdk/energy-copilot/releases/tag/v1.13.0)**. Obecnie dostępne: odczyt pomiarów/cen, Forecast.Solar, Recorder, prognoza domu na 7 dni oraz **ciągła optymalizacja w trybie `dry_run`**. Integracja **nie zapisuje nastaw falownika**. Harmonogram fizyczny 15 minut nie jest jeszcze przetłumaczony na sześć rzeczywistych okien TOU Deye (`executable=false`).

Zatwierdzone reguły, cele i uprawnienia: [REQUIREMENTS.md](requirements/REQUIREMENTS.md). Jedynym źródłem produkcji w integracji jest `sensor.pv_sum`; nie stosuje się PV1/PV2.

## Planner Lab — tylko GitHub Pages

**[Otwórz Planner Lab](https://duckerdk.github.io/energy-copilot/planner-lab/)**. Uruchamia się w przeglądarce (Pyodide i Web Worker), bez lokalnego serwera, instalacji Pythona ani Home Assistant. Dane scenariusza nie są wysyłane do serwera aplikacyjnego. Repozytorium publikuje stronę przez [planner-lab-pages.yml](.github/workflows/planner-lab-pages.yml); wymagana konfiguracja Pages: **Settings → Pages → Build and deployment → GitHub Actions**.

W tabeli można zmienić godzinowe ceny spot, prognozę PV, pobór domu, SOC, pojemność, napięcie, ograniczenia prądowe i sprawność na 24–72 h. Obliczenia wykorzystują **ciągły solver scenariuszy z `engine.py` i oryginalny fizyczny walidator z `planner.py`**. Ceny zakupu: spot + migawka taryf N1 z 20.10.2026 (nie aktualizuje się automatycznie); sprzedaż: spot. Przykładowe dobowe zużycie bazuje na godzinowej historii HA 19–20.10.2026 i powtarza się w scenariuszach dłuższych. Możliwy import/eksport scenariuszy JSON/CSV oraz eksport wyników kwartalnych. Strona nie steruje falownikiem ani nie udowadnia fizycznej wykonalności sześciu TOU.

## Instalacja i aktualizacja HACS

Wymagany Home Assistant **2026.10 lub nowszy** (testowany Core 2026.10.2, Python 3.14).

1. Dodaj repozytorium `https://github.com/duckerdk/energy-copilot` do HACS jako **Integration**.
2. Zainstaluj najnowszy opublikowany GitHub Release, uruchom ponownie HA i dodaj integrację w **Ustawienia → Urządzenia i usługi**.
3. Po aktualizacji sprawdź `installed_version` oraz `installed_build.tag` i `installed_build.integrity` w diagnostyce. Oficjalne wydanie ma `payload_matches_build_info`.

Alternatywne ręczne kopiowanie `custom_components/energy_copilot` nie zapewnia `BUILD_INFO.json` ani gwarantowanego pochodzenia wydania. Nie trzeba zmieniać ESPHome, Modbus lub ustawień falownika.

## Planowanie w HA

W **Energy Co-Pilot → Konfiguruj** ustaw `dry_run`. Status `sensor.energy_co_pilot_planning_status` oznacza: `monitor` — brak planu, `blocked` — brak istotnych danych, `preview` — wygenerowany plan dla dostępnego horyzontu (`complete` albo `partial`). `sensor.energy_co_pilot_modeled_saving` jest **modelowaną** różnicą kosztu względem wariantu bez cykli magazynu, a **nie** realną oszczędnością wobec aktualnego Deye.

Od v1.13.0 optymalizator rozpatruje **cały wspólny horyzont opublikowanych cen i dostępnych prognoz**, z krokiem czasu 15 min, ale **ciągłą energią baterii** (bez dawnej siatki 0,10 kWh). Zachowuje SOC 20–100%, limity prądowe 50/100 A, koszt degradacji 0,40 DKK/kWh DC, zakaz eksportu baterii i niezależną walidację przepływów. Koniec planu uwzględnia modelowaną wartość pozostawionej energii; nie stosuje sztywnego docelowego SOC. Wycena okresu po końcu znanych cen jest niepewnym wskaźnikiem opartym **wyłącznie na opublikowanych cenach i prognozie zużycia**, nie wymyślonymi cenami jutra.

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

**Zużycie domu:** model 7-dniowy czyta godzinowe statystyki HA do 365 dni, uwzględnia dni tygodnia, dni robocze/wolne, duńskie święta i DST. Obejmuje 672 kwadranse; energia godzinowa jest dzielona po równo na kwadranse. Wariant oparty o pochodny bilans domu **nie jest niezależnym pomiarem AC**. Raport jakości pokazuje 7-dniowy holdout historyczny oraz narastające błędy prognozy PV i domu porównywane z odczytami po zamrożeniu prognoz; nie są dowodem fizycznej kalibracji.

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
| [EXECUTION](requirements/EXECUTION.md) | Przyszłe wykonanie TOU, STOP i bezpieczeństwo |
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

`main` publikuje nowe wydanie HACS **tylko po zmianie wersji manifestu i udanym CI**. GitHub Release zawiera `energy_copilot.zip`, `BUILD_INFO.json` i `SHA256SUMS`. Scalenie zmian w samej dokumentacji **nie tworzy nowego wydania**.
