export function displayTimezone(profileTimezone?: string | null): string {
  if (profileTimezone && profileTimezone.trim() !== "") {
    return profileTimezone;
  }
  return "UTC";
}

export function formatInUserTimezone(iso: string, profileTimezone?: string | null): string {
  return new Date(iso).toLocaleString("en-US", {
    timeZone: displayTimezone(profileTimezone),
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}
