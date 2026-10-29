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

Przy tej samej energii i równoważnym koszcie w horyzoncie wybierać **łagodniejsze ładowanie**: rozłożyć je na dostępne kwadranse i minimalizować sumę kwadratów prądów ładowania, a następnie szczytowy prąd; **50 A to tylko limit**. Dostępne kwadranse musi wyznaczyć planer według opublikowanych cen, rzeczywistego czasu, wymaganego przyrostu SOC i ograniczeń; harmonogram 15-minutowy nie uprawnia do więcej niż sześciu okien TOU. Nie poświęcać istotnej korzyści ekonomicznej dla mniejszego prądu ani nie zakładać, że prąd zadany jest prądem rzeczywistym. Przy niepewnej marginalnej korzyści po degradacji i stratach wybierać brak **dodatkowego** cyklu. W przypadku zbliżonych kosztów preferować mniejszą liczbę zapisów i stabilniejsze nastawy, ale nie odwracać tym ekonomicznie istotnej przewagi. Zewnętrzna walidacja planu po solverze ponownie liczy bilanse, ograniczenia, koszt i zgody, niezależnie od rozwiązania optymalizatora.

## Dynamiczny zapas przed szczytem

Model prognozy zużycia korzysta tylko z 45 dni z podwyższonymi wagami dla ostatnich 7 i 14 dni. Na podstawie odseparowanego 7-dniowego holdoutu przechowuje całkowity i wieczorny błąd (`forecast − actual`) oraz 75. percentyl dodatniego niedoszacowania. Dla drogiego, dostatecznie długiego okresu przedział niepewności obliczany jest jako \(\max(0,-bias_{peak})\,h + 0.5\,P75_{peak}\sqrt{h}\) kWh AC. Po przeliczeniu na DC i odjęciu wolnej rezerwy w planie dodatkowy zapas jest ograniczony do **15 pp SOC**. Ta formuła jest świadomą heurystyką, nie estymatą prawdopodobieństwa.

Dodatkowe ładowanie powstaje wyłącznie w poprzedzających szczyt, względnie tanich kolejnych kwadransach, w których nie ma eksportu PV, ładowania PV ani rozładowania. Energia rozkłada się na co najmniej dwa kwadranse i musi przejść **niezależny symulator fizyczny**, łącznie z 20–100% SOC i ograniczeniami prądów ładowania. Używać reprezentatywnej ceny górnego kwartylu szczytu i jawnego współczynnika ryzyka **0,65**; jeżeli oczekiwana wartość unikniętego drogiego zakupu nie pokrywa dodatkowego kosztu, pozostawić plan bez zmian. Rzeczywista historia błędów nie jest kalibracją prawdopodobieństwa. Nowy zapas nie ogranicza faktycznego rozładowania w szczycie — próg TOU nadal steruje dostępnością całej energii.

**Wykres SOC ma pokazywać wynik z dodanym realnym ładowaniem**, a prognoza zużycia domu pozostaje nietknięta (bez dopisywania fikcyjnego poboru). Rozdzielić koszt bazowy, koszt dodatkowej ochrony i stan `applied/no_reserve_needed/no_safe_window` w diagnostyce. Zapis limitów prądów tylko przy celowym rozciągnięciu/przesunięciu ładowania, bez nowego powodu sterowania.

## Wynik
Dla każdego slotu: UTC, ceny i wersja danych, prognoza PV i zużycia, SOC początek/koniec, przepływy PV/dom/bateria/sieć, zamierzony Grid Charge/TOU/Solar Sell oraz **wyłącznie celowe czasowe ograniczenia prądu ładowania** (przesunięcie/rozciągnięcie), koszty wariantów, degradacja, niepewność i status wykonalności. Plan jest **intencją**, nie potwierdzonym przepływem. Executor: [EXECUTION.md](EXECUTION.md), testy: [VALIDATION.md](VALIDATION.md).

## Implementacja i ograniczenia dowodów

Bieżący solver i walidator znajdują się w `custom_components/energy_copilot/continuous_optimizer.py`, `horizon_optimizer.py` i `planner.py`. Wersje implementacji weryfikuj w kodzie i tagu, nie według historycznego numeru w dokumencie. Plan może obejmować wiele kwadransów, ale jego przełożenie na aktywny TOU i fizyczny przepływ wymaga odrębnej weryfikacji. `Load First` i blokada eksportu baterii pozostają obowiązujące.

Dane przyszłych cen kończą się na ostatnim opublikowanym przedziale. Wartość energii pozostawionej w baterii jest modelowana i oznaczona jako estymata — nie wolno dopisywać nieopublikowanych cen ani deklarować obserwowanych oszczędności bez pomiaru i baseline.
