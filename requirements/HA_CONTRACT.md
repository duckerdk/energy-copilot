# Kontrakt Home Assistant — źródła i sterowanie

Źródła decyzji i limitów: [REQUIREMENTS.md](REQUIREMENTS.md). Wykonanie: [EXECUTION.md](EXECUTION.md). Poniższy kontrakt opisuje działające M1/M2 i przyszłe encje sterujące; nie upoważnia do wysyłania komend.

## Pomiary

| Rola | Encja | Zasada |
| --- | --- | --- |
| Moc PV | `sensor.pv_sum` | **Jedyne** źródło produkcji przyjętej na wejściu falownika, w W |
| Sieć | `sensor.sun12k_total_grid_power` | Dodatnie = import, ujemne = eksport |
| Bateria | `sensor.sun12k_battery_output_power` | Dodatnie = rozładowanie, ujemne = ładowanie |
| Dom | `sensor.home_energy_consumption` | Szablon `PV + grid + battery`, nie niezależny licznik AC |
| SOC | `sensor.sun12k_battery_capacity` | %; dolna granica polityki 20% |
| Napięcie i prąd baterii | `sensor.sun12k_battery_voltage`, `sensor.sun12k_battery_output_current` | V i A; weryfikować stronę DC oraz P≈V×I |
| Sieć — odczyt dodatkowy | `sensor.sun12k_out_of_grid_total_power_2` | Nie sumować z głównym odczytem sieci |
| Liczniki dzienne | `sensor.sun12k_daily_production`, `sensor.sun12k_today_charge_of_the_battery`, `sensor.sun12k_today_discharge_of_the_battery` | kWh, nie dodatkowe źródła mocy |

Normalizacja: `grid_import=max(0,P_grid)`, `grid_export=max(0,-P_grid)`, `battery_discharge=max(0,P_bat)`, `battery_charge=max(0,-P_bat)`. Jednostki wejściowe mocy to W. Nie liczyć PV→bateria jako drugiej produkcji. `sensor.pv_sum` nie informuje, jaka produkcja PV byłaby możliwa bez ograniczenia (curtailment). Integracja **nie używa PV1/PV2**.

## Walidacja bieżących odczytów

- HA może zachować niezmieniony stan encji przez wiele godzin, niezależnie od tego, czy jest to `0 W`, dodatnia moc PV, SOC, napięcie, prąd, licznik dzienny czy wartość pochodna. **Wiek `last_changed`, `last_updated` lub `last_reported` nie stanowi samodzielnego dowodu awarii** i nie może sam wywołać `Degraded` albo odrzucenia takiej wartości.
- Dla wszystkich wymaganych i opcjonalnych pomiarów sprawdzać **aktualny stan HA**: istnienie encji, jawne `unknown/unavailable`, poprawność liczby i jednostki, znaku oraz zakresu. Nie tworzyć odczytów ani nie przesuwać ich znaczników czasu. Znacznik w przyszłości ponad tolerancję 10 s nadal jest niepoprawny.
- Brak niezależnego sygnału heartbeat sprzętu nie pozwala udowodnić fizycznej świeżości — pokazywać prawdziwy czas i `device_freshness_verified=false` w diagnostyce. Jeśli urządzenie przestanie publikować i HA pozostawi ostatnią liczbę, sam ten stan nie dowodzi aktywności urządzenia; do wykrywania takiej awarii potrzebny jest osobny sygnał dostępności/zdrowia urządzenia.
- Szablon domu `PV + grid + battery` weryfikować przy dostępnych trzech źródłach. Różnica sumy jest ostrzeżeniem o niespójności wartości as-of, **nie dowodem awarii wynikającym z różnych czasów raportowania**. Po jawnej awarii źródła i jego odzyskaniu odrzucać stary raport domu, jeżeli poprzedza moment odzyskania źródła; nie odtwarzać braków przez `float(0)`.
- Opcjonalna para napięcie×prąd baterii może aktualizować się asynchronicznie względem mocy. Jej niezgodność z mocą to ostrzeżenie diagnostyczne, nie dowód nieprawidłowości głównego pomiaru baterii. Wiarygodność fizycznego bilansu AC/DC pozostaje do potwierdzenia przed sterowaniem.
- Poprawną liczbową ujemną moc domu normalizować wewnętrznie do `max(0, home)` również przy całkowaniu historii Recorder. Nie zmieniać surowej encji i nie zastępować braków danych zerami.

`last_reported` w Python State oznacza czas ostatniego raportu HA, a `last_updated` czas aktualizacji stanu. Żaden z tych znaczników nie jest gwarantowanym heartbeat sprzętu; historyczny `last_updated` Recorder nie podlega limitowi wieku bieżących raportów.

## Ceny

- Zakup: `sensor.energi_data_service`, sprzedaż: `sensor.energi_data_spotpris`; jednostki **DKK/kWh**. Wartości HA są końcowe, bez ponownego doliczania taryf czy opłat.
- `attributes.raw_today` i `raw_tomorrow` zawierają rekordy `{hour: ISO-8601 z offsetem, price: liczba}`; `tomorrow_valid` kontroluje publikację cen na jutro. Łączyć tylko wspólne prawidłowe opublikowane godziny kupna i sprzedaży.
- Parsować do UTC z uwzględnieniem Europe/Copenhagen i DST 23/25 h. Nie wytwarzać nieopublikowanych cen, nie scalać błędnych ani zduplikowanych godzin.
- Surowe ceny mogą być zaokrąglone do 3 miejsc, a `current_price` dokładniejsze. Gdy np. `0.400` kontra `0.3996` zmienia decyzję progową, zgłosić `PRICE_THRESHOLD_AMBIGUOUS` i nie wydawać polecenia ON. Nie zmieniać progu poprzez sztuczną histerezę.

## Forecast.Solar i Recorder

- Używać natywnej usługi HA `forecast_solar.get_forecast` i wybranego config entry. Odpowiedź ma `watts` oraz `wh_period`, ze znacznikami czasu i strefą. **`wh_period[t_i]` opisuje energię Wh przedziału `(t_(i-1), t_i]` — czas oznacza KONIEC, nie początek.** Ostatni krótki przedział zachodu zachowuje rzeczywistą energię; pierwsza energia bez wcześniejszej granicy nie może być przypisana do nieznanego przedziału.
- Brak publikacji nocnych godzin **nie degraduje** `Input quality`; `forecast_state` nadal pokazuje niepełność horyzontu. Brakujące okresy dnia/zmierzchu pozostają jawnie nierozstrzygnięte. Nie uzupełniać brakujących Wh zerami ani nie dzielić całego Wh rozpoczętego okresu według arbitralnego ułamka czasu.
- Magazyn zachowuje wersję prognozy i czas jej dostępności do backtestu bez informacji z przyszłości. Pełna bateria i wyłączony Solar Sell mogą oznaczać ograniczenie produkcji — nie traktować tego automatycznie jako błędu prognozy.
- Historia Recorder rekonstruuje zmiany stanów i kwadranse z prawdziwymi granicami zapisów. Jawne `unknown/unavailable`, nieznane przerwy i brakujące źródła wykluczają fragment danych. Niezmienna wartość nocnego PV nie jest luką sama w sobie. Nie utożsamiać formatu eksportu WebSocket (`s`, `a`, `lu`, `lc`) z backendowymi obiektami Python State.
- Model obciążenia i sprawności dla M3/M5 wymaga kalibracji. Historyczne `0.9487` i `0.97` to parametry przyjęte, nie zmierzone sprawności.

Kontrakt czasów i końcowego indeksowania `wh_period` zweryfikowano na rzeczywistych danych HA 2026.10.2 z 20.10.2026. Szczegółowych próbek prywatnej historii nie przechowywać w repozytorium.

## Encje wykonawcze (dopiero M6)

| Funkcja | Encja |
| --- | --- |
| Prąd ładowania 0–50 A | `number.sun12k_maximum_battery_charge_current` |
| Prąd rozładowania 0–100 A | `number.sun12k_maximum_battery_discharge_current` |
| Prąd ładowania z sieci 0–50 A | `number.sun12k_maximum_battery_grid_charge_current` |
| Global Grid Charge | `switch.sun12k_grid_charge` |
| Solar Sell (eksport nadwyżki PV) | `switch.sun12k_solar_sell` |
| TOU globalne | `switch.sun12k_time_of_use` |
| TOU 1…6: początek, moc, SOC | `number.sun12k_time_point_N_start`, `number.sun12k_time_point_N_power`, `number.sun12k_time_point_N_capacity` |
| TOU 1…6: zezwolenie na Grid Charge | `switch.sun12k_time_point_N_charge_enable` |

Użytkownik potwierdził działanie nastaw 0 A. Przy zapisie walidować zakresy polityki i odczyt po zmianie; zgłaszane przez HA skrajne `min/max` nie muszą odpowiadać granicom sprzętu. Prąd zadany jest limitem, nie gwarancją przepływu. Nie używać nieaktywnych `battery_controller.*` ani nie modyfikować YAML/ESPHome/Modbus. Regresje: [VALIDATION.md](VALIDATION.md).
