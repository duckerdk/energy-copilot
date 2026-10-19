# Scenariusze testowe Energy Co-Pilot

**Status:** specyfikacja testów akceptacyjnych, bez implementacji. **Wszystkie ceny, profile i sprawności w przykładach są syntetycznymi danymi testowymi, nie odczytami instalacji użytkownika.**
Podstawa: [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [GOALS_AND_REQUIREMENTS.md](GOALS_AND_REQUIREMENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md).

## 1. Zasady interpretacji i kryterium zaliczenia

- Testy sprawdzają **wynik ekonomiczny, bilans fizyczny, ograniczenia i bezpieczeństwo**, a nie konkretną implementację solvera. Przy wielu równoważnych rozwiązaniach dopuszczać każdy optymalny plan spełniający niezmienniki; nie wymuszać dowolnego układu operacji.
- Gdy nie podano inaczej, testowa bateria: `capacity = 10,24 kWh`, `SOC_min = 20%`, `SOC_max = 100%`, `P_charge_max = 2,5 kW`, `P_discharge_max = 5 kW`, sprawności wszystkich czterech torów `η = 1`, koszt degradacji `0 DKK`, bez ograniczeń sieci; `E_min = 2,048 kWh`, `E_max = 10,24 kWh`. To **idealizacja wyłącznie dla jednoznacznej arytmetyki testowej**, nie rzeczywisty model wydajności.
- Cena zakupu `C_buy` oznacza **cenę z opłatami** [DKK/kWh]; cena eksportu `C_sell = spot − 0,0215 DKK/kWh`. Cena sprzedaży w teście podana wprost oznacza wartość **po prowizji**; odpowiadający jej spot jest wyższy o `0,0215`. Wszystkie kwoty DKK.
- Moc to **kW średniego przepływu w slocie**, energia to kWh; bazowy slot `Δt = 0,25 h`. W testach całogodzinnych/dłuższych profil jest identyczny w każdym kwadransie danego okresu. Gdy test wymaga stałej wartości SOC na końcu albo wartości końcowej energii, jest to **jawny warunek fikstury**, nie stała reguła projektu.
- Domyślnie: **brak zgody na eksport energii z baterii**, zatem `b_x = 0`; eksport samego PV dopuszczony, o ile przypadek nie stanowi inaczej. Tryb sprzętowego executora nieaktywny (`dry_run`).
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

**Dane:** `spot = 0,8000 DKK/kWh`; drugi przypadek `spot = −0,1000 DKK/kWh`.  
**Oczekiwane:** kolejno `C_sell = 0,7785` i `C_sell = −0,1215 DKK/kWh`. Nie stosować do sprzedaży ceny zakupu z opłatami.

### ECO-02 — Opłacalne ładowanie z sieci na potrzeby domu

**Dane:** `SOC_start = 20%`, brak PV, w pierwszej godzinie dom = 0 i `C_buy = 0,40`, w drugiej dom zużywa 1 kWh i `C_buy = 1,50`; możliwość ładowania z sieci; `E_end = E_min`; eksport z baterii zabroniony; `η = 1`.  
**Oczekiwane:** import **1 kWh** w taniej godzinie do baterii, następnie bateria → dom **1 kWh**; `SOC` po ładowaniu = `29,765625%`, po rozładowaniu = 20%; koszt `0,40 DKK` zamiast `1,50 DKK`; oszczędność `1,10 DKK`. Mocy ładowania/rozładowania nie przekraczać.

### ECO-03 — Zakup na późniejszy eksport jest nieopłacalny po stratach

**Dane:** dom = PV = 0; dopuszczony *hipotetycznie* eksport z baterii; zakup `C_buy = 0,50`, późniejszy eksport `C_sell = 0,60`; `η_grid_bat = η_bat_ac = 0,90`, koszt degradacji = 0, taki sam stan końcowy baterii.  
**Oczekiwane:** kupno 1 kWh, a następnie eksport 0,81 kWh dałyby przychód `0,486 DKK` przy koszcie `0,500 DKK`, czyli stratę `0,014 DKK`. Optymalny dodatkowy cykl = **0 kWh**; nie generować oferty sprzedaży z dodatnim zyskiem. Większe obroty przy liniowym modelu zwiększają stratę.

### ECO-04 — PV do baterii korzystniejsze niż eksport

**Dane:** teraz `PV = 1 kWh`, dom = 0, `C_sell_now = 0,30`; później dom = 1 kWh i `C_buy_later = 1,00`; brak innych PV, brak ładowania z sieci, `E_start = E_min`, `η = 1`, `E_end = E_min`.  
**Oczekiwane:** 1 kWh PV → bateria → dom; koszt netto `0,00 DKK`. Alternatywa eksport 1 kWh i późniejszy zakup 1 kWh kosztuje `1,00 − 0,30 = 0,70 DKK`; optymalizator wybiera magazynowanie.

### ECO-05 — Sprzedaż PV teraz korzystniejsza niż magazynowanie

**Dane:** jak ECO-04, lecz `C_sell_now = 1,20` i `C_buy_later = 0,70`.  
**Oczekiwane:** eksport PV 1 kWh teraz i późniejszy zakup 1 kWh do domu; koszt netto `0,70 − 1,20 = −0,50 DKK` wobec `0,00 DKK` przy magazynowaniu. Eksport PV nie wymaga zgody na sprzedaż energii **z baterii**.

### ECO-06 — Cena eksportu ujemna i brak możliwości magazynowania

**Dane:** `spot = −0,10`, więc `C_sell = −0,1215`; potencjalne PV = 1 kWh, dom = 0, bateria pełna; dopuszczony curtailment.  
**Oczekiwane:** nie eksportować 1 kWh ze stratą `0,1215 DKK`; w tym teście ograniczyć produkcję PV o 1 kWh, wynik finansowy 0 zamiast dodatniego kosztu eksportu. Nie stosować tej decyzji bez fizycznej możliwości ograniczania PV.

### ECO-07 — Degradacja rozstrzyga marginalną opłacalność

**Dane:** jak ECO-02, ale w **fiksturze testowej** koszt degradacji = `0,10 DKK za 1 kWh` energii przepływającej przez baterię, naliczany dla wejścia i wyjścia (2 kWh throughput łącznie).  
**Oczekiwane:** oszczędność na energii `1,10 DKK`, koszt degradacji `0,20 DKK`, wynik dodatkowy `+0,90 DKK`. Raportować osobno rachunek za energię i wewnętrzny koszt degradacji; nie przyjmować `0,10` jako parametru realnej baterii.

## 4. Dynamiczny SOC — dwa kontrastowe scenariusze

Dla **SOC-01** i **SOC-02** wspólne:
- Bateria startuje przy `SOC = 20%` = `E = 2,048 kWh`; `η = 1`, koszt degradacji 0, eksport z baterii zabroniony, ładowanie z sieci wyłączone, limit ładowania 2,5 kW.
- Dzisiejsze PV `6 kWh` w ciągu **3 godzin** po 2 kW; w tym czasie dom = 0, `C_sell_today = 0,20 DKK/kWh`.
- Nocą dom potrzebuje `4,608 kWh` przez **4 godziny** po 1,152 kW; brak PV; cena zakupu nocą `1,00 DKK/kWh`.
- Ceny wszystkich godzin objętych scenariuszem zostały rzeczywiście podane w fiksturze, a więc dostępne w planie. Wartość końcowa każdego dodatkowego kWh w baterii powyżej minimum przyjmowana przez fiksturę wynosi `0,20 DKK/kWh`; to parametr testowy, nie produkcyjna nastawa.
- Eksport PV jest dozwolony i technicznie wykonalny; ograniczeń punktu przyłącza brak.

### SOC-01 — Jutro dużo PV; optimum przed nocą wynosi 65%

**Dodatkowe dane:** jutro rano `10 kWh` PV przez **4 godziny** po 2,5 kW, dom = 0; `C_sell_tomorrow = 0,10 DKK/kWh`. PV wystarcza do uzupełnienia baterii do 100% z 20%; rano dozwolony jednoczesny przepływ PV do baterii i eksport PV (bez jednoczesnego importu z sieci).  
**Oczekiwane:**

1. Dziś do baterii z PV `4,608 kWh`, nadwyżkę `1,392 kWh` sprzedać po 0,20; przed nocą `E = 2,048 + 4,608 = 6,656 kWh`, **SOC = 65,0000%**.
2. W nocy bateria → dom `4,608 kWh`, import 0, rano `SOC = 20%`.
3. Jutro PV → bateria `8,192 kWh`, eksport `1,808 kWh` po 0,10, końcowy SOC 100%.
4. Przychód z PV = `1,392 × 0,20 + 1,808 × 0,10 = 0,4592 DKK`; zakup 0; koszt netto `−0,4592 DKK` (bez wewnętrznych kosztów). Wartość końcowa baterii jest taka sama dla rozważanych wariantów osiągających 100%, więc nie zmienia porównania.
5. Zmagazynowanie dziś pełnych 6 kWh zamiast 4,608 przesuwałoby 1,392 kWh eksportu z godziny sprzedaży po 0,20 do jutra po 0,10, obniżając przychód o **0,1392 DKK**. Nie wymuszać 100% już dziś.

**Warunek akceptacji:** model wyprowadza **65% jako wynik optymalizacji**, bez reguły typu „ustaw 65%”, i wskazuje ekonomiczną przyczynę (utracony przychód z eksportu dziś wobec jutrzejszej nadwyżki).

### SOC-02 — Jutro brak PV; cel SOC rośnie do 78,59375%

**Zmiana względem SOC-01:** jutro rano **PV = 0**, a dom zużywa dodatkowo `1,392 kWh` po `1,00 DKK/kWh`. Nie można ładować z sieci.  
**Oczekiwane:** dziś magazynować całe `6,000 kWh` dostępnego PV, przed nocą `E = 8,048 kWh`, **SOC = 78,59375%**; w nocy i rano pokryć z baterii razem `6,000 kWh`, zakończyć przy SOC 20% i imporcie 0. Eksport PV dziś 0. Sprzedaż dziś 1,392 kWh po 0,20 i zakup jutro 1,392 kWh po 1,00 pogorszyłyby wynik o `1,1136 DKK`.

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


## 9. Kontrakt encji HA — testy bez rzeczywistego zapisu

### MAP-01 — Zakup i sprzedaż są odrębne

**Dane:** źródło spot = `0,80 DKK/kWh`, cena końcowa zakupu w drugim źródle = `1,45 DKK/kWh`; te same znane znaczniki czasu.  
**Oczekiwane:** `C_buy = 1,45`, `C_sell = 0,7785 DKK/kWh`. Nie wolno przyjąć ceny zakupu jako ceny sprzedaży ani samego spot jako finalnej ceny zakupu.

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

## 10. Co programista ma udowodnić

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
