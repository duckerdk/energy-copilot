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
Sprawności `eta_pv_bat`, `eta_grid_bat`, `eta_bat_ac`, `eta_pv_ac` rozdzielać i kalibrować; nie mieszać W DC z W AC bez konwersji. Początkowe 0,9487/0,97 to założenia, nie pomiary. Ograniczyć SOC **20–100%**, maksymalne prądy zgodnie z REQUIREMENTS i rzeczywiste limity BMS/temperatury/napięcia; wymagania sprzętowe ostrzejsze od polityki mają pierwszeństwo.

## Wykonalność przez Deye
Planner rozważa zarówno prądy, Grid Charge, zezwolenie PV Solar Sell, jak i autonomiczne zmiany **sześciu TOU**. Nie utrzymuj dawnego obowiązkowego „current-first bez zmieniania TOU”. Sam maksymalny prąd nie wymusza zadanej mocy ani osiągnięcia SOC; aktualne napięcie × A daje górne oszacowanie mocy DC. Warunki ładowania z sieci zależą jednocześnie od ogólnego limitu, limitu sieci, globalnego Grid Charge i aktywnego okresu TOU.

Porównywać:
1. Realny `baseline_deye` bez zmian Co-Pilot;
2. Wykonywalną politykę przy pozostawieniu TOU bez zmian;
3. Wykonywalną politykę z dynamicznym TOU i Grid Charge;
4. Idealne optimum teoretyczne **tylko referencyjnie**, nie jako deklarację osiągalnych oszczędności.

Sześciu okresów TOU nie wolno traktować jak 96 odrębnych nastaw co 15 minut. Jeżeli plan wymaga brakującej funkcji lub nierealnego przepływu, oznacz `not_executable` i nie wyceniaj go jako możliwego planu do wykonania. Bez zgody na eksport baterii ustaw `b_x=0` w planie wykonawczym.

## Prognozy i horyzont
Ceny tylko opublikowane; ich brak poza horyzontem to nie zero. Wartość końcowej energii w baterii `V_terminal(E_end)` może być estymowana z historii ze wskazaniem niepewności; nie dopisuje przyszłych cen. Replan po nowych cenach, produkcji, SOC i zapotrzebowaniu. Prognozy PV i zużycia muszą być wersjonowane z datą wydania; walk-forward używa wyłącznie danych dostępnych w tamtym czasie. Ograniczoną produkcję PV klasyfikować jako `curtailed_confirmed` / `curtailment_unknown`; sam spadek pomiaru przy pełnej baterii i wyłączonym eksporcie nie jest błędem prognozy pogody.

Przy tej samej energii i równoważnym koszcie w horyzoncie wybierać **łagodniejsze ładowanie**: rozłożyć je na dostępne kwadranse i minimalizować sumę kwadratów prądów ładowania, a następnie szczytowy prąd; **50 A to tylko limit**. Dostępne kwadranse musi wyznaczyć planer według opublikowanych cen, rzeczywistego czasu, wymaganego przyrostu SOC i ograniczeń; harmonogram 15-minutowy nie uprawnia do więcej niż sześciu okien TOU. Nie poświęcać istotnej korzyści ekonomicznej dla mniejszego prądu ani nie zakładać, że prąd zadany jest prądem rzeczywistym. Przy niepewnej marginalnej korzyści po degradacji i stratach wybierać brak **dodatkowego** cyklu. W przypadku zbliżonych kosztów preferować mniejszą liczbę zapisów i stabilniejsze nastawy, ale nie odwracać tym ekonomicznie istotnej przewagi. Zewnętrzna walidacja planu po solverze ponownie liczy bilanse, ograniczenia, koszt i zgody, niezależnie od rozwiązania optymalizatora.

## Wynik
Dla każdego slotu: UTC, ceny i wersja danych, prognoza PV i zużycia, SOC początek/koniec, przepływy PV/dom/bateria/sieć, zamierzony Grid Charge/TOU/prądy/Solar Sell, koszty wariantów, degradacja, niepewność i status wykonalności. Plan jest **intencją**, nie potwierdzonym przepływem. Executor: [EXECUTION.md](EXECUTION.md), testy: [VALIDATION.md](VALIDATION.md).

## Obecna implementacja — v1.13.0

Domyślny `optimize_horizon` wykonuje całohoryzontową optymalizację ciągłych przepływów energii bez kroku SOC 0,10 kWh. Wariant dyskretny to tylko porównawczy benchmark. Walidacja `simulate_candidate` nadal niezależnie sprawdza SOC, prądy, bilanse, brak równoczesnych przeciwnych przepływów oraz wyłącznie PV do eksportu. Nie jest to wykonywalna translacja na sześć okien TOU.

Przy niezmienionym `Load First` i eksporcie baterii OFF, fizyczną sprzedaż nadwyżki PV realizuje falownik. Planer nie zadaje eksportowanej mocy. Dobiera prąd ładowania i przyszły stan Solar Sell zależny od opublikowanej ceny sprzedaży (próg ≥0,40), a przewidywany eksport jako przepływ wynikowy. Zgodnie z potwierdzeniem użytkownika falownik realizuje zadane wartości prądu ładowania. Nie zmieniać `Load First`, polityki eksportu baterii ani funkcji TOU podczas tej aktualizacji.

Dla niedostępnych jeszcze cen następnego dnia wartość końcowa nie jest równa zero: zapotrzebowanie po końcu cen do następnej prognozowanej produkcji PV pozwala dobrać **oznaczony jako niezweryfikowany** wskaźnik cen z godzin opublikowanych, a nie dopisane fikcyjne ceny. Zmienna nie jest sztywnym docelowym SOC. Godzinowy plan ujawnia ceny zakupu/sprzedaży, eksport, prąd, koszty zakupu i wpływy ze sprzedaży, a diagnostyka pokazuje statystyczne błędy prognoz bez sugerowania kalibracji fizycznej.
