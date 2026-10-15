# Dane i przetwarzanie historii w Energy Co-Pilot

**Status:** odtworzenie historycznego kontraktu CSV i ustaleń technicznych z 14.06.2025. Surowy eksport ani kod oryginalnego eksportera nie zostały przekazane do nowego repozytorium.

## 1. Źródła i format

Historyczna ścieżka: `/home/damian/energy-co-pilot/ha_history.csv`.

Odtworzony z rozmowy nagłówek:

```csv
timestamp,entity_id,value
```

Potwierdzone w relacji z historycznego uruchomienia:
- **270 873 wierszy** i **6 identyfikatorów encji** odczytanych przez loader;
- timestampy normalizowano do **UTC**;
- eksport i loader działały we wczesnym prototypie, z `pandas` w `.venv`.

### Sześć encji historycznie wymienionych przy CSV

1. `sensor.energi_data_spotpris` — cena spot, wartość liczbowa.
2. `sensor.sun12k_battery_capacity` — stan akumulatora, %.
3. `sensor.pv_sum` — moc PV, kW.
4. `sensor.home_energy_consumption` — moc domu, kW.
5. `sensor.energy_production_today` — prognoza energii PV dziś, kWh.
6. `sensor.energy_production_tomorrow` — prognoza energii PV jutro, kWh.

**Zastrzeżenie do zawartości danych:** historyczna lista encji i liczba rekordów pochodzą z jednej relacji z uruchomienia. W późniejszym debugowaniu pojawiła się informacja, że dane wykorzystane do obliczenia nocnego zużycia były danymi **cenowymi**, a nie prawidłowym szeregiem mocy domu. Nie wiemy, czy użyto innej kopii/filtra CSV, czy niepoprawnego wyboru encji. Nie wolno automatycznie zakładać, że ostatnie uruchomienie miało dostęp do prawidłowego profilu poboru.

Zatem przed obliczeniami trzeba **sprawdzić faktyczną zawartość i pokrycie** dla `sensor.home_energy_consumption`, a nie tylko obecność nagłówka.

## 2. Historyczna warstwa DataLoader

Nazwy z opracowanego prototypu:
- `HADataLoader`,
- `get_daily_aggregates()` — agregacja historii według dni,
- `get_current_data()` — dane bieżące, dostarczane agentowi,
- `current_data` i `daily_aggregates` — wejścia przekazywane w JSON do `EnergyPolicyAgent`.

W jednym historycznym uruchomieniu `copilot_v5.py` do planu trafiało **30 dni agregatów** oraz bieżące stany z HA.

**Brakuje oryginałów:** sygnatur metod, nazw kolumn wyniku, sposobu resamplingu, schematu JSON, implementacji filtrów i testów — nie zostały odtworzone.

## 3. Moc a energia: kluczowa korekta obliczeń

`sensor.home_energy_consumption` w rozmowach określano jako **kW (moc)**, a nie licznik energii w kWh. Późniejsza próba estymacji zużycia nocnego zwróciła absurdalny wynik, m.in.:

| Wartość ze zgłoszenia | Wynik |
| --- | ---: |
| Wyliczone nocne zużycie | **154 305,42 kWh** |
| Wyliczony docelowy SOC | **1 928 817,75%** |

W innej iteracji zgłaszano również estymatę `308610.85 Wh` — zatem historyczne wyniki nie są spójnym, zweryfikowanym punktem odniesienia.

Z późniejszej rozmowy wynikało założenie próbkowania mocy **co 5 minut**. Przy **rzeczywiście równomiernych** próbkach i mocy w kW:

```text
E [kWh] = Σ(P_i [kW] × 5/60 [h])
        = Σ(P_i) / 12
```

Ważne rozróżnienia:
- `Σ(P_i)` daje sumę **wartości mocy**, a nie energię.
- Jeśli próbki są nieregularne lub brak danych, stałe `5/60` jest niewiarygodne; trzeba uwzględnić rzeczywiste przedziały czasowe i przyjętą metodę całkowania.
- Nie wolno liczyć nocnego zużycia z `sensor.energi_data_spotpris` ani z mieszaniny encji.
- UTC dla zapisu timestampów nie oznacza, że „noc” należy wyznaczać według UTC — wybór godzin nocy i lokalnej strefy czasu **nie został ostatecznie ustalony**.

**To techniczne rozróżnienia i poprawki z debugowania, nie deklaracja działającego obecnie algorytmu estymacji nocy.**

## 4. Problemy historycznie naprawiane

| Obszar | Problem | Historyczny status |
| --- | --- | --- |
| Strefy czasowe | Porównanie `tz-aware` i `tz-naive datetime` | w snapshot v5.0 zadeklarowano poprawkę |
| JSON | `datetime.date` nie dawało się bezpośrednio serializować | w snapshot v5.0 zadeklarowano poprawkę |
| Spójność LLM | Te same statystyki dawały różne wyniki między próbami | zgłoszony problem, brak dowodu rozwiązania |
| Nocna energia | Sumowanie niepoprawnych danych/jednostek | błędny wynik; późniejszej poprawnej próby nie potwierdzono |
| Wybór encji | Dane cenowe użyte w roli zużycia domu | opisane w diagnozie; sprawdzenie pliku nadal potrzebne |

## 5. Kontrakt do odtworzenia, nie zrealizowany test

Minimalny zestaw sprawdzeń przed wykorzystaniem historii w planie 24h:
- liczba rekordów na `entity_id`; daty min/max i obecność danych zużycia;
- parsowanie `timestamp` jako dat ze strefą i normalizacja do UTC;
- brak niejawnego mieszania `W` / `kW` / `Wh` / `kWh`;
- wartości `unknown`, `unavailable` i braki próbek;
- duplikaty i przerwy w serii oraz częstotliwość próbkowania;
- niezależne, powtarzalne obliczenia numeryczne przed przekazaniem podsumowania do LLM;
- weryfikacja jakości i zakresu danych dla prognozy cen z `sensor.energi_data_service`.

Lista ta **nie stanowi zrealizowanych testów**; wyznacza, co musi być udokumentowane i odtworzone.

Zobacz: [pełny rejestr encji](ENTITIES.md), [historia implementacji](IMPLEMENTATION_HISTORY.md).
