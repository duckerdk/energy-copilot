# Wykonanie przez Home Assistant

**Zasady użytkownika i uprawnienia są wyłącznie w [REQUIREMENTS.md](REQUIREMENTS.md).** Dostępne encje i jakość danych opisuje [HA_CONTRACT.md](HA_CONTRACT.md). Ten plik opisuje tylko wykonanie i bezpieczeństwo.

## Tryby
- `monitor`: tylko odczyt.
- `dry_run`: plan i dziennik, **zero zapisów**.
- `supervised_test`: pojedynczy test zatwierdzony na instalacji z metodą powrotu.
- `automatic`: po włączeniu trybu live — autonomiczne limity prądu, Grid Charge, wszystkie sześć TOU i PV Solar Sell.
- `battery_export`: odrębna zdolność, każda konkretna operacja wymaga ważnej osobnej zgody.

Uprawnienia projektowe nie oznaczają, że obecne repo może już sterować falownikiem. **M1–M5 pozostają bez zapisów**. M6 wymaga sprawdzonego mapowania, aktualnych pomiarów i świadomego uruchomienia.

## Wykonawca
Przed każdą akcją: odczytaj aktualne HA, TOU, SOC, BMS, ceny i `plan_id`; sprawdź kompletność, granice prądowe, 20% SOC, dostępność i zgodę. Polecenia przez natywne `number.set_value` i `switch.turn_on/off`, bez własnego Modbus. Nie utożsamiaj ustawienia *maksymalnego* prądu z wymuszeniem konkretnych kW ani osiągnięciem celu SOC. Do prądu używaj dostępnego napięcia i obsługiwanego kroku; odrzucaj nielegalną wartość zamiast ją cicho przycinać.

Polecenie już wykonane: nie powtarzaj. Timeout z nieznanym skutkiem: nie ponawiaj w ciemno. Sukces usługi HA to najwyżej `applied`; `confirmed` wymaga odczytu i odpowiedniej obserwacji. Wykonawca ma stany `planned`, `blocked`, `applying`, `applied`, `confirmed`, `failed`, `uncertain`, `recovery_required`; każda zmiana stanu do logu. Tylko jeden aktywny executor. Przycisk STOP zatrzymuje kolejne działania, nie obiecuje sprzętowego wyłączenia. W trybie `automatic` ARM włącza się po starcie/reload integracji. Przejściowy błąd wejścia lub planu nie rozbraja ARM: blokuje zapisy do uzyskania nowych poprawnych danych i planu. Niepewny wynik częściowego zapisu do urządzenia pozostaje `recovery_required`, bez ślepego ponowienia.

## Dynamiczny TOU
Użytkownik **zezwolił na autonomiczną zmianę wszystkich sześciu okien**. To nie znaczy, że zapisy wielu encji są atomowe: odczytaj cały harmonogram, oceń efekt powtarzania w kolejną dobę, granicę 00:00, następstwo okien i częściową awarię w trakcie aktualizacji. Zadbaj o znaną kolejność zmian i możliwość odzyskania poprawnego układu. Nie deklaruj 96 niezależnych okresów sterowania na podstawie sześciu TOU. Grid Charge może zależeć od `switch.sun12k_grid_charge`, limitu ogólnego, limitu sieciowego i flagi charge w aktualnym TOU.

Ręczna zmiana zwykłej nastawy w trakcie aktywnej automatyki **może zostać nadpisana przy kolejnym planie**. Nie uruchamiaj wojny zapisów na każde zdarzenie HA. STOP, ochrona fizyczna i zgoda na eksport baterii mają pierwszeństwo.

## Utrata HA
Deye utrzymuje ostatnie parametry; **użytkownik akceptuje koszty ekonomiczne** nieoptymalnych nastaw podczas awarii. Nie wymagaj niezależnego wyłącznika tylko po to, by uniknąć straty finansowej. Brak HA nie jest równoznaczny z OFF, a po powrocie należy odczytać realny stan, unieważnić poprzedni plan i obliczyć nowy. Nie wolno naruszać fizycznego bezpieczeństwa falownika/BMS ani polityki minimum SOC.

## Eksport z baterii
Obecny Solar Sell zezwala tylko na nadwyżkę PV. Zmiana TOU lub pozostałych ustawień nie może przypadkowo włączyć eksportu baterii. Opcjonalna propozycja musi obejmować `proposal_id`, `plan_id`, czas, maksymalną energię eksportu z baterii [kWh AC], moc, SOC po operacji i korzyść po kosztach. Brak odpowiedzi = brak zgody. Zgoda wygasa przy zmianie warunków lub planu. Jeśli nie można fizycznie odróżnić eksportu baterii od eksportu PV, egzekwować kWh albo niezależnie zakończyć eksportu po zaniku HA, funkcja pozostaje `proposal_only` i nie wydaje komend.

## Dziennik i dashboard
Każda decyzja, również `idle/blocked`, zawiera `decision_id`, `plan_id`, UTC, wejściowe ceny i wersje prognoz, jakość pomiarów, ocenę wariantów, koszt energii i degradacji, powód, wybraną akcję i status fizycznego potwierdzenia. Bez haseł i danych tajnych. W UI pokazać cenę zakupu/sprzedaży, SOC, PV, sieć, stan planera i działania, najbliższe akcje, historię, STOP oraz zatwierdzenie/odwołanie eksportu baterii. Retencję ograniczyć bez utraty audytu decyzji. Od v1.16.8 lokalny Store przechowuje do 6000 zdarzeń z ostatnich 30 dni i eksportuje je przez diagnostykę, a sensor diagnostyczny pokazuje 5 ostatnich. Od v1.16.9 decyzje, blokady, wznowienia i wykonanie nastaw są również publikowane jako czytelne wpisy w natywnej **Aktywności** (`logbook_entry`), a logi tekstowe trafiają do **Logi systemowe → Core** (INFO w surowym logu, WARNING/ERROR w widoku skróconym). Format użytkownika nie może zawierać surowego JSON ani nazw wewnętrznych powodów; surowe pola pozostają w archiwum do diagnostyki. Nie utożsamiaj potwierdzenia nastaw z potwierdzeniem przepływu energii. Od v1.16.10 logbook entries mają osobną domenę i nie wywołują zdarzeń zmian stanu sensora. `Decision journal` pozostaje diagnostyką (stały stan `ready`/`unavailable`). Wyjaśnienia oparte są na faktach z planu: cenach, energiach, kosztach, późniejszych kwadransach. Nie twierdzić, że istnieje kontrfaktyczny wariant, jeśli go nie policzono. Koszt alternatywny w obecnym audycie jest liczony dla całego horyzontu (nie jest marginalnym kosztorysem pojedynczego kwadransa).

Testy i odbiór: [VALIDATION.md](VALIDATION.md).


### Uzgodniony sposób debugowania — od v1.16.11

- Kluczowe zdarzenia muszą odpowiedzieć na **co**, **dlaczego**, **na jakich danych** i **z jakim wynikiem**. Wyjątków nie maskować komunikatami „optymalizator wybrał” ani zbędnymi ogólnikami.
- `plan_status` zapisuje poprzedni i nowy status oraz powód blokady. `blocked` zapisuje brakujące pomiary, kod przyczyny z planera, istotne błędy jakości źródeł i status ARM; utrzymująca się blokada daje nowy wpis maksymalnie raz na kwadrans, nie co 30 sekund.
- `planned` dotyczy planu następnego pełnego kwadransa; deduplikacja obejmuje jego początek, działania oraz istotne ceny/prognozy, więc zmiana planu w tym samym kwadransie też może być widoczna.
- `applied` podaje konkretną liczbę potwierdzonych zmian i wartości przed/po dla encji; przy braku różnic podaje `0` wysłanych poleceń. `halted` zapisuje ostatnie niepotwierdzone polecenie oraz wcześniej potwierdzone zmiany.
- Wpisy `logbook_entry` zawierają `domain` i `entity_id` powiązany z rejestrem encji `Decision journal`; sensor ma stały stan i nie generuje przypadkowych zmian `planned → blocked`. Właściwe przejścia stanów planera pozostają widoczne z przyczyną.
- Mechanizm ten **nie wymaga zmian optymalizacji, ARM ani algorytmu sterowania**. Nie przypisywać solverowi hipotetycznych przyczyn bez obliczonego kontrfaktycznego wariantu.


### v1.16.12 — uzasadnienie ekonomiczne i korekty planu

- Po obliczeniu i przed audytem decyzji **wykonanie poleceń falownika ma pierwszeństwo**. Dodatkowe przeliczenie wyjaśniające jest read-only, wykonywane po części sterującej, ograniczone do 3 s; awaria lub przekroczenie czasu nie blokuje sterownika i nie jest przedstawiane jako obliczona przyczyna.
- Dla pierwszego kwadransa, przy akcjach `pv_charge`, `grid_charge`, `battery_discharge`, policz najlepszy plan na **identycznych znormalizowanych danych, efektywnościach, polityce rezerwy PV, wartości końcowego SOC i horyzoncie**, ale bez danej akcji w pierwszym kwadransie. Podawaj różnicę między kosztem alternatywy a oryginalnym celem całego horyzontu, a nie tylko wartości pojedynczych cen. Nie sugeruj, że eksport i magazynowanie tej samej energii są równoważne bez uwzględnienia sprawności i strat.
- Jeżeli różnica jest pomijalna lub ujemna, powiedz to wyraźnie. Gdy porównanie się nie uda, nie wymyślaj przyczyn. Dla `grid_import` brak wariantu z wymuszonym rozładowaniem — nie twierdzić, że taki wariant policzono.
- Wpis `planned` powstaje przy zmianie planowanego kwadransa; ponowne przeliczenie tego samego kwadransa publikuje `revised` z przyczyną (np. zmiana prognozy) i wartościami **przed → po**, nie pełną kopię planu. Zmiana akcji w korekcie otrzymuje nowe uzasadnienie ekonomiczne, jeśli jest możliwe.


### Bezpieczna polityka prądów / TOU — v1.16.13

1. **Nigdy nie zapisuj** `number.sun12k_maximum_battery_discharge_current`. W falowniku użytkownika 0 A w tym rejestrze zatrzymuje produkcję PV po kilku minutach niezależnie od innych nastaw. Wolno jedynie odczytać tę wartość; jeśli jest równa 0 A, zablokuj wszystkie zapisy i zgłoś potrzebę ręcznej korekty. Nie próbuj automatycznego przywrócenia.
2. Rozładowanie realizuje próg SOC w aktualnym TOU: brak rozładowania => próg co najmniej bieżącego (zaokrąglonego) SOC; planowane rozładowanie => próg odpowiadający planowanemu SOC na koniec kwadransa, nie poniżej 20%. Nie wyłączaj PV przez globalne ograniczenia prądu. Zmieniaj próg przy aktualizacji pomiarów, aby zabezpieczenie podążało za SOC rosnącym od PV.
3. Przy Grid Charge ON próg SOC ma znaczenie **celu ładowania z sieci**. Cel wylicz z bieżącego SOC i **wyłącznie energii grid→battery** (z uwzględnieniem sprawności i pojemności), nie z końcowego SOC obejmującego PV. Ładowanie włączać tylko, jeśli plan rzeczywiście zawiera energię z sieci i dodatni prąd. Najpierw ustaw cel/flagę TOU i prądy, potem globalne Grid Charge ON; wyłączaj Grid Charge na początku deaktywacji.
4. `Maximum Battery Charge Current` i `Maximum Battery Grid Charge Current` mogą być zapisane tylko w zakresie **1–50 A**. Globalny prąd ładowania ma obowiązywać również PV; dobieraj go na podstawie `kWh/15min × 4000 / V` i modelowej energii DC. Gdy eksport ma priorytet i brak zaplanowanego ładowania, minimalizuj ładowanie do 1 A, nie 0 A. Gdy Grid Charge jest OFF i istniejący prąd z sieci jest dodatni, nie nadpisuj go niepotrzebnie; zastane 0 A zastąp 1 A.
5. Każdy zapis musi być odczytany/potwierdzony, każda blokada i zmiana docelowego SOC lub prądu musi znaleźć uzasadnienie w dzienniku. Nie traktuj ustawienia globalnego limitu jako dokładnej gwarancji przepływu energii — TOU i prądy są ograniczeniami falownika, nie sterowaniem w zamkniętej pętli przy zachowaniu 15-minutowej energii.
6. Poprawka dotyczy **wykonawcy**, nie wyceny ekonomicznej. W diagnostyce z 28.10.2026 między 13:31 a 13:45 lokalnie planer zrewidował decyzję na ładowanie z sieci około 0,108 kWh przy SOC 99%, po czym wykonawca włączył Grid Charge. Powodem była obecność `grid_to_battery_ac_kwh > 0` w rzeczywistym zrewidowanym planie; przyszły sens ekonomiczny tej decyzji i bufor PV wymagają osobnej oceny planera, nie dowolnego obejścia w wykonawcy.


### v1.16.14 — opłacalność i celowe nastawy

- Zachować pełną dokładność liczb w modelu fizycznym; stosować **tolerancje decyzji**, nie brutalne zaokrąglanie wejściowych cen i energii. Drobna różnica <= 0,01 DKK to ekonomiczny remis; minimalna korzyść nowej kampanii ładowania z sieci to 0,10 DKK, kontynuacji już aktywnej — 0,05 DKK.
- Nie blokować jednego kwadransa z powodu nieistotnej różnicy, jeśli cały tani okres daje znaczącą korzyść. Porównać pełny horyzont z wariantem bez ładowania przez całe pierwsze ciągłe okno podobnych cen. Unikać ciągłego przesuwania początku kampanii na kolejny kwadrans.
- SOC >= 99% uznać za osiągnięcie celu 100% **dla decyzji o dalszym ładowaniu z sieci**. Nie wprowadzać sztywnej granicy 99% dla naturalnego ładowania PV.
- Gdy plan obejmuje kilka godzin niskiej, podobnej ceny (<= 0,01 DKK/kWh różnicy), wolno rozłożyć niezmienioną sumę grid-charge kWh na kwadranse. Wolno rozpocząć ładowanie wcześniej lub później wewnątrz tego samego opublikowanego taniego okna, tylko po walidacji fizycznej; sprawdzić każdy kwadrans niezależnym walidatorem i porzucić wariant, gdy wzrost kosztu przekracza 0,05 DKK.
- Globalne ograniczenie prądu ładowania baterii pozostaje bez zmian, jeśli nie zachodzi świadome **przesunięcie PV w czasie** albo weryfikowalne **rozłożenie ładowania sieciowego**. Sama prognoza PV, Solar Sell ON czy SOC99 nie uzasadniają limitu 1 A. Przy odraczaniu PV wymagaj faktycznego planowanego eksportu TERAZ oraz późniejszego ładowania; po jego zakończeniu przywróć wcześniej zapamiętaną wartość, nie nadpisując ręcznych zmian.
- Gdy Grid Charge OFF i zastany prąd ładowania z sieci wynosi np. 7 A, pozostawić bez zmiany. Gdy cały plan ładowania jest rozłożony na tanie kwadranse, skorygować tylko potrzebny limit; istniejące poprawne nastawy pozostawić. Nigdy nie zmieniać globalnego prądu rozładowania.
- Stan już aktywnego Grid Charge, jeśli wpływa na próg kontynuacji, musi być częścią metadanych HA Replay, aby Lab odtwarzał ten sam wybór.
