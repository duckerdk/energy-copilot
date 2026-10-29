# Instrukcje pracy z Energy Co-Pilot (ChatGPT / Codex)

## Źródła i zakres
1. Przeczytaj [README](README.md), [REQUIREMENTS](requirements/REQUIREMENTS.md) i [OPEN_ITEMS](requirements/OPEN_ITEMS.md), a następnie tylko dokumenty i kod potrzebne do zadania. **REQUIREMENTS jest źródłem zatwierdzonych decyzji użytkownika**. Nie zastępuj ich historycznymi notatkami, komentarzami ani przypuszczeniami.
2. Oddzielaj: `user_confirmed`, `observed`, `implemented`, `tested`, `assumed`, `unverified`. Kod, CI i pomiary falownika są różnymi dowodami. Nie nazywaj testu automatycznego odbiorem fizycznym.
3. Zmieniaj wyłącznie potrzebny zakres. Nie usuwaj testów regresyjnych na podstawie wieku błędu. Nie twórz archiwum ani nowych dokumentów, gdy wystarczy zaktualizować istniejące. W repo nie zapisuj prywatnych diagnostyk HA i danych instalacji.
4. Integracja działa przez natywne encje/usługi Home Assistant; bez bezpośrednich zapisów Modbus, ESPHome, firmware ani LLM sterującego. `monitor` i `dry_run` nie wysyłają komend. Zmian fizycznych w rzeczywistej instalacji nie wykonuj w ramach pracy nad repozytorium.
5. Zachowaj politykę minimum SOC 20%, blokadę eksportu baterii bez osobnej zgody, `Load First`, ograniczenia BMS i zasadę **nigdy nie zapisuj Maximum Battery Discharge Current** (0 A zatrzymuje PV w tej instalacji). Szczegóły wyłącznie w [REQUIREMENTS](requirements/REQUIREMENTS.md) i [EXECUTION](requirements/EXECUTION.md).

## Definicja zakończenia zadania
6. Dla zmian kodu: implementacja, adekwatne testy, lint/format, kontrola diff, aktualizacja niezbędnej dokumentacji i raport, co zweryfikowano. Nie deklaruj uruchomienia testów, których faktycznie nie wykonano.
7. Jeśli użytkownik zleca **aktualizację wersji / wydanie / publikację do HACS**, zakończeniem jest **zweryfikowany GitHub Release z kompletnymi artefaktami**, nie commit, PR, merge, tag ani uruchomienie workflow. Procedura:
   - zaktualizuj manifest do nowej, nieużytej wersji SemVer, testy i wymagane dokumenty;
   - sprawdź wyniki CI; napraw problemy, nie zostawiaj czerwonych testów jako zakończonego wydania;
   - scal zweryfikowane zmiany do `main` zgodnie z uprawnieniami i regułami repozytorium;
   - uruchom/zweryfikuj pojedynczy workflow `.github/workflows/publish-version-on-main.yml` (automatycznie po zmianie manifestu albo ręcznie przez `workflow_dispatch` dla już scalonej wersji);
   - sprawdź końcowy status jobów, nie tylko start; sprawdź tag `vX.Y.Z`, publiczny, niebędący draftem GitHub Release i aktywa `energy_copilot.zip`, `BUILD_INFO.json`, `SHA256SUMS`;
   - porównaj wersję manifestu z tagiem i pochodzeniem paczki. HACS może wymagać odświeżenia; nie twierdź, że instalacja HA została wykonana bez dostępu do HA.
8. Prowadź nadzór nad GitHub Actions **w ramach bieżącego zadania** do sukcesu lub konkretnej, wykazanej blokady. Gdy run się nie powiedzie, odczytaj logi, popraw przyczynę, ponów weryfikację. Nie przerzucaj rutynowego monitorowania na użytkownika i nie deklaruj sukcesu po samym wyzwoleniu runa. Nie obiecuj pracy w tle, jeśli środowisko jej nie obsługuje.
9. Nigdy nie przenoś istniejącego taga wersji ani nie nadpisuj opublikowanego wydania. Nie wydawaj nowej paczki pod tym samym numerem. Gdy tag istnieje bez wydania, sprawdź **oryginalny commit taga** i wznów proces bez fałszowania historii.
10. Dokumentacyjne zmiany nie wymagają podnoszenia wersji ani instalacji HACS. Nie publikuj przypadkowego wydania tylko dlatego, że zmieniła się instrukcja.

## Raport końcowy
11. Podaj commit/PR, zakres zmian, dokładnie wykonane testy i ich wyniki oraz ewentualne ograniczenia. Przy wydaniu podaj **link do GitHub Release** i listę zweryfikowanych aktywów. Jeśli publikacja się nie udała, napisz wprost **NIEGOTOWE**, wskaż wynik workflow i jednoznaczny błąd — bez sugerowania, że merge oznacza gotową wersję.
