# Planner Lab — lokalne laboratorium optymalizacji

**Cel:** ręcznie ustawiać ceny zakupu i sprzedaży, produkcję PV, zużycie domu i SOC, a następnie oglądać decyzje **prawdziwego** silnika Energy Co-Pilot (pliki horizon_optimizer.py i planner.py). Narzędzie jest całkowicie niezależne od działającego Home Assistant, nie odczytuje jego danych ani nie steruje falownikiem.

## Uruchomienie — Windows

1. Pobierz / rozpakuj całe repozytorium duckerdk/energy-copilot (GitHub → Code → Download ZIP). Pozostaw oryginalny układ katalogów.
2. Zainstaluj Python 3.11 lub nowszy, jeżeli nie jest dostępny. Żadne dodatkowe pakiety nie są potrzebne.
3. Uruchom dwuklikiem **tools/planner_lab/start_windows.bat**, albo otwórz terminal w katalogu repozytorium i wpisz: **py -3 tools/planner_lab/server.py**
4. W przeglądarce otwórz **http://127.0.0.1:8765**. Zatrzymanie: Ctrl+C w konsoli.

Linux/macOS: z katalogu głównego repozytorium uruchom **python3 tools/planner_lab/server.py**. Przy zajętym porcie: dodaj **--port 8766** i otwórz nowy adres.

Serwer wiąże wyłącznie 127.0.0.1. Nie potrzebuje internetu, telemetrii, połączenia z HA ani falownikiem.

## Użytkowanie

1. Wybierz scenariusz przykładowy oraz horyzont (24, 48, 72 h). Kliknięcie **Wczytaj przykładowe dane** wypełnia tabelę.
2. Zmień SOC początkowy, pojemność, napięcie, limity prądu i sprawność.
3. Edytuj ceny (DKK/kWh), produkcję PV (średnia moc kW DC) i zużycie domu (średnia moc kW AC) osobno dla każdej godziny. Krok kwadransowy obliczany jest jako kW × 0,25 h. Ceny godzinowe są powtarzane przez 4 kwadranse. Godziny w tabeli wyświetlają lokalny czas Europe/Copenhagen; początek scenariusza jest zapisywany w UTC.
4. Kliknij **Oblicz plan**. Wykresy pokazują ładowanie z sieci, ładowanie PV, rozładowanie, cenę i SOC. W tabeli są decyzje godzinowe i koszty.
5. Możesz eksportować wejście do CSV (separator średnik), cały scenariusz do JSON i wyniki z rozdzielczością **15 minut** do CSV. Powtórzenie identycznego scenariusza pozwala porównać skutki pojedynczych zmian.

## Scenariusze

- **Tania noc / drogi wieczór:** ustaw SOC 25% i obserwuj ładowanie przed szczytem. Zmień cenę nocy na wysoką.
- **Słoneczny dzień:** obniż SOC i dodaj dużą produkcję w południe, by sprawdzić pozostawianie miejsca na PV.
- **Tania energia przy pełnej baterii:** ustaw wyższy SOC, później drogą energię i zmieniaj cenę pośrednią, sprawdzając, czy planer opóźnia rozładowanie.
- **Pochmurne 48 godzin:** analizuj zakup z sieci przy braku korzystnego PV.
- **Jednakowe ceny:** sprawdź, czy planer unika nieopłacalnego dodatkowego cyklu.

## Zakres i ograniczenia

- Wykorzystywane są oryginalne moduły produkcyjne Python, załadowane bez uruchamiania integracji Home Assistant. Nie ma kopii logiki w JavaScript ani zamodelowanych na sztywno decyzji.
- Każdy wynik weryfikuje produkcyjny symulator: SOC 20–100%, limity prądów 50/100 A, brak eksportu z baterii oraz brak równoczesnego importu i eksportu w kwadransie.
- Horyzont 1–72 godziny jest podawany ręcznie. Nie pobieramy prawdziwych prognoz PV, cen ani obciążenia z HA. Wejścia są świadomie sztuczne.
- Rozdzielczość modelu baterii to 0,10 kWh DC, koszt degradacji 0,40 DKK/kWh rozładowanej energii DC. Wycena pozostałej energii w baterii jest uproszczonym założeniem M3.
- **Nie ma jeszcze mapowania na sześć fizycznych okien TOU Deye** ani rzeczywistego baseline istniejącej konfiguracji falownika. Modelowana korzyść porównuje plan do braku cykli magazynu, a nie do faktycznej pracy falownika. Narzędzie służy do badania logiki, nie do generowania nastaw do wykonania.

Testy (w deweloperskim środowisku projektu): pytest tests/test_planner_lab.py -q.

## Przykład CSV

Kolumny oddzielone średnikiem (z kropką dziesiętną):

    buy;sell;pv_kw;home_kw
    0.6;0.3;0;0.5
    0.6;0.3;0;0.5
    2.5;0.3;0;1.0
    2.5;0.3;0;1.0
