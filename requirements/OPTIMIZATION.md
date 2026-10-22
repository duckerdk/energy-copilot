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

## Aktualny zakres implementacji M3
`custom_components/energy_copilot/planner.py` przyjmuje jawny ciąg 15-minutowych wejść, parametry sprawności i proponowane przepływy, weryfikuje bilans i limity oraz porównuje koszt wariantów z degradacją i wyceną końcowego SOC. `reference_no_battery` jest pomocniczym scenariuszem **bez cykli baterii**, nie rzeczywistym `baseline_deye`. Wynik `physical_candidate_only_tou_unverified` nie oznacza planu wykonalnego przez sześć TOU ani optymalności globalnej. Wartości prognostyczne, sprawności i wartość końcowa nie mają domyślnych założeń; wymagają jawnych, udokumentowanych wejść. Dostępna jest dodatkowo propozycja rozłożenia wymaganej energii ładowania sieciowego na **jawnie wskazane** kwadranse i preferencja mniejszego prądu przy koszcie równym z dokładnością numeryczną. Nadal nie dobiera to samodzielnie okien ani nie steruje falownikiem. Adapter `planning_inputs.py` wiąże istniejący `InputSnapshot` z cenami, okresami Forecast.Solar i kwadransami Recorder. Domyślne, jawnie **niezweryfikowane** oszacowanie domu powtarza wyłącznie kompletne kwadranse sprzed 24 godzin w UTC; brak historii nie jest zastępowany zerem. PV wymaga jawnego współczynnika przeliczenia prognozy na bazę DC: tego parametru nie wolno zgadywać. Gdy prognoza energii nie pokrywa pełnego kwadransa (np. ma tylko godzinne Wh), adapter blokuje plan zamiast bezpodstawnego dzielenia energii. Wynik ma `actionable=False`, bez mapowania TOU i poleceń HA. Pozostają kalibracja danych, prognoza domu, walidacja modelu rozkładu energii wewnątrz okresów Forecast.Solar, optymalizacja sześciu rzeczywistych TOU, baseline Deye i backtest.

## Weryfikacja M3 w HA — v0.1.8
Tryb `dry_run` bez usług zapisu wyświetla `planning_status` (`monitor`/`blocked`/`preview`) oraz `modeled_saving` (DKK). Podgląd porównuje bazowy brak cykli baterii z ograniczonym zbiorem **jednego** hipotetycznego cyklu ładowanie sieci→bateria→zasilanie domu, zachowując **taki sam końcowy SOC**. Zestaw scenariuszy nie dowodzi optimum globalnego ani wykonalności przez Deye. Dane pochodzą z `InputSnapshot`; dopuszczalny krótszy `partial` kończy się przed pierwszą luką prognozy, a brak pierwszego kwadransa blokuje podgląd. Współczynnik prognozy do bazy DC = 1,0 i sprawności 0,95 są jawnymi **niezweryfikowanymi założeniami testu**, nigdy decyzją wykonawczą; BMS, ograniczenia PV i rzeczywiste TOU wymagają osobnej walidacji. `modeled_saving` nie jest rzeczywistą oszczędnością wobec ustawień Deye.

## M3 v0.1.9 — nieregularne okresy Forecast.Solar
W `dry_run` adapter M3 używa wyłącznie jawnie włączonej opcji `pv_temporal_model="uniform_power_unverified"`. Opublikowana energia pojedynczego okresu PV jest integrowana na jego przecięciu z kwadransem, proporcjonalnie do rzeczywistej liczby sekund; suma wszystkich kwadransów pokrywających pełny okres równa jest oryginalnemu kWh. **To założenie stałej średniej mocy w okresie, nie udowodniona 15-minutowa prognoza**. Energia rozpoczętego okresu nie jest przepisywana w całości na pozostałą część. Nakładanie przedziałów, przerwy w danych i brakujące Wh nadal są blokadami. Jawne pochodzenie jest w `pv_temporal_model` i `pv_temporal_modeled_quarters` w encji i diagnostyce, nigdy nie włącza sterowania. Domyślna funkcja `build_planning_input` bez tej opcji nadal wymaga ścisłego pokrycia 15-minutowego; nie zmieniono historycznej polityki Recorder.

## M3 v0.1.10 — krótkie luki Recorder w prognozie domu
W `dry_run` projektor poprzedniej doby UTC może **jawnie modelować wyłącznie przyszłą prognozę obciążenia** (`short_gap_model="linear_bracketed_unverified"`). Gdy w poprzedniej dobie brakuje najwyżej **3 kolejnych kwadransów**, a bezpośrednio przed i po luce istnieją kompletne, zweryfikowane kwadranse Recorder, interpolacja liniowa ich energii wyznacza niezweryfikowany profil wyłącznie dla symulacji. Ani brakujące rekordy, ani wynik ich audytu nie są zmieniane ani zamieniane na zero. Przy braku obu punktów brzegowych, zbyt długiej przerwie lub niewystarczającej historii prognoza pozostaje niepełna i dry-run jest `blocked` albo `partial`. Nazwa metody `previous_24h_utc_linear_bracketed_gap_model_unverified` i liczba `load_modeled_quarters` widnieją w encji oraz diagnostyce. Domyślny projektor bez opcji zachowuje ścisłe reguły. Modelowanie luki **nie dowodzi wiarygodności prognozy** ani oszczędności i nie nadaje statusu `executable`.

## M3 v1.11.0 — historyczny model 7 dni
Domyślny dry_run przestaje korzystać z projekcji poprzednich 24 godzin. Zamiast tego pobiera estymację 7 dni z godzinowych statystyk do 365 dni wstecz: mediana ważona, malejąca waga starszych danych, dzień tygodnia, dzień roboczy/wolny i duńskie święta. Rozkład godzinowej energii na kwadranse jest równomierny i jeszcze niezweryfikowany. Horyzont prognozy zużycia nie rozszerza horyzontu opublikowanych cen ani Forecast.Solar. Poprzedni opis 24h dotyczy wydań historycznych. Brak modelu blokuje dry_run.


## M3 v1.12.0 — optymalizacja całego horyzontu, nadal tylko dry_run

Nowy `horizon_optimizer.py` zastępuje ograniczone badanie pojedynczego cyklu 15/30 min pełnohoryzontowym programowaniem dynamicznym po dyskretnym stanie energii baterii. Krok `0.10 kWh DC` i 15-minutowy krok czasowy są **przybliżeniem obliczeniowym**, a nie sterowaniem Deye co kwadrans. Każdy stan uwzględnia SOC 20–100%, maksymalne prądy ładowania/rozładowania, przepływy do domu, PV→dom, PV→bateria, sieć→bateria, stratę sprawności, brak eksportu baterii i degradację 0,40 DKK/kWh DC. Cena i obciążenie są oceniane przez cały wspólny horyzont opublikowanych danych. Plan może mieć wiele kwadransów ładowania i rozładowania, także gdy opłaca się zachować SOC w tańszych godzinach.

Wartość końcowej energii nie jest zerowana: jako **ostrożny, niezweryfikowany zamiennik kosztu odtworzenia kWh DC** używana jest najniższa opublikowana cena zakupu dzielona przez modelową sprawność ładowania z sieci (dolne ograniczenie 0). Nie dodaje się hipotetycznych cen po horyzoncie. Taki model wartości końcowej wymaga walidacji; bieżący plan nie jest globalnym optimum ciągłym i nie zakłada równości SOC końcowego/początkowego.

Wybrana 15-minutowa dyspozycja jest **ponownie niezależnie weryfikowana** przez istniejący symulator `simulate_candidate`. W HA widoczny jest godzinowy agregat planu (przewidywany SOC, zakup energii, energia PV, ładowanie sieciowe i PV, rozładowanie i eksport). Wariant bazowy nadal nie odtwarza rzeczywistych TOU falownika, dlatego `modeled_saving_dkk` pozostaje porównaniem do **teoretycznego braku cykli baterii**, a nie osiągalną oszczędnością. `tou_feasibility=not_evaluated`, `executable=False`. Konwersja planu na rzeczywistych sześć okien TOU, walidacja BMS i prawdziwy baseline Deye wymagają dalszego wdrożenia.

Brak prognozy PV lub opublikowanego okresu pozostaje jawną luką. Program nie wpisuje arbitralnego zera dla nieopublikowanej nocnej energii Forecast.Solar; plan może mieć `partial` horyzont krótszy niż horyzont cen. To ograniczenie wymaga osobnego, potwierdzonego źródła nocnego PV, nie cichej ekstrapolacji.
