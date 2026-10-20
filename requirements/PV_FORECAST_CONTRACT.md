# Kontrakt prognozy PV — Forecast.Solar w Home Assistant

**Status:** publiczny kontrakt natywnej akcji HA zweryfikowany w oficjalnej dokumentacji; **dostępność tej akcji w konkretnej instancji użytkownika jeszcze nie została sprawdzona**. To zadanie automatycznej diagnostyki Codexa, nie powód do ręcznego przepisywania atrybutów ani pytania o ceny.

**Źródła:** [oficjalna akcja Forecast.Solar: Get forecast](https://www.home-assistant.io/actions/forecast_solar.get_forecast/); [oficjalna integracja Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/).

## 1. Źródło pełnego profilu

**Preferowana droga:** natywna akcja Home Assistant `forecast_solar.get_forecast` zwracająca dane w odpowiedzi (response data). Co-Pilot pobiera ją przez **wewnętrzne API usług HA**, bez połączenia do zewnętrznego Forecast.Solar, bez osobnego klienta HTTP i bez modyfikowania integracji Forecast.Solar.

| Element | Znaczenie |
| --- | --- |
| Akcja HA | `forecast_solar.get_forecast` |
| Parametr wymagany | `config_entry`: wybrany wpis konfiguracji Forecast.Solar, **nie** identyfikator sensora |
| `resolution: raw` | Natywna rozdzielczość: 15 minut (jeżeli dostawca udostępnia) albo 1 godzina (np. plan bezpłatny) |
| `resolution: hourly` | Agregacja do pełnych godzin |
| `start` / `end` | Opcjonalny zakres żądanych danych, koniec wyłączny |
| `watts` | Mapa `ISO timestamp z offsetem → prognozowana moc W`; przy `hourly`: średnia moc godzinowa |
| `wh_period` | Mapa `ISO timestamp z offsetem → prognozowana energia Wh w okresie`; przy `hourly`: energia całej godziny |

Oficjalny format odpowiedzi jest następujący (wyłącznie **przykład schematu**, nie dane instalacji):

```yaml
watts:
  "2026-09-30T08:00:00+02:00": 412
  "2026-09-30T09:00:00+02:00": 1350
wh_period:
  "2026-09-30T08:00:00+02:00": 395
  "2026-09-30T09:00:00+02:00": 1312
```

**Kluczowa zaleta:** HA zwraca **swoją już pobraną prognozę**, a nie odpytuje serwisu Forecast.Solar przy każdym wywołaniu akcji. Nie generujemy sztucznie większej rozdzielczości prognozy przez częstsze odpytywanie. Prognozy co do zasady nie są pomiarami i nie muszą zgadzać się w 100% z uzyskiem.

## 2. Wybór wpisu i kontrola dostępności

Codex musi:
1. Rozpoznać, czy akcja `forecast_solar.get_forecast` jest w danej instalacji **rzeczywiście dostępna**. Oficjalna dokumentacja nie potwierdza wersji posiadanej przez użytkownika.
2. Przez HA wykryć dostępne wpisy `forecast_solar`; gdy jest jeden, użyć go; gdy więcej niż jeden, pozwolić użytkownikowi wybrać wpis w config/options flow. **Nie hardkodować** `config_entry`, ID sensora, lokalizacji, tokenu ani instalacji.
3. Pobierać wynik jako **response data**, nie stan nowej encji i nie zakładać, że profil jest w atrybutach `sensor.energy_production_today`.
4. Wykazać w diagnostyce: `forecast_source = forecast_solar.get_forecast`, wybrany wpis, rozdzielczość, liczbę okresów, pierwszy/ostatni okres, czas uzyskania, ostatnio zarejestrowaną wersję prognozy i ewentualny błąd.
5. Jeżeli akcja **nie istnieje**, zastosować `pv_hourly_forecast = unavailable` i jawny `missing_capabilities`. **Nie** tworzyć profilu godzinowego z samej sumy dziennej ani wymyślać krzywej produkcji. Możliwy osobny wariant mapowania rzeczywiście potwierdzonych atrybutów innych encji, ale nie jest warunkiem specyfikacji bazowej.
6. Przy czasowej awarii usługi można prezentować archiwalną prognozę z oznaczeniem wieku, ale nie wolno podawać jej jako świeżej prognozy do automatycznych decyzji. Starzenie i ważność mają być jawne i testowane.

**Brak twardo zakodowanego interwału publikacji:** według dokumentacji integracja bezpłatna zwykle aktualizuje dane co godzinę, z kluczem API około co 30 minut; dostępność nowych danych w HA trzeba wykrywać na podstawie wersji i momentu uzyskania, a nie deklarować każdą decyzję 15-minutową jako nową prognozę.

## 3. Jednostki, okresy, UTC i energia

- Pierwotną, zachowującą bilans podstawą jest **`wh_period`**, czyli energia [Wh] danego okresu. `watts` to prognozowana moc [W] i przy `raw` nie musi równać się średniej energii w danym odcinku — nie zastępować `wh_period` przez `watts × czas` bez potwierdzenia interpretacji.
- Klucz `timestamp` oznacza **początek okresu** i ma offset strefowy. Parsować do UTC i dopiero łączyć z cenami. Zachować dobowy przełom i DST (23/25 godzin).
- Okres w `raw` może mieć 15 albo 60 minut: rozpoznawać po kolejnych początkach okresów / trybie źródła; ostatni interwał musi mieć znaną długość zgodną z udokumentowaną rozdzielczością. Nie zakładać arbitralnie 1h dla każdej instalacji.
- Na okres `[start_utc,end_utc)` przechowywać `energy_wh`, `average_power_w = energy_wh / duration_h`, `source`, `obtained_at_utc`, `issued_at_utc` gdy dostępny; jeśli dostawca nie ujawnia realnego `issued_at`, oznaczyć `not_provided`, nie podstawiać `obtained_at` jako rzekomej daty publikacji.
- Dla 15-minutowego slotu z prawdziwą prognozą 15-minutową użyć jego `wh_period` bez ponownej interpolacji.
- **Przy prognozie wyłącznie godzinowej** optymalizator może podzielić `Wh_hour / 4` na cztery kwadranse tylko jako jawny **model rozłożenia energii w godzinie**, nie jako cztery niezależnie opublikowane wartości. Suma kwadransów ma dokładnie zachować godzinowe Wh. Ten przybliżony rozkład nie może służyć do oceny „dokładności 15-minutowej” ani obietnic idealnego kształtu generacji.
- Dla kwadransa bieżącego rozpoczętego w trakcie godziny zastosować **pozostałą część okresu**; nie przypisać wcześniejszej produkcji jako przyszłej energii.
- Zasięg profilu PV jest **niezależny** od czasu publikacji ceny DK1. Plan z wyliczeniem kosztu kończy się na faktycznie opublikowanym wspólnym horyzoncie zakupu/sprzedaży [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md).

## 4. Powiązanie z instalacją i bilansem

Potwierdzone encje odczytowe:
- `sensor.energy_production_today` — prognozowana produkcja dziś, **15,865 kWh** w migawce z 19.10.2026.
- `sensor.energy_production_today_remaining` — prognoza pozostała dziś, **4,431 kWh**.
- `sensor.energy_production_tomorrow` — prognoza jutro, **7,536 kWh**.
- `sensor.pv_sum` — bieżący agregat MPPT: **3034 W** = `sensor.sun12k_pv1_power` + `sensor.sun12k_pv2_power` w tej samej migawce.
- `sensor.pv_forecast_next_24h` = **51,72 bez jednostki**: **nie** używać jako energii, mocy ani zastępczego źródła prognozy, dopóki semantyka nie jest udokumentowana.
- Encje `battery_controller.*` to osierocone pozostałości, ignorowane jako wejścia i sterowania.

Dla celu optymalizatora forecast.solar jest prognozą **potencjalnej produkcji**, a `sensor.pv_sum` obserwacją rzeczywistej mocy PV (punkt DC/AC wymaga jawnego zmapowania). Nie odejmować od `wh_period` automatycznie ładowania baterii, jeśli prognoza już opisuje całość uzysku. Model DC/AC i parametry Forecast.Solar (moc szczytowa, płaszczyzny, tłumienie, ograniczenie przez falownik) potrzebują kalibracji na danych **bez curtailment**.

## 5. Historia prognoz i ocena jakości

- Utrwalać **migawkę odpowiedzi** `wh_period` pobranej **przed** prognozowanym okresem; `obtained_at` i wersja danych muszą rozróżniać zmiany. Nie nadpisywać starych prognoz.
- Tylko taka migawka umożliwia prawidłowe testy `walk-forward` bez później poznanej pogody. W ramach jednego slotu zachować jakość prognozy i horyzont wyprzedzenia.
- Potencjalnego PV **nie da się dokładnie odtworzyć** z produkcji ograniczonej przez sterowanie. Przedziały `curtailed_confirmed` lub `curtailment_unknown` wyłączyć z kalibracji dokładności (nie twierdzić, że „prognoza się nie zgadza”, jeśli PV ograniczono).
- 100% zgodności z uzyskiem nie jest wymagane; ma znaczenie **wpływ rozkładu błędów prognozy na decyzje ekonomiczne**. Przed kalibracją używać jawnie oznaczonej prognozy punktowej i testów wrażliwości, bez wymyślonego „90% zaufania”.
- Aktualne `sensor.energy_production_today` i dawne `sensor.sun12k_daily_production` pokazujące inne wartości **nie** są dowodem awarii prognozy ani błędnego sterowania.

## 6. Testy kontraktu — do zaimplementowania przez Codexa (nie wykonano)

- `PVF-01`: akcja `forecast_solar.get_forecast` dostępna, jeden config entry → poprawny wybór i mapowanie.
- `PVF-02`: dwa wpisy Forecast.Solar → wymagany jawny wybór, brak nieprzewidzianego podwójnego zsumowania.
- `PVF-03`: akcja niedostępna → `missing_capabilities`, brak wymyślonej prognozy godzinowej.
- `PVF-04`: `watts` i `wh_period` pokazują różne wartości zgodnie ze swoją definicją → podstawą bilansu jest `wh_period`, bez podwójnego mnożenia przez 1h.
- `PVF-05`: 1000 Wh w godzinie → cztery kwadranse po 250 Wh **z oznaczeniem aproksymacji**; suma dokładnie 1000 Wh.
- `PVF-06`: 250 Wh w autentycznym okresie 15 min → 250 Wh przypisane temu slotowi, nie podzielone ponownie.
- `PVF-07`: brakuje okresu pośród mapy → luka jawna i ograniczona wykonalność; bez interpolowania dobowej sumy.
- `PVF-08`: powtórzona lokalnie godzina 02:00 w DST jesienią, różne offsety → różne interwały UTC.
- `PVF-09`: `issued_at` nie jest dostępny w odpowiedzi → pole `not_provided`, bez sfabrykowania czasu publikacji.
- `PVF-10`: na kolejny cykl HA zwraca tę samą prognozę → nie tworzyć fałszywej nowej wersji ani nie twierdzić, że wzrosła precyzja forecastu.
- `PVF-11`: awaria akcji → dane przestarzałe jawnie oznaczone; brak automatycznej decyzji opartej na nieznanym profilu PV.
- `PVF-12`: pomiar PV został sztucznie ograniczony przez pełną baterię i eksport OFF → nie poprawiać modelu według różnicy „prognoza − produkcja”.
- `PVF-13`: profil PV sięga dalej niż znane ceny → plan wyceniany tylko na horyzoncie opublikowanych cen.
- `PVF-14`: bieżący kwadrans 10:30–10:45, prognoza godzinna 10:00–11:00 → nie traktować energii minionych 30 min jako przyszłej.
- `PVF-15`: brak jednostki na `sensor.pv_forecast_next_24h` → nie używać jako kWh.
- `PVF-16`: prognoza godzinowa suma dziś różna od sensora `energy_production_today` z powodu chwili pobrania / innej agregacji → zgłosić diagnostykę rozbieżności, nie odrzucać automatycznie całej prognozy.
- `PVF-17`: user confirmed precise inverter current limit, prognoza PV za niska → różnica to błąd prognozy wejściowej, nie sztuczny błąd sterowania Deye.
- `PVF-18`: brak `wh_period` albo uszkodzone timestampy → status danych `invalid`, nie wyprowadzać fałszywego godzinowego profilu z `watts`.

**Warunek odbioru:** Codex potrafi pobrać profil jako natywną odpowiedź HA, udokumentować jakość i źródło oraz oznaczyć brak akcji bez zgadywania. Do startu implementacji modułu prognoz nie jest potrzebne ręczne kopiowanie atrybutów dwóch encji cen ani sensorów dziennych Forecast.Solar.
