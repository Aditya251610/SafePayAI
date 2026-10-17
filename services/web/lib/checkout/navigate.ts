/** Full-page navigation to an external URL. Kept apart so tests can replace it. */
export function goTo(url: string): void {
  window.location.assign(url);
}
