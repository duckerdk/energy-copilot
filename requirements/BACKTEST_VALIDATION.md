# Walidacja ekonomiczna i testy historyczne (backtesting)

**Status:** normatywna specyfikacja oceny optymalizatora w `dry_run`, przed kodem i przed sterowaniem. **Nie jest raportem uzyskanych oszczędności.**
Zależności: [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [TEST_SCENARIOS.md](TEST_SCENARIOS.md), [DECISION_LOGGING.md](DECISION_LOGGING.md), [ARCHITECTURE.md](ARCHITECTURE.md).

## 1. Cel

Sprawdzić, czy optymalizator **rzeczywiście obniża koszt zakupu minus przychód eksportu**, po uwzględnieniu strat i szacowanego marginalnego zużycia baterii, a nie tylko poprawia autokonsumpcję. Udowodnić deterministyczność, poprawny bilans, odporność na błąd prognozy, brak fałszywych oszczędności i brak „wiedzy o przyszłości”.

**Główne wyniki raportu:** koszt rachunkowy netto DKK, przychód ze sprzedaży DKK, import/eksport kWh, koszt modelowy degradacji DKK, wartość energii w magazynie na końcu okresu i powiązana niepewność. Dla obu strategii ten sam okres, początkowy SOC i zestaw fizycznych ograniczeń.

## 2. Reguła walk-forward — najważniejsza

Backtest **odtwarza** decyzje w chronologicznej kolejności na danych, które były dostępne **w momencie decyzji**.

1. Dla `t0` zebrać wyłącznie ceny opublikowane do `t0`, wersję prognozy PV/zużycia istniejącą do `t0`, pomiary i model dostępny do `t0`.
2. Uruchomić planner, zapisać `decision_id`, harmonogram, uzasadnienie i przewidywany wynik. **Nie** używać rzeczywistych przyszłych pomiarów do ustalenia bieżącego celu SOC ani modeli uczonych na danych po `t0`.
3. Symulować pierwszy krok lub część kroku po `t0` na rzeczywistej pogodzie/obciążeniu **tylko wtedy, gdy dane pozwalają odtworzyć fizyczne możliwości tej alternatywy**; dalej przejść do kolejnego kroku, zaktualizować stan baterii i ponownie planować.
4. Około 13:00 kolejnej doby ceny następnego dnia pojawiają się **dopiero po rzeczywistym timestampie publikacji danych**; jeżeli archiwalnego czasu publikacji nie ma, użyć jawnie oznaczonego konserwatywnego założenia w osobnej symulacji, a nie przedstawiać jako odtworzenia faktów.
5. Wersja modelu i parametry użyte do danego testu pozostają zamrożone; kalibracja na historii do `t0`, weryfikacja na przyszłych w stosunku do uczenia próbkach.

W razie braku historycznych migawek prognoz, nie wolno zastępować ich później skorygowanymi prognozami ani rzeczywistą produkcją jako „prognozą”. Oznaczyć test `limited_hindsight_validation` lub `blocked_for_walk_forward`.

## 3. Dobór danych i kompletność

| Warstwa | Minimalne wymaganie i problem |
| --- | --- |
| Ceny kupna | Końcowa zmienna taryfa DKK/kWh z odpowiednimi do każdego interwału opłatami; nie stosować aktualnych stawek wstecz bez oznaczenia symulacji |
| Ceny sprzedaży | Dokładna cena pobrana z `sensor.energi_data_spotpris` dla okresu historycznego, **bez dodatkowych przeliczeń**; brakujące archiwalne ceny = brak danych, nie odtwarzać ich z narzutów |
| PV prognozowane | Migawki Forecast.Solar sprzed danego okresu, wersja, horyzont i rozdzielczość |
| PV faktyczne | Jednoznaczna moc/energia PV z uwzględnieniem DC-coupled i możliwej blokady produkcji |
| Obciążenie domu | Historyczny rzeczywisty pobór domu po AC (nie import z sieci); brak podwójnego liczenia ładowania z sieci |
| Bateria | SOC, pojemność, ograniczenia mocy, sprawność według potwierdzonej strony AC/DC, zachowanie BMS |
| Sieć i eksport | Import/eksport z licznika, ograniczenia fizyczne, możliwość oddzielenia sprzedaży PV od sprzedaży baterii |
| Zdarzenia | Godziny zmian harmonogramu, ręcznych ingerencji, dostępność danych i awarie; wsteczne „idealne” sterowanie zakazane jako dowód gotowości |

**Curtailment:** mierzone 35 kWh przy prognozie 60 kWh w dzień z pełną baterią i wyłączonym eksportem **nie oznacza** dostępności tylko 35 kWh ani utraty dokładnie 25 kWh. W scenariuszach kontrfaktycznych „eksport PV włączony” trzeba znać potencjalną produkcję — jeśli brak wiarygodnego oszacowania, taki dzień nie może stanowić twardego dowodu przewagi algorytmu.

## 4. Co porównujemy

**A. Baseline rzeczywisty:** koszt zapisany przez licznik i rzeczywiste historyczne ceny, rzeczywista standardowa praca Deye. To obserwacja tamtej instalacji, **nie** bezpośrednio odtwarzalna alternatywa dla innej baterii/rozporządzania energią.

**B. Baseline symulowany:** model standardowej strategii Deye, sprawdzony na okresach, gdy działał bez optymalizatora (PV → dom/bateria, istniejące nastawy, eksport). Parametry modelu, błędy odwzorowania i ograniczenia opisane jawnie.

**C. Co-Pilot symulowany:** decyzje `walk-forward` z tym samym modelem przepływów i tą samą historyczną pogodą/zużyciem, bez informacji przyszłych w momencie decyzji.

Różnicę `B − C` można nazywać **modelową korzyścią wobec baseline**; różnicę `A − C` przedstawiać tylko z wyraźnym zaznaczeniem kontrfaktycznego charakteru C i błędu modelu. Nie deklarować „zaoszczędzono X DKK” na podstawie samego historycznego backtestu. Rzeczywisty efekt wymaga wdrożenia, pomiarów i adekwatnej korekty czynników zewnętrznych.

**Odrębna ocena sposobu wykonania:** dla każdej decyzji energetycznej porównywać nie tylko wynik idealnego MPC, ale też ograniczoną wykonalność przy **current-first z niezmienianym TOU** i opcjonalnie **dynamic TOU**. Uwzględnić ograniczoną liczbę okien, utrzymywanie się nastaw po zaniku HA, utratę okazji PV przy limicie 5 A, ryzyko pozostawionego ładowania sieciowego i liczbę zmian encji. Wartość prądu A jest maksymalnym dopuszczeniem, a nie wymuszoną mocą; nie symulować idealnej realizacji przepływów, jeśli brak fizycznej walidacji. Szczegóły i testy CTRL: [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md).

## 5. Ta sama energia końcowa i sprawiedliwy okres porównania

Wyrównanie końcowego SOC albo jawna **wartość końcowej energii w magazynie** jest konieczne do interpretacji zysków. Nie zaliczać do oszczędności przypadkowego wypróżnienia baterii w ostatniej godzinie testu, jeśli baseline pozostawił więcej energii.

- Raport pokazywać oddzielnie `SOC_start`, `SOC_end_baseline`, `SOC_end_optimizer` oraz `end_energy_value_dkk`.
- Jeżeli nie da się wiarygodnie wycenić różnicy na końcu, raportować zarówno surowy koszt rachunku, jak i **różnicę energii** oraz stan `economic_comparison_incomplete`; nie udawać dokładnej przewagi.
- Uwzględnić modelowy throughput i degradację dla strategii bazowej i optymalizatora, nie tylko dla jednej z nich.
- Pokazać również wynik po wyłączeniu degradacji i przy przedziale prawdopodobnych sprawności — jako analizę wrażliwości, nie zastępować nią głównej miary.

## 6. Scenariusze niepewności i zakresy

- Oceniać co najmniej **rzeczywistą pogodę**, skalibrowaną prognozę na dzień następny oraz scenariusze błędu prognozy dostępne *ex ante*, a nie „idealny oracle” jako podstawowy wynik.
- Liczyć statystykę błędu osobno dla wyprzedzenia prognozy, pory roku i odpowiednio reprezentowanych warunków; jeśli brak migawek, zgłosić brak możliwości empirycznej kalibracji.
- Wyniki pokazać osobno dla wysokich i niskich cen, niskiej i wysokiej produkcji PV, dni z ograniczaniem oraz godzin cen ujemnych.
- Niepewność ceny **poza faktycznie opublikowanym horyzontem** nie jest prognozowaną ceną. Analiza rezerwy końcowej może korzystać z fizycznego popytu/PV oraz scenariuszy, ale nie przypisuje im rzekomo znanego rachunku.
- W backteście osobno wyliczać warianty `without_battery_export` i `with_approval_hypothetical`. **Żadna symulacja nie oznacza zgody użytkownika**.

## 7. Metryki i kryteria odbioru

| Metryka | Raport |
| --- | --- |
| `net_grid_bill_dkk` | Import kWh × cena z `sensor.energi_data_service` − eksport kWh × cena z `sensor.energi_data_spotpris`; **obie bez korekt** |
| `battery_degradation_dkk` | Oddzielny modelowy koszt marginalnego zużycia obu strategii |
| `energy_losses_kwh` | Fizyczne straty, bez ponownego doliczania do kosztu rachunku |
| `net_economic_result_dkk` | Rachunek + marginalna degradacja + porównywalnie wyceniona energia końcowa (jawne założenie) |
| `grid_import_kwh / grid_export_kwh` | Ilości z licznika/modelu i kontrola znaku |
| `pv_curtailment_unknown_share` | Ile okresów jest nieodpowiednich do twardej rekonstrukcji potencjału PV |
| `forecast_sample_coverage` | Liczba i jakość dawnych migawek, odsetek reprezentatywnych okresów |
| `simulated_action_feasibility` | Udział planów możliwych do wykonania przez **potwierdzone** zdolności HA; idealny model oddzielnie |
| `relative_improvement_with_uncertainty` | DKK i zakres przy realnych różnicach SOC/sprawności/prognoz; brak sztucznej dokładności |

**Kryterium odbioru modelu:** bilans fizyczny zamyka się w każdym slocie; wynik nie pogarsza się z powodu wykrywalnych błędów arytmetycznych, nie używa przyszłości, benchmark sprawdza ograniczenia, a raport jawnie odróżnia zmierzone od symulowanych. **Nie wpisywać z góry progu % oszczędności**, bo zależy od danych i pogody. Ujemna korzyść w uczciwym teście jest poprawnym wynikiem diagnostycznym i wymaga dalszej analizy.

## 8. Scenariusze odbiorcze

- `BKT-01`: snapshot ceny i PV dostarczony po `t0` jest ignorowany przy decyzji w `t0`.
- `BKT-02`: brak archiwalnych prognoz prowadzi do `blocked_for_walk_forward`, a nie porównania z przyszłą produkcją.
- `BKT-03`: różne końcowe SOC pokazują różnicę energii i ograniczenie porównywalności; nie zysk wyliczony tylko z rachunku.
- `BKT-04`: brak potencjału PV podczas curtailment nie powoduje dopisania „straconych” kWh jako rzeczywistego eksportu w strategii alternatywnej.
- `BKT-05`: obie strategie otrzymują te same historyczne ceny z odpowiednich encji HA **bez jakichkolwiek przeliczeń, podatków, taryf lub potrąceń**; brakujące dane są oznaczone jako brak.
- `BKT-06`: wynik dla idealnej wiedzy przyszłości jest osobno oznaczony `oracle_upper_bound`, nie raport główny.
- `BKT-07`: cena następnego dnia nie jest dostępna od 00:00, lecz od faktycznej publikacji około 13:00 poprzedniego dnia.
- `BKT-08`: zmiana czasu zachowuje 23/25 godzin i właściwe uporządkowanie w UTC.
- `BKT-09`: niedostępne rzeczywiste sterowanie oddziela `ideal_plan` od `feasible_plan`.
- `BKT-10`: raportowana modelowa korzyść nie jest oznaczana „zaoszczędzono” bez fizycznego wdrożenia.
- `BKT-11`: brak danych do uczciwej wyceny końcowego SOC oznacza `economic_comparison_incomplete`.
- `BKT-12`: bez zgody rzeczywistej nie ma eksportu baterii w planie wykonywalnym, choć można wyliczyć ofertę hipotetyczną.

## 9. Wynik dla programisty i operatora

Wynik analizy: zakres dat i godzin, kompletność danych, porównanie strategii A/B/C, cena z opłatami, udział curtailment, dynamika SOC, DKK kosztu i degradowania baterii, miara niepewności, lista blokad oraz powiązane `decision_id` z [DECISION_LOGGING.md](DECISION_LOGGING.md). Dostępny bez ręcznego generowania JSON — raport i odnośniki w panelu HA, z zachowaniem lokalnej prywatności.

**Próg implementacji:** dopóki `BKT-01`–`BKT-12` nie są spełnione w testach albo jawnie zablokowane przez brak historycznych danych, nie twierdzić, że prognozowane oszczędności są empirycznie zweryfikowane.
