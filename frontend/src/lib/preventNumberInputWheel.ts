/** Stop mouse-wheel from incrementing/decrementing focused number inputs. */
export function installPreventNumberInputWheel(): void {
  document.addEventListener(
    "wheel",
    (event) => {
      const el = document.activeElement;
      if (el instanceof HTMLInputElement && el.type === "number") {
        event.preventDefault();
      }
    },
    { passive: false }
  );
}
