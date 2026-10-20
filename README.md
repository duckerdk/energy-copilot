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

Formularz umożliwia mapowanie czujników z HA_CONTRACT, wybór `monitor`/`dry_run`, odczytywanego przełącznika Solar Sell i opcjonalnego config entry Forecast.Solar. Ustawienia można zmienić przez Opcje; integracja przeładuje się automatycznie. `dry_run` w M1/M2 nadal wyłącznie odczytuje dane — planner nie jest jeszcze zaimplementowany.

Sensor diagnostyczny **Input quality** i pobierana diagnostyka pokazują problemy ze źródłami. Brak Forecast.Solar, Recorder lub poprawnej historii oznacza jakość `degraded`, nie wymyślone dane. Prognoza korzysta z natywnego `forecast_solar.get_forecast` w rozdzielczości `raw`, bez bezpośredniego połączenia z API dostawcy. Maksymalnie 48 wersji prognoz jest przechowywanych lokalnie w `.storage`; usunięcie integracji usuwa ten magazyn. Każda wersja ma czas pobrania i obejmuje tylko przedziały zaczynające się nie wcześniej niż pobranie.

Historia obejmuje ostatnie 24 h w pełnych kwadransach UTC, ze źródłami PV/sieć/bateria/dom. Recorder przechowuje zmiany stanów, więc nie dowodzi ciągłej dostępności niezmiennego czujnika: przedłużenie próbki ponad 5 min jest oznaczane jako nieweryfikowalne. To konserwatywny odczyt danych dla M2, nie gotowy profil sezonowy ani model uczenia M3/M5. Diagnostyka raportuje przyjęte limity świeżości i synchronizacji. Nie potwierdzono jeszcze działania na fizycznej instalacji użytkownika ani sprawności AC/DC.

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
