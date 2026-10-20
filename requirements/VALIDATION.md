# Walidacja, backtest, logowanie i prezentacja

**Decyzje użytkownika: [REQUIREMENTS.md](REQUIREMENTS.md).** Nie kopiować poniższych wcześniejszych ograniczeń dostępu jako decyzji użytkownika. Szczególnie: automatyczny grid charge i 6 TOU są dozwolone po testach live; ręczna zmiana może być nadpisana przy nowym planie; stała degradacja to 0,40 DKK/kWh rozładowania DC.


---

## BACKTEST VALIDATION


**Status:** normatywna specyfikacja oceny optymalizatora w `dry_run`, przed kodem i przed sterowaniem. **Nie jest raportem uzyskanych oszczędności.**
Zależności: [OPTIMIZATION_MODEL.md](OPTIMIZATION.md), [TEST_SCENARIOS.md](VALIDATION.md), [DECISION_LOGGING.md](VALIDATION.md), [ARCHITECTURE.md](EXECUTION.md).

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

**Odrębna ocena sposobu wykonania:** dla każdej decyzji energetycznej porównywać nie tylko wynik idealnego MPC, ale też ograniczoną wykonalność przy **current-first z niezmienianym TOU** i opcjonalnie **dynamic TOU**. Uwzględnić ograniczoną liczbę okien, utrzymywanie się nastaw po zaniku HA, utratę okazji PV przy limicie 5 A, ryzyko pozostawionego ładowania sieciowego i liczbę zmian encji. Wartość prądu A jest maksymalnym dopuszczeniem, a nie wymuszoną mocą; nie symulować idealnej realizacji przepływów, jeśli brak fizycznej walidacji. Szczegóły i testy CTRL: [CONTROL_STRATEGY.md](EXECUTION.md).

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

Wynik analizy: zakres dat i godzin, kompletność danych, porównanie strategii A/B/C, cena z opłatami, udział curtailment, dynamika SOC, DKK kosztu i degradowania baterii, miara niepewności, lista blokad oraz powiązane `decision_id` z [DECISION_LOGGING.md](VALIDATION.md). Dostępny bez ręcznego generowania JSON — raport i odnośniki w panelu HA, z zachowaniem lokalnej prywatności.

**Próg implementacji:** dopóki `BKT-01`–`BKT-12` nie są spełnione w testach albo jawnie zablokowane przez brak historycznych danych, nie twierdzić, że prognozowane oszczędności są empirycznie zweryfikowane.


---

## TEST SCENARIOS


**Dodatkowe testy z potwierdzonych danych HA:** 18 przypadków `PRICE-01..18` w [HA_PRICE_SERIES_CONTRACT.md](HA_CONTRACT.md); obejmują atrybuty, flagę jutra, DST, opłaty w cenie i rozbieżną chwilę publikacji. Nie dublować tych testów w scenariuszach MAP/TIME.

**Status:** specyfikacja testów akceptacyjnych, bez implementacji. **Wszystkie ceny, profile i sprawności w przykładach są syntetycznymi danymi testowymi, nie odczytami instalacji użytkownika.**
Podstawa: [OPTIMIZATION_MODEL.md](OPTIMIZATION.md), [GOALS_AND_REQUIREMENTS.md](REQUIREMENTS.md), [ARCHITECTURE.md](EXECUTION.md), [ENTITY_CONTRACT.md](HA_CONTRACT.md).

## 1. Zasady interpretacji i kryterium zaliczenia

- Testy sprawdzają **wynik ekonomiczny, bilans fizyczny, ograniczenia i bezpieczeństwo**, a nie konkretną implementację solvera. Przy wielu równoważnych rozwiązaniach dopuszczać każdy optymalny plan spełniający niezmienniki; nie wymuszać dowolnego układu operacji.
- Gdy nie podano inaczej, testowa bateria: `capacity = 10,24 kWh`, `SOC_min = 20%`, `SOC_max = 100%`, `P_charge_max = 2,5 kW`, `P_discharge_max = 5 kW`, sprawności wszystkich czterech torów `η = 1`, koszt degradacji `0 DKK`, bez ograniczeń sieci; `E_min = 2,048 kWh`, `E_max = 10,24 kWh`. To **idealizacja wyłącznie dla jednoznacznej arytmetyki testowej**, nie rzeczywisty model wydajności.
- `C_buy` to wartość z `sensor.energi_data_service`, `C_sell` to wartość z `sensor.energi_data_spotpris` [DKK/kWh], **bez przeliczeń**. Wykonywalny plan automatycznego eksportu PV dopuszcza sprzedaż tylko przy `C_sell >= 0,40 DKK/kWh`; wszystkie kwoty w DKK. [PV_EXPORT_POLICY.md](EXECUTION.md).
- Moc to **kW średniego przepływu w slocie**, energia to kWh; bazowy slot `Δt = 0,25 h`. W testach całogodzinnych/dłuższych profil jest identyczny w każdym kwadransie danego okresu. Gdy test wymaga stałej wartości SOC na końcu albo wartości końcowej energii, jest to **jawny warunek fikstury**, nie stała reguła projektu.
- Domyślnie: **brak zgody na eksport energii z baterii**, zatem `b_x = 0`; automatyczny eksport PV dozwolony wyłącznie od 0,40 DKK/kWh z HA, o ile test nie stanowi inaczej. Tryb sprzętowego executora nieaktywny (`dry_run`).
- Tolerancja sprawdzeń numerycznych: energia i moc `1e-6` odpowiednich jednostek, pieniądze `1e-4 DKK`, SOC `1e-4 punktu procentowego`. Nie wprowadzać tolerancji, która pozwala naruszyć granice bezpieczeństwa.
- Każdy przypadek w raporcie ma `id`, dane wejściowe, rozwiązanie planu, obliczony koszt, naruszenia ograniczeń, wersję/ważność planu i rezultat `PASS/FAIL/BLOCKED`. `BLOCKED` oznacza brak koniecznego zweryfikowanego wejścia lub sterowania, nie zaliczony test.
- **Rozdzielenie rezultatów:** stan `planned` nie jest wykonaniem `applied`, a `applied` bez pomiaru zwrotnego nie jest `confirmed`.

## 2. Bilans fizyczny i konwersje

### PHY-01 — Energia ze slotu 15-minutowego

**Dane:** `P = 4 kW` stale przez 15 min.  
**Oczekiwane:** `E = 4 × 0,25 = 1,000 kWh`. Żaden moduł nie interpretuje 4 kW jako 4 kWh.

### PHY-02 — PV DC jednocześnie do domu i baterii

**Dane:** 15 min, `S = 4 kW` PV dostępnego po DC, `L = 2 kW` poboru domu, `SOC_start = 50%`, sprawności = 1, brak importu/eksportu.  
**Oczekiwane:** `s_h = 2 kW`, `s_b = 2 kW`, `s_x = s_c = 0`; PV = `1,000 kWh`, dom z PV = `0,500 kWh`, magazyn z PV = `0,500 kWh`; `E_end = 5,620 kWh`, `SOC_end = 54,8828125%`. Suma przepływów DC = 4 kW; nie dodawać ponownie energii ładowania DC do całkowitego uzysku PV.

### PHY-03 — Magazyn pełny i eksport wyłączony

**Dane:** 15 min, `S = 4 kW`, `L = 1 kW`, `SOC = 100%`, brak eksportu PV i baterii; przyjęto możliwość ograniczania PV.  
**Oczekiwane:** `s_h = 1 kW`, `s_b = s_x = 0`, `s_c = 3 kW`; uzyskana energia PV = `0,250 kWh`, niewykorzystany **potencjał w modelu idealnym** = `0,750 kWh`. Nie oczekiwać fizycznej produkcji 1 kWh przy zablokowanych odbiorach. Ten przypadek jest testem *symulacji znanej dostępnej mocy*, nie metodą wyznaczania rzeczywistego curtailment z samego licznika.

### PHY-04 — Granica SOC i redukcja mocy

**Dane:** start `SOC = 21%` = `2,1504 kWh`, 15 min, PV = 0, dom żąda 2 kW, `η_bat_ac = 1`.  
**Oczekiwane:** przy `E_min = 2,048 kWh` dostępne z baterii `0,1024 kWh`, zatem moc baterii do domu **nie przekracza `0,4096 kW`**; resztę pokrywa sieć (minimum `1,5904 kW`). SOC nigdy nie spada poniżej 20%.

### PHY-05 — Względna sprawność torów, bez podwójnego liczenia strat

**Dane:** bateria start `E_min`; w pierwszej godzinie import 1 kWh AC do baterii przy `η_grid_bat = 0,90`; w drugiej godzinie dom zużywa 0,81 kWh, pokryte w całości z baterii przy `η_bat_ac = 0,90`; brak PV, eksportu i pozostałych przepływów.  
**Oczekiwane:** przyrost energii w baterii `0,900 kWh`, później oddana energia AC `0,810 kWh`, strata całkowita `0,190 kWh` względem importu; SOC na końcu = SOC na początku. Koszt strat istnieje poprzez przepływy i ceny, nie jako drugi, niezależny narzut do rachunku.

### PHY-06 — Brak fizycznej pętli import/eksport

**Dane:** ten sam slot, jeden punkt przyłącza, dodatnia cena sprzedaży wyższa od ceny zakupu; brak potwierdzenia osobnego pomiaru/braku kompensacji.  
**Oczekiwane:** brak równoczesnych dodatnich wartości `Grid_import` i `Grid_export` w wykonywalnym planie. Optymalizator nie może tworzyć darmowego zysku z jednoczesnego, fikcyjnego zakupu i sprzedaży przez jeden licznik; wyjątek wymaga zweryfikowanej topologii i zasad rozliczeń.

## 3. Decyzje ekonomiczne — wyniki liczbowe

### ECO-01 — Cena eksportu netto

**Dane:** `sensor.energi_data_spotpris` podaje `0,8000 DKK/kWh`; drugi przypadek `−0,1000 DKK/kWh`.  
**Oczekiwane:** kolejno `C_sell = 0,8000` i `C_sell = −0,1000 DKK/kWh`. **Nie wykonywać żadnych potrąceń ani dopłat**. W drugim przypadku automatyczny eksport PV jest wyłączony.

### ECO-02 — Opłacalne ładowanie z sieci na potrzeby domu

**Dane:** `SOC_start = 20%`, brak PV, w pierwszej godzinie dom = 0 i `C_buy = 0,40`, w drugiej dom zużywa 1 kWh i `C_buy = 1,50`; możliwość ładowania z sieci; `E_end = E_min`; eksport z baterii zabroniony; `η = 1`.  
**Oczekiwane:** import **1 kWh** w taniej godzinie do baterii, następnie bateria → dom **1 kWh**; `SOC` po ładowaniu = `29,765625%`, po rozładowaniu = 20%; koszt `0,40 DKK` zamiast `1,50 DKK`; oszczędność `1,10 DKK`. Mocy ładowania/rozładowania nie przekraczać.

### ECO-03 — Zakup na późniejszy eksport jest nieopłacalny po stratach

**Dane:** dom = PV = 0; dopuszczony *hipotetycznie* eksport z baterii; zakup `C_buy = 0,50`, późniejszy eksport `C_sell = 0,60`; `η_grid_bat = η_bat_ac = 0,90`, koszt degradacji = 0, taki sam stan końcowy baterii.  
**Oczekiwane:** kupno 1 kWh, a następnie eksport 0,81 kWh dałyby przychód `0,486 DKK` przy koszcie `0,500 DKK`, czyli stratę `0,014 DKK`. Optymalny dodatkowy cykl = **0 kWh**; nie generować oferty sprzedaży z dodatnim zyskiem. Większe obroty przy liniowym modelu zwiększają stratę.

### ECO-04 — PV do baterii korzystniejsze niż eksport

**Dane:** teraz `PV = 1 kWh`, dom = 0, `C_sell_now = 0,50`; później dom = 1 kWh i `C_buy_later = 1,00`; brak innych PV, brak ładowania z sieci, `E_start = E_min`, `η = 1`, `E_end = E_min`.  
**Oczekiwane:** 1 kWh PV → bateria → dom; koszt netto `0,00 DKK`. Alternatywa eksport 1 kWh i późniejszy zakup 1 kWh kosztuje `1,00 − 0,50 = 0,50 DKK`; optymalizator wybiera magazynowanie.

### ECO-05 — Sprzedaż PV teraz korzystniejsza niż magazynowanie

**Dane:** jak ECO-04, lecz `C_sell_now = 1,20` i `C_buy_later = 0,70`.  
**Oczekiwane:** eksport PV 1 kWh teraz i późniejszy zakup 1 kWh do domu; koszt netto `0,70 − 1,20 = −0,50 DKK` wobec `0,00 DKK` przy magazynowaniu. Eksport PV nie wymaga zgody na sprzedaż energii **z baterii**.

### ECO-06 — Cena eksportu ujemna i brak możliwości magazynowania

**Dane:** `sensor.energi_data_spotpris` podaje `−0,10`, zatem `C_sell = −0,10` bez przeliczeń; potencjalne PV = 1 kWh, dom = 0, bateria pełna; dopuszczony curtailment.  
**Oczekiwane:** nie eksportować 1 kWh ze stratą `0,10 DKK`; w tym teście ograniczyć produkcję PV o 1 kWh, wynik finansowy 0 zamiast dodatniego kosztu eksportu. Nie stosować tej decyzji bez fizycznej możliwości ograniczania PV.

### ECO-07 — Degradacja rozstrzyga marginalną opłacalność

**Dane:** jak ECO-02, ale w **fiksturze testowej** koszt degradacji = `0,10 DKK za 1 kWh` energii przepływającej przez baterię, naliczany dla wejścia i wyjścia (2 kWh throughput łącznie).  
**Oczekiwane:** oszczędność na energii `1,10 DKK`, koszt degradacji `0,20 DKK`, wynik dodatkowy `+0,90 DKK`. Raportować osobno rachunek za energię i wewnętrzny koszt degradacji; nie przyjmować `0,10` jako parametru realnej baterii.


### ECO-08 — Niezależne optimum z rzeczywistym kosztem strat i degradacji

**Dane:** dwie kolejne godziny, każda podzielona na 4 sloty. Pojemność 10,24 kWh, SOC początkowy i końcowy **50%**, eksport baterii zabroniony. W 1. godzinie PV dostępne 2 kWh (2 kW, dom 0), sprzedaż PV netto `0,65 DKK/kWh`. W 2. godzinie PV 0, dom pobiera 2 kWh, zakup końcowy `1,20 DKK/kWh`. Brak innego źródła ładowania. Sprawności `η_pv_bat = 0,95`, `η_bat_ac = 0,90`, `η_pv_ac = 1`; testowy koszt degradacji = `0,10 DKK/kWh` PV przyjętego do baterii plus `0,08 DKK/kWh` AC oddanego z baterii. Ograniczenia mocy z fikstury głównej.

**Oczekiwane wyprowadzenie (nie narzucać celu SOC):**
- Dla 1 kWh PV skierowanego do magazynu zamiast na eksport: energia później oddana do domu = `0,95 × 0,90 = 0,855 kWh`.
- Uniknięty zakup = `0,855 × 1,20 = 1,026 DKK`.
- Utracony eksport = `0,65 DKK`; degradacja = `0,10 + 0,08 × 0,855 = 0,1684 DKK`.
- Dodatkowa korzyść na 1 kWh PV = `1,026 − 0,65 − 0,1684 = +0,2076 DKK`, więc ekonomicznie optymalne jest wykorzystanie **całych dostępnych 2 kWh PV** do baterii.
- Energia w baterii po ładowaniu = `5,12 + 1,90 = 7,02 kWh`, **SOC = 68,5546875%**; oddana później energia AC = `1,710 kWh`, zakup do domu = `0,290 kWh`, końcowy SOC 50%.
- Wynik wybranego planu = zakup `0,290 × 1,20 = 0,348 DKK` + degradacja `0,3368 DKK` = **0,6848 DKK**. Plan bez ładowania baterii: zakup `2 × 1,20` minus sprzedaż PV `2 × 0,65` = **1,1000 DKK**. Różnica = **+0,4152 DKK** na korzyść magazynowania.

**Warunek:** wyznaczony SOC wynika z niezależnego rachunku marginalnego, nie z oczekiwanego poziomu 65% lub 78,59375%. Wykonanie dowolnego planu musi zachować limity i identyczny SOC końcowy.

### ECO-09 — Eksport PV teraz, ładowanie magazynu z tańszej sieci później

**Dane:** trzy kolejne godziny (12 kwadransów), `η = 1`, koszt degradacji 0; start i koniec baterii SOC 20%, brak zgody na eksport baterii. Godzina 1: PV 1 kWh, dom 0, sprzedaż netto `0,90 DKK/kWh`. Godzina 2: PV 0, dom 0, cena zakupu `0,20 DKK/kWh`, ładowanie z sieci dostępne. Godzina 3: PV 0, dom 2 kWh, cena zakupu `1,50 DKK/kWh`. Limity mocy pozwalają na ładowanie 2 kWh w godzinę 2.

**Oczekiwane:** eksport **1 kWh PV** w godzinie 1; ładowanie baterii **2 kWh z sieci** w godzinie 2; rozładowanie **2 kWh do domu** w godzinie 3. Rachunek = `2 × 0,20 − 1 × 0,90 = −0,50 DKK`. Alternatywa: magazynować 1 kWh PV i dokupić 1 kWh do baterii w godzinie 2 → koszt `+0,20 DKK`. Wybrany plan jest lepszy o **0,70 DKK**. Nie występuje równoczesny import i eksport w jednym slocie ani eksport z baterii.

## 4. Dynamiczny SOC — dwa kontrastowe scenariusze

Dla **SOC-01** i **SOC-02** wspólne:
- Bateria startuje przy `SOC = 20%` = `E = 2,048 kWh`; `η = 1`, koszt degradacji 0, eksport z baterii zabroniony, ładowanie z sieci wyłączone, limit ładowania 2,5 kW.
- Dzisiejsze PV `6 kWh` w ciągu **3 godzin** po 2 kW; w tym czasie dom = 0, `C_sell_today = 0,80 DKK/kWh` (powyżej progu eksportu).
- Nocą dom potrzebuje `4,608 kWh` przez **4 godziny** po 1,152 kW; brak PV; cena zakupu nocą `1,00 DKK/kWh`.
- Ceny wszystkich godzin objętych scenariuszem zostały rzeczywiście podane w fiksturze, a więc dostępne w planie. Wartość końcowa każdego dodatkowego kWh w baterii powyżej minimum przyjmowana przez fiksturę wynosi `0,20 DKK/kWh`; to parametr testowy, nie produkcyjna nastawa.
- Eksport PV jest dozwolony i technicznie wykonalny; ograniczeń punktu przyłącza brak.

### SOC-01 — Jutro dużo PV; optimum przed nocą wynosi 65%

**Dodatkowe dane:** jutro rano `10 kWh` PV przez **4 godziny** po 2,5 kW, dom = 0; `C_sell_tomorrow = 0,50 DKK/kWh` (powyżej progu eksportu). PV wystarcza do uzupełnienia baterii do 100% z 20%; rano dozwolony jednoczesny przepływ PV do baterii i eksport PV (bez jednoczesnego importu z sieci).  
**Oczekiwane:**

1. Dziś do baterii z PV `4,608 kWh`, nadwyżkę `1,392 kWh` sprzedać po 0,80; przed nocą `E = 2,048 + 4,608 = 6,656 kWh`, **SOC = 65,0000%**.
2. W nocy bateria → dom `4,608 kWh`, import 0, rano `SOC = 20%`.
3. Jutro PV → bateria `8,192 kWh`, eksport `1,808 kWh` po 0,50, końcowy SOC 100%.
4. Przychód z PV = `1,392 × 0,80 + 1,808 × 0,50 = 2,0176 DKK`; zakup 0; koszt netto `−2,0176 DKK` (bez wewnętrznych kosztów). Wartość końcowa baterii jest taka sama dla rozważanych wariantów osiągających 100%, więc nie zmienia porównania.
5. Zmagazynowanie dziś pełnych 6 kWh zamiast 4,608 przesuwałoby 1,392 kWh eksportu z godziny sprzedaży po 0,80 do jutra po 0,50, obniżając przychód o **0,4176 DKK**. Nie wymuszać 100% już dziś.

**Warunek akceptacji:** model wyprowadza **65% jako wynik optymalizacji**, bez reguły typu „ustaw 65%”, i wskazuje ekonomiczną przyczynę (utracony przychód z eksportu dziś wobec jutrzejszej nadwyżki).

### SOC-02 — Jutro brak PV; cel SOC rośnie do 78,59375%

**Zmiana względem SOC-01:** jutro rano **PV = 0**, a dom zużywa dodatkowo `1,392 kWh` po `1,00 DKK/kWh`. Nie można ładować z sieci.  
**Oczekiwane:** dziś magazynować całe `6,000 kWh` dostępnego PV, przed nocą `E = 8,048 kWh`, **SOC = 78,59375%**; w nocy i rano pokryć z baterii razem `6,000 kWh`, zakończyć przy SOC 20% i imporcie 0. Eksport PV dziś 0. Sprzedaż dziś 1,392 kWh po 0,80 i zakup jutro 1,392 kWh po 1,00 pogorszyłyby wynik o `0,2784 DKK`.

**Warunek akceptacji:** zmiana jutrzejszej produkcji i zużycia automatycznie zmienia optymalny cel SOC, **bez ręcznej zmiany progu**.

## 5. Publikacja cen i czas

### TIME-01 — Dynamiczny koniec horyzontu, bez wymyślania 48 godzin

**Dane:** lokalnie 2026-10-19 12:55; ceny opublikowane do końca 2026-10-19, dla dnia 20.10 brak; po godz. 13:00 źródło przekazuje kompletną serię z datami 2026-10-20 00:00–23:59.  
**Oczekiwane:** przed publikacją koniec horyzontu **19.10 24:00**; po faktycznym otrzymaniu jutra koniec **20.10 24:00**, bez 21.10. Sama godzina 13:00, bez nowej serii, **nie przedłuża** horyzontu. Pierwszy bieżący slot może być częściowy.

### TIME-02 — Brakujący slot cenowy

**Dane:** lista cen z pominięciem jednego wymaganego interwału; są ceny przed i po luce.  
**Oczekiwane:** brak interpolacji lub podstawienia spot za końcową cenę zakupu. Plan nie może udawać kompletnego przedziału; luka oznaczona jako nieznana, a sterowanie zależne od luki zablokowane/przeplanowane na kompletnym fragmencie. Podać jawnie okres luki.

### TIME-03 — Zmiana czasu w Danii

**Dane:** kompletny dobowy zbiór cen w Europe/Copenhagen w dniach 2026-03-29 i 2026-10-25.  
**Oczekiwane:** odpowiednio **23 godziny = 92 sloty 15-minutowe** oraz **25 godzin = 100 slotów**; jesienna godzina 02:00 istnieje dwukrotnie jako dwie różne chwile UTC, żadnej nie nadpisywać. Doba 24h nie jest zakładana sztywno.

### TIME-04 — Replanowanie a ważność poleceń

**Dane:** plan `P1` powstał o 12:55, nowa seria cen o 13:08 uruchamia `P2`, executor otrzymuje spóźniony rezultat `P1`.  
**Oczekiwane:** polecenia i zgody dotyczące nieaktualnego `P1` niewykonalne; każdy wynik zawiera `plan_id`, czas utworzenia, zakres slotów i ważność. Wykonać tylko aktualnie ponownie zweryfikowane decyzje.

## 6. Uczenie prognoz i curtailment

### PVQ-01 — Prognoza 60 kWh, zmierzono 35 kWh przy ograniczonym eksporcie

**Dane:** prognoza potencjalnej produkcji na dzień = 60 kWh, rzeczywiście pozyskana = 35 kWh; kilka godzin pełna bateria, eksport OFF, niewystarczające dane do niezależnego pomiaru potencjału PV.  
**Oczekiwane:** **nie raportować automatycznego błędu prognozy −25 kWh** ani utraconego uzysku +25 kWh. Godziny podejrzane oznaczyć `curtailment_unknown`, a potwierdzone ograniczenia `curtailed_confirmed`. Statystyki uczenia liczyć jedynie ze zweryfikowanych godzin `uncurtailed`, bez udawania, że pozostałe są reprezentatywne.

### PVQ-02 — Pochmurny dzień bez ograniczenia

**Dane:** wiarygodna prognoza z poprzedniego dnia = 8 kWh, zmierzono 6 kWh, potwierdzono brak curtailment i kompletność pomiarów.  
**Oczekiwane:** błąd `actual − forecast = −2 kWh`; próbka kwalifikuje się do kalibracji, z przypisaniem do właściwego wyprzedzenia prognozy.

### PVQ-03 — Migawka prognozy, nie późniejsza korekta

**Dane:** wczoraj o 13:00 prognoza na dzisiaj = 8 kWh, dzisiaj o 10:00 poprawiona na 6 kWh, produkcja 6 kWh, bez curtailment.  
**Oczekiwane:** ocena jakości „prognozy na jutro” używa 8 kWh i błędu −2 kWh; ocena prognozy krótkoterminowej może osobno użyć 6 kWh i błędu 0. Nie nadpisywać starej migawki nową.

### PVQ-04 — Brak reprezentatywnej historii

**Dane:** wszystkie słoneczne okresy oznaczone `curtailed_confirmed` lub `curtailment_unknown`; pozostają wyłącznie pochmurne dni bez ograniczenia.  
**Oczekiwane:** `insufficient_history` dla kalibracji na słoneczne dni, brak deklaracji „90% pewności”; nie dopasowywać korekty PV na podstawie sztucznie zaniżonej produkcji.

## 7. Zgoda, dostępność wejść i bezpieczeństwo

### SAFE-01 — Brak zgody na sprzedaż z baterii

**Dane:** dostępne 1 kWh baterii powyżej minimum, dom = PV = 0, atrakcyjna cena eksportu, znane późniejsze tanie ładowanie z sieci; zgoda = brak.  
**Oczekiwane:** w **wykonywalnym** planie `b_x = 0`. Można sporządzić osobną *propozycję* z kwotą netto, ale nie zmieniać stanu zezwolenia na eksport baterii ani nie wydawać komendy. Eksport samego PV nie jest automatycznie zabroniony.

### SAFE-02 — Opłacalna sprzedaż z baterii po zatwierdzeniu

**Dane:** 1 kWh baterii ponad minimum, `η = 1`, `C_sell_now = 1,50`, późniejszy zakup do odtworzenia zapasu `C_buy_later = 0,20`, koszt degradacji 0, dostępne ładowanie z sieci, zgoda na konkretny `plan_id`, slot i maksimum 1 kWh; wszystkie stany zweryfikowane.  
**Oczekiwane:** w uproszczonym teście dodatkowy wynik = `1,50 − 0,20 = +1,30 DKK`; plan może dopuścić eksport **maksymalnie 1 kWh** i późniejsze uzupełnienie, wyłącznie w zatwierdzonym oknie. Kwota propozycji w realnym systemie musi ponadto uwzględnić stratę sprawności, degradację i koszt utraconej autokonsumpcji.

### SAFE-03 — Zgoda wygasła albo plan uległ zmianie

**Dane:** udzielono zgody na plan `P1`, potem minęło okno czasowe lub zoptymalizowano `P2` (inna godzina/energia/cena).  
**Oczekiwane:** `approval_valid = false` dla sprzedaży z `P1` i `P2`; nie wolno przenosić zgody na nowy plan, nawet jeśli nadal oczekiwany zysk jest dodatni. Brak odpowiedzi = brak zgody.

### SAFE-04 — Niepewne/nieaktualne dane

**Dane:** `unknown` albo `unavailable` dla SOC, brak świeżej ceny zakupu lub niedostępny stan zwrotny podstawowej encji sterowania.  
**Oczekiwane:** stan `BLOCKED` dla poleceń zależnych od danego sygnału, bez zgadywania wartości i bez wywołania usług. Możliwe zachowanie ostatnich poprawnych odczytów tylko do wyraźnie określonego wieku danych dla **monitoringu**, nie do niezweryfikowanego sterowania.

### SAFE-05 — Przestój HA nie może pozostawiać niebezpiecznej intencji

**Dane:** przed przerwą aktywne polecenie ładowania/eksportu, następnie utrata HA, Wi-Fi albo wykonawcy; niezweryfikowane zachowanie przełączników/urządzenia po utracie komunikacji.  
**Oczekiwane:** przed potwierdzeniem niezależnego mechanizmu bezpiecznego działania executor pozostaje **wyłączony**; `dry_run` nadal umożliwia planowanie. Sam brak kolejnych poleceń lub ponowny start HA **nie stanowią** dowodu przywrócenia normalnego trybu.

### SAFE-06 — Komenda rozładowania na dom nie może ukryć eksportu

**Dane:** bieżący dom = 1 kW, PV = 0, brak zgody na eksport z baterii, planowany pobór z baterii 2 kW do AC; brak innego odbiornika.  
**Oczekiwane:** zasilanie z baterii do domu nie może przekroczyć 1 kW w tym slocie; pozostałe 1 kW byłoby eksportem z magazynu, a więc bez zgody jest niedopuszczalne. Jeśli mapowanie encji nie pozwala rozdzielić kierunków, blokować taki rozkaz zamiast zakładać, że „pójdzie na dom”.


## 8. Kontrakt encji HA — testy bez rzeczywistego zapisu

### MAP-01 — Zakup i sprzedaż są odrębne

**Dane:** źródło spot = `0,80 DKK/kWh`, cena końcowa zakupu w drugim źródle = `1,45 DKK/kWh`; te same znane znaczniki czasu.  
**Oczekiwane:** `C_buy = 1,45`, `C_sell = 0,80 DKK/kWh` bez przeliczeń. Nie wolno używać jednej encji jako obu cen ani korygować otrzymanych wartości.

### MAP-02 — Zmiana jednostki mocy

**Dane:** mock encji PV daje `2500 W`, encja obciążenia domu daje `1,2 kW`, a slot trwa 15 min.  
**Oczekiwane:** po normalizacji PV = `2,5 kW`, dom = `1,2 kW`, energia PV = `0,625 kWh`; brak błędnego `2500 kW`.

### MAP-03 — Niejednoznaczna definicja mocy baterii

**Dane:** istniejąca encja o stanie `-500 W`, nieznana konwencja znaku i nieokreślony punkt pomiaru DC/AC.  
**Oczekiwane:** brak arbitralnego przypisania do ładowania lub rozładowania; `data_quality = invalid` dla tej roli i blokada zależnych poleceń.

### MAP-04 — Prognozy jutra nie opublikowano mimo godziny 13:00

**Dane:** zegar 13:10; dostępne ceny wyłącznie do dzisiaj 23:59, brak jutra.  
**Oczekiwane:** `price_horizon_end` = koniec dzisiejszej doby; brak symulowania nieopublikowanych cen, plan nie przekracza dostępnego horyzontu cen.

### MAP-05 — Planowana moc nie jest potwierdzeniem wykonania

**Dane:** planner zwraca `charge_power_kw = 2`, nie ma fizycznie zweryfikowanej encji regulacji mocy ładowania.  
**Oczekiwane:** sensor może wyświetlić zamiar 2 kW, `missing_capabilities` zawiera brak regulacji, executor nie wysyła żadnej komendy. Nie zastępować sterowania mocą przełącznikiem zezwolenia na ładowanie.

### MAP-06 — Niezweryfikowane znaczenie historycznego limitu prądu

**Dane:** skonfigurowano `number.sun12k_maximum_battery_grid_charge_current` z opisem niezgodnym między pierwotną logiką PV a etykietą grid; nie przeprowadzono testu skutku.  
**Oczekiwane:** sterowanie tą encją pozostaje zablokowane niezależnie od tego, czy liczba wynosi 1 A czy 40 A; jednocześnie można używać sprawdzonych encji do odczytu i symulacji.

### MAP-07 — Własne zakresy prądu zamiast błędnych granic HA

**Dane:** HA reklamuje `min = -16777220 A`, `max = 16777220 A` dla trzech regulatorów. W polityce Energy Co-Pilot odpowiednio **0–50 A**, **0–100 A**, **0–50 A**. W trybie `dry_run` testować wartości: ładowanie `-1, 0, 50, 51 A`; rozładowanie `-1, 0, 100, 101 A`; grid charge `-1, 0, 50, 51 A`.

**Oczekiwane:** dla każdej encji tylko wartości **wewnątrz własnego domkniętego przedziału** przechodzą walidację numeryczną, a `-1 A` i przekroczenie maksimum są odrzucane z `CURRENT_LIMIT_OUT_OF_RANGE` bez zapisu. Znaczenie fizyczne wartości 0 wymaga niezależnej walidacji.

### MAP-08 — 0 A nie jest automatycznym poleceniem wyłączenia

**Dane:** plan wymaga zatrzymania ładowania; karta akcji nie potwierdza semantyki ustawienia 0 A na `number.sun12k_maximum_battery_grid_charge_current`.

**Oczekiwane:** dopuszczenie 0 A w polityce liczbowej **nie** powoduje wywołania HA. Działanie ma status `blocked` / `CAPABILITY_NOT_VALIDATED`, aż zatwierdzona będzie fizyczna reakcja falownika oraz procedura bezpiecznego zatrzymania.

### MAP-09 — Osierocone encje Battery Controller ignorowane

**Dane:** występuje `switch.battery_controller_optimization_enabled = on` i `select.battery_controller_control_mode = hybrid`, ale użytkownik potwierdził, że to pozostałości bez działającego kontrolera.

**Oczekiwane:** Energy Co-Pilot **nie** wykorzystuje ich jako źródeł, nie wydaje do nich komend i nie tworzy z nich powodu blokady. Potwierdzony *rzeczywiście działający* konkurencyjny wykonawca zapisujący nastawy Deye jest traktowany osobno.

## 9. Co programista ma udowodnić

| Zestaw | Wynik akceptacji |
| --- | --- |
| PHY | Bilans energii i jednostki poprawne w każdym slocie; granice nigdy nieprzekroczone |
| ECO | Dokładne wyniki DKK i brak nieopłacalnych dodatkowych cykli |
| SOC | Dwa różne SOC z dwóch różnych prognoz, bez hardcodowania stałego procentu |
| TIME | Horyzont tylko opublikowanych cen, brak sztucznych godzin i poprawne DST |
| PVQ | Curtailment nie psuje kalibracji, przechowanie dawnych wersji prognoz |
| SAFE | Bez zgody, sprawnych danych i potwierdzonego toru kontroli brak poleceń sprzętowych |
| MAP | Poprawne mapowanie cen/jednostek i wyraźny rozdział planu od rzeczywistych akcji |

**Warunek ukończenia testów dokumentacyjnych:** wszystkie powyższe oczekiwane wyniki mają dać się wyrazić w testach automatycznych i symulacji z fikcyjnymi encjami. Scenariusze celowo izolują pojedyncze zjawiska; **nie zastępują walidacji rzeczywistej topologii, taryfy, sprawności ani procedury fail-safe**. Przy braku wymaganych informacji oznaczyć odpowiedni etap jako `BLOCKED`, nie tworzyć fikcyjnej kompatybilności.


---

## DECISION LOGGING


**Status: wymaganie obowiązujące do pierwszego uruchomienia w trybie monitor/dry-run.** Dotyczy decyzji planera i późniejszych poleceń wykonawcy. Dane przechowywane lokalnie w HA; bez zewnętrznej telemetrii i bez ręcznego eksportu JSON do analizy bieżącego działania.

## 1. Cel

Każda istotna decyzja optymalizatora ma być **wyjaśnialna i możliwa do prześledzenia**: skąd wzięły się ceny i prognozy, dlaczego wybrano ładowanie/eksport/brak działania, jakie alternatywy rozważono, czy plan był wykonalny, a później — czy został wykonany.

Szczególnie podczas rozruchu użytkownik musi widzieć **podstawy każdej decyzji** bez wyszukiwania ich w kodzie lub uruchamiania debuggera.

Rejestrować także:
- plan: `charge_from_grid`, `charge_from_pv`, `discharge_to_home`, `propose_battery_export`, `export_pv`, `curtail_pv` i `idle`; każda decyzja ON/OFF eksportu PV podaje **cenę sprzedaży wprost z HA, próg 0,40 DKK/kWh, decyzję switch i jej powód**;
- wynik `blocked`, błędy i odstąpienie od komendy;
- każdą aktualizację planu po cenach około 13:00 lub istotnej zmianie danych;
- powody zmiany/odrzucenia propozycji eksportu baterii;
- polecenie HA, skutek fizyczny, konflikt, retry i wyjście z trybu;
- zmianę jakości danych i ograniczeń, jeśli wpłynęła na decyzję.

## 2. Dwa poziomy informacji

**Widok bieżący — poziom INFO, włączony od pierwszego uruchomienia:**
- godzina decyzji, aktywny `plan_id`, okres slotu i ważność;
- działanie: co i z jaką zamierzoną mocą, skąd/dokąd energia, docelowy SOC;
- ceny kupna i sprzedaży **dokładnie z odpowiednich encji HA** (bez przeliczeń), próg zezwolenia eksportu PV 0,40 DKK/kWh; prognoza PV i poboru dla rozpatrywanych okresów;
- przewidywany koszt wybranego planu, przewidywany wynik względem **porównywalnej alternatywy**; wartość degradacji i ryzyka osobno;
- krótkie konkretne uzasadnienie oraz status wykonawczy `planned`, `blocked`, `applied`, `confirmed` albo `uncertain`.

**Widok szczegółowy — poziom DEBUG (przez konfigurację HA), włączany do analizy:**
- pełne dane slotów użyte przez model, po normalizacji, z czasami publikacji i wersjami prognoz;
- moce i bilans energii, ograniczenia, liczba kandydatów albo status solvera, ewentualne naruszenia i powody odrzucenia;
- porównywalne alternatywy i ich koszty, z tym samym horyzontem i warunkiem końcowym SOC;
- wagi/model degradacji i niepewności, sposób policzenia wartości energii na końcu horyzontu;
- przebieg weryfikacji rzeczywistej akcji, czas, wartości odczytane i warunki potwierdzenia.

Logi INFO nie mogą być ogólnikami typu „optymalizacja korzystna” lub „prognoza dobra”. Muszą podawać **liczby i ich źródła**, a jeśli dane są nieznane — dokładnie to zaznaczać. Nie dopisywać fikcyjnych prawdopodobieństw ani procentowych oszczędności.

## 3. Struktura rekordu

Minimum dla każdej iteracji:

| Pole | Wymaganie |
| --- | --- |
| `decision_id`, `plan_id`, `model_version`, `created_at_utc` | Stabilna identyfikacja i możliwość porównania replanowań |
| `trigger` | Np. regularny cykl, nowe ceny, zmiana PV/SOC/zużycia, nowa zgoda, błąd |
| `effective_slot_utc`, `price_horizon_end_utc` | Slot decyzyjny i ostatnia **opublikowana** cena |
| `inputs` | SOC %, PV/dom kW, ceny kupna/sprzedaży, prognozy PV/zużycia z godzinami i jakością, dostępne limity, źródła danych |
| `economics` | Planowany rachunek netto DKK, koszty degradacji i ryzyka DKK, wartość końcowa energii i scenariusz porównawczy |
| `choice` | Logiczne źródło energii, odbiorca, moc, cel SOC, eksport/ograniczenie PV lub bezczynność |
| `alternatives` | Co najmniej realny wariant **bez dodatkowej akcji**; dla wyborów kluczowych drugi wariant, gdy wykonalny; różnica DKK |
| `reason_codes` i `reason_text` | Maszynowy stabilny kod i jednozdaniowa przyczyna oparta na liczbach |
| `constraints` i `missing_capabilities` | SOC, moc, zgoda, ograniczenie eksportu, brak aktualnych danych, możliwość realizacji |
| `status` | `planned` / `blocked` / `superseded` / `executed` / `partially_executed`; osobny status sprzętowy |
| `linked_actions` | Identyfikatory akcji HA, jej stanu i niezależnego pomiaru skutku, **jeżeli działanie nastąpiło** |

Każde pole liczbowe z jednostką. Znaczniki czasu jednoznaczne UTC. W zapisie należy przechować wersję/odcisk danych wejściowych oraz istotne agregaty, aby późniejsza zmiana prognozy nie nadpisywała przyczyny dawnej decyzji.

**To nie jest obowiązek logowania całej historii 15-minutowych encji przy każdym przeliczeniu.** Wystarczy deterministyczny zestaw użytych wartości i odwołanie do lokalnej migawki, jeśli istnieje; szczegóły DEBUG powinny umożliwiać odtworzenie rozstrzygnięcia.

**Wymóg rozdzielenia planu i skutku przy sterowaniu prądem:** dziennik decyzji rejestruje `backend = current_first | dynamic_tou_candidate | none`, `active_tou_period` (jeśli znany), `intended_energy_flow_kw`, `proposed_charge_current_limit_a`, `proposed_grid_charge_current_limit_a`, `proposed_discharge_current_limit_a`, `ha_entity_id`, `persistent_after_ha_loss = true`, `expected_effect`, `observed_battery_power_kw`, `observed_grid_power_kw` i `unfulfilled_intent_reason`. Zamiana kW na A bazuje na **aktualnym napięciu** i oznaczonej niepewności, nie na stałej wartości. Nie raportować „ładowanie 2 kW wykonane” wyłącznie dlatego, że encja przyjęła nowy limit A. Przy opcji dynamicznego TOU zapisać porównanie z `current_first` i powód, dlaczego sześć okien jest potrzebne. Metodologia: [CONTROL_STRATEGY.md](EXECUTION.md), dokładny schemat translacji i testy: [CURRENT_CONTROLLER_MODEL.md](EXECUTION.md).

## 4. Rzetelne porównanie alternatyw

- Porównywać **ten sam horyzont**, prognozy, start SOC, parametry sprawności i **porównywalną wartość energii końcowej**; inaczej różnica zysków jest myląca.
- `baseline` definiować jawnie (np. brak nowej akcji optymalizatora przy zachowaniu zweryfikowanej standardowej pracy falownika), nie zastępować go fikcyjnym scenariuszem „wszystko z sieci”, jeśli Deye normalnie korzysta z PV.
- Koszt faktury = zakupy z opłatami minus eksport netto; koszt degradacji i ryzyka podać osobno. Jeżeli brak wystarczających danych do uczciwego porównania, `benefit_vs_baseline` = nieznany i `reason_code = BASELINE_UNAVAILABLE`.
- Dla odpowiedzi „dlaczego nie 100% SOC?” podać prognozowane przyszłe zapotrzebowanie, PV, ceny i różnicę opłacalności przechowania dodatkowej kWh względem eksportu teraz, a nie wskazywać arbitralny próg.
- Wariant alternatywny niespełniający ograniczeń oznaczyć `infeasible` zamiast przypisywać mu dowolną kwotę.

## 5. Typowe kody przyczyn

`GRID_CHEAPER_AFTER_LOSSES`, `PV_STORAGE_MORE_VALUABLE`, `PV_EXPORT_MORE_VALUABLE`, `PV_EXPORT_BELOW_MIN_PRICE`, `PV_EXPORT_ALLOWED`, `NEGATIVE_EXPORT_PRICE`, `TARGET_SOC_FROM_DEMAND`, `TERMINAL_ENERGY_VALUE`, `FORECAST_UNCERTAINTY`, `CURTAILMENT_SUSPECTED`, `PRICE_NOT_PUBLISHED`, `SOC_LIMIT`, `POWER_LIMIT`, `BATTERY_EXPORT_NOT_APPROVED`, `CAPABILITY_NOT_VALIDATED`, `STALE_DATA`, `NO_POSITIVE_NET_BENEFIT`, `NO_ACTION_BEST`, `PLAN_SUPERSEDED`, `ACTUATION_NOT_CONFIRMED`, `BASELINE_UNAVAILABLE`.

Kody mogą się łączyć: np. ładowanie PV wybrane dzięki cenom **i** dostępnej mocy baterii. Nie wpisywać „100% pewności prognozy” ani „odzyskaliśmy 25 kWh” na podstawie różnicy prognoza/produkcja podczas curtailment.

## 6. Przykładowy wpis INFO (wyłącznie dane syntetyczne)

> 2026-10-19 13:15, plan P27, slot 13:15–13:30. Tryb dry-run.  
> **Decyzja:** PV → bateria 1,5 kW, docelowy SOC 65%.  
> **Podstawa:** SOC teraz 43%; cena sprzedaży PV teraz 0,30 DKK/kWh; planowana cena zakupu w nocy 1,00 DKK/kWh; prognoza nocnego zapotrzebowania 4,6 kWh.  
> **Porównanie:** magazynowanie tej energii korzystniejsze niż jej sprzedaż i późniejszy zakup, po modelowych stratach i degradacji — różnica **do wyliczenia przez silnik**, nie wpisana na sztywno.  
> **Wykonanie:** nie wykonywano; moduł monitor/dry-run.

W rzeczywistym logu pole `comparison_delta_dkk` musi zawierać obliczoną kwotę **albo** jawny stan `unknown` — przykład nie uprawnia do podawania wyimaginowanego zysku.

## 7. Miejsce i trwałość logów

- **Źródło prawdy:** lokalny, ograniczony ilościowo rejestr zdarzeń integracji, uporządkowany po `timestamp_utc`; nie polegać tylko na przewijalnym systemowym `home-assistant.log`.
- **Widok HA:** ostatnia decyzja i jej uzasadnienie zawsze dostępne na panelu; przewijana historia decyzji z filtrami `plan_id`, typ decyzji, blokada, czas i rezultat. Możliwe użycie natywnych encji, zdarzeń HA i standardowych kart; konkretną reprezentację dobrać po sprawdzeniu ograniczeń platformy.
- **Dziennik systemowy HA:** INFO dla planu/zmian i alertów, DEBUG dla rozszerzonych obliczeń po świadomym włączeniu; bez zalewania logów każdą zmianą techniczną, jeśli nie zmienia ona decyzji.
- **Proponowana polityka rozruchowa:** lokalna retencja **30 dni** z limitem wielkości, obrót FIFO i opcja eksportu diagnostyki na żądanie (po anonimizacji). Retencja jest parametrem konfiguracji; limit chroni pamięć i bazę Recorder. **Nie wolno po cichu wyłączyć zapisywania przyczyn decyzji po określonej dacie**.
- Nie logować tokenów, danych uwierzytelnienia, prywatnych URL, pełnych historii domowników, identyfikatorów osoby, lokalizacji dokładnej. Dane cenowe, wynik planu i zagregowana moc są potrzebne; rozbudowane dane godzinowe przechowywać lokalnie i tylko w zakresie koniecznym.
- Po ponownym uruchomieniu HA historia jest zachowana, ale poprzedni plan nie staje się przez to aktywny; nowy plan/log wskazuje rekoncyliację.

## 8. Testy odbiorcze

- `LOG-01` każda nowa decyzja, w tym `idle` i `blocked`, daje czytelny wpis INFO z `plan_id` i konkretną przyczyną.
- `LOG-02` log pokazuje prawdziwą cenę finalną zakupu i cenę sprzedaży netto, nie myli ich z ceną spot.
- `LOG-03` prognoza zmieniona po decyzji nie nadpisuje migawek i uzasadnienia starego planu.
- `LOG-04` wynik porównania dwóch planów z różnym końcowym SOC nie podaje pozornego zysku bez wyrównania wartości końcowej energii.
- `LOG-05` system w `dry_run` raportuje `planned`, a nie `confirmed` ani „wykonano”.
- `LOG-06` brak fizycznego potwierdzenia polecenia daje `uncertain` i odnośnik do poprzedniego `action_id`.
- `LOG-07` restart odtwarza **historię diagnostyczną**, ale nie zatwierdzenie eksportu ani aktywne komendy.
- `LOG-08` retencja ogranicza pamięć, nie powoduje utraty ostatniego wpisu przyczyny aktualnego planu.
- `LOG-09` użytkownik znajduje ostatnią przyczynę i historię w panelu HA bez ręcznego eksportu JSON.
- `LOG-10` brak kosztu porównawczego jest `unknown`, nie 0 DKK i nie sztucznym zyskiem.

**Warunek odbioru M3/M4:** bez działającego rejestru przyczyn decyzji projekt nie jest gotowy do uruchomienia nawet w trybie dry-run.


---

## HA DASHBOARD


**Status:** projekt funkcjonalny; bez kodu dashboardu. Priorytet: **natywne sensory/encje HA oraz standardowe karty Lovelace**, bez dodatkowej aplikacji lub własnego frontendu dopóki standardowe mechanizmy spełniają zadanie.
Powiązania: [ENTITY_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION.md), [EXECUTION_CONTRACT.md](EXECUTION.md), [GOALS_AND_REQUIREMENTS.md](REQUIREMENTS.md).

## 1. Zasada prezentacji

Panel w jednym miejscu odpowiada na pięć pytań:

1. **Co dzieje się teraz?** Pomiary PV, domu, baterii, sieci i SOC, z jednostkami i znacznikami aktualności.
2. **Co system planuje?** Intencja ładowania/rozładowania, docelowy SOC, moc, źródło, odbiorca energii, następna zmiana trybu, powód.
3. **Dlaczego?** Cena zakupu **z opłatami**, cena sprzedaży **netto**, oczekiwana korzyść względem wariantu bazowego, prognoza PV i domu, warunki i ograniczenia.
4. **Co wydarzy się później?** Harmonogram slotów, przewidywany SOC, import/eksport i koszt do końca **opublikowanych cen**.
5. **Czy działa automatycznie?** Tryb `monitor`/`dry_run`/automatyka, status wykonawcy, potwierdzenie skutków oraz zgody i blokery.

**Zakaz mylenia wielkości:** planowane wartości oznaczać `plan`, zmierzone `actual`, potwierdzenie komendy `confirmed`; prognozowane oszczędności nie są już uzyskanymi pieniędzmi.

## 2. Układ jednego widoku

| Sekcja (od góry) | Zawartość | Zachowanie |
| --- | --- | --- |
| **Status i blokady** | Tryb, `plan_status`, `executor_status`, `last_update`, `price_horizon_end`, liczba krytycznych problemów | Blokady widoczne nawet bez przewijania; przy `blocked` wskazać konkretną przyczynę |
| **Bieżąca energia** | PV kW, dom kW, import/eksport kW, bateria ładowanie/rozładowanie kW, SOC % | Oddzielnie znane pomiary i symulacje; status `unknown` nie pokazywany jako 0 |
| **Aktualna decyzja** | Zamierzona akcja, źródło (`pv`/`grid`/`mixed`), cel (`home`/`export`), moc, `target_soc_pct`, uzasadnienie, przewidywany czas zakończenia | W `dry_run` jednoznaczna etykieta „propozycja, nie wykonywana” |
| **Ceny i wynik** | Teraz: finalna cena zakupu i netto sprzedaży DKK/kWh; planowany koszt netto w horyzoncie, modelowy koszt degradacji i ryzyka **oddzielnie** | Nie wyświetlać wewnętrznego kosztu jako składnika faktury |
| **Harmonogram i prognozy** | Oś czasu do ostatniego znanego slotu: cena kupna/sprzedaży, PV, dom, SOC, import/eksport, zmiany planu | Tooltip z przedziałem czasu; różnica między prognozą a historią; wskazanie czasu publikacji cen |
| **Propozycje sprzedaży baterii** | Czas, dozwolone kWh i kW, dodatkowy wynik DKK, SOC po operacji, ważność, przyciski Zatwierdź/Odrzuć | Dostępne wyłącznie dla konkretnej `proposal_id`; bez odpowiedzi brak zgody |
| **Diagnostyka** | Jakość prognoz, curtailment, brakujące encje i działania, ostatnia nieudana akcja, ostatni potwierdzony pomiar | Pozwolić sprawdzić przyczynę i zakres blokady bez zrzutu pełnych prywatnych historii |

Możliwe są zakładki „Przegląd”, „Plan i koszty”, „Zgody”, „Diagnostyka” w **jednym** dashboardzie HA, jeśli pojedynczy widok okaże się przeładowany. Nie budować własnej, drugiej aplikacji.

## 3. Publiczny model stanów

Poniższe nazwy to **wewnętrzne role wyników**; ostateczne stabilne encje HA mają zostać opisane przez programistę w kontrakcie interfejsu. Nie traktować ich jak już istniejących `entity_id`.

| Grupa | Pola |
| --- | --- |
| Plan | `plan_id`, `plan_status`, `generated_at`, `price_horizon_end`, `next_decision_at`, `decision_reason` |
| Bateria | `battery_soc_actual_pct`, `battery_soc_forecast_pct`, `target_soc_pct`, `charge_source`, `charge_power_kw`, `discharge_destination`, `discharge_power_kw` |
| Energia | `pv_actual_kw`, `pv_forecast_kw`, `house_actual_kw`, `house_forecast_kw`, `grid_import_actual_kw`, `grid_export_actual_kw`, `grid_import_plan_kw`, `grid_export_plan_kw` |
| Ceny | `buy_price_now_dkk_kwh`, `sell_price_now_dkk_kwh`, `price_series_quality` |
| Koszty | `expected_net_bill_dkk`, `expected_degradation_dkk`, `expected_risk_dkk`, `incremental_benefit_vs_baseline_dkk` |
| Wykonanie | `control_mode`, `executor_status`, `last_action_id`, `last_action_result`, `last_physical_confirmation_at`, `missing_capabilities` |
| Propozycja | `proposal_id`, `approval_state`, `expires_at`, `approval_window`, `max_battery_export_kwh`, `estimated_extra_profit_dkk` |
| Dane | `forecast_issued_at`, `forecast_quality`, `curtailment_status`, `data_quality` |

**Wymogi:** prawidłowe jednostki i `device_class`/`state_class` tam, gdzie mają sens; nie używać klasy licznika energii dla wartości chwilowych i prognoz. Długiego harmonogramu nie przedstawiać jako jednego stanu tekstowego sensora (ogranzenia HA); zapewnić osobne pola aktualnej akcji, krótki podgląd i pełną ustrukturyzowaną serię w diagnostyce/atrybutach tylko gdy mieszczą się w limitach praktycznych HA. Szczegółowy sposób publikacji harmonogramu jest decyzją implementacyjną programisty, zachowując możliwość odczytu bez ręcznego eksportowania JSON.

## 4. Ceny i horyzont

- Zakup pokazywany dokładnie z `sensor.energi_data_service`, sprzedaż dokładnie z `sensor.energi_data_spotpris` — **bez korekt**. Panel pokazuje próg eksportu PV **0,40 DKK/kWh**, propozycję ON/OFF i aktualny stan `switch.sun12k_solar_sell` [PV_EXPORT_POLICY.md](EXECUTION.md).
- Horyzont planu kończy się na ostatniej **rzeczywiście opublikowanej** cenie. Jeżeli jutro nie opublikowano jeszcze cen, pokazać „Ceny jutra niedostępne” i nie rysować fikcyjnego dalszego profilu ceny.
- Po rzeczywistej publikacji jutrzejszych cen (zwykle około 13:00) panel aktualizuje horyzont bez sugerowania, że istnieje prognoza zawsze na 48 h.
- Wszystkie wykresy z lokalną prezentacją Europe/Copenhagen i poprawną obsługą dwukrotnej jesiennej godziny 02:00.

## 5. Zgoda na eksport z magazynu

Propozycja na panelu zawiera **jednocześnie**: czas początku i końca, liczbę kWh AC i maksymalną moc, prognozowany dodatkowy wynik po kosztach, spodziewany SOC, datę wygaśnięcia, `proposal_id` i `plan_id`. Widoczne dwie akcje `Zatwierdź` oraz `Odrzuć`. Naciśnięcie wymaga sprawdzenia, czy to aktualna propozycja; przy przeterminowaniu odmówić zamiast przyjąć pozorną zgodę.

- Po kliknięciu zatwierdzenia aktualizuje się **stan zgody**, nie polecenie eksportu. Realny eksport następuje wyłącznie przez wykonawcę po spełnieniu wszystkich blokad.
- Po zmianie planu zatwierdzenie automatycznie traci ważność; nowa propozycja = nowa decyzja.
- Powiadomienie mobilne może prowadzić do panelu konkretnej propozycji; historyczna usługa `notify.mobile_app_pixel_7dk` jest opcjonalna, nie zakładać jej dostępności na stałe.
- Nie prezentować przycisku „Zatwierdź”, gdy brak możliwości fizycznego, osobno mierzonego i bezpiecznie odwracalnego eksportu z baterii; ewentualny wariant pokazuje się jako **hipotetyczny**.

**Kontrola zamiaru prądowego:** w widoku decyzji wskazać oddzielnie: wybrany limit ogólnego ładowania [A], limit sieci [A], limit rozładowania [A], bieżące napięcie baterii [V], przewidywany przepływ DC [kW] i faktyczny pomiar [kW], aktywny TOU oraz status wykonalności. Limit 5 A nie jest deklaracją, że cały czas płynie dokładnie 5 A; powód ograniczenia (PV/BMS/SOC/TOU) powinien być czytelny z rejestru decyzji. Szczegóły: [CURRENT_CONTROLLER_MODEL.md](EXECUTION.md).

## 6. Stop, blokady i awarie

- Widoczny przełącznik wstrzymania automatyki może zablokować **nowe akcje**; nazwa ma wskazywać, że to nie sprzętowy E-STOP.
- Przy `unavailable`/`unknown` rozróżnić „0 kW” i „brak pomiaru”.
- Brak potwierdzenia fizycznego: wyświetlić `uncertain` albo `recovery_required` i czas ostatniego potwierdzonego pomiaru; nie pokazywać sukcesu.
- Brak niezależnego fail-safe = niemożliwość włączenia trybu automatycznego, ale nadal działa podgląd/planowanie w `dry_run`.
- Panel musi wskazywać, które konkretnie funkcje są dostępne jako `validated_write`, a które tylko w symulacji.

## 7. Rejestr decyzji widoczny od pierwszego uruchomienia

Widok pokazuje **ostatnią decyzję wraz z cenami, prognozami, SOC, planowaną mocą, porównaniem kosztów i uzasadnieniem** oraz historię decyzji z czasem, `plan_id`, przyczyną, stanem i możliwością rozwinięcia danych. Każda bezczynność/odmowa/odrzucenie planu musi mieć wyjaśnienie; brak obliczonego wyniku przedstawiać jako nieznany, nie 0. Wspiera poziom INFO zawsze dostępny i konfigurowalny DEBUG, bez ręcznego eksportu JSON. Logi po restarcie zachowane lokalnie, z ograniczoną retencją. Kontrakt pól i testy: [DECISION_LOGGING.md](VALIDATION.md).

## 8. Weryfikacja UX na danych fikcyjnych

- `UI-01`: brak nowych cen po 13:00 — wykres kończy się dziś, informacja o braku jutra.
- `UI-02`: aktualny SOC nieznany — brak „0%” i brak fałszywej wykonywalnej rekomendacji.
- `UI-03`: plan `dry_run` wskazuje ładowanie 2 kW — status mówi wyraźnie „nie wykonano”, nie „ładowanie aktywne”.
- `UI-04`: zatwierdzenie wygasłej propozycji — bez zgody, wyświetlony powód.
- `UI-05`: nowy `plan_id` — poprzednia zgoda i przyciski propozycji unieważnione.
- `UI-06`: odczyt 60 kWh prognozy, 35 kWh uzysku przy ograniczaniu PV — nie prezentować „25 kWh błędu prognozy” bez weryfikacji curtailment.
- `UI-07`: eksporter PV jest możliwy, a eksport baterii nie — stan i przyciski nie sugerują, że są tą samą funkcją.
- `UI-08`: błąd potwierdzenia komendy — status `uncertain`, nie sukces działania.
- `UI-09`: ujemna cena sprzedaży w HA — widoczny znak i wartość **bez przeliczenia**, eksport PV OFF przy progu 0,40.
- `UI-10`: po jesiennej zmianie czasu — osobne punkty dla obu wystąpień lokalnej 02:00.
- `UI-11`: historia decyzji pokazuje rzeczywistą przesłankę ekonomiczną i alternatywę, także dla `idle`/`blocked`, oraz osobno stan wykonania.

## 9. Warunek odbioru

Użytkownik widzi w HA bez ręcznego JSON: **aktualne pomiary, następne decyzje, cały dostępny horyzont cen i planu, koszt netto, SOC, prognozy, powody oraz blokady i zgody**. UI nie może sugerować faktycznego sterowania, gdy aktywny jest tylko podgląd.
