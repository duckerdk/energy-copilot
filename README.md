# Energy Co-Pilot

Projekt prototypowego systemu zarządzania energią dla **Home Assistant**: instalacja fotowoltaiczna (PV), magazyn energii i sieć elektroenergetyczna.

**Stan dokumentacji: 15.10.2026.** Repozytorium zostało założone jako punkt odtworzenia wcześniejszych prac. **Nie zawiera jeszcze kodu źródłowego, konfiguracji Home Assistant ani działającego wdrożenia.** Opis poniżej dotyczy historycznych prac z 14.06.2025, a nie potwierdzonego dzisiaj systemu.

## Cel projektu

Planowanie zakupu, magazynowania, zużycia i sprzedaży energii przy uwzględnieniu:
- aktualnego SOC magazynu i zużycia domu;
- bieżących i prognozowanych cen energii;
- aktualnej i prognozowanej produkcji PV;
- zapotrzebowania na energię na noc i rezerwy bezpieczeństwa.

Priorytety opisane w logice v5.1: **zasilanie domu z PV**, zapewnienie energii na noc, a następnie ekonomicznie uzasadnione ładowanie i sprzedaż.

## Co zrobiono dotychczas

Według historycznego snapshotu v5.0 oraz rozmów projektowych:
- Opracowano warstwę wczytywania danych historycznych CSV do pandas (`HADataLoader`) oraz metody `get_daily_aggregates()` i `get_current_data()`.
- Rozwiązywano problemy UTC, dat bez strefy czasowej i serializacji dat do JSON.
- Zbudowano prototyp `EnergyPolicyAgent`, przekazujący dane do modelu językowego i generujący propozycję planu działań na 24 godziny.
- Opracowano i przyjęto **logikę sterowania v5.1**.
- Podejmowano dalsze próby rozwoju; część nie przeszła uruchomienia lub dawała błędne wyniki.

**Ważne:** historyczne deklaracje o „gotowym backendzie” nie są dowodem działania obecnego systemu. Kod ze wspomnianego dokumentu Canvas „Energy Copilot V5” nie jest obecnie dostępny w tym repozytorium.

## Aktualny zakres repozytorium

| Plik | Zawartość |
| --- | --- |
| [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) | Chronologia prac, fakty/ograniczenia, status wersji, kwestie niewyjaśnione |
| [docs/reference/logic_v5.1.txt](docs/reference/logic_v5.1.txt) | Źródłowy tekst logiki v5.1 |
| [docs/reference/snapshot_v5.0.txt](docs/reference/snapshot_v5.0.txt) | Historyczny snapshot v5.0 z 14.06.2025 |

## Stan realizacji

- **Udokumentowane:** cele, logika v5.1, interfejs encji HA, koncepcja architektury i historyczne wyniki prototypu.
- **Niepotwierdzone:** kompletność i odtwarzalność kodu, poprawność algorytmu, integracja z rzeczywistym falownikiem, automatyczne sterowanie oraz praca produkcyjna.
- **Do wykonania w osobnym kroku:** ocena istniejących prac i ewentualna rewizja założeń. Tego etapu nie wykonano w ramach niniejszego uporządkowania dokumentacji.

Dokumentacja świadomie odróżnia **założenia**, **deklaracje historyczne** i **wyniki potwierdzone uruchomieniem**. Nie należy traktować samej logiki opisowej jako gotowej automatyki sterującej.
