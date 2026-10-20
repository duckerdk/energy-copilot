# Kalibracja, parametry początkowe i ekonomiczne ryzyko modelu

**Cel:** rozstrzygnąć zasady pracy bez wymyślania wielkości, których jeszcze nie zmierzono. To nie są nowe pytania o wzory do użytkownika. Specyfikacja obowiązuje przy przygotowaniu `monitor/dry_run`; aktywne sterowanie ma osobne blokady P0.

## 1. Rozdzielenie wartości potwierdzonych, skonfigurowanych i zmierzonych

| Parametr | Wartość startowa/źródło | Status i użycie |
| --- | --- | --- |
| Pojemność nominalna | 10,24 kWh | Potwierdzona przez użytkownika; może być bazą odniesienia dla SOC, nie jest zmierzoną pojemnością użyteczną AC |
| SOC | **20–100%** | **Twarde minimum polityki Co-Pilot = 20%** (potwierdzone 20.10.2026); BMS/falownik mogą wymagać wyższego minimum. Plan nigdy nie zakłada celowego rozładowania poniżej 20% |
| Moc ładowania/rozładowania | 2,5 kW / 5 kW | Zadeklarowane parametry pracy do walidacji na stronie AC/DC |
| Instalacja PV | 8,4 kWp, sprzężenie DC | Potwierdzone w projekcie; zmierzone granice zależne od falownika |
| Koszt zakupu magazynu | 19 000 DKK | Dane do szacowania marginalnego kosztu cyklu, nie koszt operacyjny doliczany w całości |
| Sprawność ładowania | 0,9487 | **Tylko wartość skonfigurowana w zrzucie diagnostycznym z 19.10.2026**, nie pomiar; dopuszczona jako jawny scenariusz startowy w dry-run |
| Sprawność rozładowania | 0,9487 | Taki sam status; produkt obu wartości ≈ 0,9000, ale nie stanowi dowodu sprawności każdego toru |
| Sprawność toru PV po DC | 0,97 | Wartość pomocnicza skonfigurowana w zrzucie; **nie zakładać**, że opisuje sprawność całego toru PV→bateria ani PV→AC |
| Cena sprzedaży | `sensor.energi_data_spotpris.raw_*.price` | **Bez żadnych potrąceń**; użyć dokładnie danych z HA |
| Koszt degradacji baterii | **0,40 DKK/kWh energii rozładowanej z baterii DC** | **Stała decyzja użytkownika 20.10.2026**, stosować do wszystkich porównań ekonomicznych, w tym ładowania z sieci; nie estymować z ceny zakupu baterii |

**Zrzut Battery Controller jest jedynie historycznym źródłem wartości początkowych. Nowy optymalizator nie może zależeć od tej integracji ani odziedziczyć jej decyzji, czujników wirtualnych, waluty „EUR” czy kosztów kupna/sprzedaży.** W zrzucie nazwy źródłowych czujników są ukryte jako `REDACTED`. Sama konfiguracja nie dowodzi kalibracji na pracującym systemie.

## 2. Sprawność — sposób jej ustalenia

W modelu rozdzielać `η_pv_bat`, `η_grid_bat`, `η_bat_ac` i `η_pv_ac` w zgodzie z fizyczną stroną pomiaru. Dopuszczalne są różne wyniki przy różnym obciążeniu.

1. Ze zweryfikowanych punktów pomiarowych zintegrować moc z czasem w okresach stabilnego ładowania z sieci, ładowania z PV i rozładowania.
2. Wykluczyć okresy braków danych, curtailment nie dającego się odtworzyć, równoczesnych niejednoznacznych przepływów i zmian ustawień.
3. Jeśli pomiar energii po stronie baterii jest tylko BMS, uwzględnić jego niepewność i ewentualne działanie BMS/balansowanie. Nie identyfikować strat pojedynczego toru z samego bilansu licznika AC, jeśli tor DC nie jest obserwowalny.
4. Zweryfikować na odłożonym zbiorze danych, policzyć zakres niepewności i powtarzać kalibrację po zmianach baterii lub instalacji.
5. Przy braku danych mocowych można pokazać symulację z parametrami skonfigurowanymi, lecz oznaczyć `efficiency_quality = assumed`; nie deklarować zysku netto jako zweryfikowanego.

## 3. Stały koszt degradacji — decyzja użytkownika

**Przyjęta stawka:** `battery_degradation_cost_dkk_per_kwh = 0.40` DKK/kWh, określona przez użytkownika 20.10.2026. To koszt ekonomiczny eksploatacji magazynu, **nie** składnik ceny zakupu energii z HA ani minimalna cena eksportu PV (ta ostatnia niezależnie wynosi 0,40 DKK/kWh).

**Konwencja rozliczenia w modelu:** naliczać **raz od energii rozładowanej z baterii na jej zaciskach DC** (`E_battery_discharge_dc_kwh`), bez ponownego naliczania przy wcześniejszym ładowaniu:

`Cost_degradation_DKK = 0.40 * E_battery_discharge_dc_kwh`

Przykład: 2 kWh rozładowania z baterii DC kosztuje modelowo 0,80 DKK zużycia baterii. Cena zakupu energii, sprawności konwersji i koszt degradacji to odrębne składniki. Żadnego kosztu nie naliczać dwukrotnie za ładowanie i rozładowanie tego samego cyklu.

**Przy zakupie energii w celu późniejszego ładowania i rozładowania** planner musi już podczas decyzji o zakupie uwzględnić przewidywany koszt przyszłego rozładowania, straty energii i wartość SOC po horyzoncie. To, że koszt księgowany jest na przepływie rozładowania, nie pozwala traktować taniego ładowania jako darmowego cyklu. Ta sama stawka dotyczy energii uprzednio zgromadzonej z PV.

To jest **parametr polityki ekonomicznej wybrany przez użytkownika**, nie zmierzona degradacja BSLBATT ani wyliczenie z 19 000 DKK i liczby cykli. Nie blokować planera z powodu nieznanego `N_EFC`; nie zastępować tej stawki autonomiczną estymacją.

## 4. Czy wykonać marginalnie opłacalny cykl?

**Przyjęta zasada użytkownika:** operacja z niepewną dodatnią korzyścią po stratach i degradacji nie jest automatycznie wymuszana.

- Dla porównywalnych wariantów policzyć `incremental_gain_dkk`, oddzielnie koszt fakturowy, degradację, stratę fizyczną, końcową wartość SOC oraz ryzyko.
- Jeżeli wiarygodny wynik jest dodatni nawet po uwzględnieniu rozsądnego zakresu niepewności → dopuścić do planowania (nie oznacza uprawnienia do wykonania).
- Jeżeli znak wyniku zmienia się między wiarygodnymi wariantami sprawności i prognozy (przy **stałej** degradacji 0,40 DKK/kWh) → `benefit_uncertain`, preferować brak **dodatkowego** cyklu lub niepotrzebnego przełączenia; pokazać dlaczego i z jakimi liczbami.
- **Obowiązuje próg podany przez użytkownika:** minimalna cena eksportu PV `0,40 DKK/kWh` z `sensor.energi_data_spotpris` (konfigurowalna wartość startowa). Nie stosować progów arbitralnych do innych decyzji ekonomicznych. [PV_EXPORT_POLICY.md](PV_EXPORT_POLICY.md).
- Realizować zwykłą standardową pracę falownika zgodnie z dotychczasowym trybem, jeśli automat nie może wykazać dodatniego wyniku zmiany.

## 5. Prognozy i model końcowego SOC

- PV: zapisywać historyczne **wersje prognoz** sprzed daty produkcji. Walidować tylko na okresach bez ograniczania PV i z potwierdzonym punktem pomiaru. Brak historii daje `insufficient_history`.
- Zużycie domu: profil co 15 min budowany z historii z podziałem na porę dnia, dzień tygodnia i sezon, o ile dane na to pozwalają; parametry adaptacyjne oceniane walk-forward.
- Przyszłe ceny: **nie uzupełniać** po ostatnim opublikowanym slocie. Gdy prognozy PV i zużycia wykraczają poza ceny, posłużyć się historycznie skalibrowaną wartością energii końcowej (`-V_terminal(E_end)`) albo jawnie zgłosić jej niepewność. Metoda: [FORECAST_POLICY.md](FORECAST_POLICY.md).
- Punktowe prognozy podczas rozruchu są dopuszczone **do prezentacji**. Do decyzji wykonawczej potrzebna jest rzetelna ocena opłacalności po błędach wejściowych.

## 6. Testy odbioru kalibracji

- `CAL-01`: parametry 0,9487/0,97 z konfiguracji obcej integracji otrzymują status `assumed`, a nie `measured`.
- `CAL-02`: dwa pomiary tej samej energii DC i AC nie są dodawane jako dwa źródła PV.
- `CAL-03`: koszt fizycznych strat w rachunku nie jest ponownie doliczany jako osobna „opłata za straty”.
- `CAL-04`: rozładowanie 2 kWh DC → degradacja 0,80 DKK; wcześniejsze ładowanie tych 2 kWh nie powoduje drugiej opłaty.
- `CAL-05`: zakup energii do ładowania z sieci musi porównać przyszłą oszczędność z ceną zakupu, stratami i degradacją 0,40 DKK/kWh przyszłego rozładowania; gdy zysk niepewny, brak dodatkowego cyklu.
- `CAL-06`: brak reprezentatywnych migawek PV → `insufficient_history`, bez fałszywych procentów pewności.
- `CAL-07`: zmiana parametru kalibracji aktualizuje wersję modelu i zapis uzasadnienia w [DECISION_LOGGING.md](DECISION_LOGGING.md).

**Granica rozstrzygnięcia:** koszt degradacji i granica SOC to decyzje użytkownika; parametry fizyczne i dokładność prognoz wymagają danych, a nie kolejnych pytań o stawkę cyklu.
