# Kontrakt decyzyjny — v5.1 oraz późniejsza korekta v5.1.1

**Cel dokumentu:** zachować dokładne założenia techniczne i ich późniejsze zmiany, bez samodzielnej zmiany strategii. Oryginalny tekst: [logic_v5.1.txt](reference/logic_v5.1.txt). Korekta v5.1.1 pochodzi z historycznej rozmowy użytkownika.

## 1. Dane wejściowe

- Aktualny SOC: `sensor.sun12k_battery_capacity` [%].
- Aktualna cena spot: `sensor.energi_data_spotpris` [zakładane DKK/kWh].
- Godzinowe przyszłe ceny: `sensor.energi_data_service` [struktura nieznana].
- Produkcja PV / zużycie domu: `sensor.pv_sum` i `sensor.home_energy_consumption` [kW].
- Prognoza PV na dziś i jutro: `sensor.energy_production_today` / `sensor.energy_production_tomorrow` [kWh].
- Wyjścia: `switch.sun12k_solar_sell`, `switch.sun12k_grid_charge`, `number.sun12k_maximum_battery_grid_charge_current`.
- Powiadomienia: `notify.mobile_app_pixel_7dk`.

## 2. Parametry źródłowe v5.1

| Parametr | Oryginalna wartość |
| --- | --- |
| Użytkowa pojemność magazynu | 8 kWh |
| Zakładany zakres SOC | 20–100% |
| Założone nocne zużycie | minimum 5 kWh, preferowane 8 kWh |
| Bufor SOC | 10% (w źródłowym wzorze dodawane jest **10 punktów procentowych**) |
| Minimalna cena sprzedaży | 0,4 DKK/kWh |
| Cykl pełnego planowania | raz dziennie, np. 00:10 |
| Horyzont planu AI | 24 godziny (snapshot v5.0) |

Wzór **dokładnie jak w dokumencie v5.1**:

```python
required_soc_percent = (night_consumption_kwh / 8.0) * 100 + 10
# 5 kWh -> 72.5%
```

Nie ma tu potwierdzonego kodu ochrony przed wartościami poza zakresem ani uzgodnionej definicji momentu „przed nocą”. Te kwestie nie są rozstrzygane w tej dokumentacji.

## 3. Oryginalna strategia v5.1 — warunki

1. **Priorytet fizyczny/strategiczny:** PV najpierw zasila dom.
2. **Dostępność energii na noc:** system przewiduje zużycie nocne i dodaje bufor.
3. **Jeżeli prognoza PV wystarczy:** nadwyżkę PV można **sprzedać rano w okresie wysokiej ceny**, a doładowanie magazynu przesunąć na okres spadku ceny.
4. **Jeżeli prognoza PV jest słaba:** ładowanie magazynu ma wyprzedzać sprzedaż.
5. **Próg sprzedaży w tekście:** przy cenie poniżej 0,4 `solar_sell=OFF`; przy cenie ≥ 0,4 `solar_sell=ON`.
6. **Ładowanie z sieci:** przy SOC poniżej docelowego analizować nadchodzące ceny i kupować w najtańszym okresie; w logice v5.1 wskazano „tylko przy braku produkcji PV” i „nigdy przy wysokiej cenie”.
7. **Planowanie cykliczne:** pełna kalkulacja dzienna przy użyciu aktualnych prognoz, powiadomienie o istotnych działaniach.

**Nie ma kompletnej definicji algorytmu rankingowego godzin, kosztów transakcyjnych, ograniczeń importu/eksportu, długości okien, priorytetów kolidujących reguł ani warunków awaryjnych.** Dokument opisuje zachowanie oczekiwane.

## 4. Korekta v5.1.1 — obowiązujące rozróżnienie sterowania

W późniejszej rozmowie użytkownik doprecyzował:

| Funkcja | Poprawna historyczna intencja v5.1.1 |
| --- | --- |
| Włącz/wyłącz ładowanie **z sieci** | `switch.sun12k_grid_charge` |
| Ogranicz ładowanie **z PV** w oczekiwaniu na tańsze godziny | `number.sun12k_maximum_battery_grid_charge_current`; w rozmowie `1 A` |
| Zezwól/zablokuj sprzedaż | `switch.sun12k_solar_sell` |

**Konflikt:** nazwa `number.sun12k_maximum_battery_grid_charge_current` i opis w oryginalnym pliku v5.1 sugerują limit ładowania **z sieci**, podczas gdy korekta mówi o limicie **PV**. Dopóki działanie encji nie zostanie sprawdzone na faktycznym urządzeniu, nie należy na jej podstawie wykonywać automatycznych sterowań. Korekta jest wiernym zapisem ustalenia użytkownika, nie zweryfikowanym faktem o oprogramowaniu falownika.

## 5. Granice stanu realizacji

- Istniał prototyp `EnergyPolicyAgent` tworzący plan 24 h; snapshot v5.0 opisał go jako gotowy szkielet.
- Logikę zapisano w formie dokumentu tekstowego / promptu.
- Brak źródeł i testów potwierdzających, że wszystkie powyższe warunki rzeczywiście działały.
- Brak potwierdzonego wykonawcy sterowań do HA; skutek na falowniku nie został zbadany.
- Historyczna estymacja nocy generowała błędne wyniki; tego wyniku nie wolno wykorzystywać do decyzji.

**Nie implementujemy nowej logiki ani nie oceniamy opłacalności w ramach tego etapu.**
