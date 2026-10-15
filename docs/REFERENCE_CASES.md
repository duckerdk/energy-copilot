# Przypadki referencyjne z historycznych uruchomień

To **historyczne wejścia i wyniki z rozmów**, NIE przygotowane teraz testy automatyczne ani wzorzec poprawności optymalizacji. Przy implementacji można nimi porównać zachowanie i osobno ocenić, czy wynik był uzasadniony.

## RC-001 — plan sprzedaży przy wysokiej cenie

| Zmienna | Wartość źródłowa |
| --- | ---: |
| SOC | 99% |
| Pojemność użytkowa | 8 kWh |
| Wskazana ilość energii w baterii | 7,92 kWh |
| Przyjęte zapotrzebowanie nocne | 5 kWh |
| Bufor SOC | 10 p.p. |
| Wymagany SOC | 72,5% |
| Cena spot | 0,979 DKK/kWh |
| Próg sprzedaży | 0,4 DKK/kWh |
| Prognoza PV dziś | 41,823 kWh |
| Prognoza PV jutro | 21,218 kWh |

**Wygenerowany plan** (raport z `python3 copilot_v5.py`):

```yaml
plan_proposed_by_llm:
  switch.sun12k_solar_sell: "on"
  switch.sun12k_grid_charge: "off"
  number.sun12k_maximum_battery_grid_charge_current: 1  # A
```

**Niepotwierdzone:** rzeczywisty stan urządzeń, wywołanie usług sterowania, okres ważności tego planu, przełożenie parametru `1 A` na realny prąd PV. To wyłącznie historyczny *plan*.

## RC-002 — próg ceny sprzedaży z dokumentu v5.1

| Warunek z dokumentu | Oczekiwane zachowanie według dokumentu |
| --- | --- |
| Spot `< 0,4 DKK/kWh` | `switch.sun12k_solar_sell` = OFF |
| Spot `>= 0,4 DKK/kWh` | `switch.sun12k_solar_sell` = ON |

To reguła specyfikacji, **nie wynik przetestowanej automatyki**. Nierozstrzygnięta jest kolizja tego prostego progu z nadrzędną rezerwą energii na noc.

## RC-003 — wzór docelowego SOC z dokumentu v5.1

```text
((5 kWh / 8 kWh) × 100) + 10 = 72,5%
```

To sprawdzenie arytmetyki historycznego wzoru, bez rozstrzygania jego sensowności ani ograniczeń.

## RC-004 — dane do diagnozy błędnej estymacji

- Raportowane nocne zużycie: `154305.42 kWh`.
- Raportowany wymagany SOC: `1928817.75%`.
- Osobna iteracja: `308610.85 Wh`.
- Zgłoszona przyczyna: niewłaściwe źródło danych i/lub jednostki.
- **Status:** wynik błędny, nie używać jako celu testu pozytywnego. Powinien być przypadkiem regresyjnym dla walidacji wejścia i jednostek.

## RC-005 — statystyka fragmentu CSV z testu v1

```text
count: 132
min: -0.04747252125
max: 1.38425766384675
mean: 0.48622474251546033
sum: 64.18166601204076
```

Brakuje filtra encji, zakresu dat i danych źródłowych. Nie da się użyć jako automatycznego testu bez ich odzyskania.

## Zakres pewności

Przypadki zapisane jako **reported_example** albo **requirement**, a nie **verified_regression_test**. Kiedy pojawią się oryginalne pliki i logi, trzeba dopiero wyodrębnić testy automatyczne, niezależnie zweryfikować wyliczenia i ustalić jednostki.
