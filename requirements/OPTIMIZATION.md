# Optymalizacja kosztu energii

**Źródło celów i uprawnień: [REQUIREMENTS.md](REQUIREMENTS.md).** Dane: [HA_CONTRACT.md](HA_CONTRACT.md). Ten plik określa matematykę, nie wprowadza nowych decyzji użytkownika.

## Cel
Na 15-minutowych przedziałach UTC do końca **wspólnych opublikowanych cen** minimalizować:
```text
J = SUM_t( grid_import_kWh[t] * buy_DKK_kWh[t]
         -grid_export_kWh[t] * sell_DKK_kWh[t] )
    + 0.40 * SUM_t( battery_discharge_DC_kWh[t] )
    + risk_cost_DKK
    - terminal_battery_value_DKK(E_end)
```
Stawka degradacji to przyjęty stały **0,40 DKK/kWh rozładowanej energii DC**, tylko raz; ładowanie z sieci należy ocenić z uwzględnieniem **późniejszego** rozładowania i kosztu, mimo że powstaje później. Straty przetworników są już w przepływach — nie doliczać ich ponownie jako opłat. Raportować koszt faktury, degradację, łączny koszt i ryzyko oddzielnie. Autokonsumpcja **nie** ma niezależnego priorytetu. Nie dokonywać fikcyjnego rozładowania na koniec cen, jakby pozostały SOC był bezwartościowy.

## Model przepływów
Jednoznacznie rozdzielać:
- `s_b` PV DC→bateria; `s_h` PV DC→przetwornik AC/dom; `s_x` PV DC→AC/eksport; `s_c` niewykorzystana PV.
- `g_b` sieć AC→bateria; `b_h` bateria→dom AC; `b_x` bateria→eksport AC.
- Import/eksport sieci na punkcie przyłącza są rozłączne przy jednym czujniku netto. Nie planować jednoczesnego ładowania i rozładowania baterii; nie liczyć PV→bateria dwa razy.

Przykładowe równanie stanu (przy jawnej definicji stron pomiaru):
```text
E_next = E + dt * (eta_pv_bat*s_b + eta_grid_bat*g_b
                    - (b_h+b_x)/eta_bat_ac)
```
Sprawności `eta_pv_bat`, `eta_grid_bat`, `eta_bat_ac`, `eta_pv_ac` rozdzielać i kalibrować; nie mieszać W DC z W AC bez konwersji. Początkowe 0,9487/0,97 to założenia, nie pomiary. Ograniczyć SOC **20–100%**, dopuszczalne tempo **ładowania** zgodnie z REQUIREMENTS i pozostałe granice sprzętowe BMS/temperatury/napięcia; parametr nastawy maksymalnego prądu rozładowania nie jest wejściem ani ograniczeniem modelu Energy Co-Pilot.

## Wykonalność przez Deye
Planner rozważa harmonogram **przesuwania lub rozciągania ładowania**, Grid Charge, zezwolenie PV Solar Sell, jak i autonomiczne zmiany **sześciu TOU**. Obliczony prąd potrzebny do bilansu energii jest wartością prognostyczną, a nie powodem ani poleceniem przestawienia prądu ładowania falownika. Każda zmiana nastawy wymaga osobnej, wyraźnej intencji przesunięcia lub rozciągnięcia ładowania. Nie utrzymuj dawnego obowiązkowego „current-first bez zmieniania TOU”. Sam maksymalny prąd nie wymusza zadanej mocy ani osiągnięcia SOC; aktualne napięcie × A daje górne oszacowanie mocy DC. Warunki ładowania z sieci zależą jednocześnie od ogólnego limitu, limitu sieci, globalnego Grid Charge i aktywnego okresu TOU.

Porównywać:
1. Realny `baseline_deye` bez zmian Co-Pilot;
2. Wykonywalną politykę przy pozostawieniu TOU bez zmian;
3. Wykonywalną politykę z dynamicznym TOU i Grid Charge;
4. Idealne optimum teoretyczne **tylko referencyjnie**, nie jako deklarację osiągalnych oszczędności.

Sześciu okresów TOU nie wolno traktować jak 96 odrębnych nastaw co 15 minut. Jeżeli plan wymaga brakującej funkcji lub nierealnego przepływu, oznacz `not_executable` i nie wyceniaj go jako możliwego planu do wykonania. Bez zgody na eksport baterii ustaw `b_x=0` w planie wykonawczym.

## Prognozy i horyzont
Ceny tylko opublikowane; ich brak poza horyzontem to nie zero. Wartość końcowej energii w baterii `V_terminal(E_end)` może być estymowana z historii ze wskazaniem niepewności; nie dopisuje przyszłych cen. Replan po nowych cenach, produkcji, SOC i zapotrzebowaniu. Prognozy PV i zużycia muszą być wersjonowane z datą wydania; walk-forward używa wyłącznie danych dostępnych w tamtym czasie. Ograniczoną produkcję PV klasyfikować jako `curtailed_confirmed` / `curtailment_unknown`; sam spadek pomiaru przy pełnej baterii i wyłączonym eksporcie nie jest błędem prognozy pogody.

Przy tej samej energii i równoważnym koszcie w horyzoncie wybierać **łagodniejsze ładowanie**: rozłożyć je na dostępne kwadranse i preferować rozłożenie kampanii na dostępne kwadranse bez nieuzasadnionych zmian limitów prądowych; **50 A to tylko limit**. Dostępne kwadranse musi wyznaczyć planer według opublikowanych cen, rzeczywistego czasu, wymaganego przyrostu SOC i ograniczeń; harmonogram 15-minutowy nie uprawnia do więcej niż sześciu okien TOU. Nie poświęcać istotnej korzyści ekonomicznej dla mniejszego prądu ani nie zakładać, że prąd zadany jest prądem rzeczywistym. Przy niepewnej marginalnej korzyści po degradacji i stratach wybierać brak **dodatkowego** cyklu. W przypadku zbliżonych kosztów preferować mniejszą liczbę zapisów i stabilniejsze nastawy, ale nie odwracać tym ekonomicznie istotnej przewagi. Zewnętrzna walidacja planu po solverze ponownie liczy bilanse, ograniczenia, koszt i zgody, niezależnie od rozwiązania optymalizatora.

## Wspólna strategia scenariuszowa 2.0.0

**Nowa polityka [REQUIREMENTS.md](REQUIREMENTS.md) zastępuje osobny algorytm
`no_idle_prepeak_window` i samodzielne dopisywanie prądu ładowania po optymalizacji.**

1. Bazowy solver oblicza wykonalny nominalny plan 15-minutowy, minimalizując prawdziwe koszty opublikowanych cen i degradacji. Następnie buduje alternatywy: zostawienie miejsca na możliwą większą PV, odroczenie ładowania do bliższej godziny szczytu oraz dodatkową rezerwę energetyczną na wyższe rzeczywiste zużycie. Każda alternatywa ponownie przechodzi **`simulate_candidate`**; nie należy zmieniać samych słupków wykresu ani dodawać fikcyjnych Wh do prognozy.
2. Scenariusz PV: prognozowane `PV×1,45`, plus dostępny zaobserwowany percentyl niedoszacowania (maksymalnie 0,45 kWh/kwadrans), i zużycie mniejsze do `0,5×MAE/4` kWh/kwadrans. To stress test, a nie prognozowany rzeczywisty nadmiar. Przyszła niewykorzystana możliwa energia PV jest wyceniana po odjęciu przychodu alternatywnego eksportu, strat i degradacji. Waga ostrożności = **0,55** (niekalibrowana).
3. Scenariusz zużycia: historyczne niedoszacowanie z odseparowanego holdoutu oraz P75 w godzinach 16–22 wyceniają niedobór baterii podczas drogiego szczytu. Waga ostrożności = **0,65** (niekalibrowana); dodatkowy cel nie może przekroczyć **15 pp SOC**. Wariant z nagrodą za energię na **początku szczytu** nadal udostępnia pełną energię podczas szczytu — nie ustawia wysokiej blokującej podłogi TOU.
4. Odroczenie zakupów nie ma stałej godziny. Kandydaci obejmują różne okna liczone wstecz od rzeczywistego szczytu cenowego; solver sam uwzględnia ograniczenie 50 A i wybiera wariant tylko przy korzyści w wyniku skorygowanym o ryzyko. Nie wymuszać godzin 12:00 ani 14:00. Replan co 15 minut korzysta z aktualnego SOC.
5. **Minimalna korzyść dla całej kampanii ładowania**: porównanie niezależnego planu z wykluczeniem wszystkich kwadransów tej operacji, a nie tylko pierwszego kwadransa. Nowa operacja wymaga minimum **0,10 DKK**, trwająca **0,05 DKK** w scenariuszowym wyniku po kosztach. **Warunek 2.0.3:** wynik zakazu kwadransów jest najpierw sprawdzany pod kątem relokacji zakupu w pozostałych kwadransach horyzontu (przyrost zakupu AC ponad 0,001 kWh poza zakazanym oknem). Jeśli występuje relokacja, pomijamy test materialności i zachowujemy tańsze wykonalne położenie istniejącej kampanii. Filtr wolno zastosować tylko, gdy alternatywa faktycznie usuwa zakup, nie przenosi go na droższą godzinę. Diagnostyka `robust_policy.charge_relocations_preserved` podaje zachowane kampanie i ilość relokowanej energii; `minor_charges_rejected` dotyczy jedynie odrzuconych kampanii. Wynik operacji zapisany w diagnostyce nie jest potwierdzonym zyskiem; plan i energia fizyczna nadal mają rzeczywiste jednostki i dokładność.
6. Wartość końcowego SOC przy braku opublikowanych następnych cen używa **zdyskontowanej o 35%**, dodatkowo ograniczonej znanym kosztem zakupu wyceny energii do obsłużenia rzeczywistego prognozowanego obciążenia przed następną PV. Nie pozwala kupić 100% baterii tylko dla domniemanej przyszłej sprzedaży lub nieznanej taryfy. Nie fikcjonować kwadransów poza dostępnością cen.
7. Scenariusze nie są wyuczoną dystrybucją ani formalnym wieloscenariuszowym optimum globalnym. To ograniczony zbiór porównanych pełnohoryzontowych wariantów z jawnie nieskalibrowanymi wagami; osobna walidacja walk-forward i na żywym Deye jest obowiązkowa przed twierdzeniem o oszczędnościach.

**Kontrakt wykonawczy:** ani wyniki scenariuszy, ani kolumna szacowanego prądu nie upoważniają do samowolnego przestawiania prądów. Jedynymi powodami zmian są świadome przesunięcie lub rozciągnięcie ładowania. TOU ma sześć stałych przedziałów; wykonawca aktualizuje bieżący slot co kwadrans. `tou_feasibility` to tylko statyczna projekcja komend, **nie** potwierdzenie fizycznej wykonalności i nie status `executable=true`.

### Korekta 2.0.1 — bieżący SOC i koszt ryzyka
- Każdy nowy plan HA zaczyna się od **zaobserwowanego SOC**, a pierwszy przedział może obejmować tylko pozostające sekundy aktywnego kwadransa. Kolejne przedziały są pełnymi kwadransami. Model ogranicza kWh ładowania proporcjonalnie do rzeczywistej długości pierwszego przedziału, bez wytwarzania fikcyjnego czasu ładowania.
- Bieżące poprawne pomiary W domu i PV korygują oszacowanie w pierwszych trzech przedziałach wagami 0,65 / 0,30 / 0,15; odchylenie ograniczone do ±3 kW. Dalszy horyzont korzysta z prognoz 45-dniowej i Forecast.Solar. Każdy plan jest nadal przeliczany dla całej dostępnej krzywej cen.
- Funkcja straty za niedoszacowanie zużycia **nie może zależeć bezpośrednio od najmniejszego nominalnego SOC w szczycie**. Dodatkowy scenariusz zużycia pobiera energię powyżej minimum 20%; gdy jej zabraknie, kosztuje import przy cenie konkretnego kwadransa, a brakująca energia końcowa jest wyceniana raz. Wariant importu i przechowania energii musi przejść porównanie z wariantem rozładowania **w ramach rzeczywistej przyszłej prognozy zużycia**.
- Jednoznaczna decyzja `battery_discharge` oznacza wykonawczo TOU SOC **20%** w aktywnym kwadransie; `grid_import` można wybrać tylko w ramach rzeczywiście korzystnego wariantu pełnohoryzontowego. Zmiana decyzji po wzroście SOC działa w tym samym kwadransie. Poziom SOC planowany na koniec kwadransa nie jest progiem ograniczającym rozładowanie.

## Wynik
Dla każdego slotu: UTC, ceny i wersja danych, prognoza PV i zużycia, SOC początek/koniec, przepływy PV/dom/bateria/sieć, zamierzony Grid Charge/TOU/Solar Sell oraz **wyłącznie celowe czasowe ograniczenia prądu ładowania** (przesunięcie/rozciągnięcie), koszty wariantów, degradacja, niepewność i status wykonalności. Plan jest **intencją**, nie potwierdzonym przepływem. Executor: [EXECUTION.md](EXECUTION.md), testy: [VALIDATION.md](VALIDATION.md).

## Implementacja i ograniczenia dowodów

Bieżący solver i walidator znajdują się w `custom_components/energy_copilot/continuous_optimizer.py`, `horizon_optimizer.py` i `planner.py`. Wersje implementacji weryfikuj w kodzie i tagu, nie według historycznego numeru w dokumencie. Plan może obejmować wiele kwadransów, ale jego przełożenie na aktywny TOU i fizyczny przepływ wymaga odrębnej weryfikacji. `Load First` i blokada eksportu baterii pozostają obowiązujące.

Dane przyszłych cen kończą się na ostatnim opublikowanym przedziale. Wartość energii pozostawionej w baterii jest modelowana i oznaczona jako estymata — nie wolno dopisywać nieopublikowanych cen ani deklarować obserwowanych oszczędności bez pomiaru i baseline.
