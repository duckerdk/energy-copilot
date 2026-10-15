# Energy Co-Pilot — dane wymagające doprecyzowania na etapie wyboru technologii

**Status:** lista otwartych kwestii **implementacyjnych / ekonomicznych**, nie nowa ankieta i nie uzgodnione decyzje użytkownika. Cele funkcjonalne zebrano już w [GOALS_AND_REQUIREMENTS.md](GOALS_AND_REQUIREMENTS.md). Nie należy wracać do potwierdzania ustaleń, które użytkownik już przekazał.

| Priorytet | Kwestia do ustalenia | Dlaczego potrzebna | Zasada |
| --- | --- | --- | --- |
| Krytyczny | **Cena netto sprzedaży energii do Vindstød**: kontrakt, opłaty/potrącenia, jednostka i aktualizacja | Warunek wyliczenia rzeczywistej opłacalności eksportu i arbitrażu | **Nie wymyślać marż**; pozyskać reguły rozliczeń |
| Krytyczny | **Identyfikatory HA bieżących pomiarów**, zwłaszcza finalnej ceny zakupu, eksportu/importu i mocy baterii | Kontrakt wejścia dla wybranego systemu | Korzystać z istniejących encji, nie modyfikować ESPHome |
| Krytyczny | **Sposób wykonania sterowań poprzez encje HA oraz fabryczny harmonogram Deye** | Zapewnienie wykonalności planu i powrotu do normalnej pracy po błędzie | Nie grzebać w Modbus ani firmware; nie polegać na starym sprzecznym znaczeniu `number.sun12k_maximum_battery_grid_charge_current` bez potwierdzenia skutku |
| Wysoki | Obecna dostępność i szczegółowość prognoz PV z Forecast.Solar | Same „dziś/jutro” nie wystarczają do rozkładu godzinowego | Sprawdzić atrybuty HA / forecast API, nie zakładać danych z samego zrzutu |
| Wysoki | Rozdzielczość i kompletność **wieloletniej** historii HA, rozkład importu, zużycia, eksportu, SOC | Symulacja i uczciwe porównanie rozwiązań | Standardowy Recorder / Energy Dashboard może udostępniać różne agregacje; wymaga sprawdzenia |
| Wysoki | Efektywność AC↔bateria, ograniczenia mocy, BMS i minimalnego SOC | Poprawny bilans, ograniczenia harmonogramu, degradacja | Bez zgadywania wydajności i przeliczania 8 kWh na realny zasięg energetyczny |
| Wysoki | Model kosztu degradacji przy koszcie kompletu 19 000 DKK i danych BSLBATT | Odmowa nieopłacalnych cykli | Ustalić trwałość, zakres pracy i metodę rozliczenia kosztu |
| Wysoki | Procedura bezpiecznego oddania kontroli fabrycznemu Deye przy awarii aplikacji i sieci | Wymóg użytkownika: powrót do standardowej pracy falownika | Nie nadpisywać nieznanych bezpiecznych nastaw |
| Średni | Źródło/prognoza profilu zużycia domu oraz rozdzielczość cen i prognoz | Dobry plan czasowy i właściwa optymalizacja | Dokonać porównania na danych HA |
| Średni | Powiadomienie o sprzedaży z baterii, termin odpowiedzi, ponowna walidacja opłacalności | Nie dopuścić do nieautoryzowanego eksportu z magazynu | Każda sprzedaż z baterii tylko za zgodą; brak zgody = brak transakcji |
| Średni | Kryterium testu względem **fabrycznego trybu Deye** i okres analizy | Udowodnienie niższego rachunku netto, a nie samej jakości prognozy | Raportować kWh, średnią cenę, przychody i koszty |
| Niski | Sposób przyszłego dołączania sterowalnych odbiorników | Wymóg rozszerzalności | Bez implementowania teraz |

## Zasady analizy kandydatów

1. Sprawdzić, czy rozwiązanie **faktycznie** przyjmuje ceny zakupu z pełnymi opłatami oraz **osobno** cenę sprzedaży netto, a nie tylko spot.
2. Sprawdzić, czy obsłuży harmonogram i niezależne ładowanie z sieci, PV i rozładowanie baterii w granicach Deye **przez Home Assistant**.
3. Wymagać deterministycznej walidacji planu, symulacji i mechanizmu zgody dla eksportu z magazynu.
4. Porównać koszty utrzymania i złożoność: proste HA, lokalny EMHASS, mały własny optimizer, inne realne alternatywy.
5. Nie zakładać, że jakiekolwiek narzędzie będzie automatycznie kompatybilne z własnym zestawem encji HA.

To lista do etapu **analizy rozwiązań**, a nie polecenie wdrożenia lub ingerowania w urządzenia.
