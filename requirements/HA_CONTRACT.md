# Kontrakt Home Assistant — źródła danych i sterowanie

Wymagania ekonomiczne i uprawnienia: [REQUIREMENTS.md](REQUIREMENTS.md). Fizyczna realizacja: [EXECUTION.md](EXECUTION.md).

## Czujniki
| Rola | Encja | Interpretacja |
|---|---|---|
| Produkcja PV DC | `sensor.pv_sum` | **PV1 + PV2 na wejściach DC falownika**, niezależnie od podziału energii |
| PV1 / PV2 | `sensor.sun12k_pv1_power`, `sensor.sun12k_pv2_power` | Składowe PV; nie dodawać drugi raz do `pv_sum` |
| Sieć | `sensor.sun12k_total_grid_power` | **Dodatnie = import, ujemne = eksport** |
| Bateria | `sensor.sun12k_battery_output_power` | **Dodatnie = rozładowanie, ujemne = ładowanie** |
| Napięcie/prąd baterii | `sensor.sun12k_battery_voltage`, `sensor.sun12k_battery_output_current` | Weryfikować relację P≈V·I i stronę DC z danymi HA |
| SOC | `sensor.sun12k_battery_capacity` | %; twarda dolna granica polityki w REQUIREMENTS |
| Zużycie domu | `sensor.home_energy_consumption` | Pochodna `pv_sum + total_grid_power + battery_output_power` |
| Alternatywny odczyt sieci | `sensor.sun12k_out_of_grid_total_power_2` | Nie dodawać do `total_grid_power` |
| Energia dzienna | `sensor.sun12k_daily_production`, `sensor.sun12k_today_charge_of_the_battery`, `sensor.sun12k_today_discharge_of_the_battery` | Kumulowane kWh, nie odrębne źródła mocy |

Normalizacja mocy: `grid_import=max(0,P_grid)`, `grid_export=max(0,-P_grid)`, `battery_discharge=max(0,P_bat)`, `battery_charge=max(0,-P_bat)`. Wszystkie wartości wejściowe początkowo [W], następnie konwersja na kW. Kierunki potwierdził użytkownik; nie zadawać mu znów tych pytań. `sensor.pv_sum` pokazuje **moc faktycznie przyjętą na wejściach falownika**, a nie potencjał produkcji ograniczonej (curtailment). Nie doliczać PV→bateria jako dodatkowej produkcji.

**Dom jest szablonem, nie niezależnym licznikiem.** Używa `float(0)`, co maskuje `unavailable` i tworzy możliwe fałszywe odczyty także w historii. Dla każdego slotu uczenia, backtestu i decyzji sprawdź dostępność i aktualność wszystkich źródłowych PV/grid/battery, ich synchronizację i jednostki. Oznacz `invalid_input`, `historical_quality_unverifiable` i `snapshot_not_synchronous`, zamiast zakładać zero. Zerowa reszta z równania szablonu nie dowodzi fizycznej sprawności. Strony AC/DC i straty wymaga model [OPTIMIZATION.md](OPTIMIZATION.md).

**Potwierdzona polityka normalizacji domu (20.10.2026):** krótkie ujemne odczyty bilansu `home` mogą powstawać przy przełączeniach PV/baterii, skokach obciążenia i opóźnieniach Modbus. Dla **ważnego liczbowego pomiaru** przy poprawnie dostępnych PV/grid/battery stosuj w Energy Co-Pilot `P_home_effective=max(0,P_home_raw)`. W historii całkuj moc skorygowaną odcinek po odcinku, bez odrzucania całego kwadransa tylko za ujemny pik. Zachowaj w audycie liczność/czas i wpływ korekty, nie publikuj surowych zdarzeń w standardowej diagnostyce. `unknown`, `unavailable`, błędne jednostki, brak danych składowych, problem po awarii źródła lub luka Recorder pozostają **brakiem danych**, nigdy zerem. Czujnika HA nie zmieniać. To świadoma reguła obliczeniowa, nie weryfikacja fizycznego modelu AC/DC. [Decyzja nadrzędna](REQUIREMENTS.md).

## Ceny
- `sensor.energi_data_service`: końcowa cena zakupu; `sensor.energi_data_spotpris`: cena sprzedaży. Ceny z HA są danymi końcowymi; **bez dodawania lub odejmowania opłat**.
- Obie encje udostępniają `attributes.raw_today`, `raw_tomorrow`, `tomorrow_valid` oraz rekordy `hour` i `price`. Odczytaj tylko rzeczywiście opublikowane dane, wspólne ważne przedziały kupna i sprzedaży.
- Parsuj godzinę do UTC, zachowaj strefę Europe/Copenhagen i zmiany DST (23/25 godzin), wykryj puste, duplikowane, przeterminowane i rozbieżne sloty. **Nie dopisuj cen nieopublikowanych**.
- Surowe ceny godzinowe mogą być zaokrąglone do 3 miejsc, a `current_price` dokładniejsze. Gdy np. `raw.price=0.400` i `current_price=0.3996` dają sprzeczne decyzje co do eksportu PV, oznacz `PRICE_THRESHOLD_AMBIGUOUS`, bez polecenia ON. Nie modyfikuj progu cenowego „histerezą”.

## Prognozy
- Forecast.Solar w HA: użytkownik potwierdził widoczność `forecast_solar.get_forecast`. Przy M2 sprawdź rzeczywisty `config_entry`, odpowiedź, `wh_period`/jednostki, daty, UTC i pokrycie. Nie rekonstruuj fikcyjnych przedziałów z samej sumy dziennej.
- Forecast PV i historia: przechowuj wersje prognoz oraz ich czas **sprzed** prognozowanego okresu. Pełna bateria i Solar Sell OFF mogą oznaczać curtailment; nie ucz błędu Forecast.Solar na takich przedziałach bez potwierdzenia, że produkcja była nieograniczona.
- Prognoza zapotrzebowania: Recorder z `home_energy_consumption`, profil na 15 min z porą dnia/tygodnia/sezonem i kontrolą źródeł historycznych. Używaj tylko danych znanych w chwili decyzji.
- Sprawności PV→bateria, grid→bateria, bateria→AC, PV→AC są osobne. Parametry `0.9487` i `0.97` to historyczne wartości konfiguracyjne, **nie zmierzone wyniki**. Kalibrować z obserwowalnych okresów, raportując niepewność.

## Kontrakt potwierdzony surowym eksportem HA — 20.10.2026

Źródło: eksport z działającego HA 2026.10.2, wykonany 20.10.2026 14:15 CEST, dla wersji Energy Co-Pilot 0.1.1; pełnego pliku zawierającego prywatną historię gospodarstwa domowego **nie umieszczać w repozytorium**. Rozdzielać format i obserwacje od walidacji fizycznej.

- **Pomiary bieżące:** 11 wskazanych encji istnieje, wszystkie mają oczekiwane jednostki (`W`, `V`, `A`, `%`, `DKK/kWh`). Przykładowe wartości: `pv_sum=185 W=51+134 W`; `home=3802 W=185+11+3606 W`; `battery=3606 W` i `V×I≈3606.57 W`. Znaczniki `last_updated` poszczególnych źródeł różnią się (PV 12:14:35.354 UTC, grid 12:14:50.498 UTC; **15,144 s**). Eksport z frontendowego `hass.states` ma `last_reported=null`; **nie dowodzi to**, że wewnętrzny obiekt Python HA nie ma `last_reported`.
- **Ceny:** obie encje zawierają `raw_today` i `raw_tomorrow` — po 24 rekordy `{hour: ISO 8601 z offsetem, price: liczba DKK/kWh}`; `tomorrow_valid=true`; brak luk/duplikatów, zgodność godzin zakupu i sprzedaży. `current_price` ma większą precyzję niż `raw`. Tego dnia (bez zmiany DST) 48 opublikowanych godzin, od 20.10 00:00 CEST do 22.10 00:00 CEST.
- **Forecast.Solar:** rzeczywista odpowiedź usługi HA `forecast_solar.get_forecast` zawiera `watts` i `wh_period`, każda po 24 znaczniki czasu ze strefą. **Kluczowe: `wh_period[t_i]` to Wh dla przedziału `(t_(i-1), t_i]`, czyli znacznika KOŃCA przedziału**, a nie początku. Obliczenie całki trapezowej z dwóch sąsiednich `watts` i rzeczywistego czasu między nimi potwierdza tę semantykę dla **23/23 przedziałów**, błąd absolutny ≤0,5 Wh (zaokrąglenie). Np. `wh_period[10:00]=614 Wh` odpowiada 09:00–10:00 (434→793 W). `wh_period[18:06:30]=9 Wh` odpowiada ostatniemu przedziałowi 18:00–18:06:30, a **nie** nieograniczonemu okresowi po zachodzie. Na granicach wschodu/zachodu i nocy czasy nie muszą być pełnymi godzinami. Zmiana przypisania energii ma krytyczne znaczenie dla planowania.
- **Recorder:** frontendowe WebSocket `history/history_during_period` oddaje obiekty skrócone `s` (stan), `a` (atrybuty), `lu` (Unix epoch seconds) i niekiedy `lc`; to **format eksportu WebSocket**, nie tożsamy z Pythonowymi obiektami State/LazyState używanymi przez integrację. W czterech sześciogodzinnych porcjach 24 h wystąpiło: PV 3741, sieć 4412, bateria 4322, dom 12446 rekordów (wraz z wartościami na granicach okien). PV=0 pozostaje niezmienne wiele godzin nocą — brak zmiany stanu nie jest dowodem utraty aktualności sprzętu.
- **Potwierdzone anomalie:** trzy krótkie, zbieżne epizody `pv:unknown` i `grid/battery:unavailable` (20.10 około 12:48, 13:30, 13:53 CEST); `home` pozostaje liczbowy również podczas epizodów. Dodatkowo `home` ma **26 ujemnych rekordów w 8 różnych kwadransach**, minimum -1768 W. Wszystkie 12446 rekordów `home` zgadzają się z sumą ostatnich zanotowanych `pv+grid+battery` w granicach 1 W, lecz algebraiczna zgodność szablonu **nie dowodzi poprawnego fizycznego zużycia domu**. Surowe ujemne wartości nie są normalnym poborem: zgodnie z nadrzędną decyzją używamy do obliczeń ich normalizacji `max(0, home)` wyłącznie przy ważnych źródłach i audytujemy korekty. Ocena błędu profilu wymaga weryfikacji synchronizacji i semantyki DC/AC, ale nie jest warunkiem zastosowania zatwierdzonej polityki. Eksport WebSocket nie zawiera pełnych informacji o przebiegach procesów Recorder i ustawieniach filtrów.

**Konsekwencje dla Codexa:** zachować poprawione indeksowanie `wh_period` według KOŃCA przedziału, energię ostatniej granicy i regresje UTC/DST. Odróżniać niezmienny stan nocnego PV od braku źródła. Normalizować ujemny `home` według REQUIREMENTS dopiero po walidacji kontekstu; nie tworzyć zer z braków ani nie przedstawiać równania szablonu jako dowodu fizycznego pomiaru. Implementacja kodu tylko przez Codexa.

## Encje wykonawcze
| Akcja | Encja |
|---|---|
| Limit prądu ładowania 0–50 A | `number.sun12k_maximum_battery_charge_current` |
| Limit rozładowania 0–100 A | `number.sun12k_maximum_battery_discharge_current` |
| Limit ładowania z sieci 0–50 A | `number.sun12k_maximum_battery_grid_charge_current` |
| Global Grid Charge | `switch.sun12k_grid_charge` |
| Eksport nadwyżki PV | `switch.sun12k_solar_sell` |
| TOU ON/OFF | `switch.sun12k_time_of_use` |
| TOU 1…6: start, power, capacity | `number.sun12k_time_point_N_start`, `number.sun12k_time_point_N_power`, `number.sun12k_time_point_N_capacity` |
| TOU 1…6: Grid Charge | `switch.sun12k_time_point_N_charge_enable` |

Użytkownik potwierdził poprawne działanie nastaw 0 A i pozostałych regulatorów. W oprogramowaniu nadal walidować zakres/odczyt; HA potrafi zgłaszać absurdalne min/max ±16 777 220 A. Nie stosować ich. Limity są maksimum, **nie gwarantowaną mocą**. Nie używać nieaktywnych pozostałości `battery_controller.*`. Nie zmieniać YAML/ESPHome/Modbus. Testy: [VALIDATION.md](VALIDATION.md).
