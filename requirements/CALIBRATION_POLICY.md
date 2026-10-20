# Kalibracja, parametry początkowe i ekonomiczne ryzyko modelu

**Cel:** rozstrzygnąć zasady pracy bez wymyślania wielkości, których jeszcze nie zmierzono. To nie są nowe pytania o wzory do użytkownika. Specyfikacja obowiązuje przy przygotowaniu `monitor/dry_run`; aktywne sterowanie ma osobne blokady P0.

## 1. Rozdzielenie wartości potwierdzonych, skonfigurowanych i zmierzonych

| Parametr | Wartość startowa/źródło | Status i użycie |
| --- | --- | --- |
| Pojemność nominalna | 10,24 kWh | Potwierdzona przez użytkownika; może być bazą odniesienia dla SOC, nie jest zmierzoną pojemnością użyteczną AC |
| SOC | 20–100% | Przyjęte przez użytkownika; faktyczne limity BMS mają pierwszeństwo |
| Moc ładowania/rozładowania | 2,5 kW / 5 kW | Zadeklarowane parametry pracy do walidacji na stronie AC/DC |
| Instalacja PV | 8,4 kWp, sprzężenie DC | Potwierdzone w projekcie; zmierzone granice zależne od falownika |
| Koszt zakupu magazynu | 19 000 DKK | Dane do szacowania marginalnego kosztu cyklu, nie koszt operacyjny doliczany w całości |
| Sprawność ładowania | 0,9487 | **Tylko wartość skonfigurowana w zrzucie diagnostycznym z 19.10.2026**, nie pomiar; dopuszczona jako jawny scenariusz startowy w dry-run |
| Sprawność rozładowania | 0,9487 | Taki sam status; produkt obu wartości ≈ 0,9000, ale nie stanowi dowodu sprawności każdego toru |
| Sprawność toru PV po DC | 0,97 | Wartość pomocnicza skonfigurowana w zrzucie; **nie zakładać**, że opisuje sprawność całego toru PV→bateria ani PV→AC |
| Cena sprzedaży | `sensor.energi_data_spotpris.raw_*.price` | **Bez żadnych potrąceń**; użyć dokładnie danych z HA |
| Koszt cyklu / liczba EFC | nieznane | Nie podstawiać trwale parametru z głowy; sposób obliczania poniżej |

**Zrzut Battery Controller jest jedynie historycznym źródłem wartości początkowych. Nowy optymalizator nie może zależeć od tej integracji ani odziedziczyć jej decyzji, czujników wirtualnych, waluty „EUR” czy kosztów kupna/sprzedaży.** W zrzucie nazwy źródłowych czujników są ukryte jako `REDACTED`. Sama konfiguracja nie dowodzi kalibracji na pracującym systemie.

## 2. Sprawność — sposób jej ustalenia

W modelu rozdzielać `η_pv_bat`, `η_grid_bat`, `η_bat_ac` i `η_pv_ac` w zgodzie z fizyczną stroną pomiaru. Dopuszczalne są różne wyniki przy różnym obciążeniu.

1. Ze zweryfikowanych punktów pomiarowych zintegrować moc z czasem w okresach stabilnego ładowania z sieci, ładowania z PV i rozładowania.
2. Wykluczyć okresy braków danych, curtailment nie dającego się odtworzyć, równoczesnych niejednoznacznych przepływów i zmian ustawień.
3. Jeśli pomiar energii po stronie baterii jest tylko BMS, uwzględnić jego niepewność i ewentualne działanie BMS/balansowanie. Nie identyfikować strat pojedynczego toru z samego bilansu licznika AC, jeśli tor DC nie jest obserwowalny.
4. Zweryfikować na odłożonym zbiorze danych, policzyć zakres niepewności i powtarzać kalibrację po zmianach baterii lub instalacji.
5. Przy braku danych mocowych można pokazać symulację z parametrami skonfigurowanymi, lecz oznaczyć `efficiency_quality = assumed`; nie deklarować zysku netto jako zweryfikowanego.

## 3. Marginalny koszt degradacji — bez arbitralnej stawki

Rozdzielamy dwie rzeczy: rachunek za energię i modelowy koszt utraty żywotności magazynu. Nie doliczamy całych 19 000 DKK do pojedynczego dnia.

Jako **jawny model testowy**, do analizy wrażliwości, można użyć EFC (equivalent full cycles), całkowitej energii przepływającej przez baterię i liczby referencyjnych cykli `N_EFC`:

`E_window = 10,24 × (1,00 − 0,20) = 8,192 kWh`

`cost_per_EFC = 19 000 / N_EFC [DKK/cykl]`

`cost_per_kWh_bidirectional_DC = 19 000 / (2 × 8,192 × N_EFC) [DKK/kWh przepływu przez baterię]`

Całkowity koszt marginalny uproszczonego cyklu to `cost_per_kWh_bidirectional_DC × (E_charge_in + E_discharge_out)`, **gdy obie energie są mierzone po tej samej stronie DC i zdefiniowane spójnie**. Przy pełnym cyklu od 20 do 100% i z powrotem energia `E_charge_in + E_discharge_out = 16,384 kWh` DC, co daje 19 000/N_EFC DKK na cykl. Straty AC/DC modelowane są osobno; nie doliczać ich drugi raz.

| `N_EFC` — ilustracyjna trwałość, **nie** dane producenta | Modelowy koszt pełnego EFC | Modelowy koszt 1 kWh przepływu DC łącznie |
| ---: | ---: | ---: |
| 3 000 | 6,3333 DKK | 0,3866 DKK |
| 6 000 | 3,1667 DKK | 0,1933 DKK |
| 10 000 | 1,9000 DKK | 0,1160 DKK |

**Uwaga:** liczba EFC to ilustracja, nie potwierdzona specyfikacja BSLBATT ani prognoza czasu wymiany. Rzeczywista degradacja zależy od głębokości cyklu, temperatury, C-rate, SOC i starzenia kalendarzowego; koszt *marginalny* może znacząco odbiegać od liniowego amortyzowania pierwotnego zakupu. Podstawową decyzję ekonomiczną testować dla kilku możliwych modeli i tylko potem przyjąć profil produkcyjny.

## 4. Czy wykonać marginalnie opłacalny cykl?

**Przyjęta zasada użytkownika:** operacja z niepewną dodatnią korzyścią po stratach i degradacji nie jest automatycznie wymuszana.

- Dla porównywalnych wariantów policzyć `incremental_gain_dkk`, oddzielnie koszt fakturowy, degradację, stratę fizyczną, końcową wartość SOC oraz ryzyko.
- Jeżeli wiarygodny wynik jest dodatni nawet po uwzględnieniu rozsądnego zakresu niepewności → dopuścić do planowania (nie oznacza uprawnienia do wykonania).
- Jeżeli znak wyniku zmienia się między wiarygodnymi wariantami kalibracji → `benefit_uncertain`, preferować brak **dodatkowego** cyklu lub niepotrzebnego przełączenia; pokazać dlaczego i z jakimi liczbami.
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
- `CAL-04`: pełen EFC daje odpowiednio 6,3333/3,1667/1,9000 DKK przy trzech ilustracyjnych N.
- `CAL-05`: przy wynikach przeciwnych znaków w rozsądnych parametrach degradowania brak uruchomienia dodatkowego cyklu w automatyce; przy `dry_run` pokazany zakres.
- `CAL-06`: brak reprezentatywnych migawek PV → `insufficient_history`, bez fałszywych procentów pewności.
- `CAL-07`: zmiana parametru kalibracji aktualizuje wersję modelu i zapis uzasadnienia w [DECISION_LOGGING.md](DECISION_LOGGING.md).

**Granica rozstrzygnięcia:** matematyczna zasada i sposób kalibracji są zdefiniowane; faktyczne `N_EFC`, parametry fizyczne i dokładność prognoz wymagają danych, a nie decyzji użytkownika „z głowy”.
