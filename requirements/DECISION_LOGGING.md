# Rejestr decyzji i diagnostyka optymalizatora

**Status: wymaganie obowiązujące do pierwszego uruchomienia w trybie monitor/dry-run.** Dotyczy decyzji planera i późniejszych poleceń wykonawcy. Dane przechowywane lokalnie w HA; bez zewnętrznej telemetrii i bez ręcznego eksportu JSON do analizy bieżącego działania.

## 1. Cel

Każda istotna decyzja optymalizatora ma być **wyjaśnialna i możliwa do prześledzenia**: skąd wzięły się ceny i prognozy, dlaczego wybrano ładowanie/eksport/brak działania, jakie alternatywy rozważono, czy plan był wykonalny, a później — czy został wykonany.

Szczególnie podczas rozruchu użytkownik musi widzieć **podstawy każdej decyzji** bez wyszukiwania ich w kodzie lub uruchamiania debuggera.

Rejestrować także:
- plan: `charge_from_grid`, `charge_from_pv`, `discharge_to_home`, `propose_battery_export`, `export_pv`, `curtail_pv` i `idle`;
- wynik `blocked`, błędy i odstąpienie od komendy;
- każdą aktualizację planu po cenach około 13:00 lub istotnej zmianie danych;
- powody zmiany/odrzucenia propozycji eksportu baterii;
- polecenie HA, skutek fizyczny, konflikt, retry i wyjście z trybu;
- zmianę jakości danych i ograniczeń, jeśli wpłynęła na decyzję.

## 2. Dwa poziomy informacji

**Widok bieżący — poziom INFO, włączony od pierwszego uruchomienia:**
- godzina decyzji, aktywny `plan_id`, okres slotu i ważność;
- działanie: co i z jaką zamierzoną mocą, skąd/dokąd energia, docelowy SOC;
- cena kupna **pełna** i sprzedaży **netto**; prognoza PV i poboru dla rozpatrywanych okresów;
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

## 4. Rzetelne porównanie alternatyw

- Porównywać **ten sam horyzont**, prognozy, start SOC, parametry sprawności i **porównywalną wartość energii końcowej**; inaczej różnica zysków jest myląca.
- `baseline` definiować jawnie (np. brak nowej akcji optymalizatora przy zachowaniu zweryfikowanej standardowej pracy falownika), nie zastępować go fikcyjnym scenariuszem „wszystko z sieci”, jeśli Deye normalnie korzysta z PV.
- Koszt faktury = zakupy z opłatami minus eksport netto; koszt degradacji i ryzyka podać osobno. Jeżeli brak wystarczających danych do uczciwego porównania, `benefit_vs_baseline` = nieznany i `reason_code = BASELINE_UNAVAILABLE`.
- Dla odpowiedzi „dlaczego nie 100% SOC?” podać prognozowane przyszłe zapotrzebowanie, PV, ceny i różnicę opłacalności przechowania dodatkowej kWh względem eksportu teraz, a nie wskazywać arbitralny próg.
- Wariant alternatywny niespełniający ograniczeń oznaczyć `infeasible` zamiast przypisywać mu dowolną kwotę.

## 5. Typowe kody przyczyn

`GRID_CHEAPER_AFTER_LOSSES`, `PV_STORAGE_MORE_VALUABLE`, `PV_EXPORT_MORE_VALUABLE`, `NEGATIVE_EXPORT_PRICE`, `TARGET_SOC_FROM_DEMAND`, `TERMINAL_ENERGY_VALUE`, `FORECAST_UNCERTAINTY`, `CURTAILMENT_SUSPECTED`, `PRICE_NOT_PUBLISHED`, `SOC_LIMIT`, `POWER_LIMIT`, `BATTERY_EXPORT_NOT_APPROVED`, `CAPABILITY_NOT_VALIDATED`, `STALE_DATA`, `NO_POSITIVE_NET_BENEFIT`, `NO_ACTION_BEST`, `PLAN_SUPERSEDED`, `ACTUATION_NOT_CONFIRMED`, `BASELINE_UNAVAILABLE`.

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
