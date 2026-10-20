# Kontrakt przyszłych cen — Energi Data Service w Home Assistant

**Status: struktura danych potwierdzona przez użytkownika 20.10.2026 na pełnych atrybutach dwóch encji.** Kontrakt implementacyjny; nie wymaga pytania o sposób publikowania cen. Nie utrwala odczytanych stawek jako konfiguracji lub prognozy. Powiązania: [ENTITY_CONTRACT.md](ENTITY_CONTRACT.md), [OPTIMIZATION_MODEL.md](OPTIMIZATION_MODEL.md), [TEST_SCENARIOS.md](TEST_SCENARIOS.md).

## 1. Źródło prawdy — wyłącznie istniejące encje HA

| Znaczenie | Encja HA | Wartość planera |
| --- | --- | --- |
| Końcowa cena zakupu **ze wszystkimi opłatami i taryfami** | `sensor.energi_data_service` | `raw_today[*].price` / `raw_tomorrow[*].price` [DKK/kWh] |
| Cena spot jako podstawa sprzedaży | `sensor.energi_data_spotpris` | `raw_today[*].price` / `raw_tomorrow[*].price` [DKK/kWh] |
| Sprzedaż netto | Nie wymaga nowej encji | `spot − 0.0215 DKK/kWh`, zgodnie z warunkami podanymi przez użytkownika |
| Bieżąca cena diagnostyczna | Atrybut `current_price` obu encji | Wartość o większej precyzji niż lista godzinowa; nie zastępuje pełnego szeregu |
| Publikacja jutra | `tomorrow_valid` w **każdej** encji | Akceptuj jutro dopiero, gdy źródło ją oznaczyło jako dostępną **i** lista jest poprawna |
| Kolejny termin odświeżenia źródła | `next_data_update` | Informacja diagnostyczna, **nie** pewny czas publikacji jutra ani sygnał pojawienia się nowych cen |
| Metadane | `currency`, `region_code`, `unit_of_measurement` | Oczekiwane `DKK`, `DK1`, `DKK/kWh`; błąd jednostki/regionu blokuje użycie |
| Rozkład składników ceny zakupu | `net_operator`, `tariffs` (w tym `additional_tariffs`) | Wyłącznie diagnostyka. **Nie dodawać żadnej z tych kwot po raz drugi** do `raw_*.price` |

**Nie wyliczać ceny zakupu ze spot + taryfy.** Użytkownik potwierdził, że `sensor.energi_data_service` już publikuje ostateczną cenę. Odmienna cena zakupu i spot jest oczekiwana. `state_class: total`, `unit: kWh` i `device_class: monetary` są metadanymi encji; planner waliduje szczególnie `currency` i `unit_of_measurement`, **nie** traktuje ceny jako licznika narastającego.

## 2. Format — potwierdzony na rzeczywistym odczycie

Atrybuty obu encji:

- `today` — lista cen bez znaczników czasu. Przydatna diagnostycznie, **nieużywana jako podstawowe źródło czasu**, bo przy zmianie czasu doba może mieć 23 lub 25 godzin.
- `raw_today` — lista obiektów `{"hour":"2026-10-20T08:00:00+02:00","price":2.406}` dla ceny zakupu; analogicznie `1.922` dla spot. Pole `hour` ma strefę/offset, `price` jest liczbą w DKK/kWh.
- `tomorrow` — lista bez timestampów albo `null`, zgodnie z dostępnością.
- `raw_tomorrow` — timestampowane obiekty po publikacji albo `null` przed publikacją.
- `tomorrow_valid` — `false` przed publikacją; sam upływ godziny 13:00 nie zastępuje tej flagi.
- `next_data_update` — przykład: zakup `13:25:40`, spot `13:28:03`; **oddzielny** czas następnego odświeżenia, może się różnić.
- `today_min/max/mean`, `tomorrow_min/max/mean` i `today_remaining_*` — wskaźniki informacyjne; **nie** budować szeregu na podstawie wartości średnich lub minimalnych.

**Snapshot 20.10.2026, przed cenami jutrzejszymi:** obie encje miały po **24** pozycji w `raw_today` (00:00–23:00, offset +02:00); obie miały `tomorrow_valid: false`, `tomorrow: null` i `raw_tomorrow: null`. To pełna dostępna seria na dziś i **normalny** brak serii na jutro.

Wybrane potwierdzone pary godzinowe (ilustracyjne **migawki danych z 20.10**, nie stałe programu):

| Czas lokalny | Zakup końcowy DKK/kWh | Spot DKK/kWh | Sprzedaż netto DKK/kWh |
| --- | ---: | ---: | ---: |
| 08:00 | 2.406 | 1.922 | 1.9005 |
| 13:00 | 1.838 | 1.355 | 1.3335 |
| 18:00 | 3.151 | 2.008 | 1.9865 |

W tej samej migawce `current_price` miał precyzyjniejsze wartości: zakup `2.405502871680312`, spot `1.9222991216803123`; różnica do `raw_today[08:00]` wynika z **zaokrąglenia** cen w liście do trzech miejsc. Przy przetwarzaniu planu używać jednej, jawnie opisanej podstawy (`raw_*`) dla **wszystkich godzin**, bez ukrytego mieszania precyzji. Bieżące `current_price` służy do kontroli spójności i wyświetlania.

## 3. Kontrakt parsera i normalizacji

Wejście: **dwa** bieżące stany HA oraz ich atrybuty. Parser jest deterministyczny i nie korzysta z internetu, bezpośredniego Modbus ani własnego klienta API.

1. Dla każdej encji sprawdź jej dostępność, `currency = "DKK"`, `region_code = "DK1"`, `unit_of_measurement = "DKK/kWh"` oraz istnienie `raw_today`.
2. Każdy rekord parsuj z `hour` do świadomego offsetu timestampu, następnie przekonwertuj do UTC. `price` musi być skończoną liczbą; **nie** odrzucać cen zerowych lub ujemnych. Nie używać indeksów `today` jako identyfikatora godziny.
3. Nadaj godzinowemu rekordowi `start_utc` i `end_utc = start_utc + 1h` (prawy koniec wyłączny). Posortuj po UTC, sprawdź unikalność, kolejność, brak luk lub nakładania w okresie przeznaczonym do planu. Godzina powtórzona lokalnie podczas jesiennej zmiany czasu to **dwa różne** przedziały UTC.
4. Dodaj `raw_tomorrow` tylko, jeśli `tomorrow_valid === true` **dla tej encji**, `raw_tomorrow` jest listą z poprawnymi rekordami daty kolejnej doby lokalnej i jest spójna czasowo z końcem dziś. W przeciwnym razie nie bierz jutra, bez dosztukowywania listy ani interpolowania.
5. Znormalizuj oba źródła do `start_utc/end_utc`. **Dla ceny eksportu potrzebny jest rekord spot; dla importu rekord zakupu w tym samym przedziale.** Horyzont pełnej optymalizacji dwukierunkowej ogranicza **wspólny ciągły fragment** obu źródeł od bieżącej chwili. Źródła mogą opublikować jutro o różnych minutach; ich zakresów nie wolno bezrefleksyjnie utożsamiać.
6. Każda cena godzinowa obowiązuje w swoich czterech kwadransach planu 15-minutowego (z uwzględnieniem częściowo rozpoczętego pierwszego slotu). **Nie tworzyć sztucznych nowych cen** po końcu ostatniego kompletnego opublikowanego przedziału.
7. Gdy `tomorrow_valid` zmienia się z `false` na `true` i dochodzi poprawny wspólny szereg, opublikuj nową wersję danych i przelicz plan. Zmiana treści `raw_*` bez zmiany flagi też wymaga odświeżenia planu; śledzić faktyczną wersję listy/timestamp, nie samą godzinę `next_data_update`.
8. Przy `unknown/unavailable`, niekompletnym źródle, DST lub luce danych ogranicz plan do spójnego znanego fragmentu albo jawnie `blocked/partial`; nie zastępować brakującej ceny kupna spot ani odwrotnie.
9. Pojedyncze wartości diagnostyczne `current_price` porównać z rekordem dla aktywnej godziny (tolerancja odpowiada udokumentowanemu zaokrągleniu, np. `0.001 DKK/kWh`). Znaczna rozbieżność: diagnostyka; nie nadpisywać całej przyszłej serii.
10. Wynik mappera dla każdej godziny: `{start_utc,end_utc,buy_dkk_kwh,spot_dkk_kwh,sell_net_dkk_kwh,source_buy,source_spot,obtained_at_utc}`; godzina z danymi tylko z jednego źródła ma oddzielny status brakującego składnika.

`next_data_update` jest **czasem bez daty**, dlatego nie interpretować go jako dowodu publikacji ani jako znacznika czasu każdej ceny. Śledzić nową zawartość encji i flagi. Przy zmianie czasu i lokalnym dniu 23/25 h obliczenia i deduplikacja odbywają się **wyłącznie w UTC**, prezentacja w `Europe/Copenhagen`.

## 4. Reguła ekonomiczna

`C_buy[t] = buy_raw_price[t]` (wszystkie opłaty już zawarte).

`C_sell[t] = spot_raw_price[t] − 0.0215 DKK/kWh`.

Nawet jeśli `C_sell[t]` jest ujemna, zachować jej znak. Rachunek za zakup, przychód ze sprzedaży i koszt degradacji pozostają odrębnymi pozycjami funkcji celu. Nie przeliczać samych danych z atrybutu `tariffs` na drugą dopłatę.

Przykład **chwilowy** z podanych atrybutów `current_price` (nie z serii zaokrąglonej): `2.405502871680312 − 1.9222991216803123 = 0.4832037499999998 DKK/kWh` różnicy między zakupem a spot. Sprzedaż netto na tej samej podstawie: `1.9222991216803123 − 0.0215 = 1.9007991216803123 DKK/kWh`. Różnica 0,4832 nie jest dodatkową opłatą do ponownego naliczenia.

## 5. Scenariusze testowe mappera (symulacja, nie uruchomione)

- `PRICE-01`: `raw_today` z 24 godzinami, `raw_tomorrow = null`, `tomorrow_valid = false` → 24 godziny cen dla danej doby; brak jutra nie jest błędem.
- `PRICE-02`: godzina 08:00 20.10, zakup 2,406, spot 1,922 → sprzedaż 1,9005 DKK/kWh z **zaokrąglonej serii**, bez dodawania taryfy.
- `PRICE-03`: `current_price` 2,405502871680312 i 1,9222991216803123 vs seria 2,406 i 1,922 → kontrola spójności PASS w granicy precyzji listy, brak fikcyjnej korekty szeregu.
- `PRICE-04`: zakup ma `tomorrow_valid=true`, spot jeszcze `false` → brak kompletnego wspólnego planu transakcji na jutro.
- `PRICE-05`: obie flagi `true`, ale jedna lista `raw_tomorrow` jest `null` → jutro nie jest gotowe do planowania.
- `PRICE-06`: godzina 13:00 po nadejściu poprawnych danych jutra → plan przedłuża się tylko do końca **rzeczywiście** dostępnych cen, bez wpisywania 48h.
- `PRICE-07`: `next_data_update` zakupu 13:25:40 i spot 13:28:03, flagi `false` → czas nie jest dowodem nowych cen.
- `PRICE-08`: w czasie DST lokalna doba 23/25 h → parser akceptuje poprawne 23/25 rekordów, nie narzuca 24.
- `PRICE-09`: dwie lokalne godziny 02:00 przy jesiennej zmianie czasu, różne offsety → pozostają **dwoma** poprawnymi slotami UTC.
- `PRICE-10`: brak godziny wewnątrz `raw_today` → oznaczenie luki, bez imputacji i arbitrażu na nieznanej cenie.
- `PRICE-11`: spot ujemny −0,10 → cena sprzedaży −0,1215 DKK/kWh; nie obcinać do zera.
- `PRICE-12`: niepoprawna waluta, region, jednostka, timestamp bez offsetu lub `price=NaN` → odrzucenie danych z kodem przyczyny.
- `PRICE-13`: po przejściu z 23:59 na 00:00 aktualizuje się horyzont przy użyciu odpowiadających nowemu dniu list HA, bez zachowania przestarzałego `raw_today` jako przyszłej ceny.
- `PRICE-14`: wśród atrybutów zakupu są `tariffs` i `additional_tariffs` → wynik ceny wciąż równy `raw_*.price`, brak podwójnego naliczenia.
- `PRICE-15`: tablica `today` długości 25 podczas jesiennego DST → mapper nie identyfikuje godziny indeksami pozycji, tylko `raw_today[*].hour`.
- `PRICE-16`: listy kupna i spot różnią się momentem aktualizacji; nowe dane z jednej encji, stara druga → nowy plan tylko dla zweryfikowanego wspólnego horyzontu.
- `PRICE-17`: zmiana cen dziś w `raw_today` bez zmiany flagi jutra → nowa wersja cen i replan, mimo `tomorrow_valid=false`.
- `PRICE-18`: kwadrans 08:15–08:30 otrzymuje tę samą opublikowaną stawkę co przedział 08:00–09:00; indeksacja po UTC, bez interpolacji.

**Odbiór:** testy `PRICE` stanowią kontrakt do zaimplementowania przez Codexa, a nie zatwierdzenie działającego kodu. Format publikacji jest **ustalony** i nie powinien pozostawać zadaniem „dopiero ustalić z użytkownikiem”.
