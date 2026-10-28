"""Persistent technical audit with readable native Home Assistant activity/logs."""

import logging
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
RETENTION_DAYS = 30
MAX_EVENTS = 6000
_LOCAL_TIMEZONE = ZoneInfo("Europe/Copenhagen")
_ACTIVITY_EVENTS = {
    "armed",
    "manual_stop",
    "stop",
    "waiting",
    "planned",
    "decision",
    "applied",
    "blocked",
    "recovered",
    "halted",
    "failure",
}

_ACTION_NAMES = {
    "grid_charge": "ładowanie baterii z sieci",
    "battery_discharge": "zasilanie domu z baterii",
    "pv_charge": "ładowanie baterii z instalacji PV",
    "grid_import": "zasilanie domu z sieci z zachowaniem energii baterii",
    "idle": "brak aktywnego ładowania i rozładowania baterii",
}

_REASON_NAMES = {
    "automatic_mode_or_user_arm": "Tryb automatyczny jest aktywny.",
    "next_complete_quarter_not_started": "Plan rozpoczyna się od kolejnego pełnego kwadransa.",
    "controller:input_or_plan_unavailable": "Niekompletne dane lub brak aktualnego planu.",
    "fresh_valid_measurements_and_plan": "Pomiary i plan są ponownie poprawne.",
    "controller:manual_stop": "Sterowanie zostało zatrzymane ręcznie.",
    "controller:minimum_soc": "Osiągnięto minimalny dopuszczalny poziom baterii.",
    "controller:invalid_measurements": "Nieprawidłowe pomiary baterii.",
    "controller:outside_policy": "SOC lub napięcie poza dozwolonym zakresem.",
    "controller:plan_missing": "Brak planu na bieżący kwadrans.",
    "controller:no_current_or_next_quarter": "Brak bieżącego lub następnego kwadransa w planie.",
    "controller:recovery_required": "Wymagana kontrola po niepewnym wyniku zapisu.",
    "controller:invalid_dispatch": "Nieprawidłowe wartości planu wykonawczego.",
    "controller:negative_dispatch": "Plan zawiera ujemny przepływ energii.",
    "controller:simultaneous_flow": "Plan wymaga jednoczesnego ładowania i rozładowania.",
    "controller:grid_current_limit": "Przekroczony dopuszczalny limit ładowania z sieci.",
    "controller:charge_plan_without_grid_current": "Plan ładowania nie zawiera odpowiedniego limitu prądu.",
    "planner:internal_error": "Wystąpił wewnętrzny błąd planowania.",
}
_ISSUE_NAMES = {
    "invalid_input": "niepoprawny odczyt",
    "forecast_unavailable_or_invalid": "brak poprawnej prognozy PV",
    "forecast_entry_missing": "brak konfiguracji prognozy PV",
    "home_predates_source_recovery": "odczyt zużycia domu jest starszy niż dane źródłowe",
    "recorder_recording_gap": "luka w danych historycznych",
    "historical_quality_unverifiable": "niepotwierdzona jakość danych historycznych",
    "forecast_storage_failed": "błąd archiwizacji prognozy",
    "home_profile_unverified": "profil zużycia domu nie został zweryfikowany",
    "negative_home_normalized": "skorygowano ujemny odczyt zużycia domu",
    "recorder_pause_history_unverifiable": "brak potwierdzenia ciągłości zapisu Recorder",
    "forecast_observed_after_period_start": "prognoza PV zaktualizowana po rozpoczęciu przedziału",
}


def _number(value, unit="", digits=2):
    """Format values for a human, omitting unknowns rather than inventing zeros."""
    if value is None:
        return None
    try:
        formatted = f"{float(value):.{digits}f}".replace(".", ",")
    except ValueError, TypeError, OverflowError:
        return None
    return f"{formatted} {unit}".strip()


def _local_time(value):
    if not isinstance(value, str):
        return "nieznany czas"
    try:
        point = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if point.tzinfo is None:
            return "nieznany czas"
        return point.astimezone(_LOCAL_TIMEZONE).strftime("%H:%M")
    except ValueError:
        return "nieznany czas"


def _reason(value):
    if not value:
        return "Powód nie został podany."
    if value.startswith("CommandRejected:"):
        value = value.removeprefix("CommandRejected:")
    if value in _REASON_NAMES:
        return _REASON_NAMES[value]
    if "tou_not_enabled" in value:
        return "Harmonogram Time of Use nie jest włączony w falowniku."
    if "tou_schedule_mismatch" in value:
        return "Godziny okien Time of Use różnią się od oczekiwanej konfiguracji."
    if "device_write_result_uncertain" in value:
        return "Nie można potwierdzić wyniku polecenia wysłanego do falownika."
    # Unknown codes remain in the technical archive, not the human Activity view.
    return "Nieznany problem wykonania; szczegóły zapisano w diagnostyce."



def _decision_evidence(entry):
    """Report measured/optimized quantities; never invent a counterfactual cause."""
    action = entry.get("action")
    buy = entry.get("buy_dkk_per_kwh")
    later_price = entry.get("later_discharge_buy_dkk_per_kwh")
    later_at = entry.get("later_discharge_start_utc")
    later_charge_price = entry.get("later_grid_charge_buy_dkk_per_kwh")
    later_charge_at = entry.get("later_grid_charge_start_utc")
    if action == "battery_discharge":
        dc_kwh = entry.get("battery_discharge_dc_kwh")
        efficiency = entry.get("battery_to_ac_efficiency")
        degradation = entry.get("degradation_cost_dkk")
        if None not in (dc_kwh, efficiency, buy, degradation):
            ac_kwh = float(dc_kwh) * float(efficiency)
            avoided = ac_kwh * float(buy)
            return (
                f"Rozładowanie { _number(dc_kwh, 'kWh DC') } "
                f"zastępuje { _number(ac_kwh, 'kWh AC') } zakupu z sieci "
                f"o wartości { _number(avoided, 'DKK') } przy obecnej cenie. "
                f"Modelowy koszt degradacji tej operacji: "
                f"{ _number(degradation, 'DKK') }; "
                f"bilans bez wpływu na dalszy SOC: "
                f"{ _number(avoided - float(degradation), 'DKK') }."
            )
        return (
            "Model przewiduje zasilanie domu energią z baterii. "
            "Brak danych do obliczenia jego bieżącej korzyści."
        )
    if action == "grid_charge":
        if later_at and later_price is not None:
            difference = (
                _number(float(later_price) - float(buy), "DKK/kWh")
                if buy is not None
                else None
            )
            return (
                f"W dalszej części tego planu przewidziano rozładowanie "
                f"o {_local_time(later_at)}, przy cenie zakupu "
                f"{_number(later_price, 'DKK/kWh')}. "
                + (
                    f"Różnica względem obecnej ceny: {difference}. "
                    if difference
                    else ""
                )
                + "To porównanie cen, nie obliczony koszt alternatywnego planu; "
                "do oceny opłacalności dochodzą straty i degradacja."
            )
        return (
            "Plan przewiduje pobór energii do baterii, ale nie pokazuje "
            "późniejszego rozładowania w dostępnym horyzoncie. "
            "Nie ma obliczonego wariantu alternatywnego uzasadniającego ładowanie."
        )
    if action == "grid_import":
        amount = _number(entry.get("planned_grid_import_kwh"), "kWh AC")
        if later_at and later_price is not None:
            message = (
                f"Zamiast rozładować baterię teraz, plan kupuje "
                f"{amount or 'nieznaną ilość energii'} z sieci. "
                f"Pierwsze późniejsze rozładowanie zaplanowano na "
                f"{_local_time(later_at)}, przy cenie "
                f"{_number(later_price, 'DKK/kWh')}. "
            )
            if buy is not None:
                if float(later_price) > float(buy) + 1e-6:
                    message += "Późniejsza cena jest wyższa od obecnej. "
                elif float(later_price) < float(buy) - 1e-6:
                    message += "Późniejsza cena jest niższa od obecnej. "
                else:
                    message += "Cena późniejszego rozładowania jest taka sama. "
            return (
                message
                + "Nie obliczono wariantu z wymuszonym rozładowaniem teraz, "
                "więc dokładna przyczyna oszczędzania baterii nie jest potwierdzona."
            )
        message = (
            f"Plan kupuje {amount or 'energię'} z sieci i nie rozładowuje "
            "baterii w tym kwadransie. "
        )
        if later_charge_at and later_charge_price is not None:
            message += (
                f"Następne ładowanie z sieci jest zaplanowane "
                f"na {_local_time(later_charge_at)} po "
                f"{_number(later_charge_price, 'DKK/kWh')}. "
            )
        return (
            message
            + "Brak późniejszego rozładowania w bieżącym planie. "
            "Bez osobnego wariantu nie można wskazać jednoznacznej przyczyny."
        )
    if action == "pv_charge":
        pv = entry.get("pv_forecast_dc_kwh")
        home = entry.get("home_forecast_ac_kwh")
        charge = entry.get("pv_charge_dc_kwh")
        if None not in (pv, home, charge):
            return (
                f"Przy prognozie produkcji PV {_number(pv, 'kWh DC')} "
                f"i zużycia domu {_number(home, 'kWh AC')} "
                f"model kieruje {_number(charge, 'kWh DC')} energii PV "
                "do baterii, zamiast ładować ją z sieci. "
                "To jest przepływ wybrany w planie, nie dowód przewagi "
                "nad ewentualną sprzedażą tej energii."
            )
        return "Plan przydziela dostępną energię PV do ładowania baterii."
    if action == "idle":
        return (
            "W tym kwadransie plan nie przewiduje aktywnego ładowania "
            "ani rozładowania. Nie wyznaczono osobnego kosztu "
            "alternatywnych akcji."
        )
    return "Brak danych umożliwiających wyjaśnienie decyzji."


def readable_event(entry):
    """A concise Polish statement: decision, cause, inputs and execution result."""
    event = entry["event"]
    reason = entry.get("reason")
    quarter = _local_time(entry.get("quarter_start_utc"))
    if event in {"planned", "decision"}:
        action = _ACTION_NAMES.get(entry.get("action"), "nieznana akcja planera")
        parts = [
            f"{'Plan' if event == 'planned' else 'Decyzja wykonawcy'} na {quarter}: {action}."
        ]
        soc = _number(entry.get("soc_observed_pct"), "%", 1)
        target = _number(entry.get("soc_planned_end_pct"), "%", 1)
        if soc and target:
            parts.append(f"SOC: {soc} → planowane {target}.")
        elif soc:
            parts.append(f"SOC: {soc}.")
        buy = _number(entry.get("buy_dkk_per_kwh"), "DKK/kWh")
        sell = _number(entry.get("sell_dkk_per_kwh"), "DKK/kWh")
        if buy:
            parts.append(f"Zakup: {buy}.")
        if sell:
            parts.append(f"Sprzedaż: {sell}.")
        pv = _number(entry.get("pv_forecast_dc_kwh"), "kWh")
        home = _number(entry.get("home_forecast_ac_kwh"), "kWh")
        if pv:
            parts.append(f"Prognoza PV: {pv}/15 min.")
        if home:
            parts.append(f"Prognoza domu: {home}/15 min.")
        energy_key = {
            "grid_charge": "grid_charge_ac_kwh",
            "battery_discharge": "battery_discharge_dc_kwh",
            "pv_charge": "pv_charge_dc_kwh",
            "grid_import": "planned_grid_import_kwh",
        }.get(entry.get("action"))
        if energy_key:
            energy = _number(entry.get(energy_key), "kWh")
            if energy:
                parts.append(f"Energia w planie: {energy}/15 min.")
        parts.append("Wyjaśnienie: " + _decision_evidence(entry))
        return " ".join(parts)
    if event == "applied":
        grid = _number(entry.get("grid_limit_a"), "A", 0)
        discharge = _number(entry.get("discharge_limit_a"), "A", 0)
        soc = _number(entry.get("target_tou_soc"), "%", 0)
        charge = "włączone" if entry.get("target_tou_grid_charge") else "wyłączone"
        parts = [
            f"Nastawy falownika dla kwadransa {quarter} zostały wysłane i odczytane."
        ]
        if grid:
            parts.append(f"Limit ładowania z sieci: {grid}.")
        if discharge:
            parts.append(f"Limit rozładowania: {discharge}.")
        if soc:
            parts.append(f"Cel SOC w aktywnym oknie: {soc}.")
        parts.append(f"Zezwolenie na ładowanie z sieci: {charge}.")
        parts.append(
            "Odczyt nastaw nie potwierdza jeszcze rzeczywistego przepływu energii."
        )
        return " ".join(parts)
    if event == "armed":
        return "Sterowanie automatyczne zostało uzbrojone (ARM). " + _reason(reason)
    if event == "manual_stop":
        return "Ręcznie zatrzymano sterowanie automatyczne (STOP)."
    if event == "stop":
        return "Sterowanie automatyczne zostało zatrzymane."
    if event == "waiting":
        return "Oczekiwanie na rozpoczęcie następnego kwadransa. " + _reason(reason)
    if event == "blocked":
        missing = entry.get("missing_measurements") or []
        issues = entry.get("issue_codes") or []
        details = []
        if missing:
            details.append("Brak pomiarów: " + ", ".join(missing) + ".")
        if issues:
            details.append(
                "Problemy z danymi: "
                + ", ".join(_ISSUE_NAMES.get(item, item) for item in issues[:5])
                + "."
            )
        state = (
            "ARM pozostaje aktywny; nowe polecenia są wstrzymane."
            if entry.get("phase") != "device_write_result_uncertain"
            else "Wynik zapisu wymaga kontroli."
        )
        return (
            "Wstrzymano wykonywanie planu. "
            + _reason(reason)
            + " "
            + " ".join(details + [state])
        )
    if event == "recovered":
        return "Wznowiono wykonywanie planu po odzyskaniu poprawnych danych. ARM pozostał aktywny."
    if event in {"halted", "failure"}:
        return (
            "Zatrzymano sterowanie po błędzie wykonania. "
            + _reason(reason)
            + " Wymagana kontrola przed ponowieniem poleceń."
        )
    if event == "plan_status":
        status = entry.get("planning_status")
        if status == "preview":
            return (
                "Planer przygotował plan. Pokrycie danych: "
                + str(entry.get("coverage") or "nieznane")
                + "."
            )
        if status == "blocked":
            return "Planer nie może przygotować planu. " + _reason(reason)
        return f"Status planera: {status or 'nieznany'}."
    if event == "input_quality":
        quality = entry.get("quality")
        if quality == "valid":
            return "Bieżące dane sterowania są poprawne."
        issues = entry.get("issue_codes") or []
        return f"Jakość bieżących danych: {quality or 'nieznana'}. " + (
            "Problemy: " + ", ".join(_ISSUE_NAMES.get(i, i) for i in issues[:5]) + "."
            if issues
            else ""
        )
    return "Energy Co-Pilot: odnotowano zdarzenie sterownika. " + _reason(reason)


class DecisionJournal:
    """Persist technical evidence and publish readable events to native HA views."""

    def __init__(self, hass, entry_id):
        self.hass = hass
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.decisions")
        self.entries = []
        self.available = True
        self.error = None

    async def async_load(self):
        try:
            saved = await self.store.async_load()
            if saved is not None:
                entries = saved.get("entries")
                if not isinstance(entries, list):
                    raise ValueError("invalid_decision_journal")
                self.entries = [item for item in entries if isinstance(item, dict)]
            self._trim()
        except Exception as exc:  # A corrupt archive must never stop the controller.
            self.available = False
            self.error = f"{type(exc).__name__}:{exc}"
            _LOGGER.error(
                "Energy Co-Pilot: niedostępne archiwum decyzji: %s", self.error
            )

    def _trim(self):
        cutoff = (dt_util.utcnow() - timedelta(days=RETENTION_DAYS)).isoformat()
        self.entries = [
            item
            for item in self.entries
            if isinstance(item.get("time_utc"), str) and item["time_utc"] >= cutoff
        ][-MAX_EVENTS:]

    def record(self, event, *, reason=None, **details):
        entry = {
            "decision_id": str(uuid4()),
            "time_utc": dt_util.utcnow().isoformat(),
            "event": event,
            "reason": reason,
            **details,
        }
        try:
            message = readable_event(entry)
            if event in {"halted", "failure"}:
                _LOGGER.error("Energy Co-Pilot: %s", message)
            elif event == "blocked" or (
                event == "input_quality" and entry.get("quality") != "valid"
            ):
                _LOGGER.warning("Energy Co-Pilot: %s", message)
            else:
                _LOGGER.info("Energy Co-Pilot: %s", message)
            # The native logbook_entry bus event is consumed by Home Assistant's
            # Activity integration. Keep activity concise, not per-30-second polling.
            if event in _ACTIVITY_EVENTS or (
                event == "plan_status" and entry.get("planning_status") == "blocked"
            ):
                self.hass.bus.async_fire(
                    "logbook_entry",
                    {
                        "name": "Energy Co-Pilot",
                        "message": message,
                        "domain": DOMAIN,
                    },
                )
        except Exception:
            # Presentation must never interrupt the controller or technical audit.
            _LOGGER.exception(
                "Energy Co-Pilot: nie udało się opublikować wpisu dziennika"
            )
        if self.available:
            try:
                self.entries.append(entry)
                self._trim()
                self.store.async_delay_save(lambda: {"entries": self.entries}, 5)
            except Exception as exc:
                self.available = False
                self.error = f"{type(exc).__name__}:{exc}"
                _LOGGER.exception(
                    "Energy Co-Pilot: zapis archiwum decyzji nie powiódł się"
                )
        return entry

    def recent(self, limit=30):
        return self.entries[-limit:]

    @property
    def summary(self):
        return {
            "available": self.available,
            "error": self.error,
            "retention_days": RETENTION_DAYS,
            "max_events": MAX_EVENTS,
            "retained_events": len(self.entries),
            "oldest_utc": self.entries[0]["time_utc"] if self.entries else None,
            "newest_utc": self.entries[-1]["time_utc"] if self.entries else None,
        }

    async def async_close(self):
        if self.available:
            try:
                await self.store.async_save({"entries": self.entries})
            except Exception:
                _LOGGER.exception(
                    "Energy Co-Pilot: nie udało się zapisać archiwum przy wyłączaniu"
                )
