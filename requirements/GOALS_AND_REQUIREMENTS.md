# Energy Co-Pilot — cele i wymagania nowego rozwiązania

**Status:** wymagania użytkownika zebrane w odpowiedziach na pytania 1–36; 15.10.2026.  
**Etap:** definicja potrzeb — **bez wyboru oprogramowania, implementacji i działań na Home Assistant**.  
**Źródła:** odpowiedzi użytkownika w bieżącej rozmowie; informacje techniczne i rozbieżności historyczne pozostają w [archiwum](../archive/energy-copilot-v5/README.md).

## 1. Cel nadrzędny i priorytety

**Minimalizacja końcowego rachunku netto za energię elektryczną (DKK).** To nadrzędny priorytet, także gdy koliduje z bezwzględną maksymalizacją autokonsumpcji albo minimalizacją liczby kupionych kWh.

Cele dodatkowe / mierniki działania:
1. Zmniejszyć ilość energii importowanej z sieci (kWh).
2. Obniżyć średni, rzeczywisty koszt jednostki zakupionej energii (DKK/kWh).
3. Zwiększać autokonsumpcję energii PV, **jeżeli sprzyja to wynikowi ekonomicznemu**.
4. Sprzedawać nadwyżkę, ale tylko gdy jest to opłacalne.

**Nie wolno optymalizować średniej ceny zakupu w izolacji**: tańszy średni zakup przy większej ilości energii nie musi dawać niższego rachunku. Raportować osobno całościowy koszt netto, kWh importu i średni koszt kupowanej kWh.

Docelowo rachunek netto powinien uwzględniać kwotę za import (rzeczywistą cenę ze zmiennymi opłatami), przychód z eksportu netto oraz — na etapie kalkulowania decyzji o dodatkowym cyklu — koszt zużycia baterii i straty. Koszty stałe i zakres rozliczeń wymagają ustalenia w modelu ekonomicznym.

## 2. Dozwolone decyzje energetyczne

| Operacja | Decyzja użytkownika | Tryb |
| --- | --- | --- |
| Zasilanie domu z PV i magazynu | Tak | System / standardowa praca falownika |
| Ładowanie baterii z nadwyżki PV | Tak | Automatyczne, gdy ekonomicznie uzasadnione |
| Ładowanie baterii z sieci przy korzystnej cenie | **Tak, zdecydowanie** | Automatyczne na podstawie kalkulacji |
| Sprzedaż nadwyżki produkcji PV | Tak, tylko gdy jest ekonomicznie uzasadniona | Automatyczna (w ramach zweryfikowanych możliwości falownika) |
| Celowe rozładowanie baterii w celu sprzedaży do sieci | Tak, warunkowo | **Tylko po zatwierdzeniu użytkownika** |
| Zakup energii z sieci, magazynowanie i późniejsza odsprzedaż | **Dopuszczone** | Wyłącznie jeśli opłacalne i **po zatwierdzeniu sprzedaży** |
| Sterowanie dodatkowymi odbiornikami energii | Nie teraz; w przyszłości | Poza zakresem pierwszego wdrożenia |

Nie ma stałego obowiązku pełnej baterii przed wieczorem. **SOC może być niższy, jeśli jest to korzystniejsze finansowo i przewidziano możliwość ładowania następnego dnia.**

## 3. Magazyn, granice i zasada bezpieczeństwa

- Magazyn: 2 × BSLBATT LiFePO4, 51,2 V / 100 Ah / 5120 Wh.
- Pojemność **nominalna wyliczona ze specyfikacji modułów:** 10,24 kWh.
- Przyjęta w rozmowie użytkowa pojemność dla zakresu 20–100%: około 8 kWh; matematycznie 80% × 10,24 = **8,192 kWh przed stratami i ograniczeniami BMS**. Nie traktować 8,192 kWh jako zweryfikowanej dostępnej energii AC.
- Przyjęty dotychczas zakres pracy: SOC 20–100%, z uwzględnieniem ograniczeń BMS/falownika.
- **Brak wymogu utrzymywania osobnej rezerwy na zanik napięcia sieciowego.**
- **Nie narzucać stałego docelowego SOC „na noc”** z poprzedniego projektu.
- Koszt zużycia baterii musi być oszacowany w oparciu o parametry baterii, jej trwałość i koszt; użytkownik podał 19 000 DKK za komplet.
- Bieżące sterowanie nie może naruszać limitów sprzętowych ani odbierać falownikowi fabrycznych zabezpieczeń.

## 4. Ekonomika i ceny

- Sprzedaż i arbitraż oceniane **po wszystkich istotnych kosztach**, a nie po arbitralnym progu ceny spot (poprzedni próg 0,4 DKK/kWh **nie obowiązuje jako nowy wymóg**).
- Uwzględnić rzeczywistą cenę **zakupu** z opłatami, sprawność magazynowania, koszt degradacji oraz rzeczywiste wynagrodzenie netto za **sprzedaż**.
- W HA istnieją cena spot i rzeczywista cena zakupu z opłatami.
- **Nie ma gotowej encji ceny sprzedaży netto.** Bez jej wyznaczenia nie da się policzyć pełnego zysku ani rzetelnie podjąć decyzji o opłacalności eksportu.
- Umowa / rozliczenia: **Elforbundet / Vindstød**, północna Jutlandia, operator sieci **N1**; Vindstød obsługuje również sprzedaż nadwyżek.
- Dopuszcza się pobieranie danych zewnętrznych do lokalnego algorytmu.

## 5. Zasady automatyzacji i akceptacji

**Sterowanie automatyczne:** działania niewymagające zgody użytkownika mogą wykonywać się samodzielnie, gdy przejdą sprawdzenie zasad ekonomicznych, dostępności danych, limitów falownika i magazynu.

**Sprzedaż energii zgromadzonej w baterii:** wymaga **osobnego, wyraźnego zatwierdzenia**. Powiadomienie ma zawierać:
- proponowane godziny i ilość energii (kWh);
- przewidywany **dodatkowy** zysk netto w DKK i jego uzasadnienie (ceny zakupu/sprzedaży, straty, degradacja oraz utracona możliwość autokonsumpcji, jeżeli dotyczy);
- prognozowany SOC po operacji i dalszy plan zapewnienia energii;
- opcje „Zatwierdź” / „Odrzuć”.

**Brak odpowiedzi to brak zgody.** Po upływie terminu ważności propozycja musi przestać być wykonalna; długość tego terminu jest szczegółem do ustalenia w projekcie UI.

**Awaria algorytmu, braki danych lub utrata komunikacji:** system ma umożliwić **standardową, autonomiczną pracę fabrycznego sterowania falownika Deye**; sposób bezpiecznego powrotu trzeba dopiero ustalić i zweryfikować. Użytkownik nie chce funkcji backupu energetycznego.

## 6. Architektura — twarde ograniczenia i elementy nieprzesądzone

**Ustalono:**
- Obliczenia i sterowanie **lokalnie**, na istniejącej infrastrukturze z Home Assistant; zewnętrzne prognozy i ceny są dozwolone.
- Home Assistant jest dostępny w VM na serwerze.
- Falownik Deye ma fabryczny harmonogram ładowania i rozładowania i obsługuje wszystkie wcześniej wymienione funkcje (deklaracja użytkownika).
- Komunikacja falownika z HA **już działa** przez własny Modbus na ESP32 z **ESPHome/Wi-Fi**.
- Warstwą sterowania nowego rozwiązania mają być **istniejące encje HA**; **bez ingerowania w firmware ESP32, rejestry Modbus lub sposób komunikacji**, o ile później użytkownik nie zmieni zakresu.
- Nie ma obecnie dodatkowych zarządzalnych odbiorników; projekt ma być później rozszerzalny.

**Nie wybrano:** EMHASS, własnego Pythona, automatyzacji HA, solvera, algorytmu prognozy zużycia, interwału planowania i sposobu zarządzania harmonogramami Deye. Ich ocenę przeprowadzimy osobno.

## 7. Kryteria sukcesu i weryfikacja

Główny KPI: **rzeczywisty końcowy koszt netto energii (DKK)** w porównywalnych okresach, z analizą skutków importu, eksportu, kosztów cykli i czynników zewnętrznych.

Wskaźniki dodatkowe:
- ilość importu z sieci [kWh];
- **ważona energią** średnia cena zakupionej kWh [DKK/kWh] z opłatami;
- energia wysłana do sieci [kWh], przychód netto i koszt jego osiągnięcia [DKK];
- udział wykorzystanej lokalnie energii PV / autokonsumpcji;
- throughput magazynu oraz oszacowany koszt jego degradacji;
- liczba propozycji arbitrażu, decyzje użytkownika i rzeczywisty rezultat względem propozycji.

Przed wdrożeniem: porównać kandydatów na tych samych historycznych danych z HA z zachowaniem realistycznych możliwości sterowania. **Brak przyjętego jeszcze konkretnego progu minimalnej oszczędności**, np. w DKK/rok.

## 8. Granica tej specyfikacji

To komplet **uzgodnionych celów funkcjonalnych** z aktualnej serii pytań, nie komplet szczegółów implementacyjnych. Niewyjaśnione dane i testy przed wyborem technologii zebrano w [OPEN_ITEMS.md](OPEN_ITEMS.md). Nie zmieniono encji, harmonogramów, integracji ani kodu.
