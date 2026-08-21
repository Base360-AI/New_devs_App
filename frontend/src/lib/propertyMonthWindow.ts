function timezoneOffsetMs(date: Date, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((part) => part.type === type)?.value);
  const asWallClock = Date.UTC(
    value("year"),
    value("month") - 1,
    value("day"),
    value("hour"),
    value("minute"),
    value("second"),
  );
  return asWallClock - date.getTime();
}

export function zonedLocalDate(year: number, month: number, day: number, timeZone: string): Date {
  const utcGuess = Date.UTC(year, month - 1, day, 0, 0, 0);
  const firstPass = new Date(utcGuess - timezoneOffsetMs(new Date(utcGuess), timeZone));
  return new Date(utcGuess - timezoneOffsetMs(firstPass, timeZone));
}

export function monthBounds(year: number, month: number, propertyTimezone: string): { start: Date; end: Date } {
  const start = zonedLocalDate(year, month, 1, propertyTimezone);
  const end =
    month === 12
      ? zonedLocalDate(year + 1, 1, 1, propertyTimezone)
      : zonedLocalDate(year, month + 1, 1, propertyTimezone);
  return { start, end };
}

export function isCheckInInMonth(
  checkInIso: string,
  year: number,
  month: number,
  propertyTimezone: string,
): boolean {
  const { start, end } = monthBounds(year, month, propertyTimezone);
  const instant = new Date(checkInIso);
  return instant >= start && instant < end;
}

export function sumRevenueInMonth(
  bookings: Array<{ check_in: string; amount: number }>,
  year: number,
  month: number,
  propertyTimezone: string,
): number {
  return bookings
    .filter((booking) => isCheckInInMonth(booking.check_in, year, month, propertyTimezone))
    .reduce((total, booking) => total + booking.amount, 0);
}
