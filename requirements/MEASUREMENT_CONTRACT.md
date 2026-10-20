# Kontrakt pomiarów i bilansu energii — HA / Deye / PV DC

**Cel:** jedna definicja pomiarów wejściowych do planera, diagnostyki i backtestów. **Status danych:** identyfikatory, jednostki oraz jedna migawka z 19.10.2026 potwierdzone; znaki obu kierunków, fizyczne punkty pomiarowe i niezależność sygnałów nie zostały dowiedzione. Nie odczytywać rejestrów Modbus; korzystać z istniejących encji Home Assistant.

Źródła projektu: [HA_ENTITY_SNAPSHOT_2026-10-19.md](HA_ENTITY_SNAPSHOT_2026-10-19.md), [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [LOAD_FORECAST_CONTRACT.md](LOAD_FORECAST_CONTRACT.md), [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md).

## 1. Jedna mapa wejść, bez zdublowanych kanałów

| Rola logiczna | Podstawowa encja HA | Zaobserwowane | Interpretacja do przyjęcia projektowo |
| --- | --- | --- | --- |
| Moc PV rzeczywista | \`sensor.pv_sum\` | +3034 W | Suma mocy wejścia PV z MPPT, **najpewniej DC**; potwierdzić miejsce i zależność od innych szablonów |
| PV wejście MPPT 1 | \`sensor.sun12k_pv1_power\` | +2387 W | Składnik agregatu, **nie dodawać ponownie** do \`pv_sum\` |
| PV wejście MPPT 2 | \`sensor.sun12k_pv2_power\` | +647 W | Składnik agregatu, **nie dodawać ponownie** do \`pv_sum\` |
| Zużycie domu | \`sensor.home_energy_consumption\` | +583 W | Kandydat do fizycznego poboru domu; **nie zakładać niezależności od pozostałych sensorów** |
| Inna moc LOAD | \`sensor.sun12k_load_totalpower\` | +532 W | Osobny punkt pomiarowy; nie podmieniać nim automatycznie mocy całego domu i nie dodawać do domu |
| Moc netto na sieci | \`sensor.sun12k_total_grid_power\` | −2470 W | **Hipoteza znaków:** dodatnia = zakup, ujemna = eksport; przy zakupie jeszcze niepotwierdzona |
| Inny pomiar sieci | \`sensor.sun12k_out_of_grid_total_power_2\` | −2483 W | Alternatywny sygnał/kanał; **nie sumować** z \`total_grid_power\` |
| Moc baterii | \`sensor.sun12k_battery_output_power\` | +19 W | **Hipoteza znaków:** dodatnia = rozładowanie, ujemna = ładowanie; przy ujemnym jeszcze niepotwierdzona |
| Napięcie baterii | \`sensor.sun12k_battery_voltage\` | 56,69 V | Pomiary DC; walidować czas i jednostkę |
| Prąd baterii | \`sensor.sun12k_battery_output_current\` | +0,35 A | Hipoteza znaku zgodnego z mocą; sprawdzić obie strony i to, czy jest wejściem do obliczenia mocy |
| SOC | \`sensor.sun12k_battery_capacity\` | 97% | Jedna miara SOC; 20–100% to robocze granice polityki, nie potwierdzenie rzeczywistej pojemności użytecznej |

**Zabronione źródła:** encje \`battery_controller.*\` są pozostałościami i zostały przez użytkownika wykluczone. Prognoza Forecast.Solar (\`forecast_solar.get_forecast\`) nie jest pomiarem produkcji rzeczywistej. Moc PV już skierowana po DC do baterii **należy do całkowitej produkcji PV**, nie jest drugim niezależnym zyskiem energetycznym.

## 2. Konwencja normalizacji — hipoteza do symulacji i testów

Przy znaku \`P_grid_signed_W > 0\` jako zakupie, \`P_batt_signed_W > 0\` jako rozładowaniu:

\`\`\`text
pv_kw              = max(0, P_pv_W / 1000)
house_kw           = max(0, P_house_W / 1000)   # wyłącznie poprawny, zweryfikowany odczyt
grid_import_kw     = max(0, P_grid_signed_W / 1000)
grid_export_kw     = max(0, -P_grid_signed_W / 1000)
battery_discharge_kw = max(0, P_batt_signed_W / 1000)
battery_charge_kw    = max(0, -P_batt_signed_W / 1000)
\`\`\`

Wszystkie wartości kW są **nieujemne** po podziale na kierunki; surowy znak zachować w diagnostyce. Przy braku potwierdzonej konwencji dla **obu** stron status \`sign_assumption_only\`. Nie przepisywać wartości \`abs(P)\` bez określonego kierunku. Jeżeli obie składowe import/eksport powstają z *jednego* kanału mocy netto, nie raportować równoczesnego importu i eksportu jako osobnych fizycznych zdarzeń z tej samej próbki.

## 3. Przykładowa kontrola chwilowego bilansu — i jej granice

Dla przybliżonego, **stratami nieobjętego** sprawdzenia orientacyjnego:

\`\`\`text
residual_W = PV_W + battery_output_W + grid_signed_W - house_W
           = 3034 + 19 - 2470 - 583 = 0 W
\`\`\`

Podana migawka numerycznie pasuje. Dodatkowe sprawdzenia:
- \`PV1 + PV2 = 2387 + 647 = 3034 W\` — potwierdza **agregację**, nie niezależny trzeci pomiar;
- \`V_batt × I_batt = 56,69 × 0,35 ≈ 19,84 W\`, blisko stanu sensora baterii \`19 W\`; zgodność jest pomocnicza, może też wynikać z pochodnych encji;
- \`sun12k_load_totalpower = 532 W\` różni się od \`home_energy_consumption = 583 W\` o **51 W**. Nie wolno uznać ich za ten sam pomiar.

**KRYTYCZNE: zero residual nie jest dowodem niezależnego bilansu.** \`sensor.home_energy_consumption\` może być sensorem szablonowym wyliczonym z PV, baterii i sieci. Wtedy \`residual = 0\` zachodzi **z definicji**, nie potwierdza fizycznie torów ani sprawności. Pierwsza czynność Codexa: sprawdzić **rodowód (source lineage)** użytej encji (integracja źródłowa, zależność template/helper/utility meter, czy bazuje na innych wybranych pomiarach). To zadanie analizy HA, bez potrzeby zgadywania przez użytkownika.

**Granice bilansu:** \`PV\` prawdopodobnie po DC, \`grid\` i \`house\` prawdopodobnie po AC. Przy niezerowym ładowaniu/rozładowaniu występują straty falownika, przewodów i torów baterii, więc surowe równanie \`PV + batt + grid = house\` **nie jest ogólną tożsamością fizyczną** i nie wolno wymuszać residual 0 w każdym slocie. Produkcyjny model przepływów DC/AC z odrębnymi sprawnościami opisuje [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md).

**Synchronizacja:** migawka 19.10 obejmowała wartości z przesunięciem rzędu kilku sekund. Suma asynchronicznych wartości może nie być spójna przy zmianach PV czy obciążenia. \`last_updated\` w HA jest czasem zmiany stanu, a nie zawsze czasem ostatniego pomiaru. Kod powinien odróżnić \`last_reported\` (jeżeli dostępne), realną datę próbki w atrybutach oraz brak wiarygodnego czasu; dla porównania ograniczać odstęp czasowy i jawnie flagować \`snapshot_not_synchronous\`.

## 4. Model licznika energii i rachunku — bez podwójnego liczenia

| Kanał do statystyki | Encja | Odczyt 19.10.2026 | Znaczenie/warunek |
| --- | --- | --- | --- |
| Zakup energii dzisiaj | \`sensor.sun12k_daily_energy_bought\` | 4,3 kWh | Historia **importu**, nie wielkość dodatkowa do importu wyliczonego z mocy |
| Sprzedaż energii dzisiaj | \`sensor.sun12k_daily_energy_sold\` | 4,3 kWh | Historia **eksportu** |
| PV produkcja dzisiaj | \`sensor.sun12k_daily_production\` | 23,5 kWh | Może obejmować DC→baterię; nie dodawać jej do chwilowego PV przy agregacji |
| Magazyn ładowanie dzisiaj | \`sensor.sun12k_today_charge_of_the_battery\` | 8,6 kWh | Nie liczyć jako osobny zakup albo produkcję bez znajomości źródła ładowania |
| Magazyn rozładowanie dzisiaj | \`sensor.sun12k_today_discharge_of_the_battery\` | 1,2 kWh | Nie jest równoznaczne ze sprzedażą do sieci |
| Cena zakupu dzisiaj (licznik pomocniczy) | \`sensor.sun12k_daily_energy_bought_cost\` | 0 DKK przy 4,3 kWh importu | **Podejrzane**; nie przyjmować jako rzeczywistej ceny/kosztu |
| Wynagrodzenie za sprzedaż (pomocnicze) | \`sensor.sun12k_daily_energy_sold_compensation\` | 7,136... DKK | Tylko porównanie kontrolne; stawki mogą mieć inny czas, reset i model opłat |

**Rachunek netto:** osobno wyliczać koszt **faktycznego importu** według \`sensor.energi_data_service.raw_today/raw_tomorrow\` i przychód **faktycznego eksportu** według \`sensor.energi_data_spotpris.raw_today/raw_tomorrow − 0,0215\`. Do przyszłych decyzji pracować na prognozowanym eksporcie/importie, nie na liczniku dziennym jako pomiarze mocy.

**Dwa tryby obliczania rzeczywistych kWh:** (a) przyrost **zweryfikowanego**, nierestartowanego licznika \`kWh\`, lub (b) całka z mocy z rzeczywistymi odstępami próbek. **Nie sumować** wyników obu metod jako dwóch energii. Porównywać je jako **kontrolę** po dopasowaniu tych samych przedziałów. Liczniki dobowe mają reset — różnica po północy nie jest ujemnym importem/eksportem.

**Wymaganie kalibracyjne:** bieżąca moc PV, domu i baterii to próbki [W], nie narastające kWh. Nie mnożyć każdej próbki przez stałe 15 min, jeżeli próbki pojawiają się częściej/rzadziej lub występuje przerwa; potrzebna jawna metoda interpolacji/integracji i status pokrycia. Unikać podwójnego liczenia przepływu PV→bateria: do modelu używać **jednego** przepływu \`s_b\` po DC, nie dodawać go drugi raz do \`PV\`.

## 5. Reguły jakości i obsługi niezgodności

1. \`unknown\`, \`unavailable\`, \`NaN\`, brak jednostki lub konflikt jednostek = **brak wiarygodnego wejścia**, nie zero.
2. Stan \`sensor.sun12k_total_grid_power < 0\` w zaobserwowanym eksporcie to **silna wskazówka**, nie dowód działania tego znaku podczas importu; analogicznie \`battery_output_power > 0\` dla rozładowania i wartość ujemna przy ładowaniu.
3. Weryfikację fizycznych znaków oprzeć na **niewymagających zapisu** porównaniach różnych naturalnie występujących stanów: dzień PV→eksport, noc importu, rzeczywiste ładowanie baterii, rozładowanie baterii. Jeśli takich historii brak, status \`unverified_direction\`, model nie może potajemnie przedefiniować znaków.
4. Status \`dependency_suspected\` przy wyliczanym \`home_energy_consumption\`, brak niezależnego potwierdzenia bilansu. Nie potrzebujemy sztucznej tolerancji „0% strat”.
5. Każde porównanie odczytów wymaga **podobnego czasu pomiaru** i jawnego dopuszczalnego odchylenia względem realnej rozdzielczości sensorów; brak daty ostatniego raportu oznaczyć i ograniczyć diagnozę.
6. Błąd bilansu nie jest automatycznie błędem falownika ani powodem „uczenia korekty mocy”. Najpierw kierunki znaków, punkty AC/DC, pochodność szablonów, rozdzielczość, asynchroniczność i straty.
7. Gdy pomiary importu/eksportu nie są zweryfikowane w obu kierunkach, monitor/dry-run nadal działa z ograniczoną diagnostyką; **nie raportować oszczędności z dokładnością do groszy jako empirycznie dowiedzionych**.

## 6. Testy do zaimplementowania — fikcyjne serie

- \`MTR-01\`: migawka PV=3034 W, bateria=+19 W, sieć=−2470 W, dom=583 W → residual=0 W i **status \`single_snapshot_only\`**, nie \`verified_independent_balance\`.
- \`MTR-02\`: MPPT1=2387 W, MPPT2=647 W, PV_sum=3034 W → nie sumować \`PV_sum + PV1 + PV2\`.
- \`MTR-03\`: \`home_energy_consumption\` jest template obliczonym jako PV+bateria+sieć → niezależność=false mimo residual=0.
- \`MTR-04\`: bateria 56,69 V i 0,35 A → 19,8415 W, zgodność pomocnicza z +19 W, nie potwierdza niezależnego pomiaru.
- \`MTR-05\`: export: grid_signed=−2,470 kW → import=0, export=2,470 kW.
- \`MTR-06\`: import: grid_signed=+1,200 kW → import=1,200 kW, export=0; znak musi być oznaczony jako potwierdzony testem/historycznym odczytem.
- \`MTR-07\`: charge: batt_signed=−1,500 kW → charge=1,500 kW, discharge=0; kierunek potwierdzić przed użyciem operacyjnym.
- \`MTR-08\`: discharge: batt_signed=+0,500 kW → discharge=0,500 kW, charge=0.
- \`MTR-09\`: PV=5000 W, home=1000 W, bateria=−2000 W, sieć=−2000 W, idealne η=1 → residual=0; nie dodawać do PV ponownie 2000 W przepływu PV→bateria.
- \`MTR-10\`: noc, PV=0, home=1000 W, bateria=−1000 W, sieć=+2000 W, η=1 → residual=0, grid_charge pozostaje **ładowaniem baterii**, nie poborem domu.
- \`MTR-11\`: noc, PV=0, home=1000 W, bateria=+1500 W, sieć=−500 W, η=1 → residual=0, ale **eksport baterii** wymaga osobnej zgody, nawet gdy przełącznik PV export jest ON.
- \`MTR-12\`: moc LOAD=532 W i dom=583 W w tej samej próbce → różnica 51 W, bez automatycznej podmiany.
- \`MTR-13\`: kupiono dziś 4,3 kWh przy \`daily_energy_bought_cost=0\` → oznaczyć koszt historyczny \`untrusted\`, nie zastępować nim bieżącej taryfy.
- \`MTR-14\`: skok licznika dobowego z 9,8 na 0,1 kWh po północy → oznaczyć reset, nie ujemną energię.
- \`MTR-15\`: 1 kW przez 5 min, 2 kW przez 10 min → energia=0,4166667 kWh, nie suma mocy i nie dwie pełne ćwierćgodziny.
- \`MTR-16\`: \`PV\` i \`grid\` z pomiarów oddalonych o 20 s podczas dużej zmiany produkcji → \`snapshot_not_synchronous\`, bez twardego żądania residual 0.
- \`MTR-17\`: \`last_updated\` sprzed 30 min bez zmiany SOC, lecz \`last_reported\` aktualny → nie traktować samego SOC jako przestarzałego.
- \`MTR-18\`: dwie encje siatki \`total_grid_power\` i \`out_of_grid_total_power_2\` prawie równe → nie dodawać ich do jednej sumy sieci.
- \`MTR-19\`: ujemny wynik ceny sprzedaży i prawdziwy eksport kWh → zachować ujemny przychód, nie obcinać do 0.
- \`MTR-20\`: \`battery_controller.*\` zawiera dane pogodowe i setpoint 0 → całkowicie pominąć w źródłach planera i detekcji aktywnego konkurencyjnego sterowania.

**Warunek dla Codexa:** rozdzielić \`confirmed_entity_exists\`, \`assumed_sign\`, \`verified_bidirectional\`, \`verified_physical_meter_point\`, \`independent_meter\` i \`synchronized_snapshot\`. Sam sukces arytmetyczny bilansu w jednej chwili **nie podnosi poziomu pewności do „zweryfikowany fizycznie”**.
