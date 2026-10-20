# Prognoza zużycia domu — wyłącznie istniejące dane Home Assistant

**Status:** kontrakt algorytmu wejściowego do planera. Sposób budowy prognozy rozstrzygnięty; **jakość danych historycznych w Recorder konkretnej instalacji jest do sprawdzenia przez Codexa**. Bez dodatkowego serwera, abonamentu prognozowego, odczytu Modbus ani osieroconych encji Battery Controller.

**Źródła:** [Home Assistant — History](https://www.home-assistant.io/integrations/history), [Recorder](https://www.home-assistant.io/integrations/recorder). Dokumenty projektu: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [FORECAST_POLICY.md](FORECAST_POLICY.md), [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md).

## 1. Sygnał i definicja popytu

- Podstawowa encja do prognozy: `sensor.home_energy_consumption`, jednostka **W**; w migawce 19.10.2026: **583 W**. **Potwierdzona definicja użytkownika:** `pv_sum + sun12k_total_grid_power + sun12k_battery_output_power` (encja HA template, nie niezależny licznik). Nie tworzyć dodatkowego sensora tylko dlatego, że jest pochodna.
- Drugi pomiar: `sensor.sun12k_load_totalpower` = **532 W** w tej samej migawce. **Nie zamieniać** automatycznie, ponieważ może oznaczać inny punkt fizyczny (np. obciążenie wyjścia falownika, a nie całego domu).
- Co-Pilot **przyjmuje istniejącą encję domu bez dalszych pytań o niezależny punkt pomiarowy**. Jej 3 składowe mają fizyczną semantykę odpowiednio PV, sieć i bateria; obecny wzór jest obowiązującym źródłem profilu. Ponieważ HA stosuje `float(0)`, przy braku którejkolwiek składowej oznaczyć wynik `invalid_input`, aby brak danych nie udawał mniejszego popytu.
- `sensor.battery_controller_consumption_forecast` i wszystkie `battery_controller.*` są nieaktywnymi pozostałościami i **nie mogą być wejściem prognozy**.

## 2. Pozyskiwanie historii

Codex ma skorzystać z **natywnego Recorder/History HA**, w zakresie dozwolonym przez aktualne API HA, z filtrem **wyłącznie wybranego entity_id i potrzebnego okresu**, bez własnego serwera REST/SQL i bez masowego pobierania stanów wszystkich urządzeń.

- Historia szczegółowa HA domyślnie obejmuje ok. **10 dni**; dalsze dane mogą istnieć tylko jako **statystyki długoterminowe godzinowe**. Nie zakładać, że jest 30 dni migawek 15-minutowych.
- Wczytywanie Recorder jest operacją bazodanową: zgodnie z zaleceniami HA stosować właściwy wykonawca / API Recorder, **nie blokować pętli asyncio** integracji.
- Przy nowych odczytach prowadzić własny **lekki lokalny agregat slotów 15-minutowych** do nauki profilu, ograniczony czasowo i rozmiarem; retencja i miejsce zapisu mają być jawne i konfigurowalne.
- Każda próbka: `start_utc`, `end_utc`, `average_load_kw`, `energy_kwh`, `coverage_pct`, `quality`, `source_entity_id`.
- Historia `unknown`, `unavailable`, ujemna, niefinita lub o nieznanej jednostce jest **brakiem danych**, nie `0 W`. Wartości skrajne traktować ostrożnie: nie obcinać realnego skoku poboru bez dowodu awarii sensora.

## 3. Normalizacja i integracja energii

`sensor.home_energy_consumption` publikuje chwilową moc. Jeżeli serię traktujemy jako próbki mocy, wyznaczamy energię slotu przez **całkowanie po czasie** z faktycznych timestampów, np. przy założeniu `sample-and-hold` pomiędzy wiarygodnymi próbkami:

`E_slot_kWh = Σ(P_i_kW × overlap_duration_i_h)`.

`P_slot_mean_kW = E_slot_kWh / covered_duration_h`, ale slot może być użyty w uczeniu tylko przy **jawnie określonym progu pokrycia i świeżości**.

Przykład syntetyczny: 600 W przez pierwsze 10 minut i 1200 W przez następne 5 minut → `E = 0,600×(10/60) + 1,200×(5/60) = 0,200 kWh`, średnia moc pełnego kwadransa `0,8 kW`.

Nie wyliczać profilu z samego stanu końcowego lub średniej `state_class` bez sprawdzenia, jak zdefiniowana jest statystyka. Jeżeli historia jest **godzinowa**, model godzinowy może służyć jako przybliżenie kwadransowe, ale cztery kwadranse nie są niezależnymi zaobserwowanymi próbkami.

## 4. Deterministyczny model prognozy początkowej

**M1 — od razu przy świeżych pomiarach:** prognoza bieżącego popytu oparta na dostępnych danych ostatnich godzin, z etykietą `provisional`; bez uznawania jej za pełną prognozę 24–35 h.

**M2 — po zebraniu historii:** profil z **odpornej mediany** historycznych, kompletnych slotów o podobnej lokalnej godzinie i rodzaju dnia. Kolejność użycia danych:
1. Te same godziny i kwadranse w porównywalnych dniach tygodnia z dostępną historią.
2. Gdy próbek jest za mało — łączny profil `dzień roboczy / weekend`, jeśli liczba obserwacji jest wystarczająca.
3. Przy ograniczonej rozdzielczości — profil godzinowy z prawidłowym rozdziałem energii (jawne `hourly_assumption`).
4. Gdy historii nie ma — konserwatywny punktowy `recent_load_baseline` wyłącznie do **diagnostyki / dry-run**, nigdy udawana wytrenowana prognoza.

**Nie wpisywać w kod** profilu odbioru np. 2,1 kW ani stałego współczynnika zużycia domu. Konfigurowalny horyzont uczenia i wymagane minimum próbek ustalić w kodzie jako bezpieczne, opisane wartości domyślne (z możliwością dostosowania); nie domagać się ich od użytkownika bez konkretnej przesłanki.

**Korekta krótkoterminowa:** przy wiarygodnej najnowszej historii można włączyć obserwowany trend względem typowego profilu, ale tylko w sposób deterministyczny, ograniczony i testowalny. Nie ekstrapolować pojedynczego skoku mocy na całą noc bez danych.

## 5. Warunki jakości i horyzont

- Każda prognoza na `[t,t+Δt)` musi mieć `forecast_kw`, `forecast_kwh`, `obtained_at_utc`, `model_version`, `training_cutoff_utc`, `coverage`, `confidence_status` i `method`; **nie** wymyślać procentowej „pewności” bez kalibracji.
- Uczenie i wszystkie cechy prognozy na decyzję `t0` mogą korzystać tylko z danych dostępnych **do t0**, nigdy ze zużycia z przyszłości.
- Godziny lokalne `Europe/Copenhagen` służą do sezonowości/rytmu domowego; same okresy porównywać i scalać w UTC, prawidłowo obsłużyć 23-/25-godzinne doby DST.
- Czujnik chwilowej mocy i odbiór w godzinach taniego ładowania z sieci **nie powinny** mieszać energii baterii z energią domu. W przeciwnym razie optymalizator błędnie „uczy się” własnych przyszłych działań.
- Prognozy dzienne PV oraz opublikowane ceny mają **oddzielną semantykę**: ceny są faktami, PV i zużycie estymatami. Zmienny horyzont cen wyznacza ekonomiczny koniec planu; profil domu musi obejmować co najmniej ten odcinek albo mieć jawne luki.
- Brak wiarygodnej prognozy domu **nie jest zgodą na 0 kW**. Plan może nadal istnieć jako `partial / dry_run` z oznaczonym ograniczeniem albo bezpiecznym scenariuszem testowym, ale nie może raportować wiarygodnych oszczędności.

## 6. Ocena i stopniowa kalibracja

- Prognozę oceniaj na **mocach/energiach zrealizowanych**, zgodnych z punktem pomiarowym; osobno średni błąd, medianowy błąd bezwzględny oraz wpływ błędu na rachunek netto.
- Na start nie wymagaj idealnej trafności; historia ma umożliwić ulepszanie profilu po obserwacji.
- Dla każdej decyzji zapisuj wersję prognozy i czas przygotowania; nie zastępuj jej późniejszą, „lepszą” migawką, gdy liczysz wynik historyczny.
- Testy walk-forward dla load muszą mieć te same daty i zasady braku wiedzy o przyszłości jak dla PV.

## 7. Testy do przygotowania przez Codexa

- `LOAD-01`: 600 W/10 min + 1200 W/5 min → 0,200 kWh, średnia 0,8 kW.
- `LOAD-02`: 1000 W przez 15 min → 0,250 kWh i 1,0 kW.
- `LOAD-03`: `unknown` przez połowę kwadransa → coverage 50%, nie 0 W.
- `LOAD-04`: brak Recorder → `insufficient_history` i sensowny komunikat, bez danych z `battery_controller.*`.
- `LOAD-05`: `sensor.home_energy_consumption = 583 W` z template `3034−2470+19`, zaś `sensor.sun12k_load_totalpower = 532 W` → używać **ustalonego** źródła domu, nie podmieniać go innym pomiarem.
- `LOAD-06`: całkowicie pusta historia → tylko `recent_load_baseline` w trybie `provisional` / dry-run, nie udawana prognoza po dobie.
- `LOAD-07`: mało danych na konkretny dzień tygodnia → przejście do agregatu roboczy/weekend lub godzinowego z etykietą jakości.
- `LOAD-08`: wartości ujemne/niefinita bez zweryfikowanej semantyki → odrzucenie z przyczyną, nie absolutna wartość.
- `LOAD-09`: okres dłuższy od retencji szczegółowego Recorder → korzystanie z uczciwie opisanych statystyk godzinowych albo brak danych, bez udawanych kwadransów.
- `LOAD-10`: zmiana DST jesienią, dwie lokalne 02:00 → osobne sloty UTC.
- `LOAD-11`: poranny wzrost obciążenia tylko dziś → nie propagować całodziennego profilu z jednej obserwacji.
- `LOAD-12`: historia zawiera ładowanie magazynu jako odrębny przepływ → nie dodawać jego energii do prognozy domu.
- `LOAD-13`: po replanowaniu stare prognozy zachowane w rejestrze, nowa ma nowy `training_cutoff`.
- `LOAD-14`: sztuczna historyczna fikstura 30 dni, prognoza t0 oparta tylko na pierwszych 20 → dni 21–30 nie trafiają do cech prognozy przed t0.
- `LOAD-15`: brak przyszłej ceny mimo wystarczającej prognozy domu → planner kończy plan na znanej cenie, a nie horyzoncie load.
- `LOAD-16`: chwilowe `unavailable` jednego ze składników `home_energy_consumption` przy `float(0)` → wynik domu `invalid_input`, nie uczenie na sztucznie zaniżonym popycie.

**Odbiór:** źródło Recorder, profil i wszystkie założenia jakości są dostępne w natywnym HA, oddzielone od fizycznego sterowania. Nie jest potrzebne żadne nowe źródło zużycia od użytkownika do stworzenia modułu prognostycznego; rzeczywista jakość zostanie zbadana po uruchomieniu na historii HA.
