# Lista do usunięcia / wyłączenia — serwer Linux

**Stan wiedzy: 15.10.2026.** Na podstawie wcześniejszych rozmów i testów. **Nie połączono się z serwerem, nie wykonano usuwania ani kontroli aktywnych procesów.**

## 1. Znany katalog starego projektu

```text
/home/damian/energy-co-pilot
~/energy-co-pilot
```

Historycznie użytkownik **ręcznie uruchamiał** skrypty z tego katalogu. Projekt tworzył plan, lecz nie wykazano, by wykonywał go w tle na falowniku. Samo ręczne uruchomienie nie dowodzi istnienia usługi systemowej.

## 2. Znane pliki — docelowo do usunięcia wraz z katalogiem, po kontroli i zabezpieczeniu

| Ścieżka względem `~/energy-co-pilot/` | Historyczny fakt | Działanie przed usunięciem |
| --- | --- | --- |
| `main.py` | użytkownik pracował z tym plikiem we wczesnych etapach | sprawdzić czy dotyczy wyłącznie Co-Pilot |
| `exporter.py` | użytkownik miał plik i uruchamiano eksport | zatrzymać ewentualny harmonogram, ocenić potrzebę danych |
| `data_loader.py` | użytkownik miał plik i uruchamiano loader | sprawdzić brak zależności innych projektów |
| `agent_llm.py` | zrelacjonowany komponent eksperymentów | archiwizacja źródła tylko jeśli jest potrzebna |
| `copilot_v2.py` | zrelacjonowany prototyp | j.w. |
| `copilot_v5.py` | użytkownik uruchamiał ręcznie | j.w. |
| `copilot_v5.2.py` | użytkownik uruchamiał, błędy integracji | j.w. |
| `Copilot_v5.4.py` | użytkownik później uruchamiał | j.w.; uwaga na wielkość liter nazwy |
| `agent.py` | historyczny moduł `HomeAssistantAPI` w projekcie | zweryfikować istnienie i użycie |
| `test_control.py` | historyczny test wywołania HA / lampy | zweryfikować i usunąć tylko lokalny skrypt testowy |
| `config.yaml` | historyczna konfiguracja `home_assistant.url` / `token` / `verify_ssl` | **sekret**: nie przenosić do publicznego repo; ustalić zależności i unieważnić dedykowany token |
| `ha_history.csv` | historyczny plik: 270 873 rekordy / 6 encji wg raportu | plik **może zawierać prywatne dane historyczne**; zdecydować o prywatnej kopii przed skasowaniem |
| `.venv/` | środowisko Python z `pandas` | usunąć razem z katalogiem dopiero po upewnieniu się, że nie jest współdzielone |
| `logic.txt` | historyczny tekst logiki | kopia źródłowej v5.1 jest w repo, ale wersji lokalnej nie porównano |

Nie oznacza to, że wszystkie te pliki nadal istnieją. Część pochodzi z historycznych relacji, a nie ze skanu serwera.

## 3. Elementy eksperymentalne — **sprawdzić istnienie, nie zakładać że są**

- [ ] `ha_api_client.py` — brak importu w v5.2; później proponowany.
- [ ] `policy_prompt.txt` — użytkownik zgłaszał brak tego pliku w trakcie próby v5.4.
- [ ] `exporter_consumption.py` oraz `ha_consumption_history.csv` — wspominane w propozycjach późniejszych eksperymentów; **nie ma potwierdzenia ich utworzenia**.
- [ ] Inne pliki `copilot_v*.py` / `Copilot_v*.py`, logi i pliki cache — tylko jeżeli są w katalogu.

## 4. Procesy, automatyczny start i zewnętrzne pozostałości — brak dowodu, że istnieją

- [ ] `crontab` użytkownika oraz ewentualne zadania systemowe uruchamiające `exporter.py`, `main.py` lub `copilot*.py`.
- [ ] Usługi `systemd` użytkownika i systemowe z `energy-co-pilot` / `copilot` w `ExecStart`.
- [ ] Kontenery Docker/Compose utworzone wyłącznie dla starego projektu, jeśli występują.
- [ ] Konfiguracje zewnętrznych supervisorów (np. `pm2`, `supervisord`), timerów lub skryptów autostartu, **jeżeli w ogóle były używane**.
- [ ] Konfiguracja sekretu dostępu HA, opcjonalnie klucza API LLM — **unieważnić tylko te, które są dedykowane temu projektowi**, oraz usunąć lokalne kopie dopiero po sprawdzeniu użycia.
- [ ] Zewnętrzne logi, kopie CSV i artefakty tymczasowe z nazwą projektu — po sprawdzeniu dat i właściciela.

**Nie usuwać globalnego Pythona, pakietów systemowych, Docker, Home Assistant, wspólnych bibliotek ani plików innych projektów.**

## 5. Polecenia do inwentaryzacji — wszystkie poniższe są tylko do odczytu

Na historycznym koncie serwera Linux:

```bash
ls -la ~/energy-co-pilot
find ~/energy-co-pilot -maxdepth 2 -type f -printf '%p\n'
crontab -l
systemctl --user list-unit-files --no-pager | grep -Ei 'copilot|energy.?co.?pilot'
systemctl list-unit-files --no-pager | grep -Ei 'copilot|energy.?co.?pilot'
docker ps -a --format '{{.Names}} {{.Image}}' | grep -Ei 'copilot|energy.?co.?pilot'
```

Dodatkowo obejrzeć definicje cron/systemd oraz uruchomione procesy — **sama nazwa zadania nie dowodzi jego właściciela**. Jeżeli `docker` lub `systemctl --user` nie jest dostępne, polecenie może zwrócić błąd; to nie jest dowód braku pozostałości.

## 6. Bezpieczna kolejność porządkowania (na później)

1. [ ] Potwierdzić co realnie jest na dysku, a co uruchamia się automatycznie.
2. [ ] Wyłączyć dedykowane procesy, timery i harmonogramy **tylko jeśli istnieją**; sprawdzić, czy nic innego od nich nie zależy.
3. [ ] Zdecydować, czy zachować **prywatną** kopię oryginalnych skryptów i CSV (repo GitHub zachowuje wyłącznie dokumentację).
4. [ ] Usunąć katalog `~/energy-co-pilot` dopiero po sprawdzeniu, że nie służy innym procesom; nie podajemy automatycznego `rm -rf`.
5. [ ] Unieważnić wyłącznie dedykowane, nieużywane już tokeny HA/LLM.
6. [ ] Potwierdzić, że nic nie próbuje wywoływać nieistniejącej ścieżki ani stale łączyć się z HA.

## Stan weryfikacji

| Obszar | Status |
| --- | --- |
| Katalog i historyczne ręczne skrypty | **Potwierdzone we wcześniejszych rozmowach**, nie skanowano serwera obecnie |
| Harmonogramy cron / systemd / Docker | **Niepotwierdzone** |
| Automatyczny wykonawca poleceń falownika | **Niepotwierdzony** |
| Usunięcie plików lub zatrzymanie usług | **Nie wykonywano** |

Zarchiwizowana lista oryginalnych plików i ich ról: [Technical baseline](../archive/energy-copilot-v5/docs/TECHNICAL_BASELINE.md), [Recovery inventory](../archive/energy-copilot-v5/docs/RECOVERY_INVENTORY.md).
