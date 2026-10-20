# Optymalizacja — model, prognozy, wartość końcowa

**Decyzje użytkownika obowiązują wyłącznie według [REQUIREMENTS.md](REQUIREMENTS.md).** Poniższe części są techniczną dokumentacją implementacyjną; starsze opinie o uprawnieniach do TOU, 0 A i stałym koszcie degradacji nie są normatywne.


---

## OPTIMIZATION MODEL


**Status:** model projektowy, nieuruchomiony i nieskalibrowany. Celem jest deterministyczna minimalizacja kosztów energii; implementacja kodu nastąpi osobno.  
**Powiązania:** [REQUIREMENTS.md](REQUIREMENTS.md), [EXECUTION.md](EXECUTION.md), [HA_CONTRACT.md](HA_CONTRACT.md), [OPEN_ITEMS.md](OPEN_ITEMS.md).

## 1. Czas i zasada planowania

- Optymalizacja krocząca (MPC) z podstawowym krokiem `Δt = 0,25 h`; moc jest średnią w slocie [kW], energia to `P × Δt` [kWh].
- **Horyzont cenowy jest zmienny**, zakończony ostatnim slotem z faktycznie opublikowaną ceną zakupu i sprzedaży. **Format danych potwierdzony:** `raw_today/raw_tomorrow`, `tomorrow_valid`, timestamp `hour` w obydwu encjach, a do planera tylko wspólne zweryfikowane przedziały. Szczegóły: [HA_CONTRACT.md](HA_CONTRACT.md). Nie tworzyć fikcyjnej prognozy cen po ostatnim opublikowanym slocie.
- Zwykle przed publikacją około 13:00 mamy ceny do końca **dzisiejszej** doby; po opublikowaniu cen następnej doby mamy również **jutro 00:00–23:59**, czyli bezpośrednio po 13:00 około 35 h. O obecności jutra decydują kompletne timestampy danych, nie sam zegar: publikacja może się opóźnić.
- Replanowanie co 15 min, po publikacji nowej doby cenowej oraz przy istotnej zmianie wejść; każda decyzja jest powiązana z wersją planu i okresem ważności. Profil prognozy PV przez [HA_CONTRACT.md](HA_CONTRACT.md) (akcja natywna HA), obciążenia przez [OPTIMIZATION.md](OPTIMIZATION.md) (Recorder).
- Rozkład cen uwzględnia rzeczywistą rozdzielczość źródła (godzinowa/15-minutowa); nie interpolować cen ani nie tworzyć brakujących slotów. Obsłużyć 23/25 godzin przy zmianie DST w Europe/Copenhagen.

## 2. Podstawowy bilans przepływów

Przy instalacji PV połączonej z baterią po **DC** planujemy przepływy w każdym slocie w kW, wszystkie nieujemne:

| Symbol | Znaczenie i strona pomiaru |
| --- | --- |
| `S` | Potencjalnie dostępna moc PV po DC (prognoza, nie pomiar produkcji ograniczonej) |
| `s_b, s_h, s_x, s_c` | PV DC → bateria, PV DC → przetwornik AC dla domu, PV DC → AC na eksport, PV celowo niewykorzystane |
| `g_h, g_b` | Sieć AC → dom, sieć AC → ładowanie baterii |
| `b_h, b_x` | Bateria → dom AC, bateria → eksport AC |
| `L` | Przewidywane zużycie domu po AC |
| `E` | Energia w magazynie [kWh], według zweryfikowanego modelu SOC |

Dla każdego slotu zachować:

```text
S = s_b + s_h + s_x + s_c
L = η_pv_ac * s_h + g_h + b_h
Grid_import = g_h + g_b
Grid_export = η_pv_ac * s_x + b_x
E_next = E + Δt*(η_pv_bat*s_b + η_grid_bat*g_b
                  - (b_h + b_x)/η_bat_ac)
```

`η_pv_ac`, `η_pv_bat`, `η_grid_bat`, `η_bat_ac` są osobnymi, zależnymi od toru konwersji współczynnikami (ewentualnie funkcjami mocy). Nie zakładać, że energia do baterii po DC przechodzi przez tor AC. **Nie podwajać energii po DC** w wielkościach PV, AC i baterii.

Ten opis to **logiczny bilans**. Mapowanie faktycznych czujników HA, konwencji znaków, czasu próbki i niezależności źródeł opisano w [HA_CONTRACT.md](HA_CONTRACT.md). W szczególności **zerowy residual jednej migawki nie dowodzi poprawnego modelu**, jeżeli pomiar domu jest szablonem pochodnym. Model obliczeniowy musi zostać dopasowany do rzeczywistych ograniczeń współpracy PV, przetwornika i magazynu: dostępności równoległych przepływów, limitów mocy oraz pomiarów potwierdzonych w HA. Nie przyjmować, że każda kombinacja matematyczna jest wykonalna przez falownik.

## 3. Ograniczenia fizyczne i uprawnienia

- `E_min ≤ E ≤ E_max` wynika z dopuszczalnego SOC (roboczo 20–100% z pierwszeństwem limitów fizycznych/BMS). `E` to energia w baterii, a nie energia dostarczona na AC.
- `η_pv_bat*s_b + η_grid_bat*g_b ≤ P_charge_max` i `b_h+b_x ≤ P_discharge_max`; ostatecznie dostosować definicje limitu do strony, na której są podawane przez encje.
- Uwzględnić dopuszczalny prąd, SOC, temperaturę, limit sieci oraz ograniczenia mocy zależne od trybu i BMS.
- Nie dopuszczać jednoczesnego ładowania i rozładowania baterii ani równoczesnego importu i eksportu przez jeden punkt sieciowy, chyba że faktyczna topologia i model taryfy dowodzą, że to poprawne.
- `b_x = 0` w **wykonywalnym** planie bez osobnej, ważnej zgody na określoną sprzedaż energii z baterii; potencjalny zysk ze sprzedaży można wyliczyć w osobnym scenariuszu ofertowym.
- `s_x` i `s_c` nie są automatycznie dostępne jako dowolne polecenia; możliwość eksportu/ograniczania produkcji wymaga zweryfikowanego kontraktu sterowania przez encje HA.
- Brak wiarygodnego sterowania jednym z przepływów oznacza ograniczenie zbioru wykonalnych działań, a nie zastąpienie go „podobną” encją.

## 4. Cel ekonomiczny

Dla opublikowanych przedziałów minimalizować:

```text
J = Σ_t Δt * (Grid_import[t] * C_buy[t]
             - Grid_export[t] * C_sell[t])
    + Cost_degradation
    + Risk_penalty
    - Terminal_continuation_value(E_end)
```

- `C_buy[t]`: **końcowa zmienna** cena zakupu z opłatami [DKK/kWh].
- `C_sell[t] = sensor.energi_data_spotpris.raw_*.price[t]` [DKK/kWh] **bez przeliczeń**; analogicznie `C_buy[t]` jest wprost z `sensor.energi_data_service`. Co-Pilot **nie oblicza** prowizji, podatków ani taryf. Automatyczny eksport PV jest dozwolony tylko przy `C_sell[t] >= 0,40` zgodnie z [REQUIREMENTS.md](REQUIREMENTS.md).
- `Cost_degradation = 0,40 DKK/kWh × suma rozładowanej energii DC baterii [kWh]`: stała użytkownika z 20.10.2026, naliczana raz przy rozładowaniu. Dotyczy również energii zgromadzonej z PV; ekonomiczną opłacalność ładowania z sieci oceniać z kosztem przyszłego rozładowania. Nie dodawać drugiego kosztu przy ładowaniu. [REQUIREMENTS.md](REQUIREMENTS.md).
- Straty energii są już reprezentowane przez sprawności w bilansie. **Nie doliczać tych samych strat ponownie jako ryczałtowej opłaty.**
- Ceny ujemne, dodatni eksport, rezygnacja z przychodu przez magazynowanie i możliwy curtailment wynikają z powyższego bilansu.
- Rozdzielać koszt fakturowy (import − eksport) od wewnętrznego kosztu degradacji i miary ryzyka.

## 5. Dynamiczny cel SOC i koniec horyzontu

- Docelowy SOC jest **wynikiem** wybranej trajektorii `E[t]`, nie sztywną liczbą. Np. 65% przed nocą może wyjść jako optimum, ale algorytm nie otrzymuje polecenia „zawsze 65%”.
- Nie wolno zerować ekonomicznej wartości magazynu na końcu dostępnych cen: spowodowałoby to pozorne korzyści z opróżnienia baterii przed północą. **Kontynuacyjna wartość energii jest odejmowana od kosztu celu**, nie dodawana jako opłata. Szczegółowa definicja: [OPTIMIZATION.md](OPTIMIZATION.md).
- Poza horyzontem **nie publikujemy cen nieopublikowanych**. Fizyczne potrzeby energetyczne oraz historycznie skalibrowana, wyraźnie niepewna wartość kontynuacyjna mają zapobiegać sztucznemu rozładowaniu przy końcu listy cen; to **nie jest** prognoza ceny po północy ani arbitralna stała rezerwa SOC. Gdy kalibracja jest niewystarczająca, podawać zakres/niepewność i unikać dodatkowych cykli o niewiarygodnym zysku. Szczegóły: [OPTIMIZATION.md](OPTIMIZATION.md).
- Replanowanie po faktycznej publikacji nowych cen aktualizuje całą trajektorię i cel SOC.

**Realizowalność planu w instalacji Deye:** referencyjne równania opisują ekonomicznie optymalny przepływ. **Według doświadczenia użytkownika falownik wykonuje limity prądu precyzyjnie i deterministycznie** — nie modelować hipotetycznej niedokładności poleceń. Jednak dostępne encje określają **maksymalny dopuszczalny prąd**, nie wymuszają jego przepływu przy braku energii lub ograniczeniach SOC/BMS. Wynik planu trzeba więc oddzielić od fizycznej możliwości uzyskania przepływu. Translator nie może deklarować, że zadał np. 2 kW ładowania, jeśli jedynie ustawił limit w A. Docelowe/minimalne SOC nie jest natywnie realizowane samą encją limitu prądu. Przy bieżącej pracy TOU SOC określa głównie warunki rozładowania, a Grid Charge plus SOC może umożliwiać cel sieciowego ładowania. Wymagane **oddzielne warianty matematycznego optimum, current-first przy niezmienianym TOU i opcjonalnego dynamicznego TOU**, z zachowaniem trwałych ostatnich nastaw po utracie HA. Metoda: [EXECUTION.md](EXECUTION.md).

**Translacja kW→A i realizowalna odpowiedź urządzenia:** [EXECUTION.md](EXECUTION.md). Planner nie ma prawa wyceniać planu wymagającego niemożliwych limitów, niedostępnego ładowania sieciowego lub fikcyjnej regulacji dynamicznego minimum SOC jako w pełni wykonalnego. Użytkownik potwierdził działanie nastaw 0 A; podczas implementacji zachować kontrolę dostępności i skutku akcji HA. Optymalizować po jawnie dostępnych nastawach, z uwzględnieniem step i napięcia, a nie po dowolnych kW.

## 6. Wyjście i zasady wykonania

Dla każdego slotu udostępnić: początek/koniec, ceny, prognozę `S` i `L`, osiem przepływów, `Grid_import` i `Grid_export`, SOC przed/po, koszt, oszacowanie ryzyka oraz przesłanki decyzji. Bieżące wyjścia: zamierzony tryb (PV/sieć/mieszany, dom/eksport), moc, docelowy SOC, prognozy, stan dostępności danych i identyfikator planu.

**Harmonogram jest intencją, nie poleceniem.** Oddzielny executor przekłada wykonalne decyzje na zweryfikowane encje HA; bez zgody nie zezwala na celowy eksport z magazynu. Gdy aktualny stan i pomiar odbiegają od planu, trzeba przeliczyć plan lub przejść do bezpiecznej strategii określonej w [EXECUTION.md](EXECUTION.md).

## 7. Prognoza PV i dane ocenzurowane przez sterowanie

W historii odróżniać potencjalną moc PV od rzeczywiście pozyskanej i celowo ograniczonej; pełna bateria i eksport OFF mogą sprawić, że pomiar nie odzwierciedli pogody. **Nie obniżać automatycznie prognozy po porównaniu 60 kWh prognozy z 35 kWh produkcji przy ograniczeniu eksportu.** Do kalibracji używać wersji prognozy zapisanej przed danym okresem i przedziałów bez ograniczenia; podejrzane wyłączyć z bezpośredniej oceny. Szczegółowa reguła i test akceptacyjny: [EXECUTION.md](EXECUTION.md).

**Nieantycypacyjność:** jeśli przyszła pogoda ma kilka możliwych scenariuszy, pierwsza akcja w bieżącym slocie musi być identyczna w każdym z nich, ponieważ ich przyszły wynik nie jest jeszcze znany. Porównania alternatyw wymagają tego samego startu SOC, horyzontu i zasad wyceny końcowego stanu. Szczegóły: [OPTIMIZATION.md](OPTIMIZATION.md).

## 8. Minimalne testy akceptacyjne modelu

1. Tożsamość bilansów PV, domu, sieci i baterii dla każdego slotu; brak energii „znikąd” oraz poprawne kW × h → kWh.
2. Prognoza wysokiej produkcji jutro i małego zużycia nocą może skutkować celem SOC **niższym niż 100%**, bez sztywnego ustawienia 65%.
3. Ładowanie z sieci tylko gdy poprawia oczekiwany wynik po kosztach, sprawności i degradacji.
4. Płatny eksport PV może być korzystniejszy niż bieżące magazynowanie, jeśli później pojawi się tańsza możliwość ładowania.
5. Brak zgody na eksport z baterii: `b_x=0` w planie wykonywalnym, niezależnie od prognozy zysku z eksportu.
6. Publikacja kolejnej doby około 13:00 poszerza plan do końca następnej doby; brak publikacji nie tworzy cen „na 48h”.
7. Ostatni slot znanych cen nie może sztucznie wymuszać wyzerowania magazynu; brakującą przyszłą cenę oznaczyć jako nieznaną.
8. Ujemne ceny, niekompletne sloty cenowe, niedokładność PV, DST, ograniczenie eksportu, zmiana planu i niekompletne sygnały.
9. Przypadek PV 60 kWh / pomiar 35 kWh z ograniczeniem: brak fałszywego błędu prognozy −25 kWh.

Pełne dane liczbowe, warunki testów i oczekiwane wyniki opisano w [VALIDATION.md](VALIDATION.md). Scenariusze z idealizowanymi sprawnościami służą testowaniu bilansów i wyborów, a nie kalibracji realnej instalacji.

## 9. Parametry wymagające danych i kalibracji

- Dokładne mapowanie przepływów i punktów pomiaru HA po DC i AC.
- Zakresy i faktyczne skutki encji sterujących, łącznie z eksportem i trybami magazynu.
- Rzeczywiste sprawności przy różnej mocy, limity mocy/prądów i rzeczywisty zakres SOC.
- Fizyczna degradacja i trwałość nie są estymowane do decyzji wykonawczych: stała **0,40 DKK/kWh rozładowania DC** jest decyzją użytkownika; ewentualny monitoring żywotności stanowi osobną funkcję diagnostyczną. [REQUIREMENTS.md](REQUIREMENTS.md).
- Statystyczny model błędów PV/zużycia i końcowy warunek energetyczny przy nieopublikowanych cenach.
- Weryfikacja wyniku kosztowego na danych historycznych, bez zakładania nieistniejących cen — metodyka [VALIDATION.md](VALIDATION.md). Każda decyzja musi mieć odtwarzalne uzasadnienie w [EXECUTION.md](EXECUTION.md).

Nie wybierać implementacji solvera ani nie wysyłać poleceń sprzętowych, dopóki nie zostaną określone realne ograniczenia i przeprowadzone testy.


## 10. Kontrakt matematyczny rozwiązania i diagnostyki

Model implementacyjny jest optymalizacją **wielookresową z bilansem i ograniczeniami**, a nie heurystyką progów cen/SOC. Rozwiązanie deterministyczne w wersji bazowej; scenariuszowe przy dostępnej, wiarygodnej kalibracji niepewności.

**Warunki konieczne dla każdego slotu:**

- Bilans `S = s_b + s_h + s_x + s_c` i `L = η_pv_ac · s_h + g_h + b_h`, z nieujemnymi strumieniami i jawnie wybranymi torami AC/DC.
- Bilans SOC: `E_next = E + Δt · (η_pv_bat·s_b + η_grid_bat·g_b − (b_h+b_x)/η_bat_ac)`.
- Granice `E_min ≤ E ≤ E_max` we wszystkich chwilach pośrednich i na końcu, moc ładowania ≤ `2,5 kW`, rozładowania ≤ `5 kW` **tylko jako aktualnie zadeklarowane ograniczenia projektu**, a przed realnymi zapisami zgodnie z potwierdzoną stroną DC/AC i ograniczeniami urządzenia.
- Ograniczenie jednoczesnego ładowania i rozładowania: suma wejść do baterii może być dodatnia tylko przy zerowych wyjściach w tym samym slocie. Implementacja może użyć binarnej zmiennej trybu (`0/1`) i ograniczeń typu `charge ≤ P_charge_max·z`, `discharge ≤ P_discharge_max·(1-z)`, o ile taki model odpowiada topologii falownika.
- Brak jednoczesnego importu i eksportu przez jeden punkt przyłącza, jeśli nie udokumentowano ich fizycznej i taryfowej odrębności; analogiczna binarna zmienna kierunku sieci.
- Eksport baterii `b_x` w planie **wykonywalnym** wynosi 0 bez ważnej zgody konkretnego planu. Ewentualny plan z eksportem ma status `proposal_only`, aż przejdzie ponowną walidację zgody i fizycznej zdolności działania.
- Nie wolno optymalizować przepływów niedostępnych w istniejącej instalacji tak, jakby można było je sterować. Planner może pokazać ekonomiczny **idealny** wariant, ale musi oddzielnie liczyć najlepszy **realnie wykonalny** wariant i status brakujących zdolności.
- W modelu scenariuszowym pierwsza akcja w bieżącym okresie musi być taka sama we wszystkich przyszłych scenariuszach, zanim napłyną kolejne obserwacje. Nieantycypacyjność dotyczy również zmian cen i przyszłego SOC.

**Funkcja celu i znak stanu końcowego:** `J = koszt_importu − przychód_eksportu + koszt_degradacji + kara_ryzyka − wartość_kontynuacyjna(E_end)`. Czynniki te nie są wzajemnie zamienne; raportować składniki osobno. Wycena terminalna jest szacunkiem statystycznym wartości opcji, a nie dopisaną prognozą cen po horyzoncie. Jej metodologia: [OPTIMIZATION.md](OPTIMIZATION.md).

**Rozstrzyganie remisów:** jeśli dwa poprawne plany mają koszt ekonomiczny równoważny w granicach błędu obliczeń i niepewności, preferować w kolejności: plan bez dodatkowego cyklu i zbędnego przełączania, plan z mniejszą liczbą poleceń, stabilniejszy względem poprzedniego planu. Nie wolno z tego robić „magicznej stałej” mogącej odwrócić realną, wiarygodną korzyść w DKK.

**Wynik solvera:** status `optimal`, `feasible_not_proven_optimal`, `infeasible`, `timeout` lub `invalid_input`, wyceniony cel, ograniczenia aktywne, naruszenia bilansu, warianty porównawcze i czas obliczeń. Gdy optimum nieudowodnione, **nie** przedstawiać go jako „najtańszy możliwy plan”. Brak rozwiązania lub naruszenie ograniczeń daje `plan_status = blocked` i brak akcji wykonawczej. Dla porównania ekonomicznego alternatywy muszą mieć ten sam stan początkowy, wyceny i warunki końcowe; stosować [EXECUTION.md](EXECUTION.md).

**Weryfikacja niezależna od solvera:** po obliczeniu ponownie przeliczyć z wyjścia bilanse PV, domu, sieci i magazynu oraz koszt, łączną sprawność i ograniczenia uprawnień. Zapisany plan z zerowym numerycznym naruszeniem w solverze, lecz niespójny w zewnętrznej kontroli, **nie jest wykonalny**.


---

## FORECAST POLICY


**Status:** techniczna specyfikacja planowania i kalibracji. Rozróżnia: **opublikowane ceny** (fakty), **prognozy PV/zużycia** (estymaty), **statystyczną niepewność poza horyzontem** (nie jest prognozą opublikowanej ceny) oraz pomiary fizyczne.

## 1. Co wiadomo w chwili decyzji

W danym momencie:
- Znana jest przyszła seria cen **tylko do ostatniego opublikowanego slotu**; zwykle około 13:00 poprzedniego dnia publikują się ceny 00:00–23:59 dnia następnego. Jeśli nowej serii brak, nie przesuwać końca planu. Format cen: [HA_CONTRACT.md](HA_CONTRACT.md). **Rozkład PV:** natywna akcja `forecast_solar.get_forecast` zwraca mapę energii `wh_period`, szczegóły [HA_CONTRACT.md](HA_CONTRACT.md).
- Prognoza PV może obejmować okres dłuższy niż ceny. Trzeba odróżnić **potencjalną** generację PV od historycznego uzysku sztucznie ograniczonego przez pełną baterię/eksport OFF.
- Prognoza domu powstaje z historii `sensor.home_energy_consumption` w Recorder, dostępnej do chwili decyzji, z odporną medianą podobnych pór/dni i jawnymi trybami braku historii. Algorytm i testy: [OPTIMIZATION.md](OPTIMIZATION.md). Błąd zależy od pory dnia/tygodnia i sezonu, gdy dane na to pozwalają.
- Warunki techniczne ograniczają plan niezależnie od prognoz.

**Nie publikować fikcyjnych cen przyszłych slotów.** Wyświetlany harmonogram ekonomiczny kończy się na ostatniej opublikowanej cenie.

## 2. Model niepewności bez fałszywej precyzji

Każda prognoza ma `issued_at` i `valid_at` oraz wersję. Walidacja używa **oryginalnej** migawki sprzed obserwacji. Model liczy historyczne błędy dla porównywalnego wyprzedzenia, osobno dla PV i obciążenia.

- Klasy jakości: `calibrated` (liczba i reprezentatywność próbek wystarczająca), `limited` (dane częściowe), `insufficient_history`, `stale`.
- Jeśli dane pozwalają, stosować scenariusze `low` / `central` / `high` dostępnego PV i zapotrzebowania domu oraz rozkład/empiryczną częstość scenariuszy, walidowaną na odłożonych okresach. Nie zakładać z góry „90% skuteczności”.
- Gdy historii migawek brak, użyć tylko jawnie oznaczonych ostrożnych scenariuszy **do symulacji**, bez nazywania ich statystycznie skalibrowanymi. Model pracuje jako `dry_run`, a niemożliwy do uzasadnienia procent pewności pozostaje nieznany.
- Nie uczyć jakości prognozy PV na okresach `curtailed_confirmed` lub `curtailment_unknown`. Pochmurne okresy bez curtailment nie wystarczają do deklaracji jakości dla słonecznego dnia.
- Zależności między prognozowanym nasłonecznieniem i obciążeniem należy zachować w scenariuszach, jeśli wynikają z danych; nie łączyć dowolnie ekstremów bez jawnego celu stress-testu.

## 3. Jak porównywać plany przy niepewności

**Zasadniczy plan:** minimalizacja oczekiwanego kosztu netto **w opublikowanym horyzoncie** z uwzględnieniem strat, zużycia baterii i wartości stanu końcowego.

- Wszystkie alternatywy porównywać przy tym samym `SOC_now`, tym samym znanym horyzoncie cen, sprawnościach, ograniczeniach i wspólnej, jawnej polityce końcowej.
- Dla przyszłych ścieżek PV/zużycia dobierać scenariusze oparte o uprzednią historię. Przed nową obserwacją wszystkie scenariusze otrzymują **identyczną pierwszą akcję**, nie wolno pozwalać plannerowi „wiedzieć”, która pogoda się wydarzy (zasada nieantycypacyjności).
- Jeżeli wiarygodne prawdopodobieństwa nie są znane, raportować przedział możliwego wyniku i odporność decyzji, bez podawania jednej dokładnej „szansy sukcesu”. Domyślnie nie wykonywać cykli o nieudowodnionym dodatnim wyniku po stratach i degradacji.
- Zasada użytkownika: minimalizacja kosztu; **nie stosować stałego SOC 65%, 80% czy 100% ani stałego bufora „na blackout”.**

## 4. Problem końca znanych cen — rozwiązanie techniczne

Jeśli koszt funkcji celu liczymy tylko do północy i przyjmujemy, że energia pozostała w baterii **nie ma wartości**, optymalizator może wyprzedać/zużyć ją przed końcem dnia bez ekonomicznego uzasadnienia. Jednocześnie **nie wolno** udawać, że znamy ceny po północy.

Proponowany sposób:
1. **Kontynuacyjna wartość energii**, oznaczona `V_terminal(E, t, season, forecast)`, opisuje **wartość opcji** posiadania energii po ostatnim znanym slocie, nie cenę prądu rzekomo opublikowaną na dalsze godziny.
2. Funkcję szacować na **dawnych** okresach poza zbiorami testowymi, z analizy rozkładu rzeczywistych cen historycznych, wcześniejszych prognoz zużycia/PV i obciążenia. Wyraźnie pokazywać, że jest to statystyczna wycena, **nie** rynkowa prognoza cen na konkretną godzinę.
3. Do funkcji celu dodać `-V_terminal(E_end)` (wartość końcowej energii *zmniejsza* wynik kosztowy). Nie dopisywać nieopublikowanych slotów do `buy_price_slots` lub `sell_price_slots`; horyzont rynkowy pozostaje bez zmian.
4. Parametry funkcji dobierać na podstawie błędu decyzji/wyniku `walk-forward`; sprawdzić, czy maksymalizuje przewidywany wynik wobec działania standardowego, nie tylko SOC.
5. Gdy dane kalibracyjne są niewystarczające, oznaczyć `terminal_value_quality = insufficient_history` i podać **zakres wrażliwości** zamiast jednej „dokładnej” kwoty. Nie traktować konserwatywnego zapasu jako wymaganego technicznie; rezerwa zależy od scenariusza, nie stałej liczby kWh.
6. Jeśli nie da się rzetelnie określić znaczenia porównania, decyzja o dużym, nieodwracalnym eksporcie baterii lub dodatkowym cyklu zostaje zablokowana; nadal wolno symulować i prezentować plan wraz z niepewnością.

**Korekta formalna:** `J = cost_known_horizon + cost_degradation + risk_penalty - V_terminal(E_end)`. Nie dodawać dodatnio „terminal_energy_value” do kosztu bez znaku i definicji.

## 5. Rozruch modelu i ewolucja

- Na starcie rejestrować prognozy, odczyty, ceny i wybrane decyzje wraz z `decision_id`. Pozyskiwać historię z HA, lecz nie zakładać, że stare rekordy produkcji zawierają dawne prognozy.
- Pierwszy etap: prognoza punktowa i analiza wrażliwości, kompletne rejestry decyzji; brak fałszywej statystyki i fałszywych zysków.
- Po wystarczającej liczbie poprawnych, reprezentatywnych migawek: osobno kalibrować błędy produkcji PV i zużycia domu, następnie model kontynuacji.
- Okresy ograniczenia produkcji rejestrować jako ocenzurowane, a nie niską produkcję; status `uncurtailed` wymaga wiarygodnego potwierdzenia.
- Zmiana modelu/parametrów ma `model_version`, lokalny zapis uzasadnienia i ponowną weryfikację na danych odłożonych do testów. Nie uczyć modelu na przyszłym wyniku testowanego dnia.

## 6. Testy, które muszą przejść

- `UNC-01`: brak cen jutra, mimo że jest 13:00 → brak fikcyjnych cen lub wydłużenia planu.
- `UNC-02`: aktualna prognoza z datą pobrania po testowanym okresie → wyłączona z kalibracji i backtestu.
- `UNC-03`: PV ograniczone przez eksport OFF + pełną baterię → nie zmniejszać jakości prognozy o całą różnicę prognoza minus pomiar.
- `UNC-04`: wysoka niepewność przy małej historii → `insufficient_history`, brak percentyla z sufitu.
- `UNC-05`: dwa scenariusze pogody mają różny wynik, ale wspólną pierwszą akcję przed nową obserwacją.
- `UNC-06`: `E_end` pozostaje wartościowe przy obliczeniu końcowego kosztu; optimizer nie opróżnia baterii wyłącznie z powodu końca pliku z cenami.
- `UNC-07`: `V_terminal` nie generuje żadnej fikcyjnej ceny w serii eksportowanej do HA.
- `UNC-08`: przy nieznanej wartości końcowej nie raportować dokładnego ekonomicznego optimum, lecz brak pewności albo przedział; nie wykonywać nieodwracalnego dodatkowego cyklu o niewiarygodnej korzyści.
- `UNC-09`: dwie alternatywy różniące się końcowym SOC nie są porównywane jak identyczne energetycznie.
- `UNC-10`: po publikacji nowych cen planner aktualizuje horyzont, a poprzednie powody zostają w rejestrze decyzji.

**Odbiór:** w [EXECUTION.md](EXECUTION.md) dla każdej decyzji podane: znane ceny, wersja prognozy, scenariusze niepewności, końcowa wartość energii (lub brak wiarygodnego oszacowania) oraz porównanie z alternatywą. W [VALIDATION.md](VALIDATION.md) sprawdzić wpływ funkcji końcowej na zysk i brak wiedzy o przyszłości.


---

## LOAD FORECAST CONTRACT


**Status:** kontrakt algorytmu wejściowego do planera. Sposób budowy prognozy rozstrzygnięty; **jakość danych historycznych w Recorder konkretnej instalacji jest do sprawdzenia przez Codexa**. Bez dodatkowego serwera, abonamentu prognozowego, odczytu Modbus ani osieroconych encji Battery Controller.

**Źródła:** [Home Assistant — History](https://www.home-assistant.io/integrations/history), [Recorder](https://www.home-assistant.io/integrations/recorder). Dokumenty projektu: [HA_CONTRACT.md](HA_CONTRACT.md), [OPTIMIZATION.md](OPTIMIZATION.md), [OPTIMIZATION.md](OPTIMIZATION.md), [VALIDATION.md](VALIDATION.md).

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

### Ostrzeżenie o brakach ukrytych przez `float(0)`

Walidować stan trzech źródłowych encji **w czasie każdej historycznej próbki**, a nie tylko przy uruchomieniu lub planowaniu. `sensor.home_energy_consumption` może mieć poprawnie wyglądającą liczbę nawet gdy jeden pomiar był niedostępny. Jeśli nie da się odtworzyć statusu składników dla potrzebnego okna Recorder, nie nazywać profilu „zweryfikowanym”; diagnostyka pokazuje `historical_quality_unverifiable`, a obliczenie może pozostać wyłącznie dry-run. Nie imputować braku jako faktycznego zerowego popytu.

**Regresja LOAD-17:** wczoraj `battery_output_power` był `unavailable`, ale `home_energy_consumption` ma historyczny stan liczbowy z domyślnym zerem → wyklucz wadliwy przedział z uczenia.

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
