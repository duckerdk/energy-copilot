/* Parse Home Assistant price and Forecast.Solar text exports in the browser.
 * No network requests, external parser, stored upload or guesswork about Wh.
 */
(function (root) {
  "use strict";

  const HOUR = 3600000;
  const MAX_HOURS = 72;
  const isoPattern = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/;
  const numberPattern = /^-?(?:\d+(?:\.\d+)?|\.\d+)$/;
  const dkFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Copenhagen", year: "numeric", month: "2-digit",
    day: "2-digit", hour: "2-digit", minute: "2-digit",
    second: "2-digit", hourCycle: "h23",
  });

  function timestamp(text) {
    if (!isoPattern.test(text)) throw Error("Nieprawidłowa data ze strefą: " + text);
    const ms = Date.parse(text);
    if (!Number.isFinite(ms)) throw Error("Niepoprawny znacznik czasu: " + text);
    return ms;
  }

  function quantity(text) {
    const value = String(text).trim();
    if (!numberPattern.test(value)) throw Error("Nieprawidłowa liczba: " + text);
    const n = Number(value);
    if (!Number.isFinite(n)) throw Error("Liczba poza zakresem: " + text);
    return n;
  }

  function parsePriceFile(raw) {
    if (typeof raw !== "string" || raw.length > 100000) throw Error("Zbyt duży plik cen (maks. 100 kB)");
    let section = null;
    let pending = null;
    const hours = [];
    for (const line of raw.split(/\r?\n/)) {
      const heading = line.match(/^\s*(raw_today|raw_tomorrow):\s*$/);
      if (heading) {
        if (pending !== null) throw Error("Brakuje ceny przy godzinie " + pending);
        section = heading[1];
        continue;
      }
      const hour = line.match(/^\s*-\s*hour:\s*['"]?([^'"\s]+)['"]?\s*$/);
      if (hour && section) {
        if (pending !== null) throw Error("Brakuje ceny przy godzinie " + pending);
        pending = timestamp(hour[1]);
        if (pending % HOUR !== 0) throw Error("Ceny muszą rozpoczynać się o pełnej godzinie");
        continue;
      }
      const price = line.match(/^\s*price:\s*(\S+)\s*$/);
      if (price && section) {
        if (pending === null) throw Error("Cena bez godziny w sekcji " + section);
        hours.push({utc: new Date(pending).toISOString(), spot: quantity(price[1])});
        pending = null;
      }
    }
    if (pending !== null) throw Error("Brakuje ceny przy ostatniej godzinie");
    if (!hours.length) throw Error("Nie znaleziono godzin w raw_today/raw_tomorrow");
    hours.sort((a, b) => Date.parse(a.utc) - Date.parse(b.utc));
    if (hours.length > MAX_HOURS) throw Error("Maksymalnie 72 godziny cen");
    for (let i = 1; i < hours.length; i++) {
      if (Date.parse(hours[i].utc) - Date.parse(hours[i - 1].utc) !== HOUR) {
        throw Error("Ceny muszą obejmować kolejne, niepowtarzające się godziny UTC");
      }
    }
    return {
      start: hours[0].utc,
      end: new Date(Date.parse(hours[hours.length - 1].utc) + HOUR).toISOString(),
      hours,
    };
  }

  function localParts(ms) {
    const items = Object.fromEntries(
      dkFormatter.formatToParts(new Date(ms))
        .filter(item => item.type !== "literal")
        .map(item => [item.type, Number(item.value)])
    );
    return items;
  }

  function localDate(ms) {
    const p = localParts(ms);
    return String(p.year).padStart(4, "0") + "-" +
      String(p.month).padStart(2, "0") + "-" + String(p.day).padStart(2, "0");
  }

  function localMidnight(ymd) {
    const desired = Date.parse(ymd + "T00:00:00Z");
    if (!Number.isFinite(desired)) throw Error("Nieprawidłowa lokalna data: " + ymd);
    let guess = desired;
    for (let i = 0; i < 4; i++) {
      const p = localParts(guess);
      const wall = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
      guess += desired - wall;
    }
    const p = localParts(guess);
    if (localDate(guess) !== ymd || p.hour !== 0 || p.minute !== 0) {
      throw Error("Nie można przeliczyć północy Europe/Copenhagen");
    }
    return guess;
  }

  function nextDay(ymd) {
    const next = new Date(Date.parse(ymd + "T00:00:00Z") + 24 * HOUR);
    return next.toISOString().slice(0, 10);
  }

  function parseSolarFile(raw) {
    if (typeof raw !== "string" || raw.length > 100000) throw Error("Zbyt duży plik PV (maks. 100 kB)");
    let section = null;
    const watts = new Map(), wh = new Map();
    for (const line of raw.split(/\r?\n/)) {
      const heading = line.match(/^\s*(watts|wh_period):\s*$/);
      if (heading) { section = heading[1]; continue; }
      if (!section) continue;
      const entry = line.match(/^\s*['"]([^'"]+)['"]:\s*(\S+)\s*$/);
      if (!entry) continue;
      const ms = timestamp(entry[1]), value = quantity(entry[2]);
      if (value < 0) throw Error("Prognoza PV nie może zawierać ujemnych W/Wh");
      const target = section === "watts" ? watts : wh;
      if (target.has(ms)) throw Error("Zduplikowany czas w " + section);
      target.set(ms, value);
    }
    const times = [...wh.keys()].sort((a, b) => a - b);
    if (times.length < 2 || !watts.size) {
      throw Error("Wymagane obie sekcje Forecast.Solar: watts i wh_period");
    }
    if (wh.get(times[0]) !== 0) {
      throw Error("Pierwszy rekord wh_period musi mieć 0 Wh (brak poprzedniej granicy)");
    }
    const first = times[0], last = times[times.length - 1];
    const day = localDate(first);
    if (localDate(last) !== day) {
      throw Error("Jeden plik Forecast.Solar powinien obejmować jeden dzień lokalny");
    }
    if (watts.get(first) !== 0 || watts.get(last) !== 0) {
      throw Error("Do bezpiecznego uzupełnienia godzin nocnych wymagane jest 0 W na obu granicach prognozy");
    }
    const begin = localMidnight(day), end = localMidnight(nextDay(day));
    const count = (end - begin) / HOUR;
    if (!Number.isInteger(count) || count < 1 || count > MAX_HOURS) {
      throw Error("Niepoprawna długość doby w Danii");
    }
    const energies = Array(count).fill(0);
    let totalWh = 0;
    for (let i = 1; i < times.length; i++) {
      const left = times[i - 1], right = times[i], energy = wh.get(right);
      if (right <= left || left < begin || right > end) {
        throw Error("Nieprawidłowy lub wychodzący poza dobę przedział PV");
      }
      totalWh += energy;
      for (let hour = Math.floor((left - begin) / HOUR);
        hour < count && begin + hour * HOUR < right; hour++) {
        const start = begin + hour * HOUR, finish = start + HOUR;
        const overlap = Math.max(0, Math.min(right, finish) - Math.max(left, start));
        if (overlap) energies[hour] += energy * overlap / (right - left);
      }
    }
    const reconstructed = energies.reduce((sum, n) => sum + n, 0);
    if (Math.abs(reconstructed - totalWh) > 0.00001) {
      throw Error("Bilans energii PV nie zgadza się po podziale na godziny");
    }
    return {
      start: new Date(begin).toISOString(),
      end: new Date(end).toISOString(),
      totalKwh: totalWh / 1000,
      sourceDate: day,
      hours: energies.map((whValue, i) => ({
        utc: new Date(begin + i * HOUR).toISOString(),
        pv_kw: whValue / 1000,
      })),
    };
  }

  const api = {parsePriceFile, parseSolarFile};
  root.PlannerDataImport = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
