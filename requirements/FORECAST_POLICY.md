# Prognozy, niepewność i wartość baterii na końcu horyzontu

**Status:** techniczna specyfikacja planowania i kalibracji. Rozróżnia: **opublikowane ceny** (fakty), **prognozy PV/zużycia** (estymaty), **statystyczną niepewność poza horyzontem** (nie jest prognozą opublikowanej ceny) oraz pomiary fizyczne.

## 1. Co wiadomo w chwili decyzji

W danym momencie:
- Znana jest przyszła seria cen **tylko do ostatniego opublikowanego slotu**; zwykle około 13:00 poprzedniego dnia publikują się ceny 00:00–23:59 dnia następnego. Jeśli nowej serii brak, nie przesuwać końca planu.
- Prognoza PV może obejmować okres dłuższy niż ceny. Trzeba odróżnić **potencjalną** generację PV od historycznego uzysku sztucznie ograniczonego przez pełną baterię/eksport OFF.
- Prognoza domu powstaje z danych dostępnych do chwili decyzji, a jej błąd powinien zależeć od pory dnia/tygodnia i sezonu, gdy dane na to pozwalają.
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

**Odbiór:** w [DECISION_LOGGING.md](DECISION_LOGGING.md) dla każdej decyzji podane: znane ceny, wersja prognozy, scenariusze niepewności, końcowa wartość energii (lub brak wiarygodnego oszacowania) oraz porównanie z alternatywą. W [BACKTEST_VALIDATION.md](BACKTEST_VALIDATION.md) sprawdzić wpływ funkcji końcowej na zysk i brak wiedzy o przyszłości.
