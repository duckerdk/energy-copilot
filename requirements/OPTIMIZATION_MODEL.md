# Model optymalizacji Energy Co-Pilot — specyfikacja dla programisty

**Status:** model projektowy, nieuruchomiony i nieskalibrowany. Celem jest deterministyczna minimalizacja kosztów energii; implementacja kodu nastąpi osobno.  
**Powiązania:** [wymagania](GOALS_AND_REQUIREMENTS.md), [architektura](ARCHITECTURE.md), [kontrakt encji](ENTITY_CONTRACT.md), [blokery](OPEN_ITEMS.md).

## 1. Czas i zasada planowania

- Optymalizacja krocząca (MPC) z podstawowym krokiem `Δt = 0,25 h`; moc jest średnią w slocie [kW], energia to `P × Δt` [kWh].
- **Horyzont cenowy jest zmienny**, zakończony ostatnim slotem z faktycznie opublikowaną ceną zakupu i sprzedaży. **Format danych potwierdzony:** `raw_today/raw_tomorrow`, `tomorrow_valid`, timestamp `hour` w obydwu encjach, a do planera tylko wspólne zweryfikowane przedziały. Szczegóły: [HA_PRICE_SERIES_CONTRACT.md](HA_PRICE_SERIES_CONTRACT.md). Nie tworzyć fikcyjnej prognozy cen po ostatnim opublikowanym slocie.
- Zwykle przed publikacją około 13:00 mamy ceny do końca **dzisiejszej** doby; po opublikowaniu cen następnej doby mamy również **jutro 00:00–23:59**, czyli bezpośrednio po 13:00 około 35 h. O obecności jutra decydują kompletne timestampy danych, nie sam zegar: publikacja może się opóźnić.
- Replanowanie co 15 min, po publikacji nowej doby cenowej oraz przy istotnej zmianie wejść; każda decyzja jest powiązana z wersją planu i okresem ważności. Profil prognozy PV przez [PV_FORECAST_CONTRACT.md](PV_FORECAST_CONTRACT.md) (akcja natywna HA), obciążenia przez [LOAD_FORECAST_CONTRACT.md](LOAD_FORECAST_CONTRACT.md) (Recorder).
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

Ten opis to **logiczny bilans**. Mapowanie faktycznych czujników HA, konwencji znaków, czasu próbki i niezależności źródeł opisano w [MEASUREMENT_CONTRACT.md](MEASUREMENT_CONTRACT.md). W szczególności **zerowy residual jednej migawki nie dowodzi poprawnego modelu**, jeżeli pomiar domu jest szablonem pochodnym. Model obliczeniowy musi zostać dopasowany do rzeczywistych ograniczeń współpracy PV, przetwornika i magazynu: dostępności równoległych przepływów, limitów mocy oraz pomiarów potwierdzonych w HA. Nie przyjmować, że każda kombinacja matematyczna jest wykonalna przez falownik.

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
- `C_sell[t] = sensor.energi_data_spotpris.raw_*.price[t]` [DKK/kWh] **bez przeliczeń**; analogicznie `C_buy[t]` jest wprost z `sensor.energi_data_service`. Co-Pilot **nie oblicza** prowizji, podatków ani taryf. Automatyczny eksport PV jest dozwolony tylko przy `C_sell[t] >= 0,40` zgodnie z [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md).
- `Cost_degradation = 0,40 DKK/kWh × suma rozładowanej energii DC baterii [kWh]`: stała użytkownika z 20.10.2026, naliczana raz przy rozładowaniu. Dotyczy również energii zgromadzonej z PV; ekonomiczną opłacalność ładowania z sieci oceniać z kosztem przyszłego rozładowania. Nie dodawać drugiego kosztu przy ładowaniu. [CALIBRATION_POLICY.md](CALIBRATION_POLICY.md).
- Straty energii są już reprezentowane przez sprawności w bilansie. **Nie doliczać tych samych strat ponownie jako ryczałtowej opłaty.**
- Ceny ujemne, dodatni eksport, rezygnacja z przychodu przez magazynowanie i możliwy curtailment wynikają z powyższego bilansu.
- Rozdzielać koszt fakturowy (import − eksport) od wewnętrznego kosztu degradacji i miary ryzyka.

## 5. Dynamiczny cel SOC i koniec horyzontu

- Docelowy SOC jest **wynikiem** wybranej trajektorii `E[t]`, nie sztywną liczbą. Np. 65% przed nocą może wyjść jako optimum, ale algorytm nie otrzymuje polecenia „zawsze 65%”.
- Nie wolno zerować ekonomicznej wartości magazynu na końcu dostępnych cen: spowodowałoby to pozorne korzyści z opróżnienia baterii przed północą. **Kontynuacyjna wartość energii jest odejmowana od kosztu celu**, nie dodawana jako opłata. Szczegółowa definicja: [FORECAST_POLICY.md](FORECAST_POLICY.md).
- Poza horyzontem **nie publikujemy cen nieopublikowanych**. Fizyczne potrzeby energetyczne oraz historycznie skalibrowana, wyraźnie niepewna wartość kontynuacyjna mają zapobiegać sztucznemu rozładowaniu przy końcu listy cen; to **nie jest** prognoza ceny po północy ani arbitralna stała rezerwa SOC. Gdy kalibracja jest niewystarczająca, podawać zakres/niepewność i unikać dodatkowych cykli o niewiarygodnym zysku. Szczegóły: [FORECAST_POLICY.md](FORECAST_POLICY.md).
- Replanowanie po faktycznej publikacji nowych cen aktualizuje całą trajektorię i cel SOC.

**Realizowalność planu w instalacji Deye:** referencyjne równania opisują ekonomicznie optymalny przepływ. **Według doświadczenia użytkownika falownik wykonuje limity prądu precyzyjnie i deterministycznie** — nie modelować hipotetycznej niedokładności poleceń. Jednak dostępne encje określają **maksymalny dopuszczalny prąd**, nie wymuszają jego przepływu przy braku energii lub ograniczeniach SOC/BMS. Wynik planu trzeba więc oddzielić od fizycznej możliwości uzyskania przepływu. Translator nie może deklarować, że zadał np. 2 kW ładowania, jeśli jedynie ustawił limit w A. Docelowe/minimalne SOC nie jest natywnie realizowane samą encją limitu prądu. Przy bieżącej pracy TOU SOC określa głównie warunki rozładowania, a Grid Charge plus SOC może umożliwiać cel sieciowego ładowania. Wymagane **oddzielne warianty matematycznego optimum, current-first przy niezmienianym TOU i opcjonalnego dynamicznego TOU**, z zachowaniem trwałych ostatnich nastaw po utracie HA. Metoda: [CONTROL_STRATEGY.md](CONTROL_STRATEGY.md).

**Translacja kW→A i realizowalna odpowiedź urządzenia:** [CURRENT_CONTROLLER_MODEL.md](CURRENT_CONTROLLER_MODEL.md). Planner nie ma prawa wyceniać planu wymagającego niemożliwych limitów, nieznanej nastawy 0 A, niedostępnego ładowania sieciowego lub fikcyjnej regulacji dynamicznego minimum SOC jako w pełni wykonalnego. Optymalizować po jawnie dostępnych nastawach, z uwzględnieniem step i napięcia, a nie po dowolnych kW.

## 6. Wyjście i zasady wykonania

Dla każdego slotu udostępnić: początek/koniec, ceny, prognozę `S` i `L`, osiem przepływów, `Grid_import` i `Grid_export`, SOC przed/po, koszt, oszacowanie ryzyka oraz przesłanki decyzji. Bieżące wyjścia: zamierzony tryb (PV/sieć/mieszany, dom/eksport), moc, docelowy SOC, prognozy, stan dostępności danych i identyfikator planu.

**Harmonogram jest intencją, nie poleceniem.** Oddzielny executor przekłada wykonalne decyzje na zweryfikowane encje HA; bez zgody nie zezwala na celowy eksport z magazynu. Gdy aktualny stan i pomiar odbiegają od planu, trzeba przeliczyć plan lub przejść do bezpiecznej strategii określonej w [ARCHITECTURE.md](ARCHITECTURE.md).

## 7. Prognoza PV i dane ocenzurowane przez sterowanie

W historii odróżniać potencjalną moc PV od rzeczywiście pozyskanej i celowo ograniczonej; pełna bateria i eksport OFF mogą sprawić, że pomiar nie odzwierciedli pogody. **Nie obniżać automatycznie prognozy po porównaniu 60 kWh prognozy z 35 kWh produkcji przy ograniczeniu eksportu.** Do kalibracji używać wersji prognozy zapisanej przed danym okresem i przedziałów bez ograniczenia; podejrzane wyłączyć z bezpośredniej oceny. Szczegółowa reguła i test akceptacyjny: [ARCHITECTURE.md](ARCHITECTURE.md#wiarygodność-prognoz-pv-przy-ograniczeniu-produkcji).

**Nieantycypacyjność:** jeśli przyszła pogoda ma kilka możliwych scenariuszy, pierwsza akcja w bieżącym slocie musi być identyczna w każdym z nich, ponieważ ich przyszły wynik nie jest jeszcze znany. Porównania alternatyw wymagają tego samego startu SOC, horyzontu i zasad wyceny końcowego stanu. Szczegóły: [FORECAST_POLICY.md](FORECAST_POLICY.md).

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

Pełne dane liczbowe, warunki testów i oczekiwane wyniki opisano w [TEST_SCENARIOS.md](TEST_SCENARIOS.md). Scenariusze z idealizowanymi sprawnościami służą testowaniu bilansów i wyborów, a nie kalibracji realnej instalacji.

## 9. Parametry wymagające danych i kalibracji

- Dokładne mapowanie przepływów i punktów pomiaru HA po DC i AC.
- Zakresy i faktyczne skutki encji sterujących, łącznie z eksportem i trybami magazynu.
- Rzeczywiste sprawności przy różnej mocy, limity mocy/prądów i rzeczywisty zakres SOC.
- Fizyczna degradacja i trwałość nie są estymowane do decyzji wykonawczych: stała **0,40 DKK/kWh rozładowania DC** jest decyzją użytkownika; ewentualny monitoring żywotności stanowi osobną funkcję diagnostyczną. [CALIBRATION_POLICY.md](CALIBRATION_POLICY.md).
- Statystyczny model błędów PV/zużycia i końcowy warunek energetyczny przy nieopublikowanych cenach.
- Weryfikacja wyniku kosztowego na danych historycznych, bez zakładania nieistniejących cen — metodyka [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md). Każda decyzja musi mieć odtwarzalne uzasadnienie w [DECISION_LOGGING.md](DECISION_LOGGING.md).

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

**Funkcja celu i znak stanu końcowego:** `J = koszt_importu − przychód_eksportu + koszt_degradacji + kara_ryzyka − wartość_kontynuacyjna(E_end)`. Czynniki te nie są wzajemnie zamienne; raportować składniki osobno. Wycena terminalna jest szacunkiem statystycznym wartości opcji, a nie dopisaną prognozą cen po horyzoncie. Jej metodologia: [FORECAST_POLICY.md](FORECAST_POLICY.md).

**Rozstrzyganie remisów:** jeśli dwa poprawne plany mają koszt ekonomiczny równoważny w granicach błędu obliczeń i niepewności, preferować w kolejności: plan bez dodatkowego cyklu i zbędnego przełączania, plan z mniejszą liczbą poleceń, stabilniejszy względem poprzedniego planu. Nie wolno z tego robić „magicznej stałej” mogącej odwrócić realną, wiarygodną korzyść w DKK.

**Wynik solvera:** status `optimal`, `feasible_not_proven_optimal`, `infeasible`, `timeout` lub `invalid_input`, wyceniony cel, ograniczenia aktywne, naruszenia bilansu, warianty porównawcze i czas obliczeń. Gdy optimum nieudowodnione, **nie** przedstawiać go jako „najtańszy możliwy plan”. Brak rozwiązania lub naruszenie ograniczeń daje `plan_status = blocked` i brak akcji wykonawczej. Dla porównania ekonomicznego alternatywy muszą mieć ten sam stan początkowy, wyceny i warunki końcowe; stosować [DECISION_LOGGING.md](DECISION_LOGGING.md).

**Weryfikacja niezależna od solvera:** po obliczeniu ponownie przeliczyć z wyjścia bilanse PV, domu, sieci i magazynu oraz koszt, łączną sprawność i ograniczenia uprawnień. Zapisany plan z zerowym numerycznym naruszeniem w solverze, lecz niespójny w zewnętrznej kontroli, **nie jest wykonalny**.
